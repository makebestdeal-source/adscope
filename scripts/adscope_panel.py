#!/usr/bin/env python3
"""AdScope 수동 제어 패널 — 서버·수집·배포를 버튼 하나로."""
from __future__ import annotations

import gzip
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, scrolledtext

# ── 경로 설정 ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = r"C:\Python314\python.exe"
if not Path(PYTHON).exists():
    PYTHON = sys.executable


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    try:
        for line in (PROJECT_ROOT / ".env").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    except Exception:
        pass
    return env


_ENV = _load_env()
MIGRATION_SECRET = _ENV.get("MIGRATION_SECRET", "")


def is_port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def kill_port(port: int):
    """Windows에서 특정 포트 사용 프로세스 강제 종료."""
    try:
        r = subprocess.run(
            f'netstat -ano | findstr ":{port} "',
            shell=True, capture_output=True, text=True
        )
        pids = set()
        for line in r.stdout.splitlines():
            parts = line.strip().split()
            if parts and parts[-1].isdigit():
                pids.add(parts[-1])
        for pid in pids:
            subprocess.run(f"taskkill /F /PID {pid}", shell=True,
                           capture_output=True)
    except Exception:
        pass


# ────────────────────────────────────────────────
#  GUI
# ────────────────────────────────────────────────

BG       = "#1a1a2e"
PANEL_BG = "#16213e"
ROW_BG   = "#0f3460"
FG       = "#e0e0e0"
GREEN    = "#4caf50"
RED      = "#f44336"
BLUE     = "#2196f3"
ORANGE   = "#ff9800"
PURPLE   = "#9c27b0"
DIM      = "#607080"


class Btn(tk.Button):
    def __init__(self, parent, text, cmd, color=BLUE, width=14, **kw):
        super().__init__(
            parent, text=text, command=cmd,
            bg=color, fg="white",
            font=("Consolas", 9, "bold"),
            relief="flat", bd=0,
            padx=10, pady=6,
            width=width,
            activebackground=color,
            activeforeground="white",
            cursor="hand2",
            **kw,
        )

    def disable(self):
        self.configure(state="disabled", bg=DIM)

    def enable(self, color=BLUE):
        self.configure(state="normal", bg=color)


