"""ADB 클라이언트 — 디바이스 연결, 스크린샷, 입력 자동화."""

import os
import subprocess
import time
from pathlib import Path
from typing import Optional

# ADB 바이너리 경로 자동 탐지
_ADB_CANDIDATES = [
    "adb",
    r"C:\Users\user\AppData\Local\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools\adb.exe",
    r"C:\platform-tools\adb.exe",
    r"C:\Android\platform-tools\adb.exe",
]


def _find_adb() -> str:
    for candidate in _ADB_CANDIDATES:
        try:
            result = subprocess.run(
                [candidate, "version"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    raise RuntimeError("ADB를 찾을 수 없습니다. Platform Tools를 설치하세요.")


ADB_BIN = _find_adb()


class ADBClient:
    """단일 디바이스에 대한 ADB 래퍼."""

    def __init__(self, serial: Optional[str] = None):
        self.serial = serial
        self._base = [ADB_BIN]
        if serial:
            self._base += ["-s", serial]
        self._screen_w: Optional[int] = None
        self._screen_h: Optional[int] = None

    # ── 디바이스 관리 ──────────────────────────────────────────

    @staticmethod
    def list_devices() -> list[dict]:
        """연결된 디바이스 목록 반환."""
        result = subprocess.run(
            [ADB_BIN, "devices", "-l"],
            capture_output=True, text=True, timeout=10
        )
        devices = []
        for line in result.stdout.strip().splitlines()[1:]:
            line = line.strip()
            if not line or "offline" in line:
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                info = {"serial": parts[0]}
                for extra in parts[2:]:
                    if ":" in extra:
                        k, v = extra.split(":", 1)
                        info[k] = v
                devices.append(info)
        return devices

    @staticmethod
    def start_server():
        subprocess.run([ADB_BIN, "start-server"], capture_output=True, timeout=15)

    def is_connected(self) -> bool:
        devices = ADBClient.list_devices()
        if self.serial:
            return any(d["serial"] == self.serial for d in devices)
        return len(devices) > 0

    def get_serial(self) -> str:
        if self.serial:
            return self.serial
        devices = ADBClient.list_devices()
        if not devices:
            raise RuntimeError("연결된 디바이스가 없습니다.")
        return devices[0]["serial"]

    # ── 화면 크기 ──────────────────────────────────────────────

    def screen_size(self) -> tuple[int, int]:
        """(width, height) — Override size 우선, 없으면 Physical size."""
        if self._screen_w:
            return self._screen_w, self._screen_h
        out = self._shell("wm size")
        physical = None
        override = None
        for line in out.splitlines():
            if "Override size" in line:
                parts = line.split(": ")[1].strip().split("x")
                override = int(parts[0]), int(parts[1])
            elif "Physical size" in line:
                parts = line.split(": ")[1].strip().split("x")
                physical = int(parts[0]), int(parts[1])
        size = override or physical
        if not size:
            raise RuntimeError(f"화면 크기 파싱 실패: {out}")
        self._screen_w, self._screen_h = size
        return size

    # ── 스크린샷 ───────────────────────────────────────────────

    def screenshot(self, save_path: str | Path) -> Path:
        """PNG 스크린샷을 save_path에 저장."""
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "wb") as f:
            result = subprocess.run(
                self._base + ["exec-out", "screencap", "-p"],
                stdout=f, stderr=subprocess.PIPE, timeout=15
            )
        if result.returncode != 0:
            raise RuntimeError(f"screencap 실패: {result.stderr.decode()}")
        return save_path

    # ── 입력 ───────────────────────────────────────────────────

    def tap(self, x: int, y: int):
        self._shell(f"input tap {x} {y}")

    def tap_rel(self, rx: float, ry: float):
        """상대 좌표 (0.0~1.0) 탭."""
        w, h = self.screen_size()
        self.tap(int(w * rx), int(h * ry))

    def swipe_up(self, distance_ratio: float = 0.4, duration_ms: int = 600):
        """위로 스크롤 (피드 내리기)."""
        w, h = self.screen_size()
        cx = w // 2
        y1 = int(h * 0.65)
        y2 = int(h * (0.65 - distance_ratio))
        self._shell(f"input swipe {cx} {y1} {cx} {y2} {duration_ms}")

    def swipe_down(self, distance_ratio: float = 0.4, duration_ms: int = 600):
        w, h = self.screen_size()
        cx = w // 2
        y1 = int(h * 0.35)
        y2 = int(h * (0.35 + distance_ratio))
        self._shell(f"input swipe {cx} {y1} {cx} {y2} {duration_ms}")

    def press_home(self):
        self._shell("input keyevent KEYCODE_HOME")

    def press_back(self):
        self._shell("input keyevent KEYCODE_BACK")

    def press_app_switch(self):
        self._shell("input keyevent KEYCODE_APP_SWITCH")

    # ── 앱 실행 ────────────────────────────────────────────────

    def launch_app(self, package: str, activity: Optional[str] = None):
        if activity:
            self._shell(f"am start -n {package}/{activity}")
        else:
            self._shell(
                f"monkey -p {package} -c android.intent.category.LAUNCHER 1"
            )
        time.sleep(2.5)

    def force_stop(self, package: str):
        self._shell(f"am force-stop {package}")

    def get_foreground_app(self) -> str:
        out = self._shell(
            "dumpsys activity activities | grep -E 'mCurrentFocus|mFocusedApp'"
        )
        return out.strip()

    # ── 네트워크 프록시 설정 ────────────────────────────────────

    def swipe_left(self, distance_ratio: float = 0.5, y_ratio: float = 0.30, duration_ms: int = 400):
        """왼쪽으로 스와이프 (배너 카드 다음 슬라이드)."""
        w, h = self.screen_size()
        cy = int(h * y_ratio)
        x1 = int(w * (0.5 + distance_ratio / 2))
        x2 = int(w * (0.5 - distance_ratio / 2))
        self._shell(f"input swipe {x1} {cy} {x2} {cy} {duration_ms}")

    def get_clipboard(self) -> str:
        """클립보드 내용 읽기 (Android 10+ 제한 있음)."""
        out = self._shell("service call clipboard 2 i32 1")
        return out.strip()

    def tap_url_bar_and_copy(self) -> str:
        """브라우저 URL 바를 탭해서 URL 선택/복사 시도."""
        w, _ = self.screen_size()
        # URL 바 위치: 화면 상단 ~5.5% (Samsung Internet / Chrome 공통)
        self.tap(w // 2, int(_ * 0.055) if hasattr(self, '_screen_h') and self._screen_h else 110)
        import time; time.sleep(0.8)
        # Select all + Copy
        self._shell("input keyevent KEYCODE_CTRL_A")
        import time; time.sleep(0.3)
        self._shell("input keyevent KEYCODE_COPY")
        return ""

    def set_wifi_proxy(self, host: str, port: int):
        """Wi-Fi 프록시 설정 (mitmproxy 연동용)."""
        self._shell(f"settings put global http_proxy {host}:{port}")

    def clear_wifi_proxy(self):
        self._shell("settings put global http_proxy :0")

    # ── 내부 유틸 ──────────────────────────────────────────────

    def _shell(self, cmd: str) -> str:
        result = subprocess.run(
            self._base + ["shell"] + cmd.split(),
            capture_output=True, text=True, timeout=15
        )
        return result.stdout

    def _run(self, *args) -> str:
        result = subprocess.run(
            self._base + list(args),
            capture_output=True, text=True, timeout=30
        )
        return result.stdout
