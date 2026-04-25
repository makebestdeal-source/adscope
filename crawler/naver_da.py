"""네이버 DA(디스플레이) 배너 크롤러 — 네트워크 인터셉트 전용.

네이버 메인(PC/모바일) DA 광고를 네트워크 응답(GFP JSON) 캡처만으로 수집.
DOM 셀렉터/iframe 파싱은 사용하지 않는다 (프로젝트 규칙 #1).

변경이력:
    2026-02-12  iframe 기반 수집으로 전면 리팩터링 (기존 셀렉터 방식 폐기)
    2026-02-26  DOM/iframe 추출 완전 제거, 네트워크 인터셉트만 유지
"""

import asyncio
import json
import os
import re
import random
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

import httpx
from loguru import logger
from playwright.async_api import Page, Response

from crawler.base_crawler import BaseCrawler
from crawler.constants import is_infra_domain
from crawler.image_utils import batch_download, detect_image_ext, is_valid_image
from crawler.personas.device_config import DeviceConfig
from crawler.personas.profiles import PersonaProfile
from crawler.url_utils import extract_domain, is_tracking_url, resolve_redirect_url, resolve_via_http


# ── 네이버 광고 지면 정의 (네트워크 캡처 전용) ──

NAVER_DA_PLACEMENTS: dict[str, list[dict]] = {
    "pc": [
        {"name": "main", "label": "PC메인", "url": "https://www.naver.com/"},
        {"name": "news", "label": "뉴스", "url": "https://news.naver.com/"},
        {"name": "sports", "label": "스포츠", "url": "https://sports.naver.com/"},
        {"name": "entertainment", "label": "연예", "url": "https://entertain.naver.com/"},
        {"name": "finance", "label": "금융", "url": "https://finance.naver.com/"},
        {"name": "shopping", "label": "쇼핑", "url": "https://shopping.naver.com/"},
        {"name": "realestate", "label": "부동산", "url": "https://land.naver.com/"},
        {"name": "auto", "label": "자동차", "url": "https://auto.naver.com/"},
        {"name": "living", "label": "리빙", "url": "https://section.blog.naver.com/ThemePost.naver"},
        {"name": "movie", "label": "영화", "url": "https://movie.naver.com/"},
        {"name": "series", "label": "시리즈", "url": "https://series.naver.com/"},
        {"name": "webtoon", "label": "웹툰", "url": "https://comic.naver.com/"},
        {"name": "cafe", "label": "카페", "url": "https://section.cafe.naver.com/"},
        {"name": "kin", "label": "지식iN", "url": "https://kin.naver.com/"},
        {"name": "tv", "label": "TV", "url": "https://tv.naver.com/"},
        {"name": "chzzk", "label": "치지직", "url": "https://chzzk.naver.com/"},
        {"name": "weather", "label": "날씨", "url": "https://weather.naver.com/"},
        {"name": "blog", "label": "블로그", "url": "https://section.blog.naver.com/"},
    ],
    "mobile": [
        {"name": "main", "label": "모바일메인", "url": "https://m.naver.com/"},
        {"name": "news", "label": "모바일뉴스", "url": "https://m.news.naver.com/"},
        {"name": "sports", "label": "모바일스포츠", "url": "https://m.sports.naver.com/"},
        {"name": "entertainment", "label": "모바일연예", "url": "https://m.entertain.naver.com/"},
        {"name": "finance", "label": "모바일금융", "url": "https://m.stock.naver.com/"},
        {"name": "shopping", "label": "모바일쇼핑", "url": "https://m.shopping.naver.com/"},
        {"name": "realestate", "label": "모바일부동산", "url": "https://m.land.naver.com/article"},
        {"name": "auto", "label": "모바일자동차", "url": "https://auto.naver.com/"},
        {"name": "movie", "label": "모바일영화", "url": "https://movie.naver.com/"},
        {"name": "webtoon", "label": "모바일웹툰", "url": "https://m.comic.naver.com/"},
        {"name": "cafe", "label": "모바일카페", "url": "https://m.cafe.naver.com/"},
        {"name": "kin", "label": "모바일지식iN", "url": "https://m.kin.naver.com/"},
        {"name": "tv", "label": "모바일TV", "url": "https://m.tv.naver.com/"},
        {"name": "chzzk", "label": "모바일치지직", "url": "https://m.chzzk.naver.com/"},
        {"name": "weather", "label": "모바일날씨", "url": "https://m.weather.naver.com/"},
        {"name": "blog", "label": "모바일블로그", "url": "https://m.blog.naver.com/"},
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
            _cur_placement = {"name": "main", "label": "메인"}

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
                            for a in ads:
                                a['_placement'] = _cur_placement['name']
                                a['_label'] = _cur_placement['label']
                            network_ad_captures.extend(ads)
                        elif 'html' in ct or 'javascript' in ct or 'text' in ct:
                            body = await response.text()
                            ads = self._parse_ad_response_body(body, url)
                            for a in ads:
                                a['_placement'] = _cur_placement['name']
                                a['_label'] = _cur_placement['label']
                            network_ad_captures.extend(ads)
                except Exception:
                    pass

            page.on('response', _on_naver_ad_response)

            # ── 서핑 모드: keyword 비어있으면 전체 지면 순회 ──
            surf_mode = not keyword or keyword in ("surf", "all")
            if surf_mode:
                visit_list = list(placements)
            else:
                match = [p for p in placements if p["name"] == keyword]
                visit_list = match if match else ([placements[0]] if placements else [])

            pages_visited = []
            for pidx, placement in enumerate(visit_list):
                _cur_placement['name'] = placement['name']
                _cur_placement['label'] = placement['label']

                try:
                    await page.goto(placement["url"], wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(2000 + random.randint(500, 1500))
                except Exception as exc:
                    logger.debug(f"[{self.channel}] {placement['name']} goto failed: {exc}")
                    continue

                pages_visited.append(placement['name'])

                # 스크롤: lazy-load GFP 요청 트리거 (서핑 모드는 더 깊이)
                scroll_count = 15 if device.is_mobile else 8
                for s in range(scroll_count):
                    await page.evaluate(f'window.scrollBy(0, {300 + s * 80})')
                    await page.wait_for_timeout(400 + random.randint(100, 300))

                # 모바일: 상단으로 돌아갔다가 재스크롤
                if device.is_mobile:
                    await page.evaluate('window.scrollTo(0, 0)')
                    await page.wait_for_timeout(800)
                    for s in range(6):
                        await page.evaluate(f'window.scrollBy(0, {500 + s * 120})')
                        await page.wait_for_timeout(400 + random.randint(100, 200))

                # 서핑 모드: 콘텐츠 섹션 기사/서브페이지 방문
                if surf_mode and placement["name"] in ("news", "sports", "entertainment", "finance"):
                    await self._visit_sub_pages(page, placement, _cur_placement)

                # 지면 간 자연스러운 대기
                if pidx < len(visit_list) - 1:
                    await page.wait_for_timeout(1000 + random.randint(500, 1500))

            # 모바일: 카테고리 탭 순회
            if device.is_mobile and self.category_tabs > 0:
                await self._navigate_category_tabs(page)

            # 네트워크 캡처에서 광고 수집
            if network_ad_captures:
                logger.debug(f"[{self.channel}] GFP captures: {len(network_ad_captures)} from {len(pages_visited)} pages")
                net_ads = self._process_raw_ads(network_ad_captures, "network_capture", source="network")
                if net_ads:
                    logger.info(f"[{self.channel}] ads: {len(net_ads)} from pages: {pages_visited}")
                    all_ads.extend(net_ads)

            await self._download_banner_images(all_ads)

            elapsed = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            return {
                "keyword": keyword or "surf",
                "persona_code": persona.code,
                "device": device.device_type,
                "channel": self.channel,
                "captured_at": datetime.utcnow(),
                "page_url": ", ".join(pages_visited) if surf_mode else (visit_list[0]["url"] if visit_list else ""),
                "screenshot_path": None,
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

    async def _visit_sub_pages(self, page: Page, placement: dict, cur_ref: dict) -> None:
        """섹션 내 기사/서브페이지 2~3개 방문하여 추가 GFP 광고 수집."""
        try:
            article_urls = await page.evaluate("""() => {
                const links = [];
                const seen = new Set();
                for (const a of document.querySelectorAll('a[href]')) {
                    const href = a.href;
                    if (!href || !href.startsWith('http')) continue;
                    if (seen.has(href)) continue;
                    if (href.match(/\\/article\\//) || href.match(/\\/news\\/read/) ||
                        href.match(/\\/ranking\\//) || href.match(/[?&]aid=/) ||
                        href.match(/\\/\\d{8,}/) || href.match(/oid=.*&aid=/)) {
                        seen.add(href);
                        links.push(href);
                        if (links.length >= 3) break;
                    }
                }
                return links;
            }""")

            for article_url in (article_urls or [])[:2]:
                cur_ref['name'] = f"{placement['name']}_article"
                cur_ref['label'] = f"{placement['label']}_article"

                try:
                    await page.goto(article_url, wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(1500 + random.randint(500, 1000))

                    for s in range(5):
                        await page.evaluate(f'window.scrollBy(0, {300 + s * 100})')
                        await page.wait_for_timeout(400 + random.randint(100, 300))
                except Exception:
                    pass

            # 원래 지면으로 복원
            cur_ref['name'] = placement['name']
            cur_ref['label'] = placement['label']

        except Exception as exc:
            logger.debug(f"[{self.channel}] sub-page nav failed: {exc}")

    # ── 공통 후처리 ──

    _PLACEMENT_PRODUCT_MAP: dict[str, str] = {
        "main": "메인DA(타임보드/롤링보드)",
        "news": "뉴스DA",
        "news_article": "뉴스기사DA",
        "sports": "스포츠DA",
        "sports_article": "스포츠기사DA",
        "entertainment": "연예DA",
        "entertainment_article": "연예기사DA",
        "finance": "증권DA",
        "finance_article": "증권기사DA",
        "shopping": "쇼핑DA",
        "realestate": "부동산DA",
        "auto": "자동차DA",
        "movie": "영화DA",
        "webtoon": "웹툰DA",
        "cafe": "카페DA",
        "tv": "TV DA",
        "chzzk": "치지직DA",
        "weather": "날씨DA",
        "blog": "블로그DA",
        "network_capture": "DA",
    }

    _PLACEMENT_PURPOSE_MAP: dict[str, str] = {
        "main": "awareness",
        "shopping": "performance",
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

            # tivan URL은 opaque base64 → adomain 기반 URL로 대체
            adomain = item.get("adomain")
            if url and "tivan.naver.com" in (url or ""):
                if adomain:
                    url = f"https://{adomain}"
                else:
                    url = None  # tivan만 있고 adomain 없으면 URL 없음
            elif not url and adomain:
                url = f"https://{adomain}"

            # 최후 fallback: advertiser_name이 도메인 형태면 URL로 사용
            if not url:
                adv_raw = item.get("advertiser_name", "")
                if adv_raw and re.match(r'^[a-zA-Z0-9가-힣][a-zA-Z0-9가-힣._-]+\.[a-zA-Z]{2,}$', adv_raw):
                    url = f"https://{adv_raw}"

            display_url = _extract_domain(url)
            if click_url and display_url and is_infra_domain(display_url):
                resolved = resolve_via_http(click_url, timeout=4)
                resolved_domain = _extract_domain(resolved)
                if resolved and resolved_domain and not is_infra_domain(resolved_domain):
                    url = resolved
                    display_url = resolved_domain
            if url and re.search(r"\.(?:css|js)(?:[?#]|$)", url, re.I):
                continue
            if display_url and any(host in display_url for host in ("pstatic.net", "nimg.naver.net")):
                continue
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

            # 개별 광고의 placement 정보 (서핑 모드에서 지면별 추적)
            item_placement = item.get("_placement", placement_name)
            item_label = item.get("_label", "")

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
                "ad_placement": f"naver_{item_placement}",
                "ad_product_name": self._PLACEMENT_PRODUCT_MAP.get(item_placement, "DA"),
                "ad_format_type": "display",
                "campaign_purpose": self._PLACEMENT_PURPOSE_MAP.get(item_placement, "awareness"),
                "creative_image_path": None,
                "extra_data": {
                    "click_url": click_url,
                    "banner_image": item.get("banner_image"),
                    "placement": item_placement,
                    "placement_label": item_label,
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
                    'adomain': domain,
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
                # 1차: 명시적 랜딩 URL 키
                landing_match = re.search(r'(?:landingUrl|clickUrl|click_url|href)[=:]\s*["\']([^"\']+)', adm)
                if landing_match:
                    click_url = landing_match.group(1)
                # 2차: tivan이면 adm에서 실제 도메인 URL 추출 시도
                if not click_url or 'tivan.naver.com' in (click_url or ''):
                    # adm에 숨겨진 실제 URL (https://실제사이트.com 패턴)
                    real_urls = re.findall(r'https?://([a-zA-Z0-9가-힣][a-zA-Z0-9가-힣._-]+\.[a-zA-Z]{2,})', adm)
                    for u in real_urls:
                        if not any(infra in u for infra in ('naver.com', 'tivan.naver', 'pstatic.net', 'nimg.naver')):
                            click_url = f"https://{u}"
                            if not domain:
                                domain = u.removeprefix('www.').removeprefix('m.')
                            break

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
                'adomain': domain,
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
                    'adomain': domain,
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
                    'adomain': domain,
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

    # -- banner image download --

    async def _download_banner_images(self, ads: list[dict]):
        """Download banner images in parallel from extra_data['banner_image'] URLs.

        batch_download()으로 동시 8개 병렬 다운로드. 순차 방식 대비 ~8x 빠름.
        URL이 tivan 등 트래킹 도메인이면 resolve_via_http()로 실제 URL 먼저 해석.
        """
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        base_dir = Path(self.settings.screenshot_dir) / self.channel / today

        # 1) tivan.naver.com 등 불투명 URL을 HTTP 추적으로 해석 (광고 URL 결측 해소)
        ads_missing_url = [a for a in ads if not a.get("url") or "tivan.naver.com" in (a.get("url") or "")]
        if ads_missing_url:
            for ad in ads_missing_url:
                click = (ad.get("extra_data") or {}).get("click_url") or ad.get("url") or ""
                if click and is_tracking_url(click):
                    resolved = resolve_via_http(click, timeout=4)
                    if resolved and resolved != click and "tivan" not in resolved:
                        ad["url"] = resolved
                        ad["display_url"] = extract_domain(resolved)
                        if not ad.get("advertiser_name"):
                            domain = extract_domain(resolved)
                            if domain and not is_infra_domain(domain):
                                ad["advertiser_name"] = domain.removeprefix("www.").removeprefix("m.")

        # 2) 배너 이미지 병렬 다운로드
        url_to_ad: dict[str, dict] = {}
        url_to_path: dict[str, Path] = {}

        for i, ad in enumerate(ads):
            extra = ad.get("extra_data") or {}
            banner_url = extra.get("banner_image")
            if not banner_url or banner_url in url_to_ad:
                continue
            ext_hint = ".jpg"
            filename = f"naver_da_banner_{i}_{datetime.now(timezone.utc).strftime('%H%M%S%f')}{ext_hint}"
            url_to_path[banner_url] = base_dir / filename
            url_to_ad[banner_url] = ad

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
                # 실제 확장자로 리네임
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
            logger.info("[{}] banner images: {} saved / {} total", self.channel, download_count, len(ads))

    # ── 헬퍼 ──

    def _get_active_placements(self, device_key: str) -> list[dict]:
        """환경변수 필터를 적용한 활성 지면 목록 반환."""
        all_placements = NAVER_DA_PLACEMENTS.get(device_key, [])
        if not _ACTIVE_PLACEMENTS:
            return all_placements
        active_names = {n.strip() for n in _ACTIVE_PLACEMENTS.split(",")}
        return [p for p in all_placements if p["name"] in active_names]


# _extract_domain / _resolve_destination_url → crawler.url_utils
_extract_domain = extract_domain
_resolve_destination_url = resolve_redirect_url
