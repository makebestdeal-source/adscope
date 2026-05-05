"""TikTok 광고 크롤러 -- Creative Center Top Ads API 캡처.

TikTok Creative Center(ads.tiktok.com)의 Top Ads 페이지를 Playwright로 로드하고,
내부 API(`creative_radar_api/v1/top_ads/v2/list`) 응답을 네트워크 캡처하여
한국 타겟 고성과 광고를 수집한다.

발견된 내부 API:
  GET /creative_radar_api/v1/top_ads/v2/list
    ?period=30&page=1&limit=20&order_by=for_you&country_code=KR&msToken=<signed>

응답 material 필드:
  ad_title, brand_name, cost, ctr, favorite, id, industry_key,
  is_search, like, objective_key, video_info{url, cover, duration, ...}

수집 전략 (2026-05 업데이트):
  1. Playwright로 Creative Center 페이지 로드 (JS 실행 → 서명된 msToken 획득)
  2. 네트워크 인터셉트로 첫 페이지 API 응답 캡처
  3. 추가 페이지: page.evaluate fetch에 서명된 msToken을 URL 쿼리로 포함
  4. fetch 실패 시: 다양한 industry 파라미터로 CC 페이지 재방문 (다중 goto)
  5. 키워드(한국어) → industry_key 매핑으로 TikTok API 필터 활용

- 로그인 불필요, headless OK
- 페이지네이션: msToken 포함 fetch() 또는 다중 goto()로 볼륨 확보
- keyword 파라미터는 industry_key로 매핑하여 API 필터로 활용
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from loguru import logger
from playwright.async_api import Response

from crawler.base_crawler import BaseCrawler
from crawler.image_utils import is_valid_image
from crawler.personas.device_config import DeviceConfig
from crawler.personas.profiles import PersonaProfile

# ── 설정 ──

TOP_ADS_BASE_URL = (
    "https://ads.tiktok.com/business/creativecenter"
    "/inspiration/topads/pc/en"
)

# 내부 API 엔드포인트 (Playwright 네트워크 캡처로 발견)
API_LIST_URL = (
    "https://ads.tiktok.com/creative_radar_api/v1/top_ads/v2/list"
)

MAX_ADS = max(1, int(os.getenv("TIKTOK_MAX_ADS", "60")))
MAX_PAGES = max(1, int(os.getenv("TIKTOK_MAX_PAGES", "3")))
# 5000 → 10000: TikTok CC는 무거운 SPA — JS 실행 + 서명 토큰 생성까지 시간 필요
PAGE_WAIT_MS = max(5000, int(os.getenv("TIKTOK_PAGE_WAIT_MS", "10000")))

# ── 키워드 → TikTok industry_key 매핑 ──
# fast_crawl.py의 keyword 값을 TikTok CC API industry_key로 변환
# API 파라미터: ?industry_key=GAMING (빈값이면 전체 피드)
_KEYWORD_TO_INDUSTRY: dict[str, str | None] = {
    "": None,                 # 필터 없음 (전체 KR 피드)
    "게임": "GAMING",
    "뷰티": "FASHION_AND_BEAUTY",
    "패션": "FASHION_AND_BEAUTY",
    "음식": "FOOD_AND_BEVERAGES",
    "반려동물": "PET",
    "교육": "EDUCATION",
    "여행": "TRAVEL",
    # 추가 매핑 (fast_crawl.py 확장 시 대비)
    "금융": "FINANCE",
    "기술": "TECHNOLOGY",
    "IT": "TECHNOLOGY",
    "건강": "HEALTH",
    "자동차": "AUTOMOTIVE",
    "엔터테인먼트": "ENTERTAINMENT",
    "쇼핑": "ECOMMERCE",
    "e커머스": "ECOMMERCE",
    "미디어": "MEDIA",
    "스포츠": "SPORTS",
}

# TikTok Creative Center에서 확인된 industry_key 전체 목록
# (keyword 매핑 없을 때 다중 goto 폴백에서 순환 사용)
_ALL_INDUSTRY_KEYS = [
    "GAMING",
    "FASHION_AND_BEAUTY",
    "FOOD_AND_BEVERAGES",
    "EDUCATION",
    "TRAVEL",
    "ECOMMERCE",
    "FINANCE",
    "TECHNOLOGY",
    "HEALTH",
    "AUTOMOTIVE",
    "ENTERTAINMENT",
    "PET",
]


def _safe_str(val) -> str:
    """값을 안전하게 문자열로 변환 (list/dict도 처리)."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, list):
        for item in val:
            if isinstance(item, str):
                return item.strip()
        return str(val[0]).strip() if val else ""
    if isinstance(val, dict):
        return str(val.get("name") or val.get("value") or "")
    return str(val).strip()


