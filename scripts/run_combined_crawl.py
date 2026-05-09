"""Run current ad collectors in two bounded phases.

Phase 1: naver_search + naver_da + kakao_da
Phase 2: youtube_ads + google_gdn + meta + naver_shopping + tiktok
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
PHASE_TIMEOUT = int(os.environ.get("COMBINED_CRAWL_PHASE_TIMEOUT", str(4 * 3600)))
R2_UPLOAD_TIMEOUT = int(os.environ.get("R2_UPLOAD_TIMEOUT", str(2 * 3600)))
UPLOAD_R2_AFTER_PHASE = os.environ.get("COMBINED_CRAWL_UPLOAD_R2_AFTER_PHASE", "1") != "0"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_DIR = ROOT / "logs"
RUN_DIR = ROOT / "cache" / "collector_runs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
RUN_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = RUN_DIR / "combined_crawl_state_latest.json"
MAIN_LOG = Path(os.environ.get("COMBINED_CRAWL_LOG", LOG_DIR / f"combined_crawl_{STAMP}.log"))


def log(message: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}"
    print(line, flush=True)
    with MAIN_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def write_state(**updates: object) -> None:
    current: dict[str, object] = {}
    if STATE_PATH.exists():
        try:
            current = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current = {}
    current.update(updates)
    current["updated_at"] = datetime.now().isoformat(timespec="seconds")
    STATE_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def run_phase(label: str, phase_key: str, cmds: list[list[str]], extra_env: dict[str, str]) -> list[int | None]:
    env = {**os.environ, **extra_env}
    deadline = time.time() + PHASE_TIMEOUT
    procs: list[tuple[subprocess.Popen, object, Path]] = []

    log("=" * 60)
    log(f"{label} start timeout={PHASE_TIMEOUT}s")
    log("=" * 60)
    write_state(**{f"{phase_key}_started_at": datetime.now().isoformat(timespec="seconds")})

    for index, cmd in enumerate(cmds, 1):
        child_log = LOG_DIR / f"{phase_key}_{index}_{Path(cmd[-1]).stem}_{STAMP}.log"
        handle = child_log.open("a", encoding="utf-8", errors="replace")
        log(f"{label} child start: {' '.join(cmd)} log={child_log}")
        proc = subprocess.Popen(
            cmd,
            env=env,
            cwd=str(ROOT),
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        procs.append((proc, handle, child_log))

    while time.time() < deadline:
        if all(proc.poll() is not None for proc, _, _ in procs):
            break
        time.sleep(10)

    for proc, _, child_log in procs:
        if proc.poll() is None:
            log(f"{label} child timeout, terminating pid={proc.pid} log={child_log}")
            proc.terminate()

    time.sleep(5)

    for proc, _, child_log in procs:
        if proc.poll() is None:
            log(f"{label} child still alive, killing pid={proc.pid} log={child_log}")
            proc.kill()

    return_codes: list[int | None] = []
    for proc, handle, child_log in procs:
        try:
            code = proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            code = None
        return_codes.append(code)
        handle.close()
        log(f"{label} child done pid={proc.pid} exit={code} log={child_log}")

    write_state(
        **{
            f"{phase_key}_finished_at": datetime.now().isoformat(timespec="seconds"),
            f"{phase_key}_return_codes": return_codes,
        }
    )
    log(f"{label} done return_codes={return_codes}")
    return return_codes


def run_r2_upload(label: str, upload_key: str, extra_env: dict[str, str]) -> int | None:
    if not UPLOAD_R2_AFTER_PHASE:
        log(f"{label} R2 upload skipped by COMBINED_CRAWL_UPLOAD_R2_AFTER_PHASE=0")
        return None

    env = {**os.environ, **extra_env, "PYTHONIOENCODING": "utf-8"}
    child_log = LOG_DIR / f"r2_upload_{upload_key}_{STAMP}.log"
    log(f"{label} R2 upload start log={child_log}")
    write_state(**{f"{upload_key}_r2_started_at": datetime.now().isoformat(timespec="seconds")})

    with child_log.open("a", encoding="utf-8", errors="replace") as handle:
        try:
            proc = subprocess.run(
                [PYTHON, "scripts/upload_images_to_r2.py"],
                env=env,
                cwd=str(ROOT),
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=R2_UPLOAD_TIMEOUT,
            )
            code: int | None = proc.returncode
        except subprocess.TimeoutExpired:
            code = None
            log(f"{label} R2 upload timeout after {R2_UPLOAD_TIMEOUT}s log={child_log}")

    write_state(
        **{
            f"{upload_key}_r2_finished_at": datetime.now().isoformat(timespec="seconds"),
            f"{upload_key}_r2_return_code": code,
            f"{upload_key}_r2_log": str(child_log),
        }
    )
    log(f"{label} R2 upload done exit={code} log={child_log}")
    return code


if __name__ == "__main__":
    log(
        "AdScope Combined Crawler start "
        f"phase_timeout={PHASE_TIMEOUT}s main_log={MAIN_LOG}"
    )
    write_state(
        run_started_at=datetime.now().isoformat(timespec="seconds"),
        phase_timeout=PHASE_TIMEOUT,
        main_log=str(MAIN_LOG),
    )

    phase1_cmds = [[PYTHON, "scripts/fast_crawl.py"]]
    if os.environ.get("COMBINED_CRAWL_RUN_DA", "1") != "0":
        phase1_cmds.append([PYTHON, "scripts/run_da_crawl.py"])
    phase1_env = {"CRAWL_MODE": "naver_only", "CRAWL_TIMEOUT": str(PHASE_TIMEOUT)}
    run_phase(
        "Phase 1: Naver/Kakao",
        "phase1",
        phase1_cmds,
        phase1_env,
    )
    run_r2_upload("Phase 1: Naver/Kakao", "phase1", phase1_env)

    phase2_env = {"CRAWL_MODE": "catalog_only", "CRAWL_TIMEOUT": str(PHASE_TIMEOUT)}
    run_phase(
        "Phase 2: Catalog channels",
        "phase2",
        [[PYTHON, "scripts/fast_crawl.py"]],
        phase2_env,
    )
    run_r2_upload("Phase 2: Catalog channels", "phase2", phase2_env)

    write_state(run_finished_at=datetime.now().isoformat(timespec="seconds"))
    log("AdScope Combined Crawler all phases done")
