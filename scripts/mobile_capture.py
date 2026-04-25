"""
모바일 광고 수집 — ADB 기반 스크린샷 자동화
============================================
사용법:
  python scripts/mobile_capture.py            # 연결된 디바이스 자동 감지
  python scripts/mobile_capture.py --serial R3CW...   # 특정 디바이스
  python scripts/mobile_capture.py --list-devices     # 디바이스 목록
  python scripts/mobile_capture.py --check            # 연결 상태 확인만

수집 흐름:
  1. 네이버 앱 실행 → 홈 배너 + 피드 + 탭(뉴스/엔터/스포츠)
  2. "광고"/"AD" 레이블 감지 → 광고 카드 탭
  3. 랜딩 URL 캡처 (브라우저 주소창 OCR)
  4. 광고주 도메인 추출 → DB 저장
"""

import argparse
import asyncio
import json
import re
import subprocess
import sys
import time
from datetime import datetime, UTC
from pathlib import Path

import numpy as np
from loguru import logger
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawler.mobile.adb_client import ADBClient
from crawler.mobile.apps.naver_app import NaverAppNavigator, PACKAGE as NAVER_PKG
from crawler.mobile.apps.kakao_app import KakaoAppNavigator
from processor.mobile_ad_detector import MobileAdDetector, _get_reader, _AD_LABEL, _bbox_center

OUTPUT_DIR = Path("mobile_captures")
DB_PATH = Path("adscope.db")
DEVICE_ID = "1c7c8f6323057ece"
LOOP_INTERVAL_SEC = 300

# URL 주소창 패턴
_URL_RE = re.compile(r"https?://[^\s\"'<>]{8,}")
# 네이버 트래킹 URL → 광고주 도메인 추출 불필요 (최종 URL 캡처)
_NAVER_TRACK_RE = re.compile(r"(ad\.naver\.com|nclick\.naver\.com|clk\.naver\.com)")


# ── 랜딩 URL 캡처 ─────────────────────────────────────────────────

def capture_landing_url(adb: ADBClient, ad_region: dict, screenshot_path: Path) -> str:
    """
    AD 위치를 탭하고 Naver 인앱 브라우저에서 랜딩 URL을 캡처합니다.

    흐름:
      1. 광고 탭 → 랜딩 페이지 로딩 대기
      2. 브라우저 하단 ≡ 메뉴 → 'URL 복사' → 클립보드 저장
      3. 브라우저 Q(검색) 아이콘 → '복사한 URL' 제안 → uiautomator 읽기
      4. 실패 시 OCR fallback

    Returns:
        광고주 URL 문자열 (없으면 "")
    """
    tap_x, tap_y = ad_region.get("tap_display_xy", (None, None))
    if tap_x is None:
        w, h = adb.screen_size()
        tap_x, tap_y = w // 2, int(h * 0.45)

    logger.info(f"  광고 탭: ({tap_x}, {tap_y})")
    adb.tap(tap_x, tap_y)
    time.sleep(7.0)  # 랜딩 페이지 로딩 대기 (검색모드 → 페이지 전환 포함)

    # 랜딩 URL 추출 (≡ → URL 복사 → Q → 복사한 URL 읽기)
    url = _read_landing_url_via_menu(adb)
    if url:
        logger.info(f"  랜딩 URL: {url}")
    else:
        # fallback: OCR
        url_shot = OUTPUT_DIR / "url_capture" / f"{screenshot_path.stem}_url.png"
        url_shot.parent.mkdir(parents=True, exist_ok=True)
        adb.screenshot(url_shot)
        url = _ocr_url_bar(url_shot)
        logger.info(f"  랜딩 URL (OCR fallback): {url or '(추출 실패)'}")

    # 앱으로 복귀 (브라우저 → Naver 홈)
    adb.press_back()
    time.sleep(0.8)
    adb.press_back()
    time.sleep(0.8)
    adb.press_back()
    time.sleep(1.0)

    return url


