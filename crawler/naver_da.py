"""네이버 DA(디스플레이) 배너 크롤러 — 네트워크 인터셉트 전용.

네이버 메인(PC/모바일) DA 광고를 네트워크 응답(GFP JSON) 캡처만으로 수집.
DOM 셀렉터/iframe 파싱은 사용하지 않는다 (프로젝트 규칙 #1).

변경이력:
    2026-02-12  iframe 기반 수집으로 전면 리팩터링 (기존 셀렉터 방식 폐기)
    2026-02-26  DOM/iframe 추출 완전 제거, 네트워크 인터셉트만 유지
"""

import json
import os
import re
import random
from datetime import datetime
from urllib.parse import parse_qs, unquote, urlparse

from loguru import logger
from playwright.async_api import Page, Response

from crawler.base_crawler import BaseCrawler
from crawler.personas.device_config import DeviceConfig
from crawler.personas.profiles import PersonaProfile


# ── 네이버 광고 지면 정의 (네트워크 캡처 전용) ──

NAVER_DA_PLACEMENTS: dict[str, list[dict]] = {
    "pc": [
        {
            "name": "main",
            "label": "PC메인",
            "url": "https://www.naver.com/",
            "description": "PC 메인 — GFP 네트워크 캡처로 DA 수집",
        },
    ],
    "mobile": [
        {
            "name": "main",
            "label": "모바일메인",
            "url": "https://m.naver.com/",
            "description": "모바일 메인 — GFP 네트워크 캡처로 DA 수집",
        },
    ],
}

# 환경변수로 수집할 지면 제어 (콤마 구분, 비어있으면 전체)
_ACTIVE_PLACEMENTS = os.getenv("NAVER_DA_PLACEMENTS", "").strip()

# 도메인 → 브랜드명 매핑 (네이버 DA에서 빈번한 광고주)
_NAVER_DOMAIN_BRAND_MAP: dict[str, str] = {
    "coupang.com": "쿠팡",
    "11st.co.kr": "11번가",
    "gmarket.co.kr": "G마켓",
    "auction.co.kr": "옥션",
    "ssg.com": "SSG",
    "tmon.co.kr": "티몬",
    "wemakeprice.com": "위메프",
    "samsung.com": "삼성전자",
    "lge.co.kr": "LG전자",
    "hyundai.com": "현대자동차",
    "kia.com": "기아",
    "oliveyoung.co.kr": "올리브영",
    "musinsa.com": "무신사",
    "kurly.com": "마켓컬리",
    "baemin.com": "배달의민족",
    "yogiyo.co.kr": "요기요",
    "kakao.com": "카카오",
    "toss.im": "토스",
    "insurance.samsung.com": "삼성화재",
    "direct.samsungfire.com": "삼성화재",
    "kb-direct.com": "KB손해보험",
    "samsung-investment.com": "삼성증권",
    "shinhan.com": "신한금융",
    "hanabank.com": "하나은행",
    "kbstar.com": "KB국민은행",
    "naver.com": "네이버",
    "smartstore.naver.com": "네이버스마트스토어",
    "booking.com": "부킹닷컴",
    "agoda.com": "아고다",
    "airbnb.co.kr": "에어비앤비",
}


