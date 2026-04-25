"""AdScope 수동 크롤러 패널 v2.0 — 포터블 버전

프로젝트 루트에 배치 → 경로 자동 감지, Python 자동 탐색
다른 PC에서도 바로 실행 가능 (24시간 루프 모드 지원)

실행법:
    python adscope_panel.py
    또는 adscope_panel.bat 더블클릭
"""
import gc
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

# ── 프로젝트 루트 자동 감지 ──────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent

# ── Python 실행파일 자동 탐색 ────────────────────────────────────────────────
def _find_python() -> str:
    """venv → 환경변수 → 일반 경로 순으로 Python 탐색."""
    candidates = [
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
        PROJECT_ROOT / "venv"  / "Scripts" / "python.exe",
        PROJECT_ROOT / "env"   / "Scripts" / "python.exe",
    ]
    for p in candidates:
        if p.exists():
            return str(p)

    # PATH에서 python 탐색
    import shutil
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            return found

    # 현재 인터프리터 사용 (fallback)
    return sys.executable

PYTHON_EXE = _find_python()

# ── 채널 정의 ────────────────────────────────────────────────────────────────
CHANNELS = [
    # (key, 표시명, 타입)
    ("youtube_ads",       "유튜브 투명성센터",    "카탈로그"),
    ("google_search_ads", "구글 검색광고 투명성", "카탈로그"),
    ("google_gdn",        "구글 GDN",             "카탈로그"),
    ("meta",              "메타 광고 라이브러리", "카탈로그"),
    ("tiktok_ads",        "틱톡 Creative Center", "카탈로그"),
    ("naver_search",      "네이버 검색광고",      "접촉"),
    ("naver_da",          "네이버 DA",            "접촉"),
    ("naver_shopping",    "네이버 쇼핑",          "접촉"),
    ("kakao_da",          "카카오 DA",            "접촉"),
    ("youtube_surf",      "유튜브 서핑",          "접촉"),
    ("meta_feed",         "메타 피드 서핑",       "접촉"),
]

CATALOG_CH = {k for k, _, t in CHANNELS if t == "카탈로그"}

BG_DARK   = "#1e1e2e"
BG_PANEL  = "#2a2a3e"
BG_ROW_A  = "#2e3b2e"   # 카탈로그 행
BG_ROW_B  = "#2e2e3d"   # 접촉 행
FG_WHITE  = "#cdd6f4"
FG_DIM    = "#6c7086"
ACCENT    = "#89b4fa"   # 파랑
GREEN     = "#a6e3a1"
YELLOW    = "#f9e2af"
RED       = "#f38ba8"
PURPLE    = "#cba6f7"