def _pick_material_value(mat: dict, *keys: str) -> str:
    for key in keys:
        value = _safe_str(mat.get(key))
        if value:
            return value
    return ""


def _pick_nested_value(mat: dict, parent_key: str, *keys: str) -> str:
    nested = mat.get(parent_key) or {}
    if not isinstance(nested, dict):
        return ""
    return _pick_material_value(nested, *keys)


def _extract_domain_hint(text: str | None) -> str | None:
    candidate = _safe_str(text)
    if not candidate:
        return None
    match = re.search(
        r"((?:https?://)?(?:www\.)?[A-Za-z0-9][A-Za-z0-9._-]*\.(?:com|co\.kr|kr|net|org|io|shop|store|biz))",
        candidate,
        re.IGNORECASE,
    )
    if not match:
        return None
    return _extract_display_domain(
        match.group(1) if "://" in match.group(1) else f"https://{match.group(1)}"
    )


def _extract_display_domain(url: str | None) -> str | None:
    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        host = urlparse(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return None
    return host or None


def _is_creative_center_modal_url(url: str | None) -> bool:
    return "ads.tiktok.com/business/creativecenter" in str(url or "")


def _normalize_material(mat: dict, position: int) -> dict | None:
    """TikTok Creative Radar API material -> 정규화된 광고 dict.

    확인된 API 필드: ad_title, brand_name, cost, ctr, favorite, id,
    industry_key, is_search, like, objective_key, video_info
    """
    if not isinstance(mat, dict):
        return None

    # 광고주 (brand_name이 주 필드)
    advertiser_name = _pick_material_value(
        mat,
        "brand_name",
        "advertiser_name",
        "brand",
        "business_name",
        "business_account_name",
        "company_name",
        "account_name",
        "author_name",
        "creator_name",
        "seller_name",
        "store_name",
        "shop_name",
        "page_name",
        "profile_name",
        "user_name",
        "username",
        "nickname",
    )
    if not advertiser_name:
        advertiser_name = _pick_nested_value(
            mat,
            "video_info",
            "brand_name",
            "author_name",
            "author",
            "nickname",
            "creator_name",
            "display_name",
            "username",
            "account_name",
            "user_name",
            "shop_name",
            "seller_name",
        )

    # 광고 텍스트 (ad_title이 주 필드)
    ad_text = (
        _safe_str(mat.get("ad_title"))
        or _safe_str(mat.get("title"))
        or _safe_str(mat.get("caption"))
    )

    # video_info (dict): url, cover, duration 등
    video_info = mat.get("video_info") or {}
    if not isinstance(video_info, dict):
        video_info = {}

    video_url = _safe_str(video_info.get("url")) or _safe_str(mat.get("video_url"))
    cover_url = (
        _safe_str(video_info.get("cover"))
        or _safe_str(mat.get("cover_url"))
        or _safe_str(mat.get("cover"))
    )
    duration = video_info.get("duration")

    # 통계 (API 필드: like, cost, ctr)
    like_count = mat.get("like")
    cost = mat.get("cost")
    ctr = mat.get("ctr")

    # ID
    material_id = str(mat.get("id") or "")

    # 카테고리
    industry = _safe_str(mat.get("industry_key"))
    objective = _safe_str(mat.get("objective_key"))
    is_search = mat.get("is_search")

    extra_data = {
        "detection_method": "tiktok_creative_center",
        "material_id": material_id,
        "video_url": video_url,
        "cover_url": cover_url,
        "industry": industry,
        "objective": objective,
    }

    # 통계 (None 아닌 것만)
    if like_count is not None:
        extra_data["like_count"] = like_count
    if cost is not None:
        extra_data["cost_level"] = cost
    if ctr is not None:
        extra_data["ctr"] = ctr
    if duration is not None:
        extra_data["duration"] = duration
    if is_search is not None:
        extra_data["is_search_ad"] = is_search

    # ── 마케팅 플랜 계층 필드 ──
    _obj_lower = objective.lower()
    if any(kw in _obj_lower for kw in ("reach", "brand")):
        _ad_product_name = "TopView"
    else:
        _ad_product_name = "인피드"

    _purpose_map = {
        "conversion": "commerce",
        "awareness": "branding",
        "reach": "branding",
        "traffic": "performance",
        "engagement": "awareness",
    }
    _campaign_purpose = "awareness"  # default
    for key, purpose in _purpose_map.items():
        if key in _obj_lower:
            _campaign_purpose = purpose
            break

    # 실제 랜딩 URL 추출 (API 응답의 landing_page 필드)
    ad_url = (
        _safe_str(mat.get("landing_page_url"))
        or _safe_str(mat.get("landing_page"))
        or _safe_str(mat.get("link"))
        or _safe_str(mat.get("url"))
    )
    # fallback: Creative Center modal URL (파이프라인에서 필터될 수 있음)
    if not ad_url and material_id:
        ad_url = (
            f"https://ads.tiktok.com/business/creativecenter"
            f"/inspiration/topads/pc/en?modal_id={material_id}"
        )

    if not advertiser_name and ad_url and not _is_creative_center_modal_url(ad_url):
        domain_hint = _extract_display_domain(ad_url)
        if domain_hint and not domain_hint.endswith("tiktok.com"):
            advertiser_name = domain_hint.split(".")[0]
    if not advertiser_name:
        text_domain_hint = _extract_domain_hint(ad_text)
        if text_domain_hint and not text_domain_hint.endswith("tiktok.com"):
            advertiser_name = text_domain_hint.split(".")[0]

    display_url = _extract_display_domain(ad_url) or "ads.tiktok.com"
    modal_fallback_used = _is_creative_center_modal_url(ad_url)

    extra_data["url_source"] = "modal_fallback" if modal_fallback_used else "landing_page"

    return {
        "advertiser_name": advertiser_name or None,
        "ad_text": ad_text or f"tiktok_ad_{material_id}",
        "ad_description": None,
        "url": ad_url,
        "display_url": display_url,
        "position": position,
        "ad_type": "tiktok_creative_center",
        "ad_placement": "tiktok_top_ads",
        "ad_product_name": _ad_product_name,
        "ad_format_type": "social",
        "campaign_purpose": _campaign_purpose,
        "creative_image_path": None,
        "extra_data": extra_data,
        "verification_status": "verified",
        "verification_source": "tiktok_creative_center",
    }


class TikTokAdsCrawler(BaseCrawler):
    """TikTok Creative Center Top Ads API 캡처로 광고 수집.

    수집 방식 (2026-05 업데이트):
    1. Playwright로 Creative Center 페이지 로드 (JS 실행 → 서명된 msToken 획득)
    2. 네트워크 인터셉트로 첫 페이지 API 응답 캡처
    3. page.evaluate fetch()에 서명된 msToken 포함 → 추가 페이지 수집
    4. fetch 실패 시: 다양한 industry CC 페이지 goto() 폴백
    5. 키워드 → industry_key 매핑 적용

    핵심 변경점:
    - PAGE_WAIT_MS 5000→10000 (SPA JS 실행 대기 충분히)
    - msToken을 cookie가 아닌 URL 쿼리 파라미터로 포함 (TikTok API 인증 요구사항)
    - industry_key 파라미터를 keyword 매핑으로 적용
    - fetch 실패 시 다중 goto 폴백으로 더 많은 네트워크 캡처
    """

    channel = "tiktok_ads"

    async def crawl_keyword(
        self,
        keyword: str,
        persona: PersonaProfile,
        device: DeviceConfig,
    ) -> dict:
        start_time = datetime.now(timezone.utc)
        context = await self._create_context(persona, device)

        try:
            ads = await self._collect_ads(context, keyword)

            elapsed = int(
                (datetime.now(timezone.utc) - start_time).total_seconds()
                * 1000
            )

            return {
                "keyword": keyword,
                "persona_code": persona.code,
                "device": device.device_type,
                "channel": self.channel,
                "captured_at": datetime.now(timezone.utc),
                "page_url": TOP_ADS_BASE_URL,
                "screenshot_path": None,
                "ads": ads,
                "crawl_duration_ms": elapsed,
            }
        finally:
            for p in context.pages:
                await p.close()
            await context.close()

    async def _collect_ads(self, context, keyword: str) -> list[dict]:
        """Creative Center 페이지 로드 + API 페이지네이션으로 광고 수집.

        수집 전략:
        1. keyword → industry_key 매핑
        2. Playwright 페이지 로드 (10초 대기 - SPA JS 실행 충분히)
        3. 네트워크 인터셉트로 첫 페이지 캡처 (항상 작동)
        4. page.evaluate fetch에 서명된 msToken 포함 → 추가 페이지
        5. fetch 실패 시 다중 industry goto 폴백
        """
        page = await context.new_page()

        try:
            # keyword → industry_key 매핑
            industry_key: str | None = _KEYWORD_TO_INDUSTRY.get(keyword)
            logger.info(
                "[tiktok_ads] keyword={!r} -> industry_key={!r}",
                keyword, industry_key,
            )

            # -- 네트워크 캡처: 모든 top_ads API 응답 수집 --
            api_materials: list[dict] = []
            capture_count = 0

            async def _on_response(response: Response):
                nonlocal capture_count
                url = response.url
                try:
                    if response.status != 200:
                        return
                    ct = response.headers.get("content-type", "")
                    if "json" not in ct:
                        return
                    if "top_ads/v2/list" in url:
                        data = await response.json()
                        mats = (data.get("data") or {}).get("materials", [])
                        if isinstance(mats, list) and mats:
                            api_materials.extend(mats)
                            capture_count += 1
                            logger.debug(
                                "[tiktok_ads] network capture #{}: {} ads (total: {})",
                                capture_count, len(mats), len(api_materials),
                            )
                            # 첫 번째 material 구조 로깅 (디버그)
                            if capture_count == 1:
                                logger.debug(
                                    "[tiktok_ads] material keys: {}",
                                    sorted(mats[0].keys()),
                                )
                                vi = mats[0].get("video_info")
                                if isinstance(vi, dict):
                                    logger.debug(
                                        "[tiktok_ads] video_info keys: {}",
                                        sorted(vi.keys()),
                                    )
                        else:
                            # code 확인 - 40101이면 인증 실패
                            code = data.get("code")
                            msg = data.get("msg", "")
                            if code and code != 0:
                                logger.warning(
                                    "[tiktok_ads] API error code={} msg={} url={}",
                                    code, msg, url[:120],
                                )
                except Exception as exc:
                    logger.debug("[tiktok_ads] response handler error: {}", exc)

            page.on("response", _on_response)

            # -- 1) 첫 페이지 로드 (industry_key 파라미터 포함) --
            # CC 페이지 URL: ?region=KR&industry=GAMING 형태로 industry 필터 적용
            page_url = f"{TOP_ADS_BASE_URL}?region=KR"
            if industry_key:
                page_url = f"{page_url}&industry={industry_key}"

            logger.info("[tiktok_ads] loading: {}", page_url[:120])
            await page.goto(page_url, wait_until="domcontentloaded", timeout=30000)

            # SPA 초기화 대기 (10초 - JS 실행 + 서명 토큰 생성 시간 필요)
            await page.wait_for_timeout(PAGE_WAIT_MS)

            first_page_count = len(api_materials)
            logger.info(
                "[tiktok_ads] first page network capture: {} ads",
                first_page_count,
            )

            if first_page_count == 0:
                logger.warning(
                    "[tiktok_ads] WARN: no ads from first page capture! "
                    "Check if TikTok CC is blocking headless browser."
                )

            # -- 2) 서명된 msToken 추출 --
            # Playwright 쿠키에서 msToken을 가져옴 (JS 실행으로 서명된 토큰)
            ms_token = ""
            try:
                cookies = await context.cookies(["https://ads.tiktok.com"])
                for cookie in cookies:
                    if cookie.get("name") == "msToken":
                        ms_token = cookie.get("value", "")
                        break
                logger.debug(
                    "[tiktok_ads] msToken from Playwright: {}...{}",
                    ms_token[:10] if ms_token else "NONE",
                    ms_token[-5:] if len(ms_token) > 10 else "",
                )
            except Exception as e:
                logger.debug("[tiktok_ads] msToken extract error: {}", e)

            # -- 3) 추가 페이지: page.evaluate fetch + msToken URL 쿼리 포함 --
            # msToken을 URL 쿼리 파라미터로 포함해야 TikTok API 인증 통과
            fetch_success_count = 0
            fetch_fail_count = 0
            orders = ["for_you", "reach", "ctr", "like"]
            periods = [30, 7, 180]

            for order in orders:
                if len(api_materials) >= MAX_ADS:
                    break
                for period in periods:
                    if len(api_materials) >= MAX_ADS:
                        break
                    for pg in range(1, MAX_PAGES + 1):
                        if len(api_materials) >= MAX_ADS:
                            break
                        for country in ("KR", ""):
                            if len(api_materials) >= MAX_ADS:
                                break

                            # URL 파라미터 구성 (msToken 포함)
                            params = (
                                f"period={period}&page={pg}&limit=20"
                                f"&order_by={order}"
                            )
                            if country:
                                params += f"&country_code={country}"
                            if industry_key:
                                params += f"&industry_key={industry_key}"
                            if ms_token:
                                params += f"&msToken={ms_token}"

                            api_url = f"{API_LIST_URL}?{params}"

                            try:
                                resp_text = await page.evaluate(f"""
                                    async () => {{
                                        const r = await fetch("{api_url}", {{
                                            credentials: "include",
                                            headers: {{
                                                "Accept": "application/json",
                                                "Referer": "https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/en"
                                            }}
                                        }});
                                        return await r.text();
                                    }}
                                """)
                                data = json.loads(resp_text)
                                code = data.get("code", 0)
                                mats = (data.get("data") or {}).get("materials", [])
                                if isinstance(mats, list) and mats:
                                    api_materials.extend(mats)
                                    fetch_success_count += 1
                                    logger.info(
                                        "[tiktok_ads] fetch ok: order={}/period={}/p={}/country={} -> {} ads",
                                        order, period, pg, country or "ALL", len(mats),
                                    )
                                elif code == 40101:
                                    # 인증 실패 → fetch 방식 포기, goto 폴백으로
                                    fetch_fail_count += 1
                                    logger.debug(
                                        "[tiktok_ads] fetch 40101 no permission "
                                        "(order={}/period={}/p={})",
                                        order, period, pg,
                                    )
                                    if fetch_fail_count >= 3:
                                        logger.warning(
                                            "[tiktok_ads] fetch 연속 3회 40101 -> goto 폴백으로 전환"
                                        )
                                        raise _FetchAuthError()
                                else:
                                    # 빈 결과 = 더 이상 페이지 없음
                                    break
                            except _FetchAuthError:
                                raise
                            except Exception as e:
                                logger.debug(
                                    "[tiktok_ads] fetch error (order={}/p={}): {}",
                                    order, pg, str(e)[:80],
                                )
                                break
                            await page.wait_for_timeout(600)

        except _FetchAuthError:
            # fetch 방식 인증 실패 → goto 폴백
            logger.info("[tiktok_ads] fetch auth failed -> goto 폴백 시작")
            api_materials = await self._collect_via_goto(
                context, page, api_materials, industry_key
            )

        except Exception as e:
            logger.error("[tiktok_ads] crawl failed: {}", e)
            return []
        finally:
            # page는 goto 폴백에서도 재사용되므로 여기서 닫음
            try:
                await page.close()
            except Exception:
                pass

        # -- 4) 중복 제거 --
        seen_ids: set[str] = set()
        unique: list[dict] = []
        for mat in api_materials:
            mid = str(mat.get("id") or id(mat))
            if mid not in seen_ids:
                seen_ids.add(mid)
                unique.append(mat)

        # -- 5) 정규화 --
        ads: list[dict] = []
        for i, mat in enumerate(unique[:MAX_ADS]):
            ad = _normalize_material(mat, i + 1)
            if ad:
                ads.append(ad)

        logger.info(
            "[tiktok_ads] '{}' -> {} ads (raw:{}, unique:{})",
            keyword, len(ads), len(api_materials), len(unique),
        )

        if not ads:
            logger.warning(
                "[tiktok_ads] WARN: 0 ads collected for keyword={!r}. "
                "TikTok may require anti-bot bypass.",
                keyword,
            )

        # -- 6) 커버 이미지 다운로드 --
        await self._download_covers(ads)

        return ads

    async def _collect_via_goto(
        self,
        context,
        page,
        existing_materials: list[dict],
        industry_key: str | None,
    ) -> list[dict]:
        """fetch 실패 시 폴백: 다양한 industry CC 페이지를 goto로 방문하여 네트워크 캡처.

        각 goto는 TikTok CC가 자체적으로 API를 호출하게 하고,
        network intercept가 그 응답을 캡처함.
        """
        api_materials = list(existing_materials)
        captured_extra: list[dict] = []

        async def _on_response_extra(response: Response):
            url = response.url
            try:
                if response.status != 200:
                    return
                ct = response.headers.get("content-type", "")
                if "json" not in ct or "top_ads/v2/list" not in url:
                    return
                data = await response.json()
                mats = (data.get("data") or {}).get("materials", [])
                if isinstance(mats, list) and mats:
                    captured_extra.extend(mats)
                    logger.debug(
                        "[tiktok_ads] goto capture: {} ads (total extra: {})",
                        len(mats), len(captured_extra),
                    )
            except Exception:
                pass

        page.on("response", _on_response_extra)

        # industry 순환: 현재 industry_key 제외하고 나머지 순환
        industries_to_visit = [industry_key] if industry_key else []
        for ind in _ALL_INDUSTRY_KEYS:
            if ind not in industries_to_visit:
                industries_to_visit.append(ind)

        for ind in industries_to_visit:
            if len(api_materials) + len(captured_extra) >= MAX_ADS:
                break

            visit_url = f"{TOP_ADS_BASE_URL}?region=KR"
            if ind:
                visit_url = f"{visit_url}&industry={ind}"

            logger.info("[tiktok_ads] goto fallback: {}", visit_url[:120])
            try:
                await page.goto(
                    visit_url, wait_until="domcontentloaded", timeout=25000
                )
                # 페이지마다 7초 대기 (SPA API 자동 호출 시간)
                await page.wait_for_timeout(7000)
                logger.debug(
                    "[tiktok_ads] goto {} -> captured {} so far",
                    ind or "ALL", len(captured_extra),
                )
            except Exception as e:
                logger.debug("[tiktok_ads] goto {} failed: {}", ind, e)
                continue

        api_materials.extend(captured_extra)
        logger.info(
            "[tiktok_ads] goto fallback complete: {} extra ads (total: {})",
            len(captured_extra), len(api_materials),
        )
        return api_materials

    async def _download_covers(self, ads: list[dict]):
        """커버 이미지 다운로드."""
        download_count = 0
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for ad in ads:
                cover_url = (ad.get("extra_data") or {}).get("cover_url")
                if not cover_url:
                    continue
                try:
                    resp = await client.get(cover_url)
                    if resp.status_code != 200:
                        continue
                    content = resp.content
                    if len(content) < 500:
                        continue

                    if not is_valid_image(content):
                        continue

                    screenshot_dir = (
                        Path(self.settings.screenshot_dir)
                        / self.channel
                        / datetime.now(timezone.utc).strftime("%Y%m%d")
                    )
                    screenshot_dir.mkdir(parents=True, exist_ok=True)

                    mid = (ad.get("extra_data") or {}).get("material_id", "unknown")
                    ts = datetime.now(timezone.utc).strftime("%H%M%S")
                    ext = ".jpg"
                    if content[:8] == b"\x89PNG\r\n\x1a\n":
                        ext = ".png"
                    elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
                        ext = ".webp"

                    filename = f"tt_cover_{str(mid)[:20]}_{ts}{ext}"
                    filepath = screenshot_dir / filename
                    filepath.write_bytes(content)

                    try:
                        stored = await self._image_store.save(
                            str(filepath), self.channel, "creative"
                        )
                        ad["creative_image_path"] = stored
                    except Exception:
                        ad["creative_image_path"] = str(filepath)

                    download_count += 1
                except Exception as exc:
                    logger.debug(
                        "[tiktok_ads] cover download failed: {}",
                        str(exc)[:60],
                    )

        if download_count:
            logger.info(
                "[tiktok_ads] covers: {} downloaded / {} total",
                download_count, len(ads),
            )

    # is_valid_image → crawler.image_utils.is_valid_image


class _FetchAuthError(Exception):
    """page.evaluate fetch()가 TikTok API 40101 인증 오류를 반환한 경우."""
    pass
