"""Naver 앱 광고 수집 — ADB + mitmproxy 기반.

Naver 앱(com.nhn.android.search)에서 네트워크 인터셉트로
GFP(Guest Feed Proxy) 광고 API 응답을 수집.

수집 흐름:
  1. ADB로 Naver 앱 실행
  2. Wi-Fi 프록시 → PC의 mitmproxy (8080)
  3. 앱 홈 → 뉴스/스포츠 탭 탐색 + 스크롤
  4. GFP JSON 응답 캡처 → 광고 파싱
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


class NaverAppCrawler:
    """Naver 앱 광고 수집기 (ADB + mitmproxy)."""

    PACKAGE = "com.nhn.android.search"
    CHANNEL = "mobile_naver"

    # Naver 앱 내 탭 좌표 (Galaxy S21 기준, 상대 좌표)
    # 실제 기기에 따라 달라질 수 있음 → tap_rel() 사용
    TABS = {
        "홈": (0.1, 0.95),
        "뉴스": (0.3, 0.95),
        "스포츠": (0.5, 0.95),
        "쇼핑": (0.7, 0.95),
    }

    def __init__(
        self,
        proxy_port: int = 8080,
        device_serial: Optional[str] = None,
        scroll_count: int = 20,
    ):
        self.proxy_port = proxy_port
        self.adb = ADBClient(serial=device_serial)
        self.scroll_count = scroll_count
        self._capturer = AppAdCapturer(
            app_name="naver",
            proxy_port=proxy_port,
            device_serial=device_serial,
            scroll_count=scroll_count,
        )

    async def crawl(self, duration_sec: int = 90) -> dict:
        """Naver 앱에서 광고 수집 후 표준 형식으로 반환."""
        start = datetime.now(timezone.utc)

        if not self.adb.is_connected():
            logger.warning(f"[{self.CHANNEL}] ADB 디바이스 없음 — 스킵")
            return self._empty_result(start)

        # mitmproxy 기반 캡처 실행
        ads = await self._capturer.capture(duration_sec=duration_sec)

        # Naver 앱 전용 후처리: 탭별 추가 수집
        try:
            await self._navigate_tabs()
            # 탭 탐색 후 추가 캡처
            extra_ads = await self._capturer.capture(duration_sec=30)
            # 중복 제거 후 병합
            existing_sigs = {(a.get("url", ""), a.get("advertiser_name", "")) for a in ads}
            for ad in extra_ads:
                sig = (ad.get("url", ""), ad.get("advertiser_name", ""))
                if sig not in existing_sigs:
                    ads.append(ad)
                    existing_sigs.add(sig)
        except Exception as exc:
            logger.debug(f"[{self.CHANNEL}] 탭 탐색 실패: {exc}")

        elapsed = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        logger.info(f"[{self.CHANNEL}] 수집 완료: {len(ads)}건 ({elapsed}ms)")

        return {
            "keyword": "surf",
            "persona_code": "mobile",
            "device": "android",
            "channel": self.CHANNEL,
            "captured_at": start,
            "page_url": "naver_app",
            "screenshot_path": None,
            "ads": ads,
            "crawl_duration_ms": elapsed,
        }

    async def _navigate_tabs(self):
        """Naver 앱 주요 탭 탐색으로 추가 GFP 광고 트리거."""
        for tab_name, (rx, ry) in self.TABS.items():
            try:
                self.adb.tap_rel(rx, ry)
                time.sleep(2.0)
                # 탭 내 스크롤 5회
                for _ in range(5):
                    self.adb.swipe_up(distance_ratio=0.3, duration_ms=400)
                    time.sleep(1.5)
                logger.debug(f"[{self.CHANNEL}] {tab_name} 탭 탐색")
            except Exception as exc:
                logger.debug(f"[{self.CHANNEL}] {tab_name} 탭 실패: {exc}")

    def _empty_result(self, start: datetime) -> dict:
        return {
            "keyword": "surf",
            "persona_code": "mobile",
            "device": "android",
            "channel": self.CHANNEL,
            "captured_at": start,
            "page_url": "naver_app",
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
    crawler = NaverAppCrawler(proxy_port=proxy_port, device_serial=device_serial)
    return await crawler.crawl(duration_sec=duration_sec)


if __name__ == "__main__":
    import json
    result = asyncio.run(run())
    print(f"수집: {len(result['ads'])}건")
    for ad in result["ads"][:3]:
        print(f"  {ad.get('advertiser_name')} | {ad.get('url')}")
