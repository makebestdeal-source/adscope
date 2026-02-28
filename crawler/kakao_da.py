"""Kakao/Daum display ad crawler."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from urllib.parse import parse_qs, unquote, urlparse

from loguru import logger
from playwright.async_api import Page, Response

from crawler.base_crawler import BaseCrawler
from crawler.landing_resolver import resolve_landings_batch
from crawler.media_targets import select_media_targets
from crawler.personas.device_config import DeviceConfig
from crawler.personas.profiles import PersonaProfile


_INFRA_DOMAINS = {
    # 광고 시스템 도메인 (광고주 아님)
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "adservice.google.com", "pagead2.googlesyndication.com",
    "ad.daum.net", "kakaoad.com", "adfit.kakao.com",
    "t1.daumcdn.net", "t1.kakaocdn.net",
    "adcr.naver.com", "ader.naver.com",
    "criteo.com", "adroll.com", "taboola.com", "dable.io",
    # 매체 도메인 (매체는 광고주 아님)
    "www.daum.net", "m.daum.net", "news.daum.net", "finance.daum.net",
    "sports.daum.net", "entertain.daum.net",
    "www.naver.com", "m.naver.com",
}


def _is_infra_domain(domain: str | None) -> bool:
    """도메인이 광고 인프라/매체인지 확인 — 광고주로 사용 불가."""
    if not domain:
        return True
    d = domain.lower().strip()
    for infra in _INFRA_DOMAINS:
        if d == infra or d.endswith("." + infra):
            return True
    return False


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
            targets = self.media_urls[: self.max_targets]
            for t_idx, target_url in enumerate(targets):
                url = self._to_mobile_url(target_url) if device.is_mobile else target_url
                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                # 스크롤: lazy-load 광고 트리거
                for s in range(8):
                    await page.evaluate(f'window.scrollBy(0, {400 + s * 100})')
                    await page.wait_for_timeout(600)
                await page.wait_for_timeout(2000)
                if t_idx < len(targets) - 1:
                    await self._inter_page_cooldown(page)

            # 광고 iframe 요소 스크린샷 캡처 (순서 보존용)
            captured_creative_paths = await self._capture_kakao_ad_elements(
                page, keyword, persona.code,
            )

            # SDK 네트워크 응답에서 광고 파싱 (핵심 수집원)
            if self._sdk_ad_captures:
                sdk_ads = self._parse_sdk_captures(self._sdk_ad_captures)
                logger.info("[{}] SDK 네트워크 캡처 {}건 -> 광고 {}건", self.channel, len(self._sdk_ad_captures), len(sdk_ads))
                # 캡처된 크리에이티브 경로를 순서 기반으로 매핑
                for i, ad in enumerate(sdk_ads):
                    if i < len(captured_creative_paths) and captured_creative_paths[i]:
                        ad["creative_image_path"] = captured_creative_paths[i]
                ads.extend(sdk_ads)

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

    async def _capture_kakao_ad_elements(
        self, page, keyword: str, persona_code: str,
    ) -> list[str | None]:
        """페이지에서 보이는 카카오 광고 iframe/컨테이너 요소를 캡처.

        Returns:
            캡처된 이미지 경로 리스트 (순서 보존, 실패 시 None)
        """
        paths: list[str | None] = []
        # 카카오 광고 iframe 셀렉터 목록
        iframe_selectors = [
            'iframe[src*="ad.daum.net"]',
            'iframe[src*="adfit"]',
            'iframe[src*="kakaoad"]',
            'iframe[src*="display.ad.daum.net"]',
        ]
        # 카카오 광고 컨테이너 셀렉터
        container_selectors = [
            'div[data-ad]',
            'div[data-adfit]',
            'div[class*="ad_wrap"]',
            'ins[data-ad-unit]',
        ]

        captured_elements = set()  # bounding box 기반 중복 방지

        for selector in iframe_selectors + container_selectors:
            try:
                count = await page.locator(selector).count()
                for idx in range(min(count, 20)):
                    try:
                        loc = page.locator(selector).nth(idx)
                        box = await loc.bounding_box()
                        if not box:
                            continue
                        # 최소 크기 필터 (너무 작은 것 제외)
                        if box["width"] < 30 or box["height"] < 20:
                            continue
                        # 중복 방지: 비슷한 위치의 요소 스킵
                        box_key = (round(box["x"], -1), round(box["y"], -1))
                        if box_key in captured_elements:
                            continue
                        captured_elements.add(box_key)

                        creative_path = await self._capture_ad_element(
                            page, loc, keyword, persona_code, "kakao_ad"
                        )
                        paths.append(creative_path)
                    except Exception:
                        paths.append(None)
            except Exception:
                continue

        logger.debug("[{}] kakao ad element capture: {}/{}", self.channel, sum(1 for p in paths if p), len(paths))
        return paths

    def _parse_sdk_captures(self, captures: list[dict]) -> list[dict]:
        """SDK JSON 응답에서 광고 정보 추출.

        두 가지 형식:
        1) /sdk/native: ads[].title, ads[].profileName, ads[].landingUrl
        2) /sdk/banner: ads[].content (HTML) -> meta 태그에서 광고주 추출
        """
        ads: list[dict] = []
        seen: set[str] = set()

        for cap in captures:
            data = cap.get('data', {})
            ad_type = cap.get('type', 'banner')

            for ad_item in data.get('ads', []):
                if ad_type == 'native':
                    # Native 형식: title, profileName, landingUrl 직접 사용
                    title = ad_item.get('title', '')
                    profile = ad_item.get('profileName', '')
                    landing_url = ad_item.get('landingUrl', '')

                    # 중복 방지
                    sig = f"{profile}:{title}"
                    if sig in seen:
                        continue
                    seen.add(sig)

                    advertiser = profile or None
                    if not advertiser and landing_url:
                        domain = self._extract_domain(landing_url)
                        if domain and not _is_infra_domain(domain):
                            advertiser = domain.removeprefix("www.").removeprefix("m.")

                    ads.append({
                        "advertiser_name": advertiser,
                        "ad_text": title or "kakao_native_ad",
                        "ad_description": ad_item.get('description'),
                        "url": landing_url,
                        "display_url": self._extract_domain(landing_url),
                        "position": len(ads) + 1,
                        "ad_type": "kakao_native",
                        "ad_product_name": "디스플레이 네이티브",
                        "ad_format_type": "display",
                        "campaign_purpose": "performance",
                        "extra_data": {
                            "click_url": landing_url,
                            "detection_method": "sdk_native_capture",
                            "profile_name": profile,
                        },
                    })

                else:
                    # Banner 형식: HTML content에서 메타 정보 추출
                    content = ad_item.get('content', '')
                    if not content:
                        continue

                    # meta 태그에서 정보 추출
                    unit_id = ''
                    dsp_name = ''
                    m = re.search(r'<meta\s+name="ad\.unitId"\s+content="([^"]*)"', content)
                    if m:
                        unit_id = m.group(1)
                    m = re.search(r'<meta\s+name="dsp\.name"\s+content="([^"]*)"', content)
                    if m:
                        dsp_name = m.group(1)

                    # 랜딩 URL 추출 (clickUrl, landingUrl 등)
                    landing_url = ''
                    for pattern in [
                        r'"(?:clickUrl|landingUrl|landing)"\s*:\s*"([^"]+)"',
                        r'(?:clickUrl|landingUrl)\s*=\s*["\']([^"\']+)',
                    ]:
                        m = re.search(pattern, content)
                        if m:
                            landing_url = unquote(m.group(1)).strip()
                            break

                    # 광고주명 추출
                    advertiser = None
                    for pattern in [
                        r'"(?:profileName|advertiserName|brandName)"\s*:\s*"([^"]+)"',
                        r'"title"\s*:\s*"([^"]{2,40})"',
                    ]:
                        m = re.search(pattern, content)
                        if m:
                            advertiser = m.group(1)
                            break

                    if not advertiser and dsp_name and dsp_name != 'MOMENT':
                        advertiser = dsp_name

                    # 중복 방지
                    sig = f"{unit_id}:{advertiser}"
                    if sig in seen:
                        continue
                    seen.add(sig)

                    if not advertiser and not landing_url and not unit_id:
                        continue

                    if not advertiser:
                        if landing_url:
                            domain = self._extract_domain(landing_url)
                            if domain and not _is_infra_domain(domain):
                                advertiser = domain.removeprefix("www.").removeprefix("m.")

                    ads.append({
                        "advertiser_name": advertiser,
                        "ad_text": advertiser or "kakao_banner_ad",
                        "ad_description": None,
                        "url": landing_url or None,
                        "display_url": self._extract_domain(landing_url) if landing_url else None,
                        "position": len(ads) + 1,
                        "ad_type": "kakao_banner",
                        "ad_product_name": "비즈보드",
                        "ad_format_type": "display",
                        "campaign_purpose": "branding",
                        "extra_data": {
                            "unit_id": unit_id,
                            "dsp_name": dsp_name,
                            "detection_method": "sdk_banner_capture",
                        },
                    })

        return ads

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
                    if candidate.startswith('http') and not _is_infra_domain(self._extract_domain(candidate)):
                        self._network_landings[url] = candidate
                        break
        except Exception:
            pass

    def _enrich_with_redirects(self, ads: list[dict]):
        """리다이렉트 맵으로 광고의 실제 랜딩 URL + 광고주 보강."""
        for ad in ads:
            click_url = ad.get("extra_data", {}).get("click_url", "")
            if not click_url:
                continue

            # 리다이렉트 체인 추적 (최대 5홉)
            final_url = click_url
            for _ in range(5):
                next_url = self._redirect_map.get(final_url)
                if not next_url:
                    break
                final_url = next_url

            if final_url != click_url:
                resolved_domain = self._extract_domain(final_url)
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
            url = self._resolve_destination_url(source_url)
            display_url = self._extract_domain(url)

            # 광고주 추출: JS 결과 → 랜딩 도메인 (인프라 도메인 제외)
            advertiser_name = item.get("advertiser_name") or None
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
                    "ad_product_name": "디스플레이 네이티브",
                    "ad_format_type": "display",
                    "campaign_purpose": "performance",
                    "extra_data": {
                        "click_url": source_url,
                        "wrapper_text": item.get("wrapper_text"),
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
            and not _is_infra_domain(self._extract_domain(ad["url"]))
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

                landing_domain = self._extract_domain(page.url)
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

    @staticmethod
    def _extract_domain(url: str | None) -> str | None:
        if not url:
            return None
        try:
            return urlparse(url).netloc or None
        except Exception:
            return None

    @staticmethod
    def _resolve_destination_url(raw_url: str | None) -> str | None:
        if not raw_url:
            return None
        try:
            parsed = urlparse(raw_url)
            query = parse_qs(parsed.query)
            # 카카오/다음 전용 파라미터 포함 (ru=redirect url, eu=encoded url, lp=landing page)
            for key in ("url", "adurl", "u", "redirect", "target", "ru", "eu", "lp", "landing"):
                values = query.get(key)
                if not values:
                    continue
                candidate = unquote(values[0]).strip()
                if candidate.startswith(("http://", "https://")):
                    return candidate
            return raw_url
        except Exception:
            return raw_url

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
