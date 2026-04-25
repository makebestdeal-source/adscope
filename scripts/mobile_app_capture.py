"""모바일 앱 광고 수집 — mitmproxy 네트워크 캡처 + ADB 앱 제어.

ADB로 앱을 구동/서핑하고, mitmproxy로 네트워크 트래픽을 캡처하여
Playwright 웹 크롤러와 동일한 방식으로 광고를 파싱합니다.

Usage:
    python scripts/mobile_app_capture.py --app naver
    python scripts/mobile_app_capture.py --app instagram
    python scripts/mobile_app_capture.py --app naver --no-proxy  # 프록시 없이 ADB만
    python scripts/mobile_app_capture.py --setup-cert           # CA 인증서 설치 안내

흐름:
  1. mitmproxy 시작 (백그라운드, 8080 포트)
  2. ADB로 폰 WiFi 프록시 설정 → PC:8080
  3. ADB로 앱 실행 + 자동 서핑 (스크롤/탭 네비게이션)
  4. mitmproxy가 캡처한 광고 서버 응답 파싱
  5. 광고 데이터 → DB 저장
  6. 프록시 해제
"""

import argparse
import asyncio
import json
import subprocess
import sys
import threading
import time
from datetime import datetime, UTC
from pathlib import Path
from collections import defaultdict

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawler.mobile.adb_client import ADBClient

# ── 광고 서버 URL 패턴 (Playwright 크롤러와 동일) ──

AD_URL_PATTERNS = {
    "naver": [
        "nam.veta.naver.com/gfp",
        "siape.veta.naver.com",
        "gfp.naver.com",
        "ade.naver.com",
    ],
    "kakao": [
        "display.ad.daum.net/sdk/",
        "ad.daum.net",
        "kakaoad.com",
    ],
    "instagram": [
        "i.instagram.com/api/v1/feed",
        "graph.instagram.com",
        "graph.facebook.com",
    ],
    "facebook": [
        "graph.facebook.com",
        "www.facebook.com/api/graphql",
    ],
}

APP_PACKAGES = {
    "naver": "com.nhn.android.search",
    "instagram": "com.instagram.android",
    "kakao": "com.kakao.talk",
    "facebook": "com.facebook.katana",
    "youtube": "com.google.android.youtube",
}

PROXY_PORT = 8080
CAPTURE_DIR = Path("mobile_captures")
DB_PATH = Path("adscope.db")


class AdResponseCapture:
    """mitmproxy addon — 광고 서버 응답을 캡처합니다."""

    def __init__(self, app: str):
        self.app = app
        self.patterns = []
        for app_key, urls in AD_URL_PATTERNS.items():
            self.patterns.extend(urls)
        self.captured: list[dict] = []
        self.lock = threading.Lock()

    def response(self, flow):
        """mitmproxy response hook — 광고 URL 매칭 시 캡처."""
        url = flow.request.url
        if not any(p in url for p in self.patterns):
            return

        try:
            content_type = flow.response.headers.get("content-type", "")
            if "json" not in content_type and "javascript" not in content_type:
                return

            body = flow.response.get_text()
            if not body or len(body) < 50:
                return

            with self.lock:
                self.captured.append({
                    "url": url,
                    "status": flow.response.status_code,
                    "content_type": content_type,
                    "body": body[:50000],  # 50KB 제한
                    "timestamp": datetime.now(UTC).isoformat(),
                })
                logger.info(f"[capture] AD response: {url[:80]}... ({len(body)} bytes)")
        except Exception as e:
            logger.debug(f"[capture] parse error: {e}")


def start_mitmproxy(addon: AdResponseCapture, port: int = PROXY_PORT):
    """mitmproxy를 별도 스레드에서 실행."""
    from mitmproxy.options import Options
    from mitmproxy.tools.dump import DumpMaster

    async def _run():
        opts = Options(listen_port=port, ssl_insecure=True)
        master = DumpMaster(opts)
        master.addons.add(addon)
        logger.info(f"[mitmproxy] Starting on port {port}...")
        await master.run()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_run())


