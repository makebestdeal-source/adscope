"""쿠키 영속화 스토어 단위 테스트."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawler.cookie_store import CookieStore


def test_save_and_load(tmp_path):
    store = CookieStore(cookie_dir=str(tmp_path))
    cookies = [
        {"name": "tracker", "value": "abc123", "domain": ".example.com", "path": "/"},
        {"name": "pref", "value": "ko", "domain": ".example.com", "path": "/"},
    ]
    store.save("M30", "google_gdn", cookies)
    loaded = store.load("M30", "google_gdn")
    assert len(loaded) == 2
    assert loaded[0]["name"] == "tracker"


def test_load_empty(tmp_path):
    store = CookieStore(cookie_dir=str(tmp_path))
    assert store.load("M30", "naver_search") == []


def test_sensitive_cookies_filtered(tmp_path):
    store = CookieStore(cookie_dir=str(tmp_path))
    cookies = [
        {"name": "SID", "value": "secret", "domain": ".google.com", "path": "/"},
        {"name": "__Secure-token", "value": "secret2", "domain": ".google.com", "path": "/"},
        {"name": "pref", "value": "ok", "domain": ".example.com", "path": "/"},
    ]
    store.save("M30", "google_gdn", cookies)
    loaded = store.load("M30", "google_gdn")
    assert len(loaded) == 1
    assert loaded[0]["name"] == "pref"


def test_clear_persona(tmp_path):
    store = CookieStore(cookie_dir=str(tmp_path))
    store.save("M30", "google_gdn", [{"name": "a", "value": "1", "domain": ".x.com", "path": "/"}])
    store.save("M30", "naver_search", [{"name": "b", "value": "2", "domain": ".y.com", "path": "/"}])
    store.clear("M30")
    assert store.load("M30", "google_gdn") == []
    assert store.load("M30", "naver_search") == []


def test_expired_cookies_cleared(tmp_path):
    store = CookieStore(cookie_dir=str(tmp_path))
    store.max_age_days = 0  # 즉시 만료
    store.save("M30", "google_gdn", [{"name": "old", "value": "x", "domain": ".x.com", "path": "/"}])
    # max_age_days=0이면 updated_at이 오늘이라도 0일 이하 → 통과
    # max_age_days를 -1로 설정하면 반드시 만료
    store.max_age_days = -1
    assert store.load("M30", "google_gdn") == []


def test_save_empty_cookies_noop(tmp_path):
    store = CookieStore(cookie_dir=str(tmp_path))
    store.save("M30", "google_gdn", [])
    assert not (tmp_path / "M30" / "google_gdn.json").exists()
