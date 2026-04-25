"""네이버 앱 네비게이터 — DA 배너 + 피드 + 탭 광고 수집."""

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from crawler.mobile.adb_client import ADBClient

PACKAGE = "com.nhn.android.search"

# 상단 탭 X 상대좌표 (뉴스/엔터/스포츠/쇼핑) — 화면 폭 비율
_TOP_TABS = [
    ("news",   0.12),
    ("enter",  0.28),
    ("sports", 0.44),
    ("shop",   0.58),
]


@dataclass
class NaverAdSession:
    screenshots: list[Path] = field(default_factory=list)
    ad_regions: list[dict] = field(default_factory=list)


class NaverAppNavigator:
    """네이버 앱 DA 배너 + 피드 광고 + 탭별 광고 수집."""

    def __init__(self, adb: ADBClient, output_dir: Path):
        self.adb = adb
        self.output_dir = output_dir

    def run_session(self, feed_scrolls: int = 6, include_tabs: bool = True) -> NaverAdSession:
        session = NaverAdSession()
        out = self.output_dir / "naver"
        out.mkdir(parents=True, exist_ok=True)

        # ── 앱 실행 ──────────────────────────────────────────
        subprocess.run(
            self.adb._base + ["shell", "am", "start", "-n",
                               f"{PACKAGE}/.ui.pages.SearchHomePage"],
            capture_output=True
        )
        time.sleep(3)
        # 홈탭 명시적 이동 (앱이 마지막 탭으로 열릴 수 있음)
        # bottom nav 2번째 아이콘(홈 N) x≈28%, y≈94%
        w, h = self.adb.screen_size()
        self.adb.tap(int(w * 0.28), int(h * 0.94))
        time.sleep(2.5)

        # ── 1. 홈 배너 (상단 DA 카드 가로 슬라이드) ──────────
        self._capture_home_banners(session, out)

        # ── 2. 홈 피드 세로 스크롤 (피드 광고 카드) ──────────
        self._capture_feed(session, out, scrolls=feed_scrolls)

        # ── 3. 상단 탭별 광고 수집 ────────────────────────────
        if include_tabs:
            self._capture_tabs(session, out, scrolls=3)

        self.adb.press_home()
        return session

    # ── 홈 배너 (가로 슬라이드) ──────────────────────────────

    def _capture_home_banners(self, session: NaverAdSession, out: Path):
        """홈 상단 DA 배너 카드를 가로로 3장 슬라이드하며 캡처."""
        w, h = self.adb.screen_size()
        # 배너 카드 세로 중앙 (~30% 높이)
        banner_cy = int(h * 0.30)
        # 배너 crop 범위 (스크린샷 픽셀 기준은 detector가 처리)

        for i in range(3):
            p = out / f"banner_{i:02d}.png"
            self.adb.screenshot(p)
            session.screenshots.append(p)
            session.ad_regions.append({
                "path": p, "region": "banner_da", "ad_type": "banner_da",
                "analyze_mode": "banner",
            })
            # 카드 왼쪽으로 스와이프 → 다음 배너
            if i < 2:
                self.adb._shell(
                    f"input swipe {int(w*0.70)} {banner_cy} {int(w*0.25)} {banner_cy} 400"
                )
                time.sleep(1.5)

    # ── 피드 세로 스크롤 ──────────────────────────────────────

    def _capture_feed(self, session: NaverAdSession, out: Path, scrolls: int):
        """홈 피드를 세로 스크롤하면서 AD 카드 캡처."""
        for i in range(scrolls):
            p = out / f"feed_{i:02d}.png"
            self.adb.screenshot(p)
            session.screenshots.append(p)
            session.ad_regions.append({
                "path": p, "region": "feed_full", "ad_type": "feed_ad",
                "analyze_mode": "full",
            })
            self.adb.swipe_up(distance_ratio=0.38)
            time.sleep(2.0)

    # ── 상단 탭별 ─────────────────────────────────────────────

    def _capture_tabs(self, session: NaverAdSession, out: Path, scrolls: int):
        """뉴스/엔터/스포츠/쇼핑 탭으로 이동해 광고 카드 수집."""
        w, h = self.adb.screen_size()
        # 상단 탭 Y 위치 (~6% 높이)
        tab_y = int(h * 0.063)

        for tab_name, tab_rx in _TOP_TABS:
            # 탭 탭
            self.adb.tap(int(w * tab_rx), tab_y)
            time.sleep(2.5)

            for i in range(scrolls):
                p = out / f"tab_{tab_name}_{i:02d}.png"
                self.adb.screenshot(p)
                session.screenshots.append(p)
                session.ad_regions.append({
                    "path": p, "region": f"tab_{tab_name}", "ad_type": "tab_feed_ad",
                    "analyze_mode": "full",
                })
                self.adb.swipe_up(distance_ratio=0.38)
                time.sleep(1.8)

        # 홈 탭으로 복귀
        subprocess.run(
            self.adb._base + ["shell", "am", "start", "-n",
                               f"{PACKAGE}/.ui.pages.SearchHomePage"],
            capture_output=True
        )
        time.sleep(2)
