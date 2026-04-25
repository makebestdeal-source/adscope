"""카카오톡 비즈보드 네비게이터 — 채팅목록 상단 배너 캡처."""

import time
from dataclasses import dataclass, field
from pathlib import Path

from crawler.mobile.adb_client import ADBClient

PACKAGE = "com.kakao.talk"


@dataclass
class KakaoAdSession:
    screenshots: list[Path] = field(default_factory=list)
    ad_regions: list[dict] = field(default_factory=list)


class KakaoAppNavigator:
    """카카오톡을 열어 비즈보드 배너를 캡처합니다."""

    def __init__(self, adb: ADBClient, output_dir: Path):
        self.adb = adb
        self.output_dir = output_dir

    def run_session(self, captures: int = 5, interval_sec: float = 4.0) -> KakaoAdSession:
        session = KakaoAdSession()
        output_dir = self.output_dir / "kakao"
        output_dir.mkdir(parents=True, exist_ok=True)

        # 앱 실행
        self.adb.launch_app(PACKAGE)
        time.sleep(3)

        w, h = self.adb.screen_size()
        # 비즈보드는 채팅목록 탭 상단 → 대략 화면 높이의 7~18%
        bizboard_crop = (0, int(h * 0.06), w, int(h * 0.20))

        for i in range(captures):
            shot_path = output_dir / f"bizboard_{i:02d}.png"
            self.adb.screenshot(shot_path)
            session.screenshots.append(shot_path)
            session.ad_regions.append({
                "path": shot_path,
                "region": "bizboard",
                "crop": bizboard_crop,
                "app": "kakao",
                "seq": i,
            })
            if i < captures - 1:
                time.sleep(interval_sec)

        # 앱 종료
        self.adb.press_home()
        return session
