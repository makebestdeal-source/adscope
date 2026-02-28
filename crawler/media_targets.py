"""Curated Korean media targets and low-cost target selection helpers.

Traffic-oriented baseline (for prioritization):
- Similarweb Korea top sites snapshot: December 2025
- Semrush South Korea top sites snapshot: December 2025

The exact rankings are volatile; this module is designed to make updates easy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib


@dataclass(frozen=True)
class MediaTarget:
    channel: str
    name: str
    url: str
    tier: str  # core | secondary | extended
    rank_hint: int  # lower means more traffic-priority


MEDIA_TARGETS: list[MediaTarget] = [
    # ═══ Google GDN publisher surfaces (KR) ═══

    # ── core (8개): 트래픽 최상위, GDN 슬롯 밀도 높음 ──
    MediaTarget("google_gdn", "Daum Main", "https://www.daum.net/", "core", 1),
    MediaTarget("google_gdn", "Maeil Business", "https://www.mk.co.kr/", "core", 2),
    MediaTarget("google_gdn", "Yonhap News", "https://www.yna.co.kr/", "core", 3),
    MediaTarget("google_gdn", "Donga", "https://www.donga.com/", "core", 4),
    MediaTarget("google_gdn", "Chosun", "https://www.chosun.com/", "core", 5),
    MediaTarget("google_gdn", "JoongAng", "https://www.joongang.co.kr/", "core", 6),
    MediaTarget("google_gdn", "Nate", "https://www.nate.com/", "core", 7),
    MediaTarget("google_gdn", "ZUM", "https://zum.com/", "core", 8),

    # ── secondary (14개): 방송사 + 경제지 + 포털/커뮤니티 ──
    MediaTarget("google_gdn", "Hankyung", "https://www.hankyung.com/", "secondary", 9),
    MediaTarget("google_gdn", "Kukmin Ilbo", "https://www.kmib.co.kr/", "secondary", 10),
    MediaTarget("google_gdn", "Hani", "https://www.hani.co.kr/", "secondary", 11),
    MediaTarget("google_gdn", "SBS News", "https://news.sbs.co.kr/", "secondary", 12),
    MediaTarget("google_gdn", "KBS News", "https://news.kbs.co.kr/", "secondary", 13),
    MediaTarget("google_gdn", "MBC News", "https://imnews.imbc.com/", "secondary", 14),
    MediaTarget("google_gdn", "Seoul Economy", "https://www.sedaily.com/", "secondary", 15),
    MediaTarget("google_gdn", "Asia Economy", "https://www.asiae.co.kr/", "secondary", 16),
    # 커뮤니티/포럼
    MediaTarget("google_gdn", "DCinside", "https://www.dcinside.com/", "secondary", 17),
    MediaTarget("google_gdn", "FMKorea", "https://www.fmkorea.com/", "secondary", 18),
    MediaTarget("google_gdn", "Clien", "https://www.clien.net/", "secondary", 19),
    # 라이프스타일/여성
    MediaTarget("google_gdn", "Woman Donga", "https://woman.donga.com/", "secondary", 20),
    MediaTarget("google_gdn", "Allure Korea", "https://www.allurekorea.com/", "secondary", 21),
    MediaTarget("google_gdn", "Cosmopolitan KR", "https://www.cosmopolitan.co.kr/", "secondary", 22),

    # ── extended (18개): 전문지 + IT/게임 + 유틸리티 + 스포츠 ──
    MediaTarget("google_gdn", "ETNews", "https://www.etnews.com/", "extended", 23),
    MediaTarget("google_gdn", "Edaily", "https://www.edaily.co.kr/", "extended", 24),
    MediaTarget("google_gdn", "Newsis", "https://www.newsis.com/", "extended", 25),
    MediaTarget("google_gdn", "Herald Economy", "https://biz.heraldcorp.com/", "extended", 26),
    MediaTarget("google_gdn", "Digital Daily", "https://www.ddaily.co.kr/", "extended", 27),
    # IT/게임/테크
    MediaTarget("google_gdn", "Inven", "https://www.inven.co.kr/", "extended", 28),
    MediaTarget("google_gdn", "Ruliweb", "https://bbs.ruliweb.com/", "extended", 29),
    MediaTarget("google_gdn", "Bloter", "https://www.bloter.net/", "extended", 30),
    MediaTarget("google_gdn", "ITWorld KR", "https://www.itworld.co.kr/", "extended", 31),
    # 스포츠/엔터
    MediaTarget("google_gdn", "Sports Chosun", "https://sports.chosun.com/", "extended", 32),
    MediaTarget("google_gdn", "Sports Donga", "https://sports.donga.com/", "extended", 33),
    MediaTarget("google_gdn", "OSEN", "https://www.osen.co.kr/", "extended", 34),
    MediaTarget("google_gdn", "Star News", "https://www.starnewskorea.com/", "extended", 35),
    # 자동차/부동산/건강
    MediaTarget("google_gdn", "Motorgraph", "https://www.motorgraph.com/", "extended", 36),
    MediaTarget("google_gdn", "Autodaily", "https://www.autodaily.co.kr/", "extended", 37),
    MediaTarget("google_gdn", "Health Chosun", "https://health.chosun.com/", "extended", 38),
    # 날씨/유틸
    MediaTarget("google_gdn", "Weather.com KR", "https://www.weather.com/ko-KR/", "extended", 39),
    MediaTarget("google_gdn", "AccuWeather KR", "https://www.accuweather.com/ko/kr/", "extended", 40),

    # ═══ Kakao DA media surfaces ═══

    # ── core (3개) ──
    MediaTarget("kakao_da", "Daum Main", "https://www.daum.net/", "core", 1),
    MediaTarget("kakao_da", "Daum Mobile", "https://m.daum.net/", "core", 2),
    MediaTarget("kakao_da", "Daum News", "https://news.daum.net/", "core", 3),
    # ── secondary (5개) ──
    MediaTarget("kakao_da", "Daum Finance", "https://finance.daum.net/", "secondary", 4),
    MediaTarget("kakao_da", "Daum Sports", "https://sports.daum.net/", "secondary", 5),
    MediaTarget("kakao_da", "Daum Entertainment", "https://entertain.daum.net/", "secondary", 6),
    MediaTarget("kakao_da", "KakaoView", "https://v.daum.net/", "secondary", 7),
    # shopping.daum.net 제거 (DNS 미존재 → ERR_NAME_NOT_RESOLVED)
    # 대체: 카카오 네트워크 파트너 앱 웹사이트
    MediaTarget("kakao_da", "Ohou (오늘의집)", "https://ohou.se/", "secondary", 8),
    # ── extended (7개): 카카오 네트워크 외부 매체 + 파트너 앱 ──
    MediaTarget("kakao_da", "Daum Cafe", "https://top.cafe.daum.net/", "extended", 9),
    MediaTarget("kakao_da", "Daum Webtoon", "https://webtoon.kakao.com/", "extended", 10),
    MediaTarget("kakao_da", "Tistory Main", "https://www.tistory.com/", "extended", 11),
    MediaTarget("kakao_da", "Brunch", "https://brunch.co.kr/", "extended", 12),
    # 파트너 앱 웹사이트 (AdFit 광고 수집)
    MediaTarget("kakao_da", "KakaoPage", "https://page.kakao.com/", "extended", 13),
    MediaTarget("kakao_da", "ZigZag", "https://zigzag.kr/", "extended", 14),
    MediaTarget("kakao_da", "Ohou Projects", "https://ohou.se/projects", "extended", 15),
    MediaTarget("kakao_da", "Ohou Store", "https://ohou.se/store", "extended", 16),
]


PROFILE_RULES = {
    # Lowest operational cost:
    # - core only
    # - small rotating sample
    "lean": {"tiers": {"core"}, "default_limit": 2},
    # Default production blend:
    "balanced": {"tiers": {"core", "secondary"}, "default_limit": 4},
    # Broadest coverage:
    "full": {"tiers": {"core", "secondary", "extended"}, "default_limit": 8},
}


def _stable_start_index(channel: str, seed: str, size: int) -> int:
    if size <= 0:
        return 0
    digest = hashlib.sha256(f"{channel}|{seed}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % size


def select_media_targets(
    channel: str,
    profile: str = "lean",
    hard_limit: int | None = None,
    rotation_key: str | None = None,
) -> list[str]:
    """Return URL list for a channel under profile/limit with deterministic rotation."""
    profile_key = profile if profile in PROFILE_RULES else "lean"
    rule = PROFILE_RULES[profile_key]

    candidates = [m for m in MEDIA_TARGETS if m.channel == channel and m.tier in rule["tiers"]]
    candidates.sort(key=lambda m: m.rank_hint)

    if not candidates:
        return []

    limit = hard_limit if hard_limit and hard_limit > 0 else rule["default_limit"]
    limit = max(1, min(limit, len(candidates)))

    if limit >= len(candidates):
        return [m.url for m in candidates]

    seed = rotation_key or datetime.utcnow().strftime("%Y%m%d%H")
    start = _stable_start_index(channel, seed, len(candidates))
    rotated = [candidates[(start + i) % len(candidates)] for i in range(limit)]
    return [m.url for m in rotated]
