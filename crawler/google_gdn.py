"""Google Display Network (GDN) crawler -- Ads Transparency Center IMAGE format.

youtube_ads.py와 동일한 Transparency Center RPC를 사용하되
format=IMAGE 필터로 디스플레이(이미지) 광고만 수집.

- 로그인 불필요, headless OK
- SearchSuggestions RPC -> 광고주 ID 목록
- SearchCreatives RPC -> 광고주별 크리에이티브 (IMAGE)
"""

from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from loguru import logger
from playwright.async_api import Page, Response

from crawler.base_crawler import BaseCrawler
from crawler.constants import AD_NETWORK_DOMAINS, is_infra_domain
from crawler.image_utils import detect_image_ext, is_valid_image
from crawler.media_targets import select_media_targets
from crawler.personas.device_config import DeviceConfig
from crawler.personas.profiles import PersonaProfile

# youtube_ads.py 파서 재사용
from crawler.youtube_ads import (
    ADVERTISER_WAIT_MS,
    MAX_ADS,
    MAX_ADVERTISERS,
    _clean_transparency_text,
    _display_domain_for_url,
    _enrich_creatives_from_preview,
    _normalize_external_landing_url,
    _parse_creatives,
    _parse_suggestions,
)

# ── 설정 ──
ADS_TRANSPARENCY_URL = (
    "https://adstransparency.google.com/"
    "?region=KR&format=IMAGE"
)

# GDN 전용 설정
GDN_MAX_ADVERTISERS = max(1, int(os.getenv("GDN_MAX_ADVERTISERS", "15")))
GDN_MAX_ADS = max(1, int(os.getenv("GDN_MAX_ADS", "50")))


def _date_range_suffix() -> str:
    """환경변수 CRAWL_DATE_* 에서 날짜 범위 URL 파라미터 생성."""
    sy = os.getenv("CRAWL_DATE_START_YEAR")
    sm = os.getenv("CRAWL_DATE_START_MONTH")
    sd = os.getenv("CRAWL_DATE_START_DAY", "1")
    ey = os.getenv("CRAWL_DATE_END_YEAR")
    em = os.getenv("CRAWL_DATE_END_MONTH")
    ed = os.getenv("CRAWL_DATE_END_DAY")
    if sy and sm and ey and em and ed:
        return (
            f"&startDate.year={sy}&startDate.month={sm}&startDate.day={sd}"
            f"&endDate.year={ey}&endDate.month={em}&endDate.day={ed}"
        )
    return ""


