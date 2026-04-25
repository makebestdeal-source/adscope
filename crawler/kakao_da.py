"""Kakao/Daum display ad crawler."""

from __future__ import annotations

import asyncio
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
from crawler.constants import is_infra_domain as _is_infra_domain
from crawler.image_utils import batch_download, detect_image_ext, is_valid_image
from crawler.landing_resolver import resolve_landings_batch
from crawler.media_targets import select_media_targets
from crawler.personas.device_config import DeviceConfig
from crawler.personas.profiles import PersonaProfile
from crawler.url_utils import extract_domain, is_tracking_url, resolve_redirect_url, resolve_via_http

try:
    from bs4 import BeautifulSoup as _BS4
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False


_GENERIC_KAKAO_ADVERTISERS = {"kakao", "카카오", "moment", "keywordad", "daum"}


class KakaoDACrawler(BaseCrawler):
    """Collect Kakao media display ad candidates from Daum pages."""

    channel = "kakao_da"
    keyword_dependent = False

    DEFAULT_TARGETS = [
        "https://www.daum.net/",
        "https://news.daum.net/",
        "https://finance.daum.net/",
    ]

    def __init__(self):
        super().__init__()
        raw_urls = os.getenv("KAKAO_MEDIA_URLS", "").strip()
        self.max_targets = max(1, int(os.getenv("KAKAO_MAX_MEDIA", "4")))
        self.landing_resolve_limit = max(0, int(os.getenv("KAKAO_LANDING_RESOLVE_LIMIT", "5")))
        self.collection_profile = os.getenv("MEDIA_COLLECTION_PROFILE", "balanced").strip().lower() or "balanced"
        self.rotation_key = os.getenv("MEDIA_ROTATION_KEY", "").strip() or None

        if raw_urls:
            parsed = [u.strip() for u in raw_urls.split(",") if u.strip()]
            self.media_urls = parsed or list(self.DEFAULT_TARGETS)
        else:
            selected = select_media_targets(
                "kakao_da",
                profile=self.collection_profile,
                hard_limit=self.max_targets,
                rotation_key=self.rotation_key,
            )
            self.media_urls = selected or list(self.DEFAULT_TARGETS)

    async def crawl_keyword(
        self,
        keyword: str,
        persona: PersonaProfile,
        device: DeviceConfig,
    ) -> dict:
        start_time = datetime.utcnow()
        context = await self._create_context(persona, device)
        page = await context.new_page()

        # 네트워크 리다이렉트 추적: ad.daum.net → 실제 랜딩 URL 매핑
        self._redirect_map: dict[str, str] = {}
        # 네트워크 요청에서 직접 광고 랜딩 URL 캡처
        self._network_landings: dict[str, str] = {}
        # display.ad.daum.net/sdk/ JSON 응답 캡처
        self._sdk_ad_captures: list[dict] = []
        async def _on_any_response(response: Response):
            """모든 응답: 리다이렉트 추적 + SDK JSON 캡처."""
            # 1) 리다이렉트 추적
            try:
                url = response.url
                status = response.status
                if status in (301, 302, 303, 307, 308):
                    headers = response.headers
                    location = headers.get("location", "")
                    if location and ("ad.daum.net" in url or "kakaoad" in url or "adfit" in url):
                        self._redirect_map[url] = location
            except Exception:
                pass

            # 2) SDK JSON 캡처
            try:
                url = response.url
                if 'display.ad.daum.net/sdk/' not in url:
                    return
                if response.status != 200:
                    return
                ct = response.headers.get('content-type', '')
                if 'json' not in ct:
                    return
                data = await response.json()
                if isinstance(data, dict) and data.get('status') == 'OK':
                    ad_type = 'native' if '/sdk/native' in url else 'banner'
                    self._sdk_ad_captures.append({'type': ad_type, 'data': data, 'url': url})
            except Exception:
                pass

        page.on("response", _on_any_response)
        page.on("request", lambda req: self._capture_ad_request(req))

        try:
            ads: list[dict] = []
            # 서핑 모드: 전체 타겟 순회 + 서브페이지 방문
            surf_mode = not keyword or keyword in ("surf", "all")
            if surf_mode:
                all_targets = select_media_targets(
                    "kakao_da", profile="full", hard_limit=50,
                )
                targets = all_targets or self.media_urls
            else:
                targets = self.media_urls[: self.max_targets]

            for t_idx, target_url in enumerate(targets):
                url = self._to_mobile_url(target_url) if device.is_mobile else target_url
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                except Exception as exc:
                    logger.debug("[{}] {} goto failed: {}", self.channel, url, exc)
                    continue
                await page.wait_for_timeout(2000 + random.randint(500, 1000))

                # 스크롤: lazy-load 광고 트리거 (서핑 모드는 더 깊이)
                scroll_count = 12 if surf_mode else 8
                for s in range(scroll_count):
                    await page.evaluate(f'window.scrollBy(0, {300 + s * 80})')
                    await page.wait_for_timeout(400 + random.randint(100, 300))

                # 서핑 모드: 뉴스/연예 섹션에서 기사 방문
                if surf_mode and any(sec in url for sec in ('news.daum', 'entertain.daum', 'sports.daum')):
                    await self._visit_daum_articles(page)

                if t_idx < len(targets) - 1:
                    await page.wait_for_timeout(1000 + random.randint(500, 1500))

            # SDK 네트워크 응답에서 광고 파싱 (핵심 수집원)
            if self._sdk_ad_captures:
                sdk_ads = self._parse_sdk_captures(self._sdk_ad_captures)
                logger.info("[{}] SDK 네트워크 캡처 {}건 -> 광고 {}건", self.channel, len(self._sdk_ad_captures), len(sdk_ads))
                ads.extend(sdk_ads)

            # SDK 응답에서 추출한 이미지 URL을 다운로드하여 creative_image_path에 저장
            await self._download_creative_images(ads)

            # DOM 파싱 (보조 - PC에서 일부 추가 가능)
            dom_ads = await self._parse_da_candidates(page)
            if dom_ads:
                logger.info("[{}] DOM 파싱 추가 {}건", self.channel, len(dom_ads))
                ads.extend(dom_ads)

            # 리다이렉트 맵으로 광고 정보 보강
            if self._redirect_map:
                self._enrich_with_redirects(ads)

            # 랜딩 클릭으로 광고주 식별 (광고주 미확인 건 대상)
            if self.landing_resolve_limit > 0:
                await self._resolve_advertisers_via_landing(context, ads)

            ads = self._dedupe_ads(ads)

            # 광고주명 없는 광고 → 랜딩 페이지에서 광고주 파악
            unresolved = [a for a in ads if not a.get("advertiser_name")]
            if unresolved:
                resolved_count = await resolve_landings_batch(
                    context, unresolved, max_resolve=5, timeout_ms=8000,
                )
                logger.info("[{}] 랜딩 해석 {}/{}건 성공", self.channel, resolved_count, len(unresolved))

            screenshot_path = None  # full-page 스크린샷 비활성화
            elapsed = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            return {
                "keyword": keyword,
                "persona_code": persona.code,
                "device": device.device_type,
                "channel": self.channel,
                "captured_at": datetime.utcnow(),
                "page_url": page.url,
                "screenshot_path": screenshot_path,
                "ads": ads,
                "crawl_duration_ms": elapsed,
            }
        finally:
            await page.close()
            await context.close()

    def _track_ad_redirect(self, response):
        """네트워크 응답에서 광고 리다이렉트 추적."""
        try:
            url = response.url
            status = response.status
            if status in (301, 302, 303, 307, 308):
                headers = response.headers
                location = headers.get("location", "")
                if location and ("ad.daum.net" in url or "kakaoad" in url or "adfit" in url):
                    self._redirect_map[url] = location
        except Exception:
            pass

    async def _download_creative_images(self, ads: list[dict]):
        """SDK 응답에서 추출한 이미지 URL을 병렬 다운로드하여 creative_image_path에 저장.

        batch_download()로 동시 8개 병렬 다운로드.
        트래킹 URL(ad.daum.net 등)은 resolve_via_http()로 먼저 해석.
        """
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        base_dir = Path(self.settings.screenshot_dir) / self.channel / today

        url_to_ad: dict[str, dict] = {}
        url_to_path: dict[str, Path] = {}

        for i, ad in enumerate(ads):
            extra = ad.get("extra_data") or {}
            dl_url = extra.get("image_url")
            if not dl_url or dl_url in url_to_ad:
                continue
            # 트래킹 URL이면 HTTP 추적
            if is_tracking_url(dl_url):
                dl_url = resolve_via_http(dl_url, timeout=4) or dl_url
            crid = extra.get("crid") or str(i)
            filename = f"kakao_creative_{crid}_{datetime.now(timezone.utc).strftime('%H%M%S%f')}.jpg"
            url_to_path[dl_url] = base_dir / filename
            url_to_ad[dl_url] = ad

        if not url_to_path:
            return

        results = await batch_download(url_to_path, concurrency=8, timeout=10, min_size=500)

        download_count = 0
        for url, success in results.items():
            if not success:
                continue
            ad = url_to_ad[url]
            filepath = url_to_path[url]
            if filepath.exists():
                try:
                    content = filepath.read_bytes()
                    real_ext = detect_image_ext(content)
                    if not filepath.name.endswith(real_ext):
                        new_path = filepath.with_suffix(real_ext)
                        filepath.rename(new_path)
                        filepath = new_path
                except Exception:
                    pass
                try:
                    stored = await self._image_store.save(str(filepath), self.channel, "creative")
                    ad["creative_image_path"] = stored
                except Exception:
                    ad["creative_image_path"] = str(filepath)
                download_count += 1

        if download_count:
            logger.info("[{}] creative images: {} saved / {} total", self.channel, download_count, len(ads))

    # is_valid_image / detect_image_ext → crawler.image_utils

    @staticmethod
    def _extract_banner_image_url(html_content: str) -> str | None:
        """배너 광고 HTML content에서 크리에이티브 이미지 URL 추출.

        우선순위:
        1) BeautifulSoup: <meta name="ad.*"> 이미지 태그, og:image, <img>
        2) JS/JSON 내장 키 (bgImageUrl, imageUrl 등)
        3) CSS background-image: url(...)
        광고 인프라 아이콘(ADmark, 1x1 트래킹 픽셀 등)은 제외.
        """
        if not html_content:
            return None

        exclude_patterns = ('ADmark', 'admark', 'i_mark', 'optout', '1x1', 'pixel', 'track')

        def _is_valid(url: str) -> bool:
            if not url or not url.startswith('http') or len(url) <= 30:
                return False
            return not any(ex in url for ex in exclude_patterns)

        # 1) BeautifulSoup 파싱 (우선순위 최고)
        if _HAS_BS4:
            try:
                soup = _BS4(html_content, "html.parser")
                # 1-a) <meta name="ad.*image*"> 태그
                for meta in soup.find_all("meta", attrs={"name": re.compile(r"ad\.", re.I)}):
                    name = meta.get("name", "").lower()
                    if "image" in name or "img" in name:
                        val = meta.get("content", "")
                        if _is_valid(val):
                            return val
                # 1-b) og:image
                og = soup.find("meta", property="og:image")
                if og:
                    val = og.get("content", "")
                    if _is_valid(val):
                        return val
                # 1-c) data-src / src <img> (크기 기준 정렬)
                imgs = soup.find_all("img")
                img_candidates = []
                for img in imgs:
                    src = img.get("data-src") or img.get("src") or ""
                    w = int(img.get("width") or 0)
                    h = int(img.get("height") or 0)
                    if _is_valid(src):
                        img_candidates.append((w * h, src))
                if img_candidates:
                    # 가장 큰 이미지 우선
                    img_candidates.sort(key=lambda x: x[0], reverse=True)
                    return img_candidates[0][1]
            except Exception:
                pass

        # 2) JS/JSON 내장 이미지 URL 키
        for pattern in [
            r'(?:bgImageUrl|imageUrl|imgUrl|backgroundImage|creativeUrl)\s*[=:]\s*["\']([^"\']+)',
            r'(?:src|background-image)\s*[=:]\s*["\']?(https?://[^\s"\'>;)]+\.(?:jpg|jpeg|png|gif|webp)[^\s"\'>;)]*)',
        ]:
            for url in re.findall(pattern, html_content, re.I):
                if _is_valid(url):
                    return url

        # 3) <img> 태그 src (regex fallback)
        for url in re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html_content, re.I):
            if _is_valid(url):
                return url

        # 4) CSS background-image: url(...)
        for url in re.findall(r'url\(["\']?(https?://[^"\')\s]+)["\']?\)', html_content, re.I):
            if _is_valid(url):
                return url

        return None

    def _parse_sdk_captures(self, captures: list[dict]) -> list[dict]:
        """SDK JSON 응답에서 광고 정보 추출.

        native / banner 형식을 각각 전용 헬퍼로 처리.
        """
        ads: list[dict] = []
        seen: set[str] = set()
        for cap in captures:
            data = cap.get('data', {})
            ad_type = cap.get('type', 'banner')
            for ad_item in data.get('ads', []):
                if ad_type == 'native':
                    ad = self._parse_sdk_native_item(ad_item, seen)
                else:
                    ad = self._parse_sdk_banner_item(ad_item, seen)
                if ad:
                    ad["position"] = len(ads) + 1
                    ads.append(ad)
        return ads

    def _parse_sdk_native_item(self, item: dict, seen: set) -> dict | None:
        """SDK native 광고 아이템 파싱 — title/profileName/landingUrl 직접 사용."""
        title = item.get('title', '')
        profile = item.get('profileName', '')
        landing_url = item.get('landingUrl', '')
        main_image = item.get('mainImage')
        image_url = main_image.get('url') if isinstance(main_image, dict) else None
        crid = item.get('crid', '')
        sig = crid or f"{profile}:{title}"
        if sig in seen:
            return None
        seen.add(sig)
        advertiser = profile or None
        if not advertiser and landing_url:
            domain = extract_domain(landing_url)
            if domain and not _is_infra_domain(domain):
                advertiser = domain.removeprefix("www.").removeprefix("m.")
        return {
            "advertiser_name": advertiser,
            "ad_text": title or "kakao_native_ad",
            "ad_description": item.get('description'),
            "url": landing_url,
            "display_url": extract_domain(landing_url),
            "ad_type": "kakao_native",
            "ad_placement": "kakao_main",
            "ad_product_name": "디스플레이 네이티브",
            "ad_format_type": "display",
            "campaign_purpose": "performance",
            "creative_image_path": None,
            "extra_data": {
                "click_url": landing_url,
                "detection_method": "sdk_native_capture",
                "profile_name": profile,
                "image_url": image_url,
                "crid": crid,
                "cid": item.get('cid', ''),
                "adid": item.get('adid', ''),
                "dsp_name": item.get('dspId', ''),
            },
        }

    def _parse_sdk_banner_item(self, item: dict, seen: set) -> dict | None:
        """SDK banner 광고 아이템 파싱 — HTML content에서 메타 정보 추출."""
        content = item.get('content', '')
        if not content:
            return None
        unit_id = ''
        dsp_name = ''
        m = re.search(r'<meta\s+name="ad\.unitId"\s+content="([^"]*)"', content)
        if m:
            unit_id = m.group(1)
        m = re.search(r'<meta\s+name="dsp\.name"\s+content="([^"]*)"', content)
        if m:
            dsp_name = m.group(1)
        landing_url = self._extract_banner_landing_url(content)
        advertiser = None
        for pattern in [
            r'"(?:profileName|advertiserName|brandName)"\s*:\s*"([^"]+)"',
            r'"title"\s*:\s*"([^"]{2,40})"',
        ]:
            m = re.search(pattern, content)
            if m:
                advertiser = m.group(1)
                break
        if not advertiser and dsp_name and dsp_name.strip().lower() not in _GENERIC_KAKAO_ADVERTISERS:
            advertiser = dsp_name
        banner_image_url = self._extract_banner_image_url(content)
        crid = item.get('crid', '')
        sig = crid or f"{unit_id}:{advertiser}"
        if sig in seen:
            return None
        seen.add(sig)
        if not advertiser and not landing_url and not unit_id:
            return None
        if not advertiser and landing_url:
            domain = extract_domain(landing_url)
            if domain and not _is_infra_domain(domain):
                advertiser = domain.removeprefix("www.").removeprefix("m.")
        return {
            "advertiser_name": advertiser,
            "ad_text": advertiser or "kakao_banner_ad",
            "ad_description": None,
            "url": landing_url or None,
            "display_url": extract_domain(landing_url) if landing_url else None,
            "ad_type": "kakao_banner",
            "ad_placement": "kakao_main",
            "ad_product_name": "비즈보드",
            "ad_format_type": "display",
            "campaign_purpose": "branding",
            "creative_image_path": None,
            "extra_data": {
                "unit_id": unit_id,
                "dsp_name": dsp_name,
                "detection_method": "sdk_banner_capture",
                "image_url": banner_image_url,
                "crid": crid,
                "cid": item.get('cid', ''),
                "adid": item.get('adid', ''),
                "banner_width": item.get('width'),
                "banner_height": item.get('height'),
            },
        }

    @staticmethod
    def _extract_banner_landing_url(content: str) -> str:
        """배너 HTML content에서 랜딩 URL 추출."""
        for pattern in [
            r'"(?:clickUrl|landingUrl|landing|click_url|redirect_url|lp)"\s*:\s*"([^"]+)"',
            r'(?:clickUrl|landingUrl|click_url)\s*=\s*["\']([^"\']+)',
            r'href\s*=\s*["\']([^"\']*(?:ad\.daum|track\.kakao|tr\.ad)[^"\']*)["\']',
            r'"(?:url|link)"\s*:\s*"(https?://[^"]+)"',
        ]:
            m = re.search(pattern, content)
            if m:
                url = unquote(m.group(1)).strip()
                if '%' in url:
                    url = unquote(url).strip()
                return url
        # fallback: 외부 URL (인프라 제외)
        for eu in re.findall(r'https?://([a-zA-Z0-9\uAC00-\uD7A3][a-zA-Z0-9\uAC00-\uD7A3._-]+\.[a-zA-Z]{2,})', content):
            if not _is_infra_domain(eu):
                return f"https://{eu}"
        return ''

    def _capture_ad_request(self, request):
        """네트워크 요청 URL에서 광고 랜딩 URL 파라미터 추출."""
        try:
            url = request.url
            if not any(d in url for d in ('ad.daum.net', 'adfit.kakao.com', 'kakaoad', 't1.daumcdn.net/adfit')):
                return
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            for key in ('lp', 'url', 'redirect', 'landing', 'ru', 'adurl', 'target'):
                values = query.get(key)
                if values:
                    candidate = unquote(values[0]).strip()
                    if candidate.startswith('http') and not _is_infra_domain(extract_domain(candidate)):
                        self._network_landings[url] = candidate
                        break
        except Exception:
            pass

    def _resolve_click_destination(self, click_url: str | None) -> tuple[str | None, str | None]:
        candidate = str(click_url or "").strip()
        if not candidate:
            return None, None

        embedded_match = re.search(r"/click/(https?://.+)$", candidate)
        if embedded_match:
            embedded_url = unquote(embedded_match.group(1)).strip()
            embedded_domain = extract_domain(embedded_url)
            if embedded_domain and not _is_infra_domain(embedded_domain):
                return embedded_url, embedded_domain

        direct_landing = self._network_landings.get(candidate)
        if direct_landing:
            direct_domain = extract_domain(direct_landing)
            if direct_domain and not _is_infra_domain(direct_domain):
                return direct_landing, direct_domain

        static_resolved = resolve_redirect_url(candidate) or candidate
        static_domain = extract_domain(static_resolved)
        if static_domain and not _is_infra_domain(static_domain):
            return static_resolved, static_domain

        final_url = candidate
        for _ in range(5):
            next_url = self._redirect_map.get(final_url)
            if not next_url:
                break
            final_url = next_url
        final_domain = extract_domain(final_url)
        if final_domain and not _is_infra_domain(final_domain):
            return final_url, final_domain

        if is_tracking_url(candidate) or (final_domain and _is_infra_domain(final_domain)):
            http_resolved = resolve_via_http(candidate, timeout=5) or final_url
            http_domain = extract_domain(http_resolved)
            if http_domain and not _is_infra_domain(http_domain):
                return http_resolved, http_domain

        return None, None

    def _enrich_with_redirects(self, ads: list[dict]):
        """리다이렉트 맵으로 광고의 실제 랜딩 URL + 광고주 보강."""
        for ad in ads:
            click_url = ad.get("extra_data", {}).get("click_url", "")
            if not click_url:
                continue

            # 리다이렉트 체인 추적 (최대 5홉)
            resolved_url, resolved_domain = self._resolve_click_destination(click_url)
            if resolved_url and resolved_domain:
                ad["url"] = resolved_url
                ad["display_url"] = resolved_domain
                if not ad.get("advertiser_name"):
                    ad["advertiser_name"] = (
                        resolved_domain.removeprefix("www.").removeprefix("m.")
                    )
                ad["extra_data"]["redirect_resolved"] = True
                continue

            final_url = click_url
            for _ in range(5):
                next_url = self._redirect_map.get(final_url)
                if not next_url:
                    break
                final_url = next_url

            if final_url != click_url:
                resolved_domain = extract_domain(final_url)
                if resolved_domain and not _is_infra_domain(resolved_domain):
                    ad["url"] = final_url
                    ad["display_url"] = resolved_domain
                    if not ad.get("advertiser_name"):
                        ad["advertiser_name"] = resolved_domain
                    ad["extra_data"]["redirect_resolved"] = True

    async def _parse_da_candidates(self, page: Page) -> list[dict]:
        raw = await page.evaluate(
            """
            () => {
                const clean = (v) => (v || "").replace(/\\s+/g, " ").trim();
                const isAdLike = (url) => {
                    if (!url) return false;
                    const s = url.toLowerCase();
                    return (
                        s.includes("ad.daum.net") ||
                        s.includes("kakaoad") ||
                        s.includes("adfit") ||
                        s.includes("doubleclick.net") ||
                        s.includes("adservice")
                    );
                };

                const out = [];
                const anchors = Array.from(document.querySelectorAll("a[href]"));
                for (const anchor of anchors) {
                    const href = anchor.href || "";
                    const wrapper = anchor.closest("section,article,div,li,aside") || anchor;
                    const wrapperText = clean(wrapper.innerText || "");
                    const hasMarker = /광고|ad|sponsored/i.test(wrapperText);
                    const hasImage = !!anchor.querySelector("img");
                    if (!(isAdLike(href) || (hasMarker && hasImage))) continue;

                    const title = clean(
                        anchor.getAttribute("aria-label") ||
                        anchor.getAttribute("title") ||
                        anchor.textContent ||
                        anchor.querySelector("img")?.getAttribute("alt") ||
                        ""
                    );
                    const advertiser = clean(
                        wrapper.querySelector("strong, .tit, .name, [class*='brand']")?.textContent || ""
                    );
                    out.push({
                        click_url: href,
                        ad_text: title || null,
                        advertiser_name: advertiser || null,
                        wrapper_text: wrapperText.slice(0, 220),
                    });
                }

                const iframes = Array.from(document.querySelectorAll("iframe[src]"));
                for (const frame of iframes) {
                    const src = frame.getAttribute("src") || frame.src || "";
                    if (!isAdLike(src)) continue;
                    out.push({
                        click_url: src,
                        ad_text: null,
                        advertiser_name: null,
                        wrapper_text: clean((frame.closest("section,article,div,aside") || frame).innerText || "").slice(0, 220),
                    });
                }

                return out;
            }
            """
        )

        ads: list[dict] = []
        seen: set[tuple[str | None, str | None, str | None]] = set()
        for item in raw:
            source_url = item.get("click_url")
            url = resolve_redirect_url(source_url) or source_url
            display_url = extract_domain(url)

            # 광고주 추출: JS 결과 → 랜딩 도메인 (인프라 도메인 제외)
            advertiser_name = item.get("advertiser_name") or None
            if (
                not advertiser_name
                and display_url
                and not _is_infra_domain(display_url)
            ):
                advertiser_name = (
                    display_url.removeprefix("www.").removeprefix("m.")
                )
            # display_url은 광고주명으로 사용하지 않음 (website 필드로 분리 저장)
            ad_text = item.get("ad_text") or item.get("wrapper_text") or "kakao_display_ad"

            signature = (url, ad_text, advertiser_name)
            if signature in seen:
                continue
            seen.add(signature)

            ads.append(
                {
                    "advertiser_name": advertiser_name,
                    "ad_text": ad_text,
                    "ad_description": None,
                    "url": url,
                    "display_url": display_url,
                    "position": len(ads) + 1,
                    "ad_type": "display_banner",
                    "ad_placement": "kakao_main",
                    "ad_product_name": "디스플레이 네이티브",
                    "ad_format_type": "display",
                    "campaign_purpose": "performance",
                    "extra_data": {
                        "click_url": source_url,
                        "wrapper_text": item.get("wrapper_text"),
                        "detection_method": "dom_candidate_scan",
                    },
                }
            )

        logger.debug("[{}] parsed {} candidates", self.channel, len(ads))
        return ads

    async def _resolve_advertisers_via_landing(self, context, ads: list[dict]):
        """광고주 미확인 광고의 랜딩 페이지를 방문하여 광고주 식별."""
        unresolved = [
            ad for ad in ads
            if not ad.get("advertiser_name") and ad.get("url")
            and not _is_infra_domain(extract_domain(ad["url"]))
        ]
        targets = unresolved[: self.landing_resolve_limit]
        if not targets:
            return

        for ad in targets:
            landing_url = ad["url"]
            page = None
            try:
                page = await context.new_page()
                await page.goto(landing_url, wait_until="domcontentloaded", timeout=10000)
                await page.wait_for_timeout(2000)

                landing_domain = extract_domain(page.url)
                landing_title = await page.title() or ""

                # 도메인에서 광고주명 추출
                advertiser = None
                if landing_domain and not _is_infra_domain(landing_domain):
                    advertiser = landing_domain.removeprefix("www.").removeprefix("m.")

                # 타이틀에서 브랜드명 추출 시도 (짧은 타이틀이 브랜드명일 가능성)
                if landing_title:
                    parts = [p.strip() for p in landing_title.split("|") + landing_title.split("-")]
                    for part in parts:
                        if 2 <= len(part) <= 20:
                            advertiser = part
                            break

                if advertiser:
                    ad["advertiser_name"] = advertiser
                    ad["extra_data"]["landing_resolved"] = True
                    ad["extra_data"]["landing_domain"] = landing_domain
                    ad["extra_data"]["landing_title"] = landing_title[:100]
                    logger.debug("[{}] 랜딩 해석: {} → {}", self.channel, landing_url, advertiser)

            except Exception as exc:
                logger.debug("[{}] 랜딩 해석 실패 {}: {}", self.channel, landing_url, exc)
            finally:
                if page:
                    await page.close()

    async def _visit_daum_articles(self, page: Page) -> None:
        """다음 뉴스/연예/스포츠 섹션에서 기사 2개 방문하여 추가 광고 수집."""
        try:
            article_urls = await page.evaluate("""() => {
                const links = [];
                const seen = new Set();
                for (const a of document.querySelectorAll('a[href]')) {
                    const href = a.href;
                    if (!href || !href.startsWith('http')) continue;
                    if (seen.has(href)) continue;
                    if (href.includes('/v/') || href.includes('/article/') ||
                        href.match(/[?&]articleId=/) || href.match(/\\/\\d{14}/)) {
                        seen.add(href);
                        links.push(href);
                        if (links.length >= 3) break;
                    }
                }
                return links;
            }""")

            for article_url in (article_urls or [])[:2]:
                try:
                    await page.goto(article_url, wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(1500 + random.randint(500, 1000))
                    for s in range(5):
                        await page.evaluate(f'window.scrollBy(0, {300 + s * 100})')
                        await page.wait_for_timeout(400 + random.randint(100, 300))
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("[{}] daum article nav failed: {}", self.channel, exc)

    @staticmethod
    def _to_mobile_url(url: str) -> str:
        """다음 URL을 모바일 URL로 변환.

        주의: m.news.daum.net 등 서브도메인 모바일 버전은 DNS 미존재.
        서브도메인은 변환하지 않고 그대로 사용 (모바일 UA로 자동 대응).
        """
        if url.startswith("https://www.daum.net"):
            return url.replace("https://www.daum.net", "https://m.daum.net")
        # 서브도메인(news, finance 등)은 모바일 서브도메인 없음 → 그대로 사용
        return url

    # _extract_domain / _resolve_destination_url → crawler.url_utils

    @staticmethod
    def _dedupe_ads(ads: list[dict]) -> list[dict]:
        out: list[dict] = []
        seen: set[tuple[str | None, str, str | None]] = set()
        for ad in ads:
            signature = (ad.get("url"), ad.get("ad_text") or "", ad.get("advertiser_name"))
            if signature in seen:
                continue
            seen.add(signature)
            ad["position"] = len(out) + 1
            out.append(ad)
        return out