def setup_phone_proxy(adb: ADBClient, pc_ip: str, port: int):
    """폰 WiFi 프록시를 PC의 mitmproxy로 설정."""
    adb.set_wifi_proxy(pc_ip, port)
    logger.info(f"[proxy] Phone proxy set to {pc_ip}:{port}")


def clear_phone_proxy(adb: ADBClient):
    """폰 WiFi 프록시 해제."""
    adb.clear_wifi_proxy()
    logger.info("[proxy] Phone proxy cleared")


def navigate_naver(adb: ADBClient, scrolls: int = 8):
    """네이버 앱 서핑 — 홈 → 피드 스크롤."""
    pkg = APP_PACKAGES["naver"]
    adb.force_stop(pkg)
    time.sleep(1)
    adb.launch_app(pkg)
    time.sleep(4)

    # 홈 탭 (하단 네비 2번째)
    w, h = adb.screen_size()
    adb.tap(int(w * 0.28), int(h * 0.94))
    time.sleep(3)

    logger.info(f"[naver] Scrolling feed ({scrolls} times)...")
    for i in range(scrolls):
        adb.swipe_up(distance_ratio=0.38)
        time.sleep(2.5 + (i % 3) * 0.5)  # 랜덤 딜레이

    adb.press_home()


def navigate_instagram(adb: ADBClient, scrolls: int = 10):
    """인스타그램 앱 서핑 — 홈 피드 스크롤."""
    pkg = APP_PACKAGES["instagram"]
    adb.force_stop(pkg)
    time.sleep(1)
    adb.launch_app(pkg)
    time.sleep(5)

    # 홈 탭 (하단 첫번째 아이콘)
    w, h = adb.screen_size()
    adb.tap(int(w * 0.10), int(h * 0.96))
    time.sleep(3)

    logger.info(f"[instagram] Scrolling feed ({scrolls} times)...")
    for i in range(scrolls):
        adb.swipe_up(distance_ratio=0.42)
        time.sleep(2.0 + (i % 4) * 0.5)

    adb.press_home()


def navigate_kakao(adb: ADBClient, scrolls: int = 5):
    """카카오톡 — 홈 탭 스크롤 (비즈보드 광고)."""
    pkg = APP_PACKAGES["kakao"]
    adb.force_stop(pkg)
    time.sleep(1)
    adb.launch_app(pkg)
    time.sleep(4)

    w, h = adb.screen_size()
    # 카카오톡 채팅 탭 상단에 비즈보드 존재
    logger.info(f"[kakao] Browsing chat tab for bizboard ads...")
    for i in range(scrolls):
        adb.swipe_up(distance_ratio=0.3)
        time.sleep(2.0)
    # 더보기 탭 → 쇼핑 영역
    adb.tap(int(w * 0.90), int(h * 0.96))
    time.sleep(3)
    for i in range(3):
        adb.swipe_up(distance_ratio=0.3)
        time.sleep(2.0)

    adb.press_home()


APP_NAVIGATORS = {
    "naver": navigate_naver,
    "instagram": navigate_instagram,
    "kakao": navigate_kakao,
}


# ── 광고 파싱 (Playwright 크롤러 로직 재사용) ──

def parse_naver_ads(captures: list[dict]) -> list[dict]:
    """네이버 GFP JSON 응답에서 광고 추출."""
    ads = []
    for cap in captures:
        if not any(p in cap["url"] for p in AD_URL_PATTERNS["naver"]):
            continue
        try:
            data = json.loads(cap["body"])
            # GFP v1/v2 format
            for ad_list_key in ("ads", "adUnits", "response"):
                items = data.get(ad_list_key, [])
                if not isinstance(items, list):
                    continue
                for item in items:
                    ad = _extract_naver_ad(item)
                    if ad:
                        ads.append(ad)
        except json.JSONDecodeError:
            continue
    return ads


