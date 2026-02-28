"""구글 검색광고 크롤러 -- Google Ads Transparency Center TEXT format.

youtube_ads.py와 동일한 Transparency Center RPC를 사용하되
platform=GOOGLE_SEARCH 필터로 텍스트(검색) 광고만 수집.

- 로그인 불필요, headless OK
- SearchSuggestions RPC -> 광고주 ID 목록
- SearchCreatives RPC -> 광고주별 크리에이티브 (TEXT)
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from playwright.async_api import Response

from crawler.base_crawler import BaseCrawler
from crawler.personas.device_config import DeviceConfig
from crawler.personas.profiles import PersonaProfile

# youtube_ads.py 파서 재사용
from crawler.youtube_ads import (
    _parse_suggestions,
    _parse_creatives,
    MAX_ADVERTISERS,
    MAX_ADS,
    ADVERTISER_WAIT_MS,
)

# ── 설정 ──
ADS_TRANSPARENCY_URL = (
    "https://adstransparency.google.com/"
    "?region=KR&format=TEXT"
)

# 구글 검색광고 전용 설정
GS_MAX_ADVERTISERS = max(1, int(os.getenv("GS_ADS_MAX_ADVERTISERS", "10")))
GS_MAX_ADS = max(1, int(os.getenv("GS_ADS_MAX_ADS", "40")))


class GoogleSearchAdsCrawler(BaseCrawler):
    """Google Ads Transparency Center TEXT format -- 구글 검색광고 수집."""

    channel = "google_search_ads"

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

            # 1) 메인 페이지 접속 (TEXT format 필터)
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

            for adv in advertisers[:GS_MAX_ADVERTISERS]:
                creative_data.clear()
                adv_url = (
                    f"https://adstransparency.google.com/"
                    f"advertiser/{adv['id']}?region=KR&format=TEXT"
                )
                try:
                    await page.goto(adv_url, wait_until="domcontentloaded")
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

            # 5) 정규화
            ads = self._normalize_creatives(all_creatives, keyword)
            logger.info(
                "[{}] '{}' -> {} ads (raw: {})",
                self.channel, keyword, len(ads), len(all_creatives),
            )

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
            if len(ads) >= GS_MAX_ADS:
                break

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

            extra_data = {
                "detection_method": "ads_transparency_rpc",
                "creative_id": cid,
                "format_type": cr.get("format_type"),
                "start_ts": cr.get("start_ts"),
                "end_ts": cr.get("end_ts"),
                "search_keyword": keyword,
                "platform": "google_search",
            }

            ads.append({
                "advertiser_name": advertiser,
                "ad_text": f"google_search_{cr.get('format_type', 'text')}",
                "ad_description": None,
                "url": adv_url,
                "display_url": "adstransparency.google.com",
                "position": len(ads) + 1,
                "ad_type": "google_search_text",
                "ad_placement": "google_search",
                "ad_product_name": "구글 검색광고",
                "ad_format_type": "text",
                "campaign_purpose": "performance",
                "extra_data": extra_data,
            })

        return ads
