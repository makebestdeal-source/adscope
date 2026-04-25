"""mitmproxy 기반 Android 앱 광고 네트워크 인터셉트.

동작 방식:
  1. PC에서 mitmproxy를 포트 8080으로 시작
  2. ADB로 Android 폰의 Wi-Fi 프록시를 PC로 설정
  3. 앱 실행 + ADB 스크롤 자동화로 광고 트래픽 유도
  4. mitmproxy가 광고 API 응답을 실시간 캡처
  5. 캡처된 JSON에서 광고 데이터 추출

사전 요구사항:
  - mitmproxy: pip install mitmproxy
  - Android 디바이스 ADB 연결 (developer options + USB debugging)
  - 디바이스에 mitmproxy CA 인증서 설치 (HTTPS 캡처용)
    → adb push ~/.mitmproxy/mitmproxy-ca-cert.pem /sdcard/
    → 디바이스 설정 > 보안 > 인증서 설치

실행:
  python -m crawler.mobile.mitmproxy_capture --app naver --persona M30
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from loguru import logger

from crawler.mobile.adb_client import ADBClient

# ── 광고 API 호스트 필터 (앱별 주요 광고 엔드포인트) ──

_AD_HOST_PATTERNS: dict[str, list[str]] = {
    "naver": [
        "nam.veta.naver.com",
        "siape.veta.naver.com",
        "gfp.naver.com",
        "ade.naver.com",
    ],
    "instagram": [
        "i.instagram.com/api/v1/feed",
        "graph.instagram.com",
        "graph.facebook.com",
    ],
    "kakao": [
        "display.ad.daum.net/sdk",
        "track.kakao.com",
        "adfit.kakao.com",
    ],
    "youtube": [
        "youtubei/v1/player",
        "googlevideo.com",
        "doubleclick.net",
    ],
}

# 모든 앱 공통 광고 호스트
_COMMON_AD_PATTERNS = [
    "doubleclick.net",
    "googleadservices.com",
    "googlesyndication.com",
    "mobon.net",
    "dable.io",
    "taboola.com",
    "criteo.com",
]


class MitmproxyAddon:
    """mitmproxy addon — 광고 응답을 큐에 수집."""

    def __init__(self, result_queue: queue.Queue, app_name: str):
        self.q = result_queue
        self.patterns = (
            _AD_HOST_PATTERNS.get(app_name, []) + _COMMON_AD_PATTERNS
        )

    def response(self, flow):
        """mitmproxy가 각 응답에 대해 호출."""
        url = flow.request.pretty_url
        if not any(p in url for p in self.patterns):
            return
        try:
            ct = flow.response.headers.get("content-type", "")
            if "json" not in ct:
                return
            body = flow.response.get_text()
            data = json.loads(body)
            self.q.put({
                "url": url,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass


class AppAdCapturer:
    """ADB + mitmproxy로 실제 Android 앱 광고를 수집."""

    # 앱별 패키지명
    APP_PACKAGES = {
        "naver": "com.nhn.android.search",
        "instagram": "com.instagram.android",
        "kakao": "com.kakao.talk",
        "youtube": "com.google.android.youtube",
    }

    # 앱별 스크롤 횟수 (광고 로드 유도)
    APP_SCROLL_COUNT = {
        "naver": 15,
        "instagram": 20,
        "kakao": 12,
        "youtube": 10,
    }

    def __init__(
        self,
        app_name: str,
        proxy_port: int = 8080,
        device_serial: Optional[str] = None,
        scroll_count: Optional[int] = None,
    ):
        self.app_name = app_name.lower()
        self.proxy_port = proxy_port
        self.adb = ADBClient(serial=device_serial)
        self.scroll_count = scroll_count or self.APP_SCROLL_COUNT.get(self.app_name, 15)
        self._result_queue: queue.Queue = queue.Queue()
        self._proxy_thread: Optional[threading.Thread] = None
        self._proxy_proc = None

    def _get_local_ip(self) -> str:
        """PC의 Wi-Fi IP 주소 반환 (Android 프록시 설정용)."""
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "192.168.1.100"  # fallback

    def _start_mitmproxy(self) -> bool:
        """mitmproxy를 백그라운드 스레드에서 시작."""
        try:
            from mitmproxy.tools.dump import DumpMaster
            from mitmproxy import options

            addon = MitmproxyAddon(self._result_queue, self.app_name)

            def _run():
                import asyncio as _asyncio
                loop = _asyncio.new_event_loop()
                _asyncio.set_event_loop(loop)

                opts = options.Options(listen_host="0.0.0.0", listen_port=self.proxy_port)
                m = DumpMaster(opts, with_termlog=False, with_dumper=False)
                m.addons.add(addon)
                try:
                    loop.run_until_complete(m.run())
                except Exception:
                    pass
                finally:
                    loop.close()

            self._proxy_thread = threading.Thread(target=_run, daemon=True)
            self._proxy_thread.start()
            time.sleep(2.0)  # mitmproxy 시작 대기
            logger.info(f"[mitmproxy] 포트 {self.proxy_port} 시작")
            return True

        except ImportError:
            logger.error("[mitmproxy] 미설치 — pip install mitmproxy")
            return False
        except Exception as exc:
            logger.error(f"[mitmproxy] 시작 실패: {exc}")
            return False

    async def capture(self, duration_sec: int = 60) -> list[dict]:
        """앱 실행 + 스크롤 + 광고 캡처 실행.

        Args:
            duration_sec: 총 수집 시간(초)

        Returns:
            수집된 광고 리스트 (정규화됨)
        """
        if not self.adb.is_connected():
            logger.error("[ADB] 디바이스 연결 없음")
            return []

        local_ip = self._get_local_ip()

        # 1) mitmproxy 시작
        if not self._start_mitmproxy():
            return []

        # 2) Android 프록시 설정
        try:
            self.adb.set_wifi_proxy(local_ip, self.proxy_port)
            logger.info(f"[ADB] Wi-Fi 프록시 설정: {local_ip}:{self.proxy_port}")
        except Exception as exc:
            logger.error(f"[ADB] 프록시 설정 실패: {exc}")
            return []

        pkg = self.APP_PACKAGES.get(self.app_name)
        if not pkg:
            logger.error(f"[ADB] 미지원 앱: {self.app_name}")
            return []

        try:
            # 3) 앱 실행
            self.adb.force_stop(pkg)
            time.sleep(1)
            self.adb.launch_app(pkg)
            logger.info(f"[ADB] {self.app_name}({pkg}) 실행")
            time.sleep(3)  # 앱 로딩 대기

            # 4) 스크롤로 피드 광고 유도
            scroll_interval = max(2.0, duration_sec / self.scroll_count)
            for i in range(self.scroll_count):
                self.adb.swipe_up(distance_ratio=0.35, duration_ms=500)
                time.sleep(scroll_interval)

                # 중간에 스크린샷 (선택적)
                if i % 5 == 0:
                    logger.debug(f"[ADB] 스크롤 {i+1}/{self.scroll_count}")

        finally:
            # 5) 프록시 해제 + 앱 종료
            try:
                self.adb.clear_wifi_proxy()
                self.adb.force_stop(pkg)
            except Exception:
                pass

        # 6) 수집된 응답 파싱
        captures = []
        while not self._result_queue.empty():
            try:
                captures.append(self._result_queue.get_nowait())
            except queue.Empty:
                break

        logger.info(f"[mitmproxy] {self.app_name} 캡처 {len(captures)}건")
        return self._parse_captures(captures)

    def _parse_captures(self, captures: list[dict]) -> list[dict]:
        """캡처된 API 응답에서 광고 데이터 정규화."""
        ads: list[dict] = []
        seen: set[str] = set()

        for cap in captures:
            url = cap.get("url", "")
            data = cap.get("data", {})

            if not isinstance(data, dict):
                continue

            parsed = []
            if self.app_name == "naver":
                parsed = self._parse_naver_gfp(data, url)
            elif self.app_name == "instagram":
                parsed = self._parse_instagram_feed(data)
            elif self.app_name == "kakao":
                parsed = self._parse_kakao_sdk(data, url)
            else:
                parsed = self._parse_generic(data, url)

            for ad in parsed:
                sig = f"{ad.get('url', '')}|{ad.get('advertiser_name', '')}"
                if sig in seen:
                    continue
                seen.add(sig)
                ad["channel"] = f"mobile_{self.app_name}"
                ad["captured_at"] = cap.get("timestamp")
                ads.append(ad)

        return ads

    def _parse_naver_gfp(self, data: dict, url: str) -> list[dict]:
        """Naver GFP JSON 파싱 (naver_da.py의 _parse_gfp_json와 동일 로직)."""
        ads = []
        for ad_item in data.get("ads", []):
            info = ad_item.get("adInfo", {})
            native = info.get("nativeData", {})
            if native:
                adomain = info.get("adomain", [])
                domain = adomain[0].removeprefix("www.") if adomain else None
                sponsor = native.get("sponsor", {})
                advertiser = sponsor.get("text") if isinstance(sponsor, dict) else domain
                link = native.get("link", {})
                click_url = link.get("curl") if isinstance(link, dict) else None
                media = native.get("media", {})
                image_url = media.get("src") if isinstance(media, dict) else None
                if advertiser or click_url:
                    ads.append({
                        "advertiser_name": advertiser,
                        "url": click_url,
                        "ad_text": advertiser or "naver_app_ad",
                        "extra_data": {"image_url": image_url, "detection_method": "mitmproxy_gfp"},
                    })
        return ads

    def _parse_instagram_feed(self, data: dict) -> list[dict]:
        """Instagram 피드 API 파싱 (meta_feed_surf.py와 동일 로직)."""
        ads = []
        items = data.get("items", data.get("feed_items", []))
        for item in items:
            if not isinstance(item, dict):
                continue
            if not (item.get("ad_id") or item.get("is_ad") or item.get("injected")):
                continue
            user = item.get("user", {})
            advertiser = user.get("full_name") or user.get("username")
            caption = item.get("caption", {})
            ad_text = caption.get("text", "")[:200] if isinstance(caption, dict) else ""
            link = item.get("link") or item.get("ad_link_url") or ""
            images = item.get("image_versions2", {}).get("candidates", [])
            image_url = images[0].get("url") if images else None
            if advertiser or link:
                ads.append({
                    "advertiser_name": advertiser,
                    "url": link,
                    "ad_text": ad_text or advertiser or "ig_app_ad",
                    "extra_data": {"image_url": image_url, "detection_method": "mitmproxy_ig_feed"},
                })
        return ads

    def _parse_kakao_sdk(self, data: dict, url: str) -> list[dict]:
        """Kakao SDK JSON 파싱 (kakao_da.py와 동일 로직)."""
        ads = []
        if data.get("status") != "OK":
            return ads
        for ad_item in data.get("ads", []):
            title = ad_item.get("title", "")
            profile = ad_item.get("profileName", "")
            landing = ad_item.get("landingUrl", "")
            main_img = ad_item.get("mainImage")
            image_url = main_img.get("url") if isinstance(main_img, dict) else None
            if profile or landing:
                ads.append({
                    "advertiser_name": profile or None,
                    "url": landing,
                    "ad_text": title or profile or "kakao_app_ad",
                    "extra_data": {"image_url": image_url, "detection_method": "mitmproxy_kakao_sdk"},
                })
        return ads

    def _parse_generic(self, data: dict, url: str) -> list[dict]:
        """범용 광고 JSON 파싱 (알려지지 않은 형식)."""
        host = urlparse(url).netloc
        return [{
            "advertiser_name": None,
            "url": None,
            "ad_text": f"app_ad_{host}",
            "extra_data": {"raw_url": url, "detection_method": "mitmproxy_generic"},
        }]


async def run_capture(
    app_name: str,
    duration_sec: int = 60,
    proxy_port: int = 8080,
    device_serial: Optional[str] = None,
) -> list[dict]:
    """외부에서 호출 가능한 단일 함수 인터페이스."""
    capturer = AppAdCapturer(
        app_name=app_name,
        proxy_port=proxy_port,
        device_serial=device_serial,
    )
    return await capturer.capture(duration_sec=duration_sec)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ADB + mitmproxy 광고 수집")
    parser.add_argument("--app", default="instagram", choices=list(AppAdCapturer.APP_PACKAGES.keys()))
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--serial", default=None)
    args = parser.parse_args()

    ads = asyncio.run(run_capture(args.app, args.duration, args.port, args.serial))
    print(f"\n수집 결과: {len(ads)}건")
    for ad in ads[:5]:
        print(f"  - {ad.get('advertiser_name')} | {ad.get('url')}")