class CrawlPanel(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"AdScope 크롤러 패널  —  {PROJECT_ROOT.name}")
        self.geometry("1100x780")
        self.minsize(800, 600)
        self.configure(bg=BG_DARK)

        self.checks: dict[str, tk.BooleanVar] = {}
        self.process: subprocess.Popen | None  = None
        self.running  = False
        self.loop_active = False
        self._log_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()

        self._build_ui()
        self._poll_log()

    # ── UI 구성 ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        # 헤더
        hdr = tk.Frame(self, bg="#313244", pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="AdScope 크롤러 패널",
                 font=("맑은 고딕", 17, "bold"), fg=ACCENT, bg="#313244").pack()
        tk.Label(hdr, text=f"프로젝트: {PROJECT_ROOT}  |  Python: {PYTHON_EXE}",
                 font=("맑은 고딕", 9), fg=FG_DIM, bg="#313244").pack()

        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill="both", expand=True, padx=12, pady=8)

        # ── 왼쪽 패널 ──
        left = tk.Frame(body, bg=BG_PANEL, bd=0, relief="flat")
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)
        left.configure(width=280)

        # 매체 선택 섹션
        tk.Label(left, text="  매체 선택", font=("맑은 고딕", 11, "bold"),
                 fg=ACCENT, bg=BG_PANEL, anchor="w").pack(fill="x", pady=(10, 4), padx=8)

        # 빠른 선택 버튼
        q_frame = tk.Frame(left, bg=BG_PANEL)
        q_frame.pack(fill="x", padx=8, pady=(0, 8))
        for label, cmd, color in [
            ("전체",   self._sel_all,      "#4c9a4c"),
            ("해제",   self._sel_none,     "#6c7086"),
            ("카탈로그", self._sel_catalog, "#c08000"),
            ("접촉",   self._sel_contact,  "#2060a0"),
        ]:
            tk.Button(q_frame, text=label, command=cmd,
                      bg=color, fg="white", font=("맑은 고딕", 8, "bold"),
                      relief="flat", padx=6, pady=2,
                      activebackground=color, cursor="hand2").pack(side="left", padx=2)

        # 채널 목록
        cur_type = None
        for key, name, ch_type in CHANNELS:
            if ch_type != cur_type:
                cur_type = ch_type
                color = GREEN if ch_type == "카탈로그" else ACCENT
                tk.Label(left, text=f"  ▸ {ch_type}",
                         font=("맑은 고딕", 9, "bold"), fg=color,
                         bg=BG_PANEL, anchor="w").pack(fill="x", padx=8, pady=(8, 2))

            var = tk.BooleanVar(value=True)
            self.checks[key] = var
            bg = BG_ROW_A if ch_type == "카탈로그" else BG_ROW_B

            row = tk.Frame(left, bg=bg)
            row.pack(fill="x", padx=8, pady=1)

            cb = tk.Checkbutton(row, variable=var, text=f"  {name}",
                                font=("맑은 고딕", 9), fg=FG_WHITE, bg=bg,
                                selectcolor=bg, activebackground=bg,
                                activeforeground=FG_WHITE, anchor="w",
                                cursor="hand2")
            cb.pack(side="left", fill="x", expand=True)

        # ── 설정 섹션 ──
        sep = tk.Frame(left, height=1, bg="#45475a")
        sep.pack(fill="x", padx=8, pady=10)
        tk.Label(left, text="  설정", font=("맑은 고딕", 11, "bold"),
                 fg=ACCENT, bg=BG_PANEL, anchor="w").pack(fill="x", padx=8, pady=(0, 8))

        # 1회 타임아웃
        self._setting_row(left, "1회 실행 시간 (분):", "timeout_var", "120")
        # 루프 모드
        self.loop_var = tk.BooleanVar(value=False)
        loop_row = tk.Frame(left, bg=BG_PANEL)
        loop_row.pack(fill="x", padx=8, pady=3)
        tk.Checkbutton(loop_row, text="  루프 모드 (반복 실행)",
                       variable=self.loop_var, font=("맑은 고딕", 9),
                       fg=YELLOW, bg=BG_PANEL, selectcolor=BG_PANEL,
                       activebackground=BG_PANEL, activeforeground=YELLOW,
                       cursor="hand2").pack(side="left")
        # 루프 대기 시간
        self._setting_row(left, "루프 대기 시간 (분):", "loop_wait_var", "30")

        # 프로젝트 경로 변경
        sep2 = tk.Frame(left, height=1, bg="#45475a")
        sep2.pack(fill="x", padx=8, pady=10)
        tk.Button(left, text="프로젝트 경로 변경", command=self._change_project,
                  bg="#45475a", fg=FG_WHITE, font=("맑은 고딕", 8),
                  relief="flat", padx=6, pady=2, cursor="hand2").pack(padx=8, pady=2, anchor="w")

        # ── 오른쪽 패널 ──
        right = tk.Frame(body, bg=BG_DARK)
        right.pack(side="right", fill="both", expand=True)

        # 상태 표시줄
        self.status_var = tk.StringVar(value="대기 중")
        status_bar = tk.Frame(right, bg="#313244", pady=5)
        status_bar.pack(fill="x")
        self.status_lbl = tk.Label(status_bar, textvariable=self.status_var,
                                   font=("맑은 고딕", 10, "bold"), fg=GREEN,
                                   bg="#313244", anchor="w")
        self.status_lbl.pack(side="left", padx=10)

        self.elapsed_var = tk.StringVar(value="")
        tk.Label(status_bar, textvariable=self.elapsed_var,
                 font=("Consolas", 9), fg=FG_DIM, bg="#313244").pack(side="right", padx=10)

        # 로그 영역
        log_frame = tk.Frame(right, bg=BG_DARK)
        log_frame.pack(fill="both", expand=True, pady=(4, 0))

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            font=("Consolas", 9),
            bg="#11111b", fg="#cdd6f4",
            insertbackground="white",
            wrap="word",
            state="disabled",
            relief="flat",
            bd=0,
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.tag_configure("header",  foreground=PURPLE,  font=("Consolas", 9, "bold"))
        self.log_text.tag_configure("success", foreground=GREEN)
        self.log_text.tag_configure("warning", foreground=YELLOW)
        self.log_text.tag_configure("error",   foreground=RED)
        self.log_text.tag_configure("info",    foreground=ACCENT)
        self.log_text.tag_configure("dim",     foreground=FG_DIM)

        # 하단 버튼바
        btn_bar = tk.Frame(self, bg="#313244", pady=8)
        btn_bar.pack(fill="x")

        self.run_btn = tk.Button(btn_bar, text="▶  수집 시작", command=self._run,
                                  bg=ACCENT, fg="#1e1e2e",
                                  font=("맑은 고딕", 11, "bold"),
                                  relief="flat", padx=20, pady=6, cursor="hand2",
                                  activebackground="#74c7ec")
        self.run_btn.pack(side="right", padx=8)

        self.stop_btn = tk.Button(btn_bar, text="■  중지", command=self._stop,
                                   bg=RED, fg="#1e1e2e",
                                   font=("맑은 고딕", 11, "bold"),
                                   relief="flat", padx=20, pady=6, cursor="hand2",
                                   state="disabled", activebackground="#eba0ac")
        self.stop_btn.pack(side="right", padx=4)

        tk.Button(btn_bar, text="로그 지우기", command=self._clear_log,
                  bg="#45475a", fg=FG_WHITE, font=("맑은 고딕", 9),
                  relief="flat", padx=10, pady=6, cursor="hand2").pack(side="right", padx=4)

        tk.Button(btn_bar, text="로그 저장", command=self._save_log,
                  bg="#45475a", fg=FG_WHITE, font=("맑은 고딕", 9),
                  relief="flat", padx=10, pady=6, cursor="hand2").pack(side="right", padx=4)

        self.loop_status_lbl = tk.Label(btn_bar, text="",
                                         font=("맑은 고딕", 9), fg=YELLOW,
                                         bg="#313244")
        self.loop_status_lbl.pack(side="left", padx=12)

    def _setting_row(self, parent, label, attr, default):
        row = tk.Frame(parent, bg=BG_PANEL)
        row.pack(fill="x", padx=8, pady=3)
        tk.Label(row, text=label, font=("맑은 고딕", 9), fg=FG_DIM,
                 bg=BG_PANEL, width=18, anchor="w").pack(side="left")
        var = tk.StringVar(value=default)
        setattr(self, attr, var)
        tk.Entry(row, textvariable=var, width=7, font=("Consolas", 9),
                 bg="#313244", fg=FG_WHITE, insertbackground=FG_WHITE,
                 relief="flat", bd=2).pack(side="left", padx=4)

    # ── 채널 선택 헬퍼 ───────────────────────────────────────────────────────
    def _sel_all(self):
        for v in self.checks.values(): v.set(True)

    def _sel_none(self):
        for v in self.checks.values(): v.set(False)

    def _sel_catalog(self):
        for k, v in self.checks.items(): v.set(k in CATALOG_CH)

    def _sel_contact(self):
        for k, v in self.checks.items(): v.set(k not in CATALOG_CH)

    # ── 수집 시작 / 중지 ─────────────────────────────────────────────────────
    def _run(self):
        selected = [k for k, v in self.checks.items() if v.get()]
        if not selected:
            messagebox.showwarning("선택 오류", "수집할 매체를 하나 이상 선택해 주세요.")
            return
        try:
            timeout_min  = int(self.timeout_var.get())
            loop_wait    = int(self.loop_wait_var.get())
        except ValueError:
            messagebox.showerror("설정 오류", "시간 값은 정수(분)로 입력해 주세요.")
            return

        self.running  = True
        self.loop_active = self.loop_var.get()
        self.run_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self._clear_log()

        self._q_log(f"수집 시작  채널: {', '.join(selected)}", "header")
        self._q_log(f"Python: {PYTHON_EXE}", "dim")
        self._q_log(f"프로젝트: {PROJECT_ROOT}", "dim")
        if self.loop_active:
            self._q_log(f"루프 모드: 완료 후 {loop_wait}분 대기 후 재시작", "warning")

        t = threading.Thread(
            target=self._loop_runner,
            args=(selected, timeout_min * 60, loop_wait * 60),
            daemon=True,
        )
        t.start()
        self._start_elapsed_timer()

    def _loop_runner(self, selected, timeout_sec, wait_sec):
        loop_count = 0
        while True:
            loop_count += 1
            if self.loop_active and loop_count > 1:
                self._q_log(f"\n루프 {loop_count}회차 시작", "header")
            self._run_subprocess(selected, timeout_sec)

            if not self.running:
                break
            if not self.loop_active:
                break

            # 루프 대기
            self._q_log(f"\n{wait_sec//60}분 대기 후 재시작...", "warning")
            self.after(0, lambda: self.loop_status_lbl.configure(
                text=f"루프 대기 중 ({wait_sec//60}분)"
            ))
            deadline = time.time() + wait_sec
            while time.time() < deadline and self.running:
                remaining = int(deadline - time.time())
                mins, secs = divmod(remaining, 60)
                self.after(0, lambda m=mins, s=secs: self.loop_status_lbl.configure(
                    text=f"다음 루프까지: {m:02d}:{s:02d}"
                ))
                time.sleep(1)

            if not self.running:
                break

        self.after(0, self._finish_ui)

    def _run_subprocess(self, channels: list[str], timeout_sec: int):
        runner = PROJECT_ROOT / "scripts" / "run_selected_channels.py"
        if not runner.exists():
            self._q_log(f"[!] 실행 스크립트 없음: {runner}", "error")
            return

        cmd = [
            PYTHON_EXE, str(runner),
            "--timeout", str(timeout_sec),
            "--channels", *channels,
        ]

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"]  = "1"

        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )

            for line in self.process.stdout:
                line = line.rstrip()
                if not line:
                    continue
                tag = _classify_line(line)
                self._q_log(line, tag)

            self.process.wait()
            rc = self.process.returncode
            if rc == 0:
                self._q_log("✓ 수집 완료", "success")
            elif rc in (None, -1, 1):
                self._q_log("■ 수집 중지됨", "warning")
            else:
                self._q_log(f"종료 코드: {rc}", "warning")

        except FileNotFoundError as e:
            self._q_log(f"[!] 실행 파일 없음: {e}", "error")
        except Exception as e:
            self._q_log(f"[!] 오류: {e}", "error")
        finally:
            self.process = None

    def _stop(self):
        self.running     = False
        self.loop_active = False
        self._q_log("중지 요청...", "warning")
        if self.process:
            self.process.terminate()
        self.loop_status_lbl.configure(text="")

    def _finish_ui(self):
        self.running = False
        self.run_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self._set_status("완료", GREEN)
        self.loop_status_lbl.configure(text="")

    # ── 로그 ─────────────────────────────────────────────────────────────────
    def _q_log(self, text: str, tag: str | None = None):
        """스레드에서 안전하게 로그 큐에 넣기."""
        self._log_queue.put((text, tag))

    def _poll_log(self):
        """메인 스레드에서 큐를 드레인하여 텍스트 위젯에 쓰기."""
        try:
            while True:
                text, tag = self._log_queue.get_nowait()
                self._write_log(text, tag)
        except queue.Empty:
            pass
        self.after(80, self._poll_log)

    def _write_log(self, text: str, tag: str | None):
        self.log_text.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        if tag:
            self.log_text.insert("end", f"[{ts}] {text}\n", tag)
        else:
            self.log_text.insert("end", f"[{ts}] {text}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _save_log(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")],
            initialfile=f"crawl_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        )
        if path:
            content = self.log_text.get("1.0", "end")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("저장 완료", f"로그가 저장되었습니다:\n{path}")

    # ── 경과 시간 타이머 ──────────────────────────────────────────────────────
    def _start_elapsed_timer(self):
        self._t_start = time.time()
        self._tick_elapsed()

    def _tick_elapsed(self):
        if not self.running:
            self.elapsed_var.set("")
            return
        elapsed = int(time.time() - self._t_start)
        h, rem  = divmod(elapsed, 3600)
        m, s    = divmod(rem, 60)
        self.elapsed_var.set(f"경과: {h:02d}:{m:02d}:{s:02d}")
        self._set_status("수집 중...", YELLOW)
        self.after(1000, self._tick_elapsed)

    def _set_status(self, text: str, color: str = FG_WHITE):
        self.status_var.set(text)
        self.status_lbl.configure(fg=color)

    # ── 프로젝트 경로 변경 ───────────────────────────────────────────────────
    def _change_project(self):
        path = filedialog.askdirectory(initialdir=str(PROJECT_ROOT))
        if path:
            global PROJECT_ROOT, PYTHON_EXE
            PROJECT_ROOT = Path(path)
            PYTHON_EXE   = _find_python()
            self.title(f"AdScope 크롤러 패널  —  {PROJECT_ROOT.name}")
            self._q_log(f"프로젝트 경로 변경: {PROJECT_ROOT}", "info")
            self._q_log(f"Python: {PYTHON_EXE}", "dim")


# ── 로그 라인 분류 ────────────────────────────────────────────────────────────
def _classify_line(line: str) -> str | None:
    l = line.lower()
    if line.startswith("===") or "== wave" in line.lower() or "results" in line:
        return "header"
    if "[+]" in line or "promoted" in line or "완료" in line or "success" in l:
        return "success"
    if "[!]" in line or "error" in l or "fail" in l or "exception" in l:
        return "error"
    if "[t]" in line or "timeout" in l or "중지" in line or "warning" in l:
        return "warning"
    if "starting" in l or "adscope" in l or "채널" in line or "python" in l:
        return "info"
    return None


# ── 진입점 ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = CrawlPanel()
    app.mainloop()
