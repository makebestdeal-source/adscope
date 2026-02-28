"""YouTube 광고 크롤러 -- Google Ads Transparency Center RPC API 캡처.

Google Ads Transparency Center의 내부 RPC API를 네트워크 인터셉트하여
YouTube 플랫폼 광고를 키워드 기반으로 수집한다.

- 로그인 불필요, headless OK
- SearchSuggestions RPC -> 광고주 ID 목록
- SearchCreatives RPC -> 광고주별 크리에이티브 목록
- keyword_dependent = True (키워드 기반 검색)
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from loguru import logger
from playwright.async_api import Response

from crawler.base_crawler import BaseCrawler
from crawler.personas.device_config import DeviceConfig
from crawler.personas.profiles import PersonaProfile

# ── 설정 ──

ADS_TRANSPARENCY_URL = (
    "https://adstransparency.google.com/"
    "?region=KR&platform=YOUTUBE"
)

# 방문할 최대 광고주 수
MAX_ADVERTISERS = max(1, int(os.getenv("YT_ADS_MAX_ADVERTISERS", "100")))
# 최대 수집 광고 수
MAX_ADS = max(1, int(os.getenv("YT_ADS_MAX_ADS", "200")))
# 광고주 페이지 대기 (ms)
ADVERTISER_WAIT_MS = max(3000, int(os.getenv("YT_ADS_WAIT_MS", "8000")))


def _parse_suggestions(data: dict) -> list[dict]:
    """SearchSuggestions RPC 응답에서 광고주 목록 추출."""
    results = []
    for item in data.get("1", []):
        info = item.get("1", {})
        if not isinstance(info, dict):
            continue
        name = info.get("1")
        adv_id = info.get("2")
        country = info.get("3")
        count_info = info.get("4", {})
        ad_count = None
        if isinstance(count_info, dict):
            inner = count_info.get("2", {})
            if isinstance(inner, dict):
                ad_count = inner.get("1")
        if name and adv_id:
            results.append({
                "name": name,
                "id": adv_id,
                "country": country,
                "ad_count": ad_count,
            })
    return results


def _extract_view_count(item: dict) -> int | None:
    """SearchCreatives RPC 응답의 개별 크리에이티브에서 view count 추출.

    Google Ads Transparency Center RPC 응답(protobuf-like JSON)에서
    impression/view count 데이터를 추출한다.

    Known field locations for impression data:
    - item["8"]["1"] or item["8"]["2"]: impression range (min/max)
    - item["9"]: single impression/view count integer
    - item["8"]: direct integer value (simplified response)
    - item["5"]["2"]["1"]: nested impression count in region data

    Returns:
        view count as integer, or None if not found.
    """
    # Strategy 1: field "8" -- impression range or direct count
    field_8 = item.get("8")
    if field_8 is not None:
        if isinstance(field_8, (int, float)):
            return int(field_8)
        if isinstance(field_8, str) and field_8.isdigit():
            return int(field_8)
        if isinstance(field_8, dict):
            # Range: {"1": min_impressions, "2": max_impressions}
            # Use the lower bound as conservative estimate
            for sub_key in ("1", "2"):
                val = field_8.get(sub_key)
                if isinstance(val, (int, float)):
                    return int(val)
                if isinstance(val, str) and val.isdigit():
                    return int(val)

    # Strategy 2: field "9" -- alternate impression count location
    field_9 = item.get("9")
    if field_9 is not None:
        if isinstance(field_9, (int, float)):
            return int(field_9)
        if isinstance(field_9, str) and field_9.isdigit():
            return int(field_9)
        if isinstance(field_9, dict):
            val = field_9.get("1")
            if isinstance(val, (int, float)):
                return int(val)
            if isinstance(val, str) and val.isdigit():
                return int(val)

    # Strategy 3: field "5" nested -- region-specific view data
    field_5 = item.get("5")
    if isinstance(field_5, dict):
        inner = field_5.get("2")
        if isinstance(inner, dict):
            val = inner.get("1")
            if isinstance(val, (int, float)):
                return int(val)
            if isinstance(val, str) and val.isdigit():
                return int(val)

    return None


def _collect_unknown_fields(item: dict) -> dict:
    """Parse unknown/unhandled fields from a creative item for debugging.

    Fields 1-7 and 12 are already parsed (creative_id, render_info,
    format_type, region, start_ts, end_ts, advertiser_name).
    This captures fields 8+ that may contain impression/view data.
    """
    known_keys = {"1", "2", "3", "4", "5", "6", "7", "12"}
    unknown = {}
    for key in item:
        if key not in known_keys:
            val = item[key]
            # Truncate long string values
            if isinstance(val, str) and len(val) > 200:
                val = val[:200] + "..."
            unknown[key] = val
    return unknown


def _parse_creatives(data: dict, advertiser_name: str) -> list[dict]:
    """SearchCreatives RPC 응답에서 크리에이티브 목록 추출."""
    results = []
    unknown_fields_sample = None
    for item in data.get("1", []):
        if not isinstance(item, dict):
            continue
        creative_id = item.get("2")
        adv_name = item.get("12") or advertiser_name
        # 타임스탬프 (unix seconds)
        start_ts = None
        end_ts = None
        start_info = item.get("6", {})
        if isinstance(start_info, dict):
            start_ts = start_info.get("1")
        end_info = item.get("7", {})
        if isinstance(end_info, dict):
            end_ts = end_info.get("1")
        # 크리에이티브 프리뷰 URL + 실제 이미지 URL 추출
        preview_url = None
        image_url = None
        render_info = item.get("3", {})
        if isinstance(render_info, dict):
            inner = render_info.get("1", {})
            if isinstance(inner, dict):
                preview_url = inner.get("4")
            # field 3.3.2: <img src="https://tpc.googlesyndication.com/..."> 형태
            inner_3 = render_info.get("3", {})
            if isinstance(inner_3, dict):
                html_str = inner_3.get("2", "")
                if isinstance(html_str, str):
                    m = re.search(r'src="(https?://[^"]+)"', html_str)
                    if m:
                        image_url = m.group(1)
        # 포맷 타입
        format_type = item.get("4")

        # view count / impression data 추출
        view_count = _extract_view_count(item)

        # 첫 아이템의 미파싱 필드 샘플 로깅 (디버깅용)
        if unknown_fields_sample is None:
            unknown_fields_sample = _collect_unknown_fields(item)

        results.append({
            "advertiser_name": adv_name,
            "creative_id": creative_id,
            "preview_url": preview_url,
            "image_url": image_url,
            "format_type": format_type,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "view_count": view_count,
        })

    # 미파싱 필드 디버그 로그 (첫 크리에이티브만)
    if unknown_fields_sample:
        logger.debug(
            "[youtube_ads] creative unknown fields sample: {}",
            unknown_fields_sample,
        )

    return results


class YouTubeAdsCrawler(BaseCrawler):
    """Google Ads Transparency Center RPC API 캡처로 YouTube 광고 수집."""

    channel = "youtube_ads"

    async def crawl_keyword(
        self,
        keyword: str,
        persona: PersonaProfile,
        device: DeviceConfig,
    ) -> dict:
        start_time = datetime.now(timezone.utc)
        context = await self._create_context(persona, device)

        try:
            page, ads = await self._collect_ads(context, keyword)

            screenshot_path = None  # full-page 스크린샷 비활성화

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
                "page_url": ADS_TRANSPARENCY_URL,
                "screenshot_path": screenshot_path,
                "ads": ads,
                "crawl_duration_ms": elapsed,
            }
        finally:
            for p in context.pages:
                await p.close()
            await context.close()

    async def _collect_ads(
        self, context, keyword: str,
    ) -> tuple:
        """키워드 검색 -> 광고주 목록 -> 각 광고주 크리에이티브 수집.

        Returns:
            (page, ads) -- page는 스크린샷용으로 열어 둠.
        """
        page = await context.new_page()

        try:
            # -- RPC 응답 캡처 설정 --
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
                        # Log field structure of first creative for discovery
                        items = data.get("1", [])
                        if items and isinstance(items[0], dict):
                            first = items[0]
                            logger.debug(
                                "[youtube_ads] SearchCreatives first item keys: {}",
                                sorted(first.keys()),
                            )
                except Exception:
                    pass

            page.on("response", _on_response)

            # -- 1) 메인 페이지 접속 --
            await page.goto(
                ADS_TRANSPARENCY_URL,
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(3000)

            # -- 2) 검색창에 키워드 입력 --
            search_ok = await self._fill_search(page, keyword)
            if not search_ok:
                logger.warning(
                    "[{}] search input not found", self.channel,
                )
                return page, []

            # -- 3) SearchSuggestions 응답 대기 --
            await page.wait_for_timeout(5000)

            # 광고주 목록 파싱
            advertisers: list[dict] = []
            for sd in suggestion_data:
                advertisers.extend(_parse_suggestions(sd))

            if not advertisers:
                logger.info(
                    "[{}] no advertisers found for '{}'",
                    self.channel, keyword,
                )
                return page, []

            logger.info(
                "[{}] '{}' -> {} advertisers found",
                self.channel, keyword, len(advertisers),
            )

            # -- 4) 상위 광고주 페이지 방문 -> 크리에이티브 수집 --
            all_creatives: list[dict] = []

            for adv in advertisers[:MAX_ADVERTISERS]:
                creative_data.clear()
                adv_url = (
                    f"https://adstransparency.google.com/"
                    f"advertiser/{adv['id']}?region=KR"
                )
                try:
                    await page.goto(
                        adv_url, wait_until="domcontentloaded",
                    )
                    await page.wait_for_timeout(ADVERTISER_WAIT_MS)

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

            # -- 5) 정규화 --
            ads = self._normalize_creatives(all_creatives, keyword)
            logger.info(
                "[{}] '{}' -> {} ads (raw: {})",
                self.channel, keyword, len(ads), len(all_creatives),
            )

            # -- 6) preview_url 이미지 다운로드 --
            await self._download_preview_images(ads)

            return page, ads

        except Exception as e:
            logger.error(
                "[{}] transparency center failed: {}",
                self.channel, e,
            )
            return page, []

    async def _fill_search(self, page, keyword: str) -> bool:
        """검색창에 키워드 입력 (type으로 Angular change detection 트리거)."""
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
    def _normalize_creatives(
        creatives: list[dict], keyword: str,
    ) -> list[dict]:
        """크리에이티브를 정규화된 광고 리스트로 변환."""
        ads: list[dict] = []
        seen_ids: set[str] = set()
        view_count_found = 0

        for cr in creatives:
            if len(ads) >= MAX_ADS:
                break

            # VIDEO(3)만 수집 — TEXT(1)=search, IMAGE(2)=GDN은 각 전용 크롤러에서 수집
            fmt_type = cr.get("format_type")
            if fmt_type is not None and fmt_type != 3:
                continue

            cid = cr.get("creative_id") or ""
            if cid in seen_ids:
                continue
            seen_ids.add(cid)

            advertiser = cr.get("advertiser_name")
            adv_id = cr.get("advertiser_id") or cid
            adv_url = None
            if advertiser:
                adv_url = (
                    f"https://adstransparency.google.com/"
                    f"advertiser/{adv_id}?region=KR"
                )

            view_count = cr.get("view_count")
            if view_count is not None:
                view_count_found += 1

            extra_data = {
                "detection_method": "ads_transparency_rpc",
                "creative_id": cid,
                "preview_url": cr.get("preview_url"),
                "image_url": cr.get("image_url"),
                "format_type": cr.get("format_type"),
                "start_ts": cr.get("start_ts"),
                "end_ts": cr.get("end_ts"),
                "search_keyword": keyword,
            }
            # view_count: include only if present (avoids null noise)
            if view_count is not None:
                extra_data["view_count"] = view_count

            # ── 마케팅 플랜 계층 필드 ──
            fmt = str(cr.get("format_type") or "").lower()
            duration_val = cr.get("duration")  # seconds (may be None)
            if "short" in fmt:
                _ad_product_name = "쇼츠 광고"
            elif duration_val is not None and int(duration_val) <= 6:
                _ad_product_name = "범퍼광고"
            elif duration_val is not None and int(duration_val) <= 15 and "non_skippable" in fmt:
                _ad_product_name = "논스킵 인스트림"
            else:
                _ad_product_name = "트루뷰 인스트림"

            if _ad_product_name in ("범퍼광고",):
                _campaign_purpose = "branding"
            elif "masthead" in fmt:
                _campaign_purpose = "branding"
            else:
                _campaign_purpose = "awareness"

            ads.append({
                "advertiser_name": advertiser,
                "ad_text": f"youtube_transparency_{cr.get('format_type', 'ad')}",
                "ad_description": None,
                "url": adv_url,
                "display_url": "adstransparency.google.com",
                "position": len(ads) + 1,
                "ad_type": "youtube_transparency",
                "ad_placement": "google_ads_transparency",
                "ad_product_name": _ad_product_name,
                "ad_format_type": "video",
                "campaign_purpose": _campaign_purpose,
                "extra_data": extra_data,
            })

        if ads:
            logger.info(
                "[youtube_ads] view_count stats: {}/{} ads had view_count data",
                view_count_found, len(ads),
            )

        return ads

    @staticmethod
    def _is_valid_image(data: bytes) -> bool:
        """바이너리 데이터가 실제 이미지인지 매직 바이트로 확인."""
        if len(data) < 8:
            return False
        # PNG
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return True
        # JPEG
        if data[:3] == b"\xff\xd8\xff":
            return True
        # GIF
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return True
        # WebP
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return True
        # BMP
        if data[:2] == b"BM":
            return True
        return False

    async def _download_preview_images(self, ads: list[dict]):
        """광고 이미지를 다운로드하여 creative_image_path에 저장.

        image_url (googlesyndication simgad)을 우선 사용하고,
        없으면 preview_url을 fallback으로 시도한다.
        """
        download_count = 0
        skip_count = 0
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for ad in ads:
                extra = ad.get("extra_data") or {}
                # image_url (실제 이미지) 우선, preview_url fallback
                download_url = extra.get("image_url") or extra.get("preview_url")
                if not download_url:
                    continue
                try:
                    resp = await client.get(download_url)
                    if resp.status_code != 200:
                        continue
                    content_bytes = resp.content
                    if len(content_bytes) < 500:
                        # 너무 작은 응답은 유효 이미지가 아님
                        continue

                    # content-type 검증
                    ct = resp.headers.get("content-type", "")
                    is_image_ct = any(
                        t in ct for t in ("image/", "application/octet-stream")
                    )

                    # 매직 바이트 검증 (content-type이 부정확할 수 있으므로 이중 확인)
                    is_valid = self._is_valid_image(content_bytes)

                    if not is_valid:
                        # JS/HTML/text 등 이미지가 아닌 응답 skip
                        skip_count += 1
                        logger.debug(
                            "[{}] preview not image (ct={}, size={}): {}",
                            self.channel, ct[:40],
                            len(content_bytes),
                            download_url[:60] if download_url else "?",
                        )
                        continue

                    # 임시 파일로 저장 후 image_store에 위임
                    screenshot_dir = (
                        Path(self.settings.screenshot_dir)
                        / self.channel
                        / datetime.now(timezone.utc).strftime("%Y%m%d")
                    )
                    screenshot_dir.mkdir(parents=True, exist_ok=True)

                    cid = (ad.get("extra_data") or {}).get("creative_id", "unknown")
                    timestamp = datetime.now(timezone.utc).strftime("%H%M%S")
                    # 확장자: 매직 바이트 기반 결정
                    ext = ".png"
                    if content_bytes[:3] == b"\xff\xd8\xff":
                        ext = ".jpg"
                    elif (
                        content_bytes[:4] == b"RIFF"
                        and content_bytes[8:12] == b"WEBP"
                    ):
                        ext = ".webp"
                    elif content_bytes[:6] in (b"GIF87a", b"GIF89a"):
                        ext = ".gif"

                    filename = f"yt_preview_{cid[:20]}_{timestamp}{ext}"
                    filepath = screenshot_dir / filename
                    filepath.write_bytes(content_bytes)

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
                        "[{}] preview download failed for {}: {}",
                        self.channel,
                        download_url[:60] if download_url else "?",
                        exc,
                    )
                    # 조용히 skip -- creative_image_path = None

        if download_count or skip_count:
            logger.info(
                "[{}] preview images: {} saved, {} skipped (not image), {} total",
                self.channel, download_count, skip_count, len(ads),
            )