def _extract_naver_ad(item: dict, depth: int = 0) -> dict | None:
    """네이버 GFP 광고 항목에서 광고주/URL 추출 (재귀)."""
    if depth > 5 or not isinstance(item, dict):
        return None

    ad_info = item.get("adInfo", item.get("adinfo", item))
    if not isinstance(ad_info, dict):
        return None

    native = ad_info.get("nativeData", ad_info.get("native", {}))
    if isinstance(native, dict):
        sponsor = native.get("sponsor", {})
        link = native.get("link", {})
        desc = native.get("desc", {})

        advertiser = sponsor.get("text") if isinstance(sponsor, dict) else None
        click_url = link.get("curl") or link.get("url") if isinstance(link, dict) else None
        ad_text = desc.get("text") if isinstance(desc, dict) else None

        if advertiser or click_url:
            return {
                "advertiser_name": advertiser,
                "ad_text": ad_text or advertiser or "",
                "url": click_url,
                "ad_type": "app_da",
                "ad_placement": "naver_app",
                "source": "mitmproxy_gfp",
            }

    # 재귀 탐색
    for v in item.values():
        if isinstance(v, dict):
            result = _extract_naver_ad(v, depth + 1)
            if result:
                return result
        elif isinstance(v, list):
            for sub in v:
                result = _extract_naver_ad(sub, depth + 1)
                if result:
                    return result
    return None


def parse_instagram_ads(captures: list[dict]) -> list[dict]:
    """인스타그램 피드 API 응답에서 광고 추출."""
    ads = []
    for cap in captures:
        if not any(p in cap["url"] for p in AD_URL_PATTERNS["instagram"]):
            continue
        try:
            data = json.loads(cap["body"])
            items = data.get("items", data.get("feed_items", []))
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                if not (item.get("ad_id") or item.get("is_ad") or
                        item.get("injected") or item.get("ad_action")):
                    continue

                user = item.get("user", {})
                advertiser = user.get("full_name") or user.get("username")
                caption = item.get("caption", {})
                ad_text = caption.get("text", "")[:200] if isinstance(caption, dict) else ""
                link = item.get("link") or item.get("ad_link_url") or ""

                if advertiser or link:
                    ads.append({
                        "advertiser_name": advertiser,
                        "ad_text": ad_text or advertiser or "",
                        "url": link,
                        "ad_type": "app_feed",
                        "ad_placement": "instagram_app",
                        "source": "mitmproxy_ig_feed",
                    })
        except json.JSONDecodeError:
            continue
    return ads


def parse_kakao_ads(captures: list[dict]) -> list[dict]:
    """카카오 SDK 응답에서 광고 추출."""
    ads = []
    for cap in captures:
        if not any(p in cap["url"] for p in AD_URL_PATTERNS["kakao"]):
            continue
        try:
            data = json.loads(cap["body"])
            if data.get("status") != "OK":
                continue
            items = data.get("ads", [])
            for item in items:
                if not isinstance(item, dict):
                    continue
                advertiser = item.get("profileName") or item.get("title")
                link = item.get("landingUrl") or item.get("click_url") or ""

                if advertiser or link:
                    ads.append({
                        "advertiser_name": advertiser,
                        "ad_text": item.get("title") or advertiser or "",
                        "url": link,
                        "ad_type": "app_bizboard",
                        "ad_placement": "kakao_app",
                        "source": "mitmproxy_sdk",
                    })
        except json.JSONDecodeError:
            continue
    return ads


APP_PARSERS = {
    "naver": parse_naver_ads,
    "instagram": parse_instagram_ads,
    "kakao": parse_kakao_ads,
}


# ── DB 저장 ──

