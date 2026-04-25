"""쿠키 유틸리티 — 플랫폼별 인증 쿠키 로딩.

brand_monitor.py / social_stats_crawler.py 에서 중복 구현되던 로직을 통합.
"""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

_ROOT = Path(__file__).resolve().parent.parent
_IG_COOKIES_PATH = _ROOT / "ig_cookies.json"


def load_ig_cookies(label: str = "") -> list[dict]:
    """ig_cookies.json에서 Instagram 쿠키를 로드하여 Playwright 형식으로 반환.

    Args:
        label: 로그 메시지에 포함할 호출자 레이블 (예: "brand_monitor").

    Returns:
        Playwright add_cookies() 형식의 쿠키 dict 리스트.
        파일 없음 또는 파싱 실패 시 빈 리스트.
    """
    prefix = f"[{label}] " if label else ""
    if not _IG_COOKIES_PATH.exists():
        logger.warning(f"{prefix}Instagram cookies not found: {_IG_COOKIES_PATH}")
        return []
    try:
        raw = json.loads(_IG_COOKIES_PATH.read_text(encoding="utf-8"))
        cookies: list[dict] = []
        for c in raw:
            cookie: dict = {
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain", ".instagram.com"),
                "path": c.get("path", "/"),
            }
            if c.get("expires") and c["expires"] > 0:
                cookie["expires"] = c["expires"]
            if c.get("httpOnly") is not None:
                cookie["httpOnly"] = c["httpOnly"]
            if c.get("secure") is not None:
                cookie["secure"] = c["secure"]
            if c.get("sameSite"):
                cookie["sameSite"] = c["sameSite"]
            cookies.append(cookie)
        logger.info(f"{prefix}Loaded {len(cookies)} Instagram cookies")
        return cookies
    except Exception as e:
        logger.warning(f"{prefix}Failed to load Instagram cookies: {e}")
        return []