class NaverDACrawler(BaseCrawler):
    """네이버 메인 DA 배너를 GFP 네트워크 응답 캡처로 수집."""

    channel = "naver_da"
    keyword_dependent = False  # 키워드 무관 — 고정 URL 방문

    def __init__(self):
        super().__init__()
        self.category_tabs = max(0, int(os.getenv("NAVER_DA_CATEGORY_TABS", "6")))

    async def crawl_keyword(
        self,
        keyword: str,
        persona: PersonaProfile,
        device: DeviceConfig,
    ) -> dict:
        start_time = datetime.utcnow()
        context = await self._create_context(persona, device)

        try:
            device_key = "mobile" if device.is_mobile else "pc"
            placements = self._get_active_placements(device_key)

            all_ads: list[dict] = []
            page = await context.new_page()

            # 네트워크 레벨 광고 캡처 (siape.veta/gfp 응답 파싱)
            network_ad_captures: list[dict] = []

            async def _on_naver_ad_response(response: Response):
                url = response.url
                if not any(d in url for d in ('nam.veta.naver.com/gfp', 'siape.veta.naver.com', 'gfp.naver.com', 'ade.naver.com', 'adimg.naver.com')):
                    return
                try:
                    if response.status == 200:
                        ct = response.headers.get('content-type', '')
                        if 'json' in ct:
                            data = await response.json()
                            ads = self._parse_gfp_json(data)
                            network_ad_captures.extend(ads)
                        elif 'html' in ct or 'javascript' in ct or 'text' in ct:
                            body = await response.text()
                            ads = self._parse_ad_response_body(body, url)
                            network_ad_captures.extend(ads)
                except Exception:
                    pass

            page.on('response', _on_naver_ad_response)

            # URL 방문 (PC/모바일 메인)
            main_url = placements[0]["url"] if placements else "https://www.naver.com/"
            await page.goto(main_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # 스크롤: lazy-load GFP 요청 트리거
            scroll_count = 12 if device.is_mobile else 3
            for s in range(scroll_count):
                await page.evaluate(f'window.scrollBy(0, {400 + s * 100})')
                await page.wait_for_timeout(600 + random.randint(100, 400))

            # 모바일: 상단으로 돌아갔다가 다시 스크롤 (남은 lazy-load 트리거)
            if device.is_mobile:
                await page.evaluate('window.scrollTo(0, 0)')
                await page.wait_for_timeout(1000)
                for s in range(6):
                    await page.evaluate(f'window.scrollBy(0, {600 + s * 150})')
                    await page.wait_for_timeout(500 + random.randint(100, 300))

            # 모바일: 카테고리 탭 순회 → 추가 GFP 네트워크 요청 트리거
            if device.is_mobile and self.category_tabs > 0:
                await self._navigate_category_tabs(page)

            # 네트워크 캡처에서 광고 수집 (nam.veta.naver.com/gfp JSON)
            if network_ad_captures:
                logger.debug(f"[{self.channel}] GFP 네트워크 원시 캡처: {len(network_ad_captures)}건")
                net_ads = self._process_raw_ads(network_ad_captures, "network_capture", source="network")
                if net_ads:
                    logger.info(f"[{self.channel}] 네트워크 캡처 광고: {len(net_ads)}건")
                    all_ads.extend(net_ads)

            screenshot_path = None  # full-page 스크린샷 비활성화

            elapsed = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            return {
                "keyword": keyword,
                "persona_code": persona.code,
                "device": device.device_type,
                "channel": self.channel,
                "captured_at": datetime.utcnow(),
                "page_url": main_url,
                "screenshot_path": screenshot_path,
                "ads": all_ads,
                "crawl_duration_ms": elapsed,
            }

        finally:
            for p in context.pages:
                await p.close()
            await context.close()

    # ── 카테고리 탭 순회 (모바일) ──

    async def _navigate_category_tabs(self, page: Page) -> None:
        """m.naver.com 상단 카테고리 탭을 순회하여 추가 GFP 네트워크 요청 트리거."""
        try:
            tab_urls = await page.evaluate("""(maxTabs) => {
                const selectors = [
                    'a[class*="nav"]', '.ca_menu a', '[data-clk*="svc."]',
                    'nav a[href]', '.service_bar a', 'a[class*="ServiceTab"]',
                ];
                const seen = new Set();
                const results = [];
                for (const sel of selectors) {
                    for (const a of document.querySelectorAll(sel)) {
                        const href = a.href || '';
                        if (!href || !href.startsWith('http')) continue;
                        if (seen.has(href)) continue;
                        if (!href.includes('naver.com')) continue;
                        if (href === 'https://m.naver.com/' || href === 'https://www.naver.com/') continue;
                        seen.add(href);
                        results.push(href);
                        if (results.length >= maxTabs) return results;
                    }
                }
                return results;
            }""", self.category_tabs)

            for tab_url in (tab_urls or []):
                try:
                    await page.goto(tab_url, wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(2000)

                    # 스크롤로 lazy-load GFP 요청 트리거
                    for s in range(4):
                        await page.evaluate(f'window.scrollBy(0, {400 + s * 100})')
                        await page.wait_for_timeout(600)

                except Exception as exc:
                    logger.debug(f"[{self.channel}] 카테고리 탭 {tab_url} 실패: {exc}")

        except Exception as exc:
            logger.debug(f"[{self.channel}] 카테고리 탭 수집 실패: {exc}")

    # ── 공통 후처리 ──

    _PLACEMENT_PRODUCT_MAP: dict[str, str] = {
        "network_capture": "성과형DA(GFA)",
    }

    _PLACEMENT_PURPOSE_MAP: dict[str, str] = {
        "network_capture": "performance",
    }

    def _process_raw_ads(
        self, raw_candidates: list[dict], placement_name: str,
        source: str = "", creative_map: dict[int, str] | None = None,
    ) -> list[dict]:
        """원시 후보 리스트를 정규화된 광고 리스트로 변환."""
        ads: list[dict] = []
        seen: set[tuple] = set()

        for raw_idx, item in enumerate(raw_candidates):
            click_url = item.get("click_url")
            url = _resolve_destination_url(click_url)
            display_url = _extract_domain(url)
            advertiser_name = item.get("advertiser_name") or None
            ad_text = item.get("ad_text") or display_url or "display_ad"

            # 중복 방지
            signature = (url or "", ad_text or "", advertiser_name or "")
            if signature in seen:
                continue
            seen.add(signature)

            # URL 필수 — URL 없는 광고는 제외 (프로젝트 규칙)
            if not url:
                continue

            # 도메인 → 브랜드명 매핑
            brand = None
            if display_url:
                clean_domain = display_url.removeprefix("www.").removeprefix("m.")
                brand = _NAVER_DOMAIN_BRAND_MAP.get(clean_domain)
                if not brand:
                    for domain_key, brand_name in _NAVER_DOMAIN_BRAND_MAP.items():
                        if clean_domain.endswith(domain_key):
                            brand = brand_name
                            break

            ads.append({
                "advertiser_name": advertiser_name,
                "brand": brand,
                "ad_text": ad_text,
                "ad_description": None,
                "url": url,
                "display_url": display_url,
                "position": len(ads) + 1,
                "ad_type": "banner",
                "ad_placement": f"naver_main_{placement_name}",
                "ad_product_name": self._PLACEMENT_PRODUCT_MAP.get(placement_name, "성과형DA(GFA)"),
                "ad_format_type": "display",
                "campaign_purpose": self._PLACEMENT_PURPOSE_MAP.get(placement_name, "awareness"),
                "creative_image_path": None,
                "extra_data": {
                    "click_url": click_url,
                    "banner_image": item.get("banner_image"),
                    "placement": placement_name,
                    "source": source,
                },
            })

        return ads

    # ── 네트워크 응답 파싱 ──

    @staticmethod
    def _parse_gfp_json(data: dict) -> list[dict]:
        """nam.veta.naver.com/gfp/v1 JSON 응답에서 광고 추출.

        GFP v1 응답에는 두 가지 광고 형식이 있다:
        1) nativeData 형식: adInfo.nativeData.sponsor/link/desc 등
        2) adContext 형식: adInfo.adContext (JSON string) + adInfo.adm (HTML)
        """
        ads: list[dict] = []
        if not isinstance(data, dict):
            return ads

        top_domains = data.get('advertiserDomains', [])

        for ad_item in data.get('ads', []):
            info = ad_item.get('adInfo', {})
            native = info.get('nativeData', {})

            # --- 형식 1: nativeData 기반 (피드 광고 등) ---
            if native:
                adomain = info.get('adomain', top_domains)
                domain = adomain[0] if adomain else None
                if domain:
                    domain = domain.removeprefix('www.').removeprefix('m.')

                sponsor = native.get('sponsor', {})
                advertiser = sponsor.get('text') if isinstance(sponsor, dict) else None
                if not advertiser and domain:
                    advertiser = domain

                link = native.get('link', {})
                click_url = link.get('curl') if isinstance(link, dict) else None

                desc = native.get('desc', {})
                desc_text = desc.get('text') if isinstance(desc, dict) else None

                media = native.get('media', {})
                image_url = media.get('src') if isinstance(media, dict) else None

                cta = native.get('cta', {})
                cta_text = cta.get('text') if isinstance(cta, dict) else None

                if not advertiser and not click_url:
                    continue

                ads.append({
                    'click_url': click_url,
                    'advertiser_name': advertiser,
                    'ad_text': desc_text or cta_text or advertiser or 'naver_da',
                    'banner_image': image_url,
                })
                continue

            # --- 형식 2: adContext + adm 기반 (배너 광고) ---
            ad_context_str = info.get('adContext', '')
            if not ad_context_str:
                continue

            try:
                ctx = json.loads(ad_context_str) if isinstance(ad_context_str, str) else ad_context_str
            except Exception:
                continue

            provider = ctx.get('adProviderName', '')
            adomain_list = ctx.get('adomain', top_domains)
            domain = None
            if adomain_list:
                d = adomain_list[0] if isinstance(adomain_list, list) else str(adomain_list)
                if d:
                    domain = d.removeprefix('www.').removeprefix('m.')

            advertiser = None
            if domain and domain not in ('', 'naver.com'):
                advertiser = domain
            elif provider and provider not in ('NAVER Direct', ''):
                advertiser = provider

            cid = ctx.get('cid', [])
            crid = ctx.get('crid', [])
            creative_type = ctx.get('creativeType', '')

            # adm HTML에서 랜딩 URL 추출
            adm = info.get('adm', '')
            click_url = None
            if adm:
                landing_match = re.search(r'(?:landingUrl|clickUrl|click_url|href)[=:]\s*["\']([^"\']+)', adm)
                if landing_match:
                    click_url = landing_match.group(1)

            ad_text = f'{creative_type} ad' if creative_type else 'naver_da_banner'
            if advertiser:
                ad_text = advertiser

            if not advertiser and not click_url and not cid:
                continue

            if not advertiser:
                advertiser = provider or f'naver_ad_{cid[0][:12]}' if isinstance(cid, list) and cid else provider or 'naver_da'

            ads.append({
                'click_url': click_url,
                'advertiser_name': advertiser,
                'ad_text': ad_text,
                'banner_image': None,
            })

        # --- GFP v2 형식: adUnits[] ---
        for ad_unit in data.get('adUnits', []):
            for ad_item in ad_unit.get('ads', []):
                info = ad_item.get('adInfo', {})
                native = info.get('nativeData', {})
                adomain = info.get('adomain', [])
                domain = adomain[0].removeprefix('www.').removeprefix('m.') if adomain else None

                advertiser = None
                click_url = None
                image_url = None
                ad_text = None

                if native:
                    sponsor = native.get('sponsor', {})
                    advertiser = sponsor.get('text') if isinstance(sponsor, dict) else domain
                    link = native.get('link', {})
                    click_url = link.get('curl') if isinstance(link, dict) else None
                    desc = native.get('desc', {})
                    ad_text = desc.get('text') if isinstance(desc, dict) else None
                    media = native.get('media', {})
                    image_url = media.get('src') if isinstance(media, dict) else None
                else:
                    advertiser = domain
                    ad_context_str = info.get('adContext', '')
                    if ad_context_str:
                        try:
                            ctx = json.loads(ad_context_str) if isinstance(ad_context_str, str) else ad_context_str
                            advertiser = ctx.get('adProviderName') or domain
                        except Exception:
                            pass

                if not advertiser and not click_url:
                    continue

                ads.append({
                    'click_url': click_url,
                    'advertiser_name': advertiser or domain or 'naver_da',
                    'ad_text': ad_text or advertiser or 'naver_da',
                    'banner_image': image_url,
                })

        # --- OpenRTB seatbid[] 형식 ---
        for seatbid in data.get('seatbid', []):
            for bid in seatbid.get('bid', []):
                adomain = bid.get('adomain', [])
                domain = adomain[0].removeprefix('www.').removeprefix('m.') if adomain else None

                adm = bid.get('adm', '')
                click_url = None
                image_url = None
                if adm:
                    landing_match = re.search(r'(?:landingUrl|clickUrl|click_url|href)[=:]\s*["\']([^"\']+)', adm)
                    if landing_match:
                        click_url = landing_match.group(1)
                    img_match = re.search(r'(?:src)[=:]\s*["\']([^"\']+\.(?:jpg|jpeg|png|gif|webp)[^"\']*)', adm, re.I)
                    if img_match:
                        image_url = img_match.group(1)

                nurl = bid.get('nurl', '')
                if not click_url and nurl:
                    click_url = nurl

                advertiser = domain
                if not advertiser and not click_url:
                    continue

                ads.append({
                    'click_url': click_url,
                    'advertiser_name': advertiser or 'naver_da',
                    'ad_text': advertiser or 'naver_da',
                    'banner_image': image_url,
                })

        return ads

    @staticmethod
    def _parse_ad_response_body(body: str, source_url: str) -> list[dict]:
        """siape.veta/gfp 응답 HTML/JS에서 광고 데이터 추출."""
        ads: list[dict] = []
        click_urls = re.findall(r'(?:href|clickUrl)[=:]\s*["\']([^"\']*adcr\.naver\.com[^"\']*)["\']', body)
        img_urls = re.findall(r'(?:src|imageUrl|bgImageUrl)[=:]\s*["\']?([^"\';\s\)]+\.(?:jpg|jpeg|png|gif|webp)[^"\';\s\)]*)', body, re.I)
        alt_texts = re.findall(r'(?:alt|title|advertiserName|brandName)[=:]\s*["\']([^"\']{2,30})["\']', body)

        for click_url in click_urls:
            resolved = _resolve_destination_url(click_url)
            display_url = _extract_domain(resolved)
            advertiser = None
            for alt in alt_texts:
                if alt.lower() not in ('광고', 'ad', 'naver', '네이버'):
                    advertiser = alt
                    break
            if not advertiser and display_url:
                advertiser = display_url

            ads.append({
                'click_url': click_url,
                'advertiser_name': advertiser,
                'ad_text': advertiser or 'naver_da',
                'banner_image': img_urls[0] if img_urls else None,
            })

        if not click_urls:
            landing_urls = re.findall(r'(?:landingUrl|landing_url|clickUrl|click_url)[=:]\s*["\']([^"\']+)["\']', body)
            for landing in landing_urls:
                decoded = unquote(landing).strip()
                if not decoded.startswith('http'):
                    continue
                display_url = _extract_domain(decoded)
                if display_url and not any(d in display_url for d in ('naver.com', 'siape.veta', 'adcr.')):
                    advertiser = None
                    for alt in alt_texts:
                        if alt.lower() not in ('광고', 'ad', 'naver', '네이버'):
                            advertiser = alt
                            break
                    ads.append({
                        'click_url': decoded,
                        'advertiser_name': advertiser or None,
                        'ad_text': advertiser or display_url or 'naver_da',
                        'banner_image': img_urls[0] if img_urls else None,
                    })

        return ads

    # ── 헬퍼 ──

    def _get_active_placements(self, device_key: str) -> list[dict]:
        """환경변수 필터를 적용한 활성 지면 목록 반환."""
        all_placements = NAVER_DA_PLACEMENTS.get(device_key, [])
        if not _ACTIVE_PLACEMENTS:
            return all_placements
        active_names = {n.strip() for n in _ACTIVE_PLACEMENTS.split(",")}
        return [p for p in all_placements if p["name"] in active_names]


# ── 모듈 레벨 유틸 ──

def _extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlparse(url).netloc or None
    except Exception:
        return None


def _resolve_destination_url(click_url: str | None) -> str | None:
    """siape/adcr 리다이렉트 URL에서 실제 목적지 URL을 추출."""
    if not click_url:
        return None
    try:
        parsed = urlparse(click_url)

        # siape.veta.naver.com 또는 adcr.naver.com 리다이렉트 해석
        if "siape.veta.naver.com" in parsed.netloc or "adcr.naver.com" in parsed.netloc:
            query = parse_qs(parsed.query)
            for key in ("r", "u", "url", "target", "eu"):
                values = query.get(key)
                if not values:
                    continue
                candidate = unquote(values[0]).strip()
                if '%' in candidate:
                    candidate = unquote(candidate).strip()
                if candidate.startswith(("http://", "https://")):
                    return candidate
            return click_url

        # 일반 리다이렉트 URL
        query = parse_qs(parsed.query)
        for key in ("r", "u", "url", "target"):
            values = query.get(key)
            if not values:
                continue
            candidate = unquote(values[0]).strip()
            if '%' in candidate:
                candidate = unquote(candidate).strip()
            if candidate.startswith(("http://", "https://")):
                return candidate

        return click_url
    except Exception:
        return click_url