async def save_to_db(device_id: str, app: str, ads: list[dict]):
    """수집된 광고를 mobile_panel_exposures에 저장."""
    import aiosqlite
    now = datetime.now(UTC).isoformat()
    channel_map = {"naver": "naver_da", "instagram": "meta", "kakao": "kakao_da"}
    channel = channel_map.get(app, "mobile_da")

    rows = []
    for ad in ads:
        rows.append((
            device_id, app, channel,
            (ad.get("advertiser_name") or "")[:200],
            (ad.get("ad_text") or "")[:500],
            ad.get("ad_type", "app_ad"),
            (ad.get("url") or "")[:1000],
            now,
            json.dumps({"source": ad.get("source", ""), "placement": ad.get("ad_placement", "")}),
        ))

    if not rows:
        return 0

    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.executemany("""
            INSERT INTO mobile_panel_exposures
              (device_id, app_name, channel, advertiser_name_raw, ad_text,
               ad_type, creative_url, observed_at, extra_data)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, rows)
        await db.commit()
    return len(rows)


# ── 메인 ──

def get_pc_ip() -> str:
    """PC의 로컬 IP 주소 추출."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def main():
    parser = argparse.ArgumentParser(description="모바일 앱 광고 수집 (mitmproxy)")
    parser.add_argument("--app", default="naver", choices=["naver", "instagram", "kakao"])
    parser.add_argument("--scrolls", type=int, default=8)
    parser.add_argument("--no-proxy", action="store_true", help="프록시 없이 ADB 서핑만")
    parser.add_argument("--setup-cert", action="store_true", help="CA 인증서 설치 안내")
    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")

    if args.setup_cert:
        print("""
=== mitmproxy CA 인증서 설치 안내 ===

1. PC에서 실행: mitmdump --listen-port 8080
2. 폰 WiFi 프록시를 PC_IP:8080으로 설정
3. 폰 브라우저에서 http://mitm.it 접속
4. Android 인증서 다운로드 + 설치
5. 설정 → 보안 → 신뢰할 수 있는 인증서 → 사용자 탭에서 확인

※ Android 10+: 사용자 인증서는 앱 트래픽에 기본 신뢰 안 됨
   → 네트워크 보안 설정이 없는 앱만 캡처 가능
   → 또는 Magisk + TrustUserCerts 모듈 필요 (루팅)
""")
        return

    # ADB 연결 확인
    ADBClient.start_server()
    adb = ADBClient()
    if not adb.is_connected():
        print("디바이스가 연결되지 않았습니다.")
        sys.exit(1)

    device_id = adb.get_serial()
    w, h = adb.screen_size()
    logger.info(f"Device: {device_id} ({w}x{h})")

    if args.no_proxy:
        # 프록시 없이 ADB 서핑만 (기존 방식)
        navigator = APP_NAVIGATORS.get(args.app)
        if navigator:
            navigator(adb, scrolls=args.scrolls)
            logger.info(f"[{args.app}] Navigation complete (no proxy capture)")
        return

    # mitmproxy 캡처 모드
    pc_ip = get_pc_ip()
    addon = AdResponseCapture(args.app)

    # mitmproxy 백그라운드 스레드 시작
    proxy_thread = threading.Thread(target=start_mitmproxy, args=(addon, PROXY_PORT), daemon=True)
    proxy_thread.start()
    time.sleep(3)  # mitmproxy 초기화 대기

    try:
        # 폰 프록시 설정
        setup_phone_proxy(adb, pc_ip, PROXY_PORT)
        time.sleep(2)

        # 앱 서핑
        navigator = APP_NAVIGATORS.get(args.app)
        if navigator:
            navigator(adb, scrolls=args.scrolls)
        else:
            logger.warning(f"[{args.app}] No navigator defined")

        # 캡처 결과 파싱
        time.sleep(3)  # 마지막 응답 대기
        with addon.lock:
            captures = list(addon.captured)

        logger.info(f"[capture] Total responses: {len(captures)}")

        # 앱별 파서로 광고 추출
        parser_fn = APP_PARSERS.get(args.app, parse_naver_ads)
        ads = parser_fn(captures)
        logger.info(f"[{args.app}] Parsed ads: {len(ads)}")

        for i, ad in enumerate(ads[:10]):
            name = (ad.get("advertiser_name") or "?")[:30]
            url = (ad.get("url") or "")[:50]
            logger.info(f"  [{i+1}] {name} | {url}")

        # DB 저장
        if ads:
            saved = asyncio.run(save_to_db(device_id, args.app, ads))
            logger.info(f"[{args.app}] Saved to DB: {saved} rows")

        # 캡처 로그 저장
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = CAPTURE_DIR / f"{args.app}_capture_{ts}.json"
        log_path.write_text(
            json.dumps({"app": args.app, "captures": len(captures), "ads": len(ads),
                        "raw": captures[:50]}, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info(f"[capture] Log saved: {log_path}")

    finally:
        # 프록시 해제
        clear_phone_proxy(adb)
        logger.info("Done.")


if __name__ == "__main__":
    main()