class AdScopePanel(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AdScope Control Panel")
        self.geometry("860x700")
        self.minsize(720, 580)
        self.configure(bg=BG)

        self._procs: dict[str, subprocess.Popen] = {}
        self._build_ui()
        self._start_status_poll()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI 구성 ──────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_server_section()
        self._build_crawl_section()
        self._build_deploy_section()
        self._build_log_section()

    def _build_header(self):
        f = tk.Frame(self, bg=BG, pady=10)
        f.pack(fill="x", padx=12)
        tk.Label(f, text="AdScope Control Panel",
                 bg=BG, fg="#64b5f6",
                 font=("Consolas", 15, "bold")).pack(side="left")
        tk.Label(f, text="수동 제어 · 자동실행 없음",
                 bg=BG, fg=DIM,
                 font=("Consolas", 9)).pack(side="left", padx=14, pady=2)

    def _section(self, label: str) -> tk.Frame:
        outer = tk.LabelFrame(self, text=f"  {label}  ",
                              bg=PANEL_BG, fg="#90a4ae",
                              font=("Consolas", 9, "bold"),
                              bd=1, relief="groove")
        outer.pack(fill="x", padx=12, pady=3)
        inner = tk.Frame(outer, bg=PANEL_BG)
        inner.pack(fill="x", padx=8, pady=6)
        return inner

    def _build_server_section(self):
        f = self._section("서버")

        # 백엔드
        r1 = tk.Frame(f, bg=PANEL_BG)
        r1.pack(fill="x", pady=3)
        self._be_lbl = tk.Label(r1, text="● 백엔드  (8000)  : 확인중",
                                 bg=PANEL_BG, fg=DIM,
                                 font=("Consolas", 9), width=36, anchor="w")
        self._be_lbl.pack(side="left")
        Btn(r1, "▶ 시작", self._start_backend, GREEN, 8).pack(side="left", padx=3)
        Btn(r1, "■ 중지", self._stop_backend, RED, 8).pack(side="left", padx=3)
        Btn(r1, "브라우저", lambda: webbrowser.open("http://localhost:8000/docs"),
            DIM, 10).pack(side="left", padx=3)

        # 프론트
        r2 = tk.Frame(f, bg=PANEL_BG)
        r2.pack(fill="x", pady=3)
        self._fe_lbl = tk.Label(r2, text="● 프론트  (3001)  : 확인중",
                                 bg=PANEL_BG, fg=DIM,
                                 font=("Consolas", 9), width=36, anchor="w")
        self._fe_lbl.pack(side="left")
        Btn(r2, "▶ 시작", self._start_frontend, GREEN, 8).pack(side="left", padx=3)
        Btn(r2, "■ 중지", self._stop_frontend, RED, 8).pack(side="left", padx=3)
        Btn(r2, "브라우저", lambda: webbrowser.open("http://localhost:3001"),
            BLUE, 10).pack(side="left", padx=3)

    def _build_crawl_section(self):
        f = self._section("수집 (fast_crawl.py)")

        r = tk.Frame(f, bg=PANEL_BG)
        r.pack(fill="x")
        self._crawl_btn = Btn(r, "▶  수집 실행", self._start_crawl, GREEN, 16)
        self._crawl_btn.pack(side="left", padx=3)
        self._crawl_stop_btn = Btn(r, "■  수집 중지", self._stop_crawl, RED, 14)
        self._crawl_stop_btn.pack(side="left", padx=3)
        self._crawl_lbl = tk.Label(r, text="대기중",
                                    bg=PANEL_BG, fg=DIM,
                                    font=("Consolas", 9))
        self._crawl_lbl.pack(side="left", padx=12)

    def _build_deploy_section(self):
        f = self._section("배포 (Railway)")

        r = tk.Frame(f, bg=PANEL_BG)
        r.pack(fill="x")
        Btn(r, "☁  DB 업로드",    self._deploy_db,       ORANGE,  14).pack(side="left", padx=3)
        Btn(r, "🚀 백엔드 배포",  self._deploy_backend,  BLUE,    14).pack(side="left", padx=3)
        Btn(r, "🌐 프론트 배포",  self._deploy_frontend, BLUE,    14).pack(side="left", padx=3)
        Btn(r, "★ DB+전체 배포",  self._deploy_all,      PURPLE,  14).pack(side="left", padx=3)

    def _build_log_section(self):
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=12, pady=(6, 0))
        tk.Label(hdr, text="로그", bg=BG, fg="#90a4ae",
                 font=("Consolas", 9, "bold")).pack(side="left")
        Btn(hdr, "지우기", self._clear_log, DIM, 6).pack(side="right")

        self._log = scrolledtext.ScrolledText(
            self,
            font=("Consolas", 9),
            bg="#0a0a1a", fg="#b0c4b0",
            insertbackground="white",
            relief="flat", bd=0,
            state="disabled",
            wrap="word",
        )
        self._log.pack(fill="both", expand=True, padx=12, pady=(2, 12))

        self._log.tag_config("info", foreground="#64b5f6")
        self._log.tag_config("ok",   foreground="#81c784")
        self._log.tag_config("warn", foreground="#ffb74d")
        self._log.tag_config("err",  foreground="#e57373")
        self._log.tag_config("dim",  foreground="#546e7a")
        self._log.tag_config("head", foreground="#ce93d8")

    # ── 로그 ─────────────────────────────────────

    def log(self, msg: str, tag: str = ""):
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._log.configure(state="normal")
        self._log.insert("end", f"[{ts}] {msg}\n", tag or "")
        self._log.configure(state="disabled")
        self._log.see("end")

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    # ── 상태 폴링 ─────────────────────────────────

    def _start_status_poll(self):
        def _poll():
            while True:
                be = is_port_open(8000)
                fe = is_port_open(3001)
                self.after(0, self._refresh_status, be, fe)
                time.sleep(2)
        threading.Thread(target=_poll, daemon=True).start()

    def _refresh_status(self, be: bool, fe: bool):
        if be:
            self._be_lbl.configure(text="● 백엔드  (8000)  : 실행중 ✓", fg=GREEN)
        else:
            self._be_lbl.configure(text="● 백엔드  (8000)  : 중지됨",   fg=RED)
        if fe:
            self._fe_lbl.configure(text="● 프론트  (3001)  : 실행중 ✓", fg=GREEN)
        else:
            self._fe_lbl.configure(text="● 프론트  (3001)  : 중지됨",   fg=RED)

    # ── subprocess 헬퍼 ───────────────────────────

    def _run(self, name: str, args: list[str],
             cwd=None, extra_env: dict | None = None,
             on_done=None):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        if extra_env:
            env.update(extra_env)

        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NO_WINDOW

        proc = subprocess.Popen(
            args,
            cwd=str(cwd or PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=flags,
        )
        self._procs[name] = proc

        def _stream():
            try:
                for raw in proc.stdout:
                    line = raw.rstrip()
                    if not line:
                        continue
                    lo = line.lower()
                    if any(w in lo for w in ("error", "traceback", "exception", "failed")):
                        tag = "err"
                    elif any(w in lo for w in ("promoted", "success", "ok", "done", "완료")):
                        tag = "ok"
                    elif any(w in lo for w in ("warn", "skip", "timeout")):
                        tag = "warn"
                    else:
                        tag = ""
                    self.after(0, self.log, line, tag)
            finally:
                proc.wait()
                rc = proc.returncode
                self._procs.pop(name, None)
                if on_done:
                    self.after(0, on_done, rc)

        threading.Thread(target=_stream, daemon=True).start()
        return proc

    def _run_shell(self, cmd: str, label: str, on_done=None):
        """단순 셸 명령 실행 (출력 로깅)."""
        self.log(f"$ {cmd}", "dim")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = subprocess.Popen(
            cmd, shell=True,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=flags,
        )
        self._procs[label] = proc

        def _stream():
            try:
                for raw in proc.stdout:
                    line = raw.rstrip()
                    if line:
                        self.after(0, self.log, line,
                                   "err" if "error" in line.lower() else "")
            finally:
                proc.wait()
                rc = proc.returncode
                self._procs.pop(label, None)
                if on_done:
                    self.after(0, on_done, rc)

        threading.Thread(target=_stream, daemon=True).start()

    # ── 서버 ─────────────────────────────────────

    def _start_backend(self):
        if is_port_open(8000):
            self.log("백엔드 이미 실행중", "warn"); return
        self.log("─── 백엔드 시작 ───", "head")
        self._run(
            "backend",
            [PYTHON, "-m", "uvicorn", "api.main:app",
             "--host", "0.0.0.0", "--port", "8000"],
            extra_env={"DATABASE_URL": "sqlite+aiosqlite:///adscope.db"},
        )

    def _stop_backend(self):
        self._kill("backend", 8000, "백엔드")

    def _start_frontend(self):
        if is_port_open(3001):
            self.log("프론트 이미 실행중", "warn"); return
        self.log("─── 프론트 시작 ───", "head")
        self._run(
            "frontend",
            ["npm.cmd", "run", "dev", "--", "--port", "3001"],
            cwd=PROJECT_ROOT / "frontend",
        )

    def _stop_frontend(self):
        self._kill("frontend", 3001, "프론트")

    def _kill(self, name: str, port: int, label: str):
        proc = self._procs.get(name)
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass
            self.log(f"{label} 프로세스 종료 요청", "warn")
        else:
            kill_port(port)
            self.log(f"{label} 포트 {port} 강제 종료", "warn")

    # ── 수집 ─────────────────────────────────────

    def _start_crawl(self):
        if "fast_crawl" in self._procs:
            self.log("수집이 이미 실행중입니다", "warn"); return
        self.log("═══ 수집 시작 (fast_crawl.py) ═══", "head")
        self._crawl_lbl.configure(text="실행중...", fg=ORANGE)
        self._crawl_btn.disable()

        def on_done(rc: int):
            color, msg = (GREEN, "완료 ✓") if rc == 0 else (RED, f"종료 rc={rc}")
            self._crawl_lbl.configure(text=msg, fg=color)
            self._crawl_btn.enable(GREEN)
            self.log(f"═══ 수집 종료 (rc={rc}) ═══",
                     "ok" if rc == 0 else "err")

        self._run(
            "fast_crawl",
            [PYTHON, "scripts/fast_crawl.py"],
            on_done=on_done,
        )

    def _stop_crawl(self):
        proc = self._procs.get("fast_crawl")
        if proc:
            proc.terminate()
            self.log("수집 중지 요청", "warn")
            self._crawl_lbl.configure(text="중지됨", fg=RED)
            self._crawl_btn.enable(GREEN)
        else:
            self.log("실행중인 수집 없음", "warn")

    # ── 배포 ─────────────────────────────────────

    def _deploy_db(self, on_done=None):
        if not MIGRATION_SECRET:
            messagebox.showerror("오류", ".env에 MIGRATION_SECRET이 없습니다.")
            return
        self.log("─── DB 업로드 시작 ───", "head")

        def _run():
            db = PROJECT_ROOT / "adscope.db"
            gz = PROJECT_ROOT / "adscope.db.gz"
            if not db.exists():
                self.after(0, self.log, "adscope.db 없음", "err")
                if on_done: self.after(0, on_done, False)
                return

            # 압축
            mb = db.stat().st_size / 1024 / 1024
            self.after(0, self.log, f"DB 압축 중... ({mb:.1f}MB)", "dim")
            with open(db, "rb") as fi, gzip.open(gz, "wb") as fo:
                shutil.copyfileobj(fi, fo)
            gz_mb = gz.stat().st_size / 1024 / 1024
            self.after(0, self.log, f"압축 완료: {gz_mb:.1f}MB", "dim")

            # 업로드
            url = f"https://api.adscope.kr/api/_upload_data?secret={MIGRATION_SECRET}"
            self.after(0, self.log, "서버 업로드 중...", "dim")
            r = subprocess.run(
                ["curl", "-s", "-X", "POST", url, "-F", f"file=@{gz}"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=str(PROJECT_ROOT),
            )
            out = (r.stdout + r.stderr).strip()
            if r.returncode == 0 and ("ok" in out.lower() or len(out) < 50):
                self.after(0, self.log, f"DB 업로드 완료: {out[:120]}", "ok")
                if on_done: self.after(0, on_done, True)
            else:
                self.after(0, self.log, f"DB 업로드 실패: {out[:200]}", "err")
                if on_done: self.after(0, on_done, False)

        threading.Thread(target=_run, daemon=True).start()

    def _deploy_backend(self, on_done=None):
        self.log("─── 백엔드 Railway 배포 ───", "head")

        def _run():
            r = subprocess.run(
                "railway service adscope && railway up -d",
                shell=True, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
                cwd=str(PROJECT_ROOT),
            )
            out = (r.stdout + r.stderr).strip()[:400]
            if r.returncode == 0:
                self.after(0, self.log, f"백엔드 배포 성공\n{out}", "ok")
                if on_done: self.after(0, on_done, True)
            else:
                self.after(0, self.log, f"백엔드 배포 실패\n{out}", "err")
                if on_done: self.after(0, on_done, False)

        threading.Thread(target=_run, daemon=True).start()

    def _deploy_frontend(self, on_done=None):
        self.log("─── 프론트 Railway 배포 ───", "head")

        def _run():
            r = subprocess.run(
                "railway service frontend && railway up -d",
                shell=True, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
                cwd=str(PROJECT_ROOT),
            )
            out = (r.stdout + r.stderr).strip()[:400]
            if r.returncode == 0:
                self.after(0, self.log, f"프론트 배포 성공\n{out}", "ok")
                if on_done: self.after(0, on_done, True)
            else:
                self.after(0, self.log, f"프론트 배포 실패\n{out}", "err")
                if on_done: self.after(0, on_done, False)

        threading.Thread(target=_run, daemon=True).start()

    def _deploy_all(self):
        """DB 업로드 → 백엔드 배포 → 프론트 배포 (순차)."""
        self.log("═══ 전체 배포 시작 (DB → 백엔드 → 프론트) ═══", "head")

        def _step2(db_ok: bool):
            if not db_ok:
                self.log("DB 업로드 실패 — 배포 중단", "err"); return
            self._deploy_backend(on_done=_step3)

        def _step3(be_ok: bool):
            self._deploy_frontend(on_done=_step4)

        def _step4(fe_ok: bool):
            self.log("═══ 전체 배포 완료 ═══", "ok")

        self._deploy_db(on_done=_step2)

    # ── 종료 ─────────────────────────────────────

    def _on_close(self):
        for proc in list(self._procs.values()):
            try:
                proc.terminate()
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    app = AdScopePanel()
    app.mainloop()