class GoogleGDNCrawler(BaseCrawler):
    """Google Ads Transparency Center IMAGE format -- GDN 디스플레이 광고 수집."""

    channel = "google_gdn"

    async def crawl_keyword(
        self,
        keyword: str,
        persona: PersonaProfile,
        device: DeviceConfig,
    ) -> dict:
        # 서핑 모드: 언론사/매체 사이트 방문하여 GDN/Criteo/Taboola 광고 인터셉트
        if keyword == "surf":
            return await self._surf_publishers(persona, device)

        start_time = datetime.now(timezone.utc)
        context = await self._create_context(persona, device)

        try:
            page, ads = await self._collect_ads(context, keyword)

            elapsed = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )

            return {
                "keyword": keyword,
                "persona_code": persona.code,
                "device": device.device_type,
                "channel": self.channel,
                "captured_at": datetime.now(timezone.utc),
                "page_url": ADS_TRANSPARENCY_URL,
                "screenshot_path": None,
                "ads": ads,
                "crawl_duration_ms": elapsed,
            }
        finally:
            for p in context.pages:
                await p.close()
            await context.close()

    async def _collect_ads(self, context, keyword: str) -> tuple:
        page = await context.new_page()

        try:
            suggestion_data: list[dict] = []
            creative_data: list[dict] = []

            async def _on_response(response: Response):
                url = response.url
                try:
                    if response.status != 200:
                        return
                    ct = response.headers.get("content-type", "")
                    if "json" not in ct:
                        return
                    if "SearchSuggestions" in url:
                        data = await response.json()
                        suggestion_data.append(data)
                    elif "SearchCreatives" in url:
                        data = await response.json()
                        creative_data.append(data)
                except Exception:
                    pass

            page.on("response", _on_response)

            # 1) 메인 페이지 접속 (IMAGE format 필터)
            await page.goto(ADS_TRANSPARENCY_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # 2) 검색창에 키워드 입력
            search_ok = await self._fill_search(page, keyword)
            if not search_ok:
                logger.warning("[{}] search input not found", self.channel)
                return page, []

            # 3) SearchSuggestions 응답 대기
            await page.wait_for_timeout(5000)

            advertisers: list[dict] = []
            for sd in suggestion_data:
                advertisers.extend(_parse_suggestions(sd))

            if not advertisers:
                logger.info("[{}] no advertisers for '{}'", self.channel, keyword)
                return page, []

            logger.info(
                "[{}] '{}' -> {} advertisers found",
                self.channel, keyword, len(advertisers),
            )

            # 4) 광고주별 크리에이티브 수집
            all_creatives: list[dict] = []

            for adv in advertisers[:GDN_MAX_ADVERTISERS]:
                creative_data.clear()
                adv_url = (
                    f"https://adstransparency.google.com/"
                    f"advertiser/{adv['id']}?region=KR&format=IMAGE{_date_range_suffix()}"
                )
                try:
                    await page.goto(adv_url, wait_until="domcontentloaded")
                    await page.wait_for_timeout(ADVERTISER_WAIT_MS)

                    # 스크롤 페이지네이션: 추가 SearchCreatives 로드
                    prev_count = len(creative_data)
                    max_scrolls = int(os.getenv("GDN_MAX_SCROLLS", "10"))
                    for scroll_i in range(max_scrolls):
                        await page.evaluate(
                            "window.scrollTo(0, document.body.scrollHeight)"
                        )
                        await page.wait_for_timeout(3000)
                        new_count = len(creative_data)
                        if new_count == prev_count:
                            break
                        logger.debug(
                            "[{}] {} scroll {} -> +{} RPC responses",
                            self.channel, adv["name"],
                            scroll_i + 1, new_count - prev_count,
                        )
                        prev_count = new_count

                    for cd in creative_data:
                        creatives = _parse_creatives(cd, adv["name"])
                        for cr in creatives:
                            cr["advertiser_id"] = adv["id"]
                        all_creatives.extend(creatives)

                    logger.debug(
                        "[{}] {} -> {} creatives",
                        self.channel, adv["name"],
                        sum(len(_parse_creatives(cd, "")) for cd in creative_data),
                    )
                except Exception as exc:
                    logger.debug(
                        "[{}] advertiser page failed {}: {}",
                        self.channel, adv["name"], exc,
                    )

                await page.wait_for_timeout(2000)

            # 5) 정규화
            await _enrich_creatives_from_preview(all_creatives, limit=max(60, GDN_MAX_ADS * 2))
            ads = self._normalize_creatives(all_creatives, keyword)
            logger.info(
                "[{}] '{}' -> {} ads (raw: {})",
                self.channel, keyword, len(ads), len(all_creatives),
            )

            # 6) 이미지 다운로드
            await self._download_preview_images(ads)

            return page, ads

        except Exception as e:
            logger.error("[{}] transparency center failed: {}", self.channel, e)
            return page, []

    async def _fill_search(self, page, keyword: str) -> bool:
        selectors = [
            "search-input input.input-area",
            "search-input input",
            "input.input-area",
            "material-input input",
        ]
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    await loc.first.click()
                    await page.wait_for_timeout(300)
                    await loc.first.type(keyword, delay=80)
                    await page.wait_for_timeout(1000)
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _normalize_creatives(creatives: list[dict], keyword: str) -> list[dict]:
        ads: list[dict] = []
        seen_ids: set[str] = set()

        for cr in creatives:
            if len(ads) >= GDN_MAX_ADS:
                break

            cid = cr.get("creative_id") or ""
            if cid in seen_ids:
                continue
            seen_ids.add(cid)

            advertiser = cr.get("advertiser_name")
            adv_url = _normalize_external_landing_url(cr.get("landing_url"))
            ad_text = _clean_transparency_text(cr.get("text_content"))
            if not adv_url or not ad_text:
                continue

            view_count = cr.get("view_count")

            extra_data = {
                "detection_method": "ads_transparency_rpc",
                "creative_id": cid,
                "preview_url": cr.get("preview_url"),
                "image_url": cr.get("image_url"),
                "format_type": cr.get("format_type"),
                "start_ts": cr.get("start_ts"),
                "end_ts": cr.get("end_ts"),
                "search_keyword": keyword,
                "platform": "google_display",
            }
            if view_count is not None:
                extra_data["view_count"] = view_count

            # 크기 기반 상품 분류
            fmt = str(cr.get("format_type") or "").lower()
            if "responsive" in fmt:
                _ad_product_name = "GDN 반응형"
            elif "native" in fmt:
                _ad_product_name = "GDN 네이티브"
            else:
                _ad_product_name = "GDN 디스플레이"

            ads.append({
                "advertiser_name": advertiser,
                "ad_text": ad_text,
                "ad_description": None,
                "url": adv_url,
                "display_url": _display_domain_for_url(adv_url),
                "position": len(ads) + 1,
                "ad_type": "gdn_display",
                "ad_placement": "google_ads_transparency",
                "ad_product_name": _ad_product_name,
                "ad_format_type": "display",
                "campaign_purpose": "performance",
                "extra_data": extra_data,
            })

        return ads

    # is_valid_image → crawler.image_utils.is_valid_image

    async def _download_preview_images(self, ads: list[dict]):
        """이미지 다운로드 (image_url 우선, preview_url fallback)."""
        download_count = 0
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for ad in ads:
                extra = ad.get("extra_data") or {}
                download_url = extra.get("image_url") or extra.get("preview_url")
                if not download_url:
                    continue
                try:
                    resp = await client.get(download_url)
                    if resp.status_code != 200:
                        continue
                    content_bytes = resp.content
                    if len(content_bytes) < 500:
                        continue
                    if not is_valid_image(content_bytes):
                        continue

                    screenshot_dir = (
                        Path(self.settings.screenshot_dir)
                        / self.channel
                        / datetime.now(timezone.utc).strftime("%Y%m%d")
                    )
                    screenshot_dir.mkdir(parents=True, exist_ok=True)

                    cid = extra.get("creative_id", "unknown")
                    timestamp = datetime.now(timezone.utc).strftime("%H%M%S")
                    ext = detect_image_ext(content_bytes)
                    filename = f"gdn_preview_{cid[:20]}_{timestamp}{ext}"
                    filepath = screenshot_dir / filename
                    filepath.write_bytes(content_bytes)

                    try:
                        stored = await self._image_store.save(
                            str(filepath), self.channel, "creative"
                        )
                        ad["creative_image_path"] = stored
                    except Exception:
                        ad["creative_image_path"] = None
                    finally:
                        try:
                            filepath.unlink(missing_ok=True)
                        except Exception:
                            pass

                    download_count += 1
                except Exception as exc:
                    logger.debug(
                        "[{}] preview download failed: {}",
                        self.channel, str(exc)[:80],
                    )

        if download_count:
            logger.info(
                "[{}] preview images: {} saved / {} total",
                self.channel, download_count, len(ads),
            )

    # ── 언론사 서핑 모드: 실제 매체 방문하여 광고 네트워크 응답 인터셉트 ──

    # AD_NETWORK_DOMAINS / is_infra_domain → crawler.constants

    async def _surf_publishers(
        self, persona: PersonaProfile, device: DeviceConfig,
    ) -> dict:
        """언론사/매체 사이트를 서핑하며 GDN/Criteo/Taboola 광고를 네트워크 인터셉트."""
        start_time = datetime.now(timezone.utc)
        context = await self._create_context(persona, device)
        page = await context.new_page()

        try:
            ad_captures: list[dict] = []
            _cur_site = {"name": "", "url": ""}

            async def _on_ad_network_response(response: Response):
                url = response.url
                if not any(d in url for d in AD_NETWORK_DOMAINS):
                    return
                try:
                    if response.status != 200:
                        return
                    ct = response.headers.get('content-type', '')

                    # 광고 네트워크 식별
                    ad_network = "unknown"
                    if 'doubleclick' in url or 'googlesyndication' in url or 'googlead' in url:
                        ad_network = "GDN"
                    elif 'criteo' in url:
                        ad_network = "Criteo"
                    elif 'taboola' in url:
                        ad_network = "Taboola"
                    elif 'dable' in url:
                        ad_network = "Dable"
                    elif 'outbrain' in url:
                        ad_network = "Outbrain"
                    elif 'buzzvil' in url:
                        ad_network = "Buzzvil"
                    elif 'mobon' in url:
                        ad_network = "Mobon"
                    elif 'adfit.kakao' in url or 'ad.daum' in url or 'track.kakao' in url:
                        ad_network = "KakaoADfit"
                    elif 'nam.veta' in url or 'gfp.naver' in url or 'siape.veta' in url:
                        ad_network = "NaverGFP"
                    elif 'rtbhouse' in url:
                        ad_network = "RTBHouse"
                    elif 'inmobi' in url:
                        ad_network = "InMobi"
                    elif 'adroll' in url:
                        ad_network = "AdRoll"

                    if 'json' in ct:
                        data = await response.json()
                        ads = self._parse_ad_network_json(data, ad_network, url)
                        for a in ads:
                            a['_site'] = _cur_site['name']
                            a['_site_url'] = _cur_site['url']
                        ad_captures.extend(ads)
                    elif 'html' in ct or 'javascript' in ct:
                        body = await response.text()
                        if len(body) > 50:
                            ads = self._parse_ad_network_html(body, ad_network, url)
                            for a in ads:
                                a['_site'] = _cur_site['name']
                                a['_site_url'] = _cur_site['url']
                            ad_captures.extend(ads)
                except Exception:
                    pass

            page.on('response', _on_ad_network_response)

            # 전체 매체 타겟 가져오기
            targets = select_media_targets("google_gdn", profile="full", hard_limit=50)
            if not targets:
                targets = ["https://www.chosun.com/", "https://www.donga.com/",
                           "https://www.joongang.co.kr/", "https://www.mk.co.kr/"]

            pages_visited = []
            for tidx, target_url in enumerate(targets):
                site_name = urlparse(target_url).netloc.replace('www.', '')
                _cur_site['name'] = site_name
                _cur_site['url'] = target_url

                try:
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(2000 + random.randint(500, 1500))
                except Exception as exc:
                    logger.debug("[{}] {} goto failed: {}", self.channel, site_name, exc)
                    continue

                pages_visited.append(site_name)

                # 스크롤: lazy-load 광고 트리거
                for s in range(8):
                    await page.evaluate(f'window.scrollBy(0, {300 + s * 80})')
                    await page.wait_for_timeout(400 + random.randint(100, 300))

                # 기사 서브페이지 2개 방문 (추가 광고 슬롯)
                await self._visit_publisher_articles(page, _cur_site)

                # 지면 간 대기
                if tidx < len(targets) - 1:
                    await page.wait_for_timeout(1000 + random.randint(500, 1500))

            # 수집된 광고 정규화
            all_ads = self._normalize_surf_captures(ad_captures)
            logger.info(
                "[{}] surf: {} ads from {} sites (raw: {})",
                self.channel, len(all_ads), len(pages_visited), len(ad_captures),
            )

            await self._download_preview_images(all_ads)

            elapsed = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )

            return {
                "keyword": "surf",
                "persona_code": persona.code,
                "device": device.device_type,
                "channel": self.channel,
                "captured_at": datetime.now(timezone.utc),
                "page_url": ", ".join(pages_visited),
                "screenshot_path": None,
                "ads": all_ads,
                "crawl_duration_ms": elapsed,
            }
        finally:
            await page.close()
            await context.close()

    async def _visit_publisher_articles(self, page: Page, cur_site: dict) -> None:
        """언론사 메인에서 기사 2개를 방문하여 추가 광고 수집."""
        try:
            article_urls = await page.evaluate("""() => {
                const links = [];
                const seen = new Set();
                for (const a of document.querySelectorAll('a[href]')) {
                    const href = a.href;
                    if (!href || !href.startsWith('http')) continue;
                    if (seen.has(href)) continue;
                    // 기사 URL 패턴
                    if (href.match(/\\/article\\//) || href.match(/\\/news\\//) ||
                        href.match(/\\/view\\//) || href.match(/\\/story\\//) ||
                        href.match(/[?&]aid=/) || href.match(/\\/\\d{8,}/)) {
                        seen.add(href);
                        links.push(href);
                        if (links.length >= 3) break;
                    }
                }
                return links;
            }""")

            orig_name = cur_site['name']
            for article_url in (article_urls or [])[:2]:
                cur_site['name'] = f"{orig_name}_article"
                try:
                    await page.goto(article_url, wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(1500 + random.randint(500, 1000))
                    for s in range(5):
                        await page.evaluate(f'window.scrollBy(0, {300 + s * 100})')
                        await page.wait_for_timeout(400 + random.randint(100, 300))
                except Exception:
                    pass

            cur_site['name'] = orig_name
        except Exception as exc:
            logger.debug("[{}] publisher article nav failed: {}", self.channel, exc)

    def _parse_ad_network_json(self, data: dict, network: str, source_url: str) -> list[dict]:
        """광고 네트워크 JSON 응답에서 광고 정보 추출 (네트워크별 파서 디스패치)."""
        if not isinstance(data, dict):
            return []
        parsers = {
            "GDN": self._parse_gdn_ads,
            "Criteo": self._parse_criteo_ads,
            "Taboola": self._parse_native_ads,
            "Dable": self._parse_native_ads,
            "Outbrain": self._parse_native_ads,
            "Buzzvil": self._parse_generic_ads,
            "Mobon": self._parse_mobon_ads,
            "KakaoADfit": self._parse_kakao_gfp_ads,
            "NaverGFP": self._parse_kakao_gfp_ads,
            "RTBHouse": self._parse_generic_ads,
            "AdRoll": self._parse_generic_ads,
            "InMobi": self._parse_generic_ads,
        }
        parser = parsers.get(network)
        return parser(data, network) if parser else []

    @staticmethod
    def _parse_gdn_ads(data: dict, network: str) -> list[dict]:
        ads = []
        for key in ('ads', 'adSlots', 'items', 'creatives'):
            for item in data.get(key, []):
                if not isinstance(item, dict):
                    continue
                click_url = (item.get('clickUrl') or item.get('click_url')
                             or item.get('landingUrl') or item.get('url') or '')
                advertiser = (item.get('advertiserName') or item.get('advertiser')
                              or item.get('brand') or '')
                image_url = (item.get('imageUrl') or item.get('image')
                             or item.get('thumbnailUrl') or '')
                if click_url or advertiser:
                    ads.append({'click_url': click_url, 'advertiser': advertiser,
                                'image_url': image_url, 'ad_network': network})
        return ads

    @staticmethod
    def _parse_criteo_ads(data: dict, network: str) -> list[dict]:
        ads = []
        for slot in data.get('slots', data.get('placements', [])):
            if not isinstance(slot, dict):
                continue
            for item in slot.get('native', {}).get('products', slot.get('ads', [])):
                if not isinstance(item, dict):
                    continue
                click_url = item.get('click') or item.get('url') or ''
                title = item.get('title') or item.get('name') or ''
                image_url = item.get('image') or item.get('img') or ''
                advertiser = item.get('brand') or item.get('seller') or ''
                if click_url or title:
                    ads.append({'click_url': click_url, 'advertiser': advertiser or title,
                                'image_url': image_url, 'ad_network': network})
        return ads

    @staticmethod
    def _parse_native_ads(data: dict, network: str) -> list[dict]:
        """Taboola / Dable / Outbrain 공통 파서."""
        ads = []
        for key in ('list', 'items', 'placements', 'recommendations'):
            for item in data.get(key, []):
                if not isinstance(item, dict):
                    continue
                click_url = item.get('url') or item.get('click_url') or item.get('link') or ''
                title = item.get('name') or item.get('title') or ''
                branding = item.get('branding') or item.get('source') or ''
                thumbnail = item.get('thumbnail', [])
                if isinstance(thumbnail, list) and thumbnail:
                    image_url = thumbnail[0].get('url', '') if isinstance(thumbnail[0], dict) else str(thumbnail[0])
                elif isinstance(thumbnail, dict):
                    image_url = thumbnail.get('url', '')
                else:
                    image_url = ''
                if click_url or title:
                    ads.append({'click_url': click_url, 'advertiser': branding or title,
                                'image_url': image_url, 'ad_network': network, 'ad_text': title})
        return ads

    @staticmethod
    def _parse_generic_ads(data: dict, network: str) -> list[dict]:
        """Buzzvil / RTBHouse / AdRoll / InMobi 공통 파서."""
        ads = []
        for key in ('ads', 'items', 'data', 'creatives'):
            for item in data.get(key, []):
                if not isinstance(item, dict):
                    continue
                click_url = (item.get('click_url') or item.get('clickUrl') or item.get('landing_url')
                             or item.get('url') or item.get('landingUrl') or '')
                advertiser = item.get('advertiser') or item.get('brand') or item.get('title') or ''
                image_url = item.get('image_url') or item.get('imageUrl') or item.get('icon_url') or item.get('image') or ''
                if click_url or advertiser:
                    ads.append({'click_url': click_url, 'advertiser': advertiser,
                                'image_url': image_url, 'ad_network': network})
        return ads

    @staticmethod
    def _parse_mobon_ads(data: dict, network: str) -> list[dict]:
        ads = []
        for key in ('ads', 'data', 'items'):
            for item in data.get(key, []):
                if not isinstance(item, dict):
                    continue
                click_url = item.get('clickUrl') or item.get('link') or item.get('url') or ''
                advertiser = item.get('advertiser') or item.get('siteName') or ''
                image_url = item.get('imgUrl') or item.get('image') or ''
                if click_url or advertiser:
                    ads.append({'click_url': click_url, 'advertiser': advertiser,
                                'image_url': image_url, 'ad_network': network})
        return ads

    @staticmethod
    def _parse_kakao_gfp_ads(data: dict, network: str) -> list[dict]:
        """KakaoADfit / NaverGFP 공통 파서."""
        ads = []
        for key in ('ads', 'adUnits', 'items'):
            for item in data.get(key, []):
                if not isinstance(item, dict):
                    continue
                info = item.get('adInfo', item)
                native = info.get('nativeData', {})
                adomain = info.get('adomain', [])
                domain = adomain[0].removeprefix('www.').removeprefix('m.') if adomain else None
                if native:
                    sponsor = native.get('sponsor', {})
                    advertiser = sponsor.get('text') if isinstance(sponsor, dict) else ''
                    link = native.get('link', {})
                    click_url = link.get('curl') if isinstance(link, dict) else ''
                    media = native.get('media', {})
                    image_url = media.get('src') if isinstance(media, dict) else ''
                else:
                    click_url = item.get('clickUrl') or item.get('landingUrl') or ''
                    advertiser = item.get('profileName') or item.get('title') or ''
                    image_url = item.get('mainImage') or item.get('imageUrl') or ''
                if not advertiser and domain:
                    advertiser = domain
                if click_url or advertiser:
                    ads.append({'click_url': click_url, 'advertiser': advertiser,
                                'image_url': image_url, 'ad_network': network, 'adomain': domain})
        return ads

    def _parse_ad_network_html(self, body: str, network: str, source_url: str) -> list[dict]:
        """광고 네트워크 HTML/JS 응답에서 광고 URL 추출."""
        ads = []
        # 랜딩 URL 추출
        url_patterns = [
            r'(?:clickUrl|landingUrl|click_url|href|url|adurl|redirect|dest)[=:]\s*["\']([^"\']+)',
            r'"(?:click|landing|url|redirect|adurl|link|dest)"\s*:\s*"([^"]+)"',
            r'adurl=([^&"\'<>\s]+)',  # doubleclick adurl 파라미터
        ]
        advertiser_patterns = [
            r'(?:advertiser|brand|advertiserName|seller|branding|source|sponsor)[=:]\s*["\']([^"\']{2,50})["\']',
            r'"(?:advertiser|brand|title|name)"\s*:\s*"([^"]{2,50})"',
        ]
        image_patterns = [
            r'(?:src|imageUrl|image|thumbnail)[=:]\s*["\']?(https?://[^\s"\'>;]+\.(?:jpg|jpeg|png|gif|webp)[^\s"\'>;]*)',
        ]

        click_urls = set()
        for pattern in url_patterns:
            for m in re.finditer(pattern, body):
                url = m.group(1)
                if url.startswith('http') and len(url) > 20:
                    domain = urlparse(url).netloc.lower()
                    if not any(d in domain for d in (
                        'doubleclick', 'googlesyndication', 'criteo', 'taboola',
                        'dable', 'outbrain', 'buzzvil', 'mobon', 'adroll', 'rtbhouse',
                        'googleadservices', 'pagead', 'adservice.google',
                    )):
                        click_urls.add(url)

        advertisers = []
        for pattern in advertiser_patterns:
            for m in re.finditer(pattern, body):
                advertisers.append(m.group(1))

        images = []
        for pattern in image_patterns:
            for m in re.finditer(pattern, body, re.I):
                images.append(m.group(1))

        for click_url in list(click_urls)[:5]:
            ads.append({
                'click_url': click_url,
                'advertiser': advertisers[0] if advertisers else '',
                'image_url': images[0] if images else '',
                'ad_network': network,
            })

        return ads

    def _normalize_surf_captures(self, captures: list[dict]) -> list[dict]:
        """서핑 모드 캡처를 정규화된 광고 리스트로 변환."""
        ads = []
        seen = set()

        for cap in captures:
            click_url = cap.get('click_url', '')
            advertiser = cap.get('advertiser', '')

            # URL에서 실제 랜딩 URL 추출
            resolved_url = click_url
            adomain = cap.get('adomain')
            if click_url:
                # tivan/GFP opaque URL → adomain 기반 URL로 대체
                if 'tivan.naver.com' in click_url or 'siape.veta.naver.com' in click_url:
                    if adomain:
                        resolved_url = f"https://{adomain}"
                    else:
                        resolved_url = ''
                else:
                    try:
                        parsed = urlparse(click_url)
                        query = parse_qs(parsed.query)
                        for key in ('url', 'adurl', 'r', 'u', 'redirect', 'target', 'landing', 'eu', 'lp', 'ru'):
                            vals = query.get(key)
                            if vals:
                                candidate = unquote(vals[0]).strip()
                                if '%' in candidate:
                                    candidate = unquote(candidate).strip()
                                if candidate.startswith('http'):
                                    resolved_url = candidate
                                    break
                    except Exception:
                        pass

            # 도메인에서 광고주명 추출
            if not advertiser and resolved_url:
                try:
                    domain = urlparse(resolved_url).netloc.lower()
                    domain = domain.removeprefix('www.').removeprefix('m.')
                    if domain and not is_infra_domain(domain):
                        advertiser = domain
                except Exception:
                    pass

            if not advertiser and not resolved_url:
                continue

            # 중복 방지
            sig = (resolved_url, advertiser)
            if sig in seen:
                continue
            seen.add(sig)

            ad_network = cap.get('ad_network', 'unknown')
            site_name = cap.get('_site', '')

            ads.append({
                "advertiser_name": advertiser or None,
                "ad_text": cap.get('ad_text', '') or advertiser or f"{ad_network}_ad",
                "ad_description": None,
                "url": resolved_url or None,
                "display_url": urlparse(resolved_url).netloc if resolved_url else None,
                "position": len(ads) + 1,
                "ad_type": f"{ad_network.lower()}_display",
                "ad_placement": f"publisher_{site_name}",
                "ad_product_name": f"{ad_network} Display",
                "ad_format_type": "display",
                "campaign_purpose": "performance",
                "creative_image_path": None,
                "extra_data": {
                    "detection_method": "publisher_surf_intercept",
                    "ad_network": ad_network,
                    "publisher_site": site_name,
                    "publisher_url": cap.get('_site_url', ''),
                    "image_url": cap.get('image_url', ''),
                    "click_url": click_url,
                },
            })

        return ads
