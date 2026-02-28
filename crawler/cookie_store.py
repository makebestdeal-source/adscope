"""페르소나별 쿠키 영속화 — 세션 간 쿠키 저장/복원.

쿠키 프로필이 여러 크롤 세션에 걸쳐 축적되도록 하여
광고 타겟팅 시스템이 안정적인 사용자 프로필을 구축할 수 있게 함.

저장 경로: {cookie_dir}/{persona_code}/{channel}.json
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

_DEFAULT_COOKIE_DIR = os.path.join(os.path.dirname(__file__), "..", "cookie_data")


class CookieStore:
    """파일 기반 쿠키 영속화 스토어."""

    def __init__(self, cookie_dir: str | None = None):
        self.cookie_dir = Path(cookie_dir or os.getenv("COOKIE_STORE_DIR", _DEFAULT_COOKIE_DIR))
        self.max_age_days = int(os.getenv("COOKIE_MAX_AGE_DAYS", "30"))

    def _path(self, persona_code: str, channel: str) -> Path:
        return self.cookie_dir / persona_code / f"{channel}.json"

    def load(self, persona_code: str, channel: str) -> list[dict]:
        """저장된 쿠키 로드. 없거나 만료되면 빈 리스트 반환."""
        path = self._path(persona_code, channel)
        if not path.exists():
            return []

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            updated_at = datetime.fromisoformat(data.get("updated_at", "2000-01-01"))
            age_days = (datetime.now(UTC) - updated_at).days
            if age_days > self.max_age_days:
                logger.debug("[cookie-store] {} {} 만료 ({}일), 삭제", persona_code, channel, age_days)
                path.unlink(missing_ok=True)
                return []

            cookies = data.get("cookies", [])
            logger.debug("[cookie-store] {} {} 로드: {}개 쿠키", persona_code, channel, len(cookies))
            return cookies
        except Exception as e:
            logger.warning("[cookie-store] {} {} 로드 실패: {}", persona_code, channel, e)
            return []

    def save(self, persona_code: str, channel: str, cookies: list[dict]):
        """쿠키를 파일에 저장."""
        if not cookies:
            return

        path = self._path(persona_code, channel)
        path.parent.mkdir(parents=True, exist_ok=True)

        # 민감 쿠키 필터 (세션 토큰 등은 제외)
        safe_cookies = [c for c in cookies if not self._is_sensitive(c)]

        data = {
            "persona_code": persona_code,
            "channel": channel,
            "updated_at": datetime.now(UTC).isoformat(),
            "cookie_count": len(safe_cookies),
            "cookies": safe_cookies,
        }

        try:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.debug("[cookie-store] {} {} 저장: {}개 쿠키", persona_code, channel, len(safe_cookies))
        except Exception as e:
            logger.warning("[cookie-store] {} {} 저장 실패: {}", persona_code, channel, e)

    def clear(self, persona_code: str | None = None, channel: str | None = None):
        """쿠키 삭제. persona_code만 지정하면 해당 페르소나 전체 삭제."""
        if persona_code and channel:
            path = self._path(persona_code, channel)
            path.unlink(missing_ok=True)
        elif persona_code:
            persona_dir = self.cookie_dir / persona_code
            if persona_dir.exists():
                for f in persona_dir.glob("*.json"):
                    f.unlink()
        else:
            # 전체 삭제
            if self.cookie_dir.exists():
                for f in self.cookie_dir.rglob("*.json"):
                    f.unlink()

    @staticmethod
    def _is_sensitive(cookie: dict) -> bool:
        """보안상 영속화하면 안 되는 쿠키 판별."""
        name = (cookie.get("name") or "").lower()
        sensitive_prefixes = ("nid_", "sid", "ssid", "sapisid", "__secure-", "csrf", "xsrf")
        return any(name.startswith(p) for p in sensitive_prefixes)


# 싱글턴
_store: CookieStore | None = None


def get_cookie_store() -> CookieStore:
    global _store
    if _store is None:
        _store = CookieStore()
    return _store
