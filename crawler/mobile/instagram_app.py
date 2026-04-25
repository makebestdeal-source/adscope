"""Instagram 앱 광고 수집 — ADB + mitmproxy 기반.

Instagram 앱(com.instagram.android)에서 피드 스크롤 중
네트워크 인터셉트로 Sponsored 광고 API 응답을 수집.

수집 흐름:
  1. ADB로 Instagram 앱 실행 (로그인 상태 유지됨)
  2. Wi-Fi 프록시 → PC의 mitmproxy
  3. 홈 피드 스크롤 → Sponsored 포스트 API 응답 캡처
  4. Reels 탭 스와이프 → 추가 광고 수집
  5. 프록시 해제, 앱 종료
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from crawler.mobile.adb_client import ADBClient
from crawler.mobile.mitmproxy_capture import AppAdCapturer


class InstagramAppCrawler:
    """Instagram 앱 광고 수집기 (ADB + mitmproxy)."""

    PACKAGE = "com.instagram.android"
    CHANNEL = "mobile_instagram"

    # Instagram 앱 내 탭 (상대 좌표)
    TABS = {
        "홈": (0.1, 0.95),
        "검색": (0.3, 0.95),
        "릴스": (0.5, 0.95),
        "숍": (0.7, 0.95),
    }

    def __init__(
        self,
        proxy_port: int = 8080,
        device_serial: Optional[str] = None,
        scroll_count: int = 25,
    ):
        self.proxy_port = proxy_port
        self.adb = ADBClient(serial=device_serial)
        self.scroll_count = scroll_count
        self._capturer = AppAdCapturer(
            app_name="instagram",
            proxy_port=proxy_port,
            device_serial=device_serial,
            scroll_count=scroll_count,
        )

    async def crawl(self, duration_sec: int = 90) -> dict:
        """Instagram 앱에서 광고 수집."""
        start = datetime.now(timezone.utc)

        if not self.adb.is_connected():
            logger.warning(f"[{self.CHANNEL}] ADB 디바이스 없음 — 스킵")
            return self._empty_result(start)

        # 홈 피드 스크롤 (primary)
        ads = await self._capturer.capture(duration_sec=duration_sec)

        # Reels 탭 추가 수집
        try:
            await self._explore_reels()
            reels_ads = await self._capturer.capture(duration_sec=30)
            existing = {(a.get("url", ""), a.get("advertiser_name", "")) for a in ads}
            for ad in reels_ads:
                sig = (ad.get("url", ""), ad.get("advertiser_name", ""))
                if sig not in existing:
                    ads.append(ad)
                    existing.add(sig)
        except Exception as exc:
            logger.debug(f"[{self.CHANNEL}] Reels 탐색 실패: {exc}")

        elapsed = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        logger.info(f"[{self.CHANNEL}] 수집 완료: {len(ads)}건 ({elapsed}ms)")

        return {
            "keyword": "surf",
            "persona_code": "mobile",
            "device": "android",
            "channel": self.CHANNEL,
            "captured_at": start,
            "page_url": "instagram_app",
            "screenshot_path": None,
            "ads": ads,
            "crawl_duration_ms": elapsed,
        }

    async def _explore_reels(self):
        """Reels 탭으로 이동하여 세로 스와이프로 추가 광고 트리거."""
        # Reels 탭 탭
        reels_x, reels_y = self.TABS["릴스"]
        self.adb.tap_rel(reels_x, reels_y)
        time.sleep(2.5)

        # 세로 스와이프 (릴 넘기기)
        for i in range(10):
            self.adb.swipe_up(distance_ratio=0.8, duration_ms=300)
            time.sleep(2.0 + (i % 3) * 0.5)

        logger.debug(f"[{self.CHANNEL}] Reels 탭 탐색 완료")

    def _empty_result(self, start: datetime) -> dict:
        return {
            "keyword": "surf",
            "persona_code": "mobile",
            "device": "android",
            "channel": self.CHANNEL,
            "captured_at": start,
            "page_url": "instagram_app",
            "screenshot_path": None,
            "ads": [],
            "crawl_duration_ms": 0,
        }


async def run(
    proxy_port: int = 8080,
    device_serial: Optional[str] = None,
    duration_sec: int = 90,
) -> dict:
    """외부 호출용."""
    crawler = InstagramAppCrawler(proxy_port=proxy_port, device_serial=device_serial)
    return await crawler.crawl(duration_sec=duration_sec)


if __name__ == "__main__":
    import json
    result = asyncio.run(run())
    print(f"수집: {len(result['ads'])}건")
    for ad in result["ads"][:3]:
        print(f"  {ad.get('advertiser_name')} | {ad.get('url')}")
