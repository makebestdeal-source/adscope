"""TikTok 광고 크롤러 -- Creative Center Top Ads API 캡처.

TikTok Creative Center(ads.tiktok.com)의 Top Ads 페이지를 Playwright로 로드하고,
내부 API(`creative_radar_api/v1/top_ads/v2/list`) 응답을 네트워크 캡처하여
한국 타겟 고성과 광고를 수집한다.

발견된 내부 API:
  GET /creative_radar_api/v1/top_ads/v2/list
    ?period=30&page=1&limit=20&order_by=for_you&country_code=KR

응답 material 필드:
  ad_title, brand_name, cost, ctr, favorite, id, industry_key,
  is_search, like, objective_key, video_info{url, cover, duration, ...}

- 로그인 불필요, headless OK
- 페이지네이션: page 파라미터로 다중 페이지 호출
- keyword 파라미터는 산업 필터 or 검색어로 활용
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
from loguru import logger
from playwright.async_api import Response

from crawler.base_crawler import BaseCrawler
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
PAGE_WAIT_MS = max(3000, int(os.getenv("TIKTOK_PAGE_WAIT_MS", "5000")))


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


def _normalize_material(mat: dict, position: int) -> dict | None:
    """TikTok Creative Radar API material -> 정규화된 광고 dict.

    확인된 API 필드: ad_title, brand_name, cost, ctr, favorite, id,
    industry_key, is_search, like, objective_key, video_info
    """
    if not isinstance(mat, dict):
        return None

    # 광고주 (brand_name이 주 필드)
    advertiser_name = (
        _safe_str(mat.get("brand_name"))
        or _safe_str(mat.get("advertiser_name"))
        or _safe_str(mat.get("nickname"))
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

    # 광고별 고유 URL (material_id 기반 — 광고주 식별용)
    ad_url = None
    if material_id:
        ad_url = (
            f"https://ads.tiktok.com/business/creativecenter"
            f"/inspiration/topads/pc/en?modal_id={material_id}"
        )

    return {
        "advertiser_name": advertiser_name or None,
        "ad_text": ad_text or f"tiktok_ad_{material_id}",
        "ad_description": None,
        "url": ad_url,
        "display_url": "ads.tiktok.com",
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

    수집 방식:
    1. Playwright로 Creative Center 페이지 로드 (쿠키/세션 획득)
    2. 내부 API 응답을 네트워크 인터셉트
    3. 추가 페이지는 Playwright 내에서 fetch()로 직접 호출
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
        """Creative Center 페이지 로드 + API 페이지네이션으로 광고 수집."""
        page = await context.new_page()

        try:
            # -- 네트워크 캡처: 첫 페이지 API 응답 --
            api_materials: list[dict] = []

            async def _on_response(response: Response):
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
                            logger.debug(
                                "[tiktok_ads] API page captured {} ads",
                                len(mats),
                            )
                            # 첫 material의 video_info 구조 로깅
                            if len(api_materials) <= 20:
                                vi = mats[0].get("video_info")
                                if isinstance(vi, dict):
                                    logger.debug(
                                        "[tiktok_ads] video_info keys: {}",
                                        sorted(vi.keys()),
                                    )
                except Exception:
                    pass

            page.on("response", _on_response)

            # -- 1) 페이지 로드 (세션/쿠키 획득 + 첫 API 자동 호출) --
            url = f"{TOP_ADS_BASE_URL}?region=KR"
            logger.info("[tiktok_ads] loading: {}", url[:100])
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(PAGE_WAIT_MS)

            first_page_count = len(api_materials)
            logger.info(
                "[tiktok_ads] first page (for_you): {} ads from API",
                first_page_count,
            )

            # -- 2) 페이지네이션 + 다양한 정렬/기간으로 볼륨 최대화 --
            all_orders = ["for_you", "reach", "ctr", "like"]
            all_periods = [30, 7, 180]
            for order in all_orders:
                for period in all_periods:
                    if len(api_materials) >= MAX_ADS:
                        break
                    for pg in range(1, MAX_PAGES + 1):
                        if len(api_materials) >= MAX_ADS:
                            break
                        # KR 우선, 전체 지역도 수집 (한국 광고주는 korean_filter에서 걸러짐)
                        for country in ("KR", ""):
                            if len(api_materials) >= MAX_ADS:
                                break
                            country_param = f"&country_code={country}" if country else ""
                            api_url = (
                                f"{API_LIST_URL}?period={period}&page={pg}&limit=20"
                                f"&order_by={order}{country_param}"
                            )
                            try:
                                resp_text = await page.evaluate(f"""
                                    async () => {{
                                        const r = await fetch("{api_url}", {{
                                            credentials: "include",
                                            headers: {{ "Accept": "application/json" }}
                                        }});
                                        return await r.text();
                                    }}
                                """)
                                data = json.loads(resp_text)
                                mats = (data.get("data") or {}).get("materials", [])
                                if isinstance(mats, list) and mats:
                                    api_materials.extend(mats)
                                    logger.info(
                                        "[tiktok_ads] order={}/period={}/page={}/country={} -> {} ads",
                                        order, period, pg, country or "ALL", len(mats),
                                    )
                                else:
                                    break  # No more pages for this combo
                            except Exception as e:
                                logger.debug(
                                    "[tiktok_ads] order={}/page={} failed: {}",
                                    order, pg, e,
                                )
                                break
                            await page.wait_for_timeout(800)

            # -- 3) 중복 제거 --
            seen_ids: set[str] = set()
            unique: list[dict] = []
            for mat in api_materials:
                mid = str(mat.get("id") or id(mat))
                if mid not in seen_ids:
                    seen_ids.add(mid)
                    unique.append(mat)

            # -- 4) 정규화 --
            ads: list[dict] = []
            for i, mat in enumerate(unique[:MAX_ADS]):
                ad = _normalize_material(mat, i + 1)
                if ad:
                    ads.append(ad)

            logger.info(
                "[tiktok_ads] '{}' -> {} ads (raw:{}, unique:{})",
                keyword, len(ads), len(api_materials), len(unique),
            )

            # -- 5) 커버 이미지 다운로드 --
            await self._download_covers(ads)

            return ads

        except Exception as e:
            logger.error("[tiktok_ads] crawl failed: {}", e)
            return []
        finally:
            await page.close()

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

                    if not self._is_valid_image(content):
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

    @staticmethod
    def _is_valid_image(data: bytes) -> bool:
        """바이너리가 유효 이미지인지 매직 바이트 확인."""
        if len(data) < 8:
            return False
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return True
        if data[:3] == b"\xff\xd8\xff":
            return True
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return True
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return True
        if data[:2] == b"BM":
            return True
        return False