def _read_landing_url_via_menu(adb: ADBClient) -> str:
    """
    Naver 인앱 브라우저 URL 추출:
      1) ≡ 메뉴 → 'URL 복사' (클립보드에 저장)
      2) 상단 검색창 탭 → copyurl_url 노드 직독
         (resource-id: com.nhn.android.search.InAppBrowser:id/copyurl_url)
    """
    import xml.etree.ElementTree as ET
    import tempfile

    def _dump_ui(remote="/sdcard/_ui_tmp.xml") -> ET.ElementTree | None:
        adb._shell(f"uiautomator dump {remote}")
        time.sleep(0.4)
        tmp = Path(tempfile.mktemp(suffix=".xml"))
        r = subprocess.run(
            adb._base + ["pull", remote, str(tmp)],
            capture_output=True, timeout=10
        )
        if r.returncode != 0 or not tmp.exists():
            return None
        tree = ET.parse(tmp)
        tmp.unlink(missing_ok=True)
        return tree

    def _find_url_by_rid(tree: ET.ElementTree, *rid_suffixes) -> str:
        """resource-id 끝부분으로 노드를 찾아 text에서 URL 반환."""
        for node in tree.getroot().iter("node"):
            rid = node.get("resource-id", "")
            if any(rid.endswith(s) for s in rid_suffixes):
                val = node.get("text", "")
                m = _URL_RE.search(val)
                if m:
                    url = m.group(0).rstrip(")")
                    if not _NAVER_TRACK_RE.search(url):
                        return url
        return ""

    def _find_url_in_tree(tree: ET.ElementTree) -> str:
        for node in tree.getroot().iter("node"):
            for attr in ("text", "content-desc"):
                val = node.get(attr, "")
                m = _URL_RE.search(val)
                if m:
                    url = m.group(0).rstrip(")")
                    if not _NAVER_TRACK_RE.search(url):
                        return url
        return ""

    def _find_and_tap(tree: ET.ElementTree, *keywords) -> bool:
        for node in tree.getroot().iter("node"):
            combined = node.get("text", "") + node.get("content-desc", "")
            if any(kw in combined for kw in keywords):
                m = re.findall(r"\d+", node.get("bounds", ""))
                if len(m) >= 4:
                    cx = (int(m[0]) + int(m[2])) // 2
                    cy = (int(m[1]) + int(m[3])) // 2
                    adb.tap(cx, cy)
                    return True
        return False

    def _tap_by_rid(tree: ET.ElementTree, *rid_suffixes) -> bool:
        for node in tree.getroot().iter("node"):
            rid = node.get("resource-id", "")
            if any(rid.endswith(s) for s in rid_suffixes):
                m = re.findall(r"\d+", node.get("bounds", ""))
                if len(m) >= 4:
                    cx = (int(m[0]) + int(m[2])) // 2
                    cy = (int(m[1]) + int(m[3])) // 2
                    adb.tap(cx, cy)
                    return True
        return False

    try:
        w, h = adb.screen_size()

        # ── 1단계: ≡ 메뉴 열기 → 'URL 복사' 탭 ─────────────────────
        # 하단 툴바 y ≈ 92.1%, ≡ 버튼 x ≈ 89%
        adb.tap(int(w * 0.89), int(h * 0.921))
        time.sleep(1.5)

        tree = _dump_ui()
        if not tree:
            return ""

        if not _find_and_tap(tree, "URL 복사", "URL복사"):
            logger.debug("'URL 복사' 못 찾음")
            adb.press_back()
            return ""
        time.sleep(0.6)

        # ── 2단계: 상단 검색창 탭 → copyurl_url 직독 ────────────────
        # 검색창 캡슐: search_window_area (y ≈ 63~252 on 2220px → 중앙 y ≈ 7.1%)
        adb.tap(w // 2, int(h * 0.071))
        time.sleep(1.0)

        tree2 = _dump_ui()
        if tree2:
            # resource-id 직접 탐색 (가장 신뢰성 높음)
            url = _find_url_by_rid(tree2, "copyurl_url")
            if url:
                logger.debug(f"copyurl_url 직독: {url}")
                adb.press_back()
                return url
            # fallback: 전체 트리 URL 탐색
            url = _find_url_in_tree(tree2)
            if url:
                adb.press_back()
                return url

        adb.press_back()

    except Exception as e:
        logger.debug(f"URL 추출 실패: {e}")

    return ""


def _ocr_url_bar(screenshot: Path) -> str:
    """브라우저 주소창 영역 OCR → URL 추출."""
    try:
        img = Image.open(screenshot).convert("RGB")
        w, h = img.size
        # 주소창: 상태바 아래 첫 번째 영역 (약 4~10%)
        url_bar = img.crop((0, int(h * 0.04), w, int(h * 0.12)))
        reader = _get_reader()
        items = reader.readtext(np.array(url_bar), detail=0, paragraph=False)
        full = " ".join(items)
        match = _URL_RE.search(full)
        if match:
            url = match.group(0).rstrip(")")
            if not _NAVER_TRACK_RE.search(url):
                return url
    except Exception as e:
        logger.debug(f"URL OCR 실패: {e}")
    return ""


# ── 광고 탭 좌표 계산 ──────────────────────────────────────────────

def _calc_tap_xy(adb: ADBClient, ad_result: dict, screenshot: Path) -> tuple[int, int]:
    """
    OCR bbox에서 AD 레이블 위치를 찾아 광고 카드 중앙을 탭 좌표로 반환.
    스크린샷 픽셀 → 디스플레이 픽셀 변환 포함.
    """
    shot_w, shot_h = Image.open(screenshot).size
    disp_w, disp_h = adb.screen_size()
    scale_x = disp_w / shot_w
    scale_y = disp_h / shot_h

    region = ad_result.get("region")
    if region:
        rx0, ry0, rx1, ry1 = region
        cx = int((rx0 + rx1) / 2 * scale_x)
        cy = int((ry0 + ry1) / 2 * scale_y)
        # AD 레이블은 카드 하단 → 카드 중앙으로 올림
        cy = max(0, cy - int(200 * scale_y))
        return cx, cy

    return disp_w // 2, int(disp_h * 0.45)


# ── DB 저장 ───────────────────────────────────────────────────────

async def save_exposures(device_id: str, detections: list[dict]):
    import aiosqlite
    now = datetime.now(UTC).isoformat()
    rows = []
    for det in detections:
        brand = det.get("brand", "")
        copy = det.get("copy", "")
        url = det.get("landing_url", "")
        if not brand and not copy:
            continue
        rows.append((
            device_id, det.get("app", ""),
            _infer_channel(det.get("app", "")),
            brand[:200], copy[:500],
            det.get("ad_type", "banner"),
            url[:1000],
            now,
            json.dumps({
                "region": det.get("region"),
                "confidence": det.get("confidence"),
                "full_text": det.get("full_text", "")[:200],
                "landing_url": url,
            }),
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


async def ensure_device_registered(adb: ADBClient, device_id: str):
    import aiosqlite
    try:
        w, h = adb.screen_size()
        screen_res = f"{w}x{h}"
    except Exception:
        screen_res = "unknown"
    now = datetime.now(UTC).isoformat()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("""
            INSERT OR IGNORE INTO mobile_panel_devices
              (device_id, device_type, os_type, screen_res, last_seen, created_at)
            VALUES (?, 'physical', 'android', ?, ?, ?)
        """, (device_id, screen_res, now, now))
        await db.execute(
            "UPDATE mobile_panel_devices SET last_seen=? WHERE device_id=?",
            (now, device_id)
        )
        await db.commit()


def _infer_channel(app: str) -> str:
    return {"naver": "naver_da", "kakao": "kakao_da",
            "youtube": "youtube_ads", "instagram": "meta"}.get(app.lower(), "mobile_da")


# ── 메인 수집 ─────────────────────────────────────────────────────

async def run_collection(adb: ADBClient, apps: list[str],
                         loop: bool = False, tap_ads: bool = True):
    device_id = adb.get_serial()
    await ensure_device_registered(adb, device_id)
    detector = MobileAdDetector(use_ocr=True)
    out_base = OUTPUT_DIR / datetime.now().strftime("%Y%m%d_%H%M")

    while True:
        total_saved = 0
        logger.info("=== 수집 세션 시작 ===")

        for app in apps:
            detections = []
            try:
                if app == "naver":
                    detections = _collect_naver(adb, detector, out_base, tap_ads)
                elif app == "kakao":
                    detections = _collect_kakao(adb, detector, out_base, tap_ads)
            except Exception as e:
                logger.error(f"[{app}] 수집 오류: {e}")
                continue

            saved = await save_exposures(device_id, detections)
            total_saved += saved
            logger.info(f"[{app}] 감지={len(detections)} 저장={saved}")

        logger.info(f"세션 완료: 총 {total_saved}건 저장")
        if not loop:
            break
        logger.info(f"{LOOP_INTERVAL_SEC}초 후 재수집...")
        await asyncio.sleep(LOOP_INTERVAL_SEC)


def _collect_naver(adb: ADBClient, detector: MobileAdDetector,
                   out_base: Path, tap_ads: bool) -> list[dict]:
    """네이버 앱 광고 수집 (배너 + 피드 + 스마트채널 탭)."""
    navigator = NaverAppNavigator(adb, out_base)
    session = navigator.run_session(feed_scrolls=5, include_tabs=True)
    detections = []

    for region_info in session.ad_regions:
        path = region_info["path"]
        mode = region_info.get("analyze_mode", "full")
        ad_type = region_info.get("ad_type", "feed_ad")

        if mode == "banner":
            results = detector.analyze_naver_banner(path)
        else:
            results = detector.analyze(path)

        for r in results:
            r["app"] = "naver"
            r["ad_type"] = ad_type

            # AD 감지 후 탭 → 랜딩 URL 캡처 (tap_ads=True일 때)
            if tap_ads and r.get("is_ad") and r.get("region"):
                try:
                    tap_x, tap_y = _calc_tap_xy(adb, r, path)
                    r["tap_display_xy"] = (tap_x, tap_y)
                    r["landing_url"] = capture_landing_url(adb, r, path)
                    # URL 없으면 광고주 미확인 → 저장하되 플래그
                    if not r["landing_url"]:
                        r["confidence"] = min(r.get("confidence", 0.5), 0.4)
                except Exception as e:
                    logger.debug(f"URL 캡처 실패: {e}")
                    r["landing_url"] = ""

            detections.append(r)

    return detections


def _collect_kakao(adb: ADBClient, detector: MobileAdDetector,
                   out_base: Path, tap_ads: bool) -> list[dict]:
    """카카오톡 비즈보드 광고 수집."""
    navigator = KakaoAppNavigator(adb, out_base)
    session = navigator.run_session(captures=4, interval_sec=5.0)
    detections = []

    for region_info in session.ad_regions:
        results = detector.analyze(region_info["path"],
                                   crop=region_info.get("crop"))
        for r in results:
            r["app"] = "kakao"
            r["ad_type"] = "bizboard"
            if tap_ads and r.get("is_ad") and r.get("region"):
                try:
                    tap_x, tap_y = _calc_tap_xy(adb, r, region_info["path"])
                    r["tap_display_xy"] = (tap_x, tap_y)
                    r["landing_url"] = capture_landing_url(adb, r, region_info["path"])
                except Exception as e:
                    logger.debug(f"URL 캡처 실패: {e}")
                    r["landing_url"] = ""
            detections.append(r)

    return detections


# ── CLI ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="모바일 광고 수집")
    parser.add_argument("--serial", help="디바이스 시리얼")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--apps", default="naver,kakao")
    parser.add_argument("--loop", action="store_true", help="5분마다 반복")
    parser.add_argument("--check", action="store_true", help="연결 상태만 확인")
    parser.add_argument("--no-tap", action="store_true", help="URL 캡처 비활성화")
    args = parser.parse_args()

    ADBClient.start_server()

    if args.list_devices:
        devices = ADBClient.list_devices()
        if not devices:
            print("연결된 디바이스 없음")
        else:
            for d in devices:
                print(f"  {d['serial']} | {d.get('model','unknown')}")
        return

    adb = ADBClient(serial=args.serial)

    if args.check:
        if adb.is_connected():
            w, h = adb.screen_size()
            print(f"연결 OK: {adb.get_serial()} ({w}x{h})")
        else:
            print("디바이스 연결 안 됨")
        return

    if not adb.is_connected():
        print("디바이스가 연결되지 않았습니다.")
        sys.exit(1)

    apps = [a.strip() for a in args.apps.split(",") if a.strip()]
    asyncio.run(run_collection(adb, apps, loop=args.loop, tap_ads=not args.no_tap))


if __name__ == "__main__":
    main()
