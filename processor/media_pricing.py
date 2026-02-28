"""매체별 광고 단가 테이블.

각 매체의 광고 가이드 기반 단가 데이터.
단가 범위(min/max)로 보수적~공격적 추정 모두 지원.
"""

from __future__ import annotations

# ──────────────────────────────────────────────
# 네이버 검색광고 (파워링크 + 비즈사이트)
# ──────────────────────────────────────────────
NAVER_SEARCH_PRICING = {
    "powerlink": {
        "model": "CPC",
        "position_click_share": {
            1: 0.24, 2: 0.18, 3: 0.13,  # 상단 (top)
            4: 0.10, 5: 0.08, 6: 0.07,  # 중단 (middle)
            7: 0.06, 8: 0.05, 9: 0.05, 10: 0.04,  # 하단 (bottom)
        },
        "zone_ranges": {
            "top": (1, 3),
            "middle": (4, 6),
            "bottom": (7, 10),
        },
    },
    "bizsite": {
        "model": "CPC",
        "position_click_share": {1: 0.04, 2: 0.03, 3: 0.02},
        "zone": "bottom",
    },
}

# ──────────────────────────────────────────────
# 네이버 DA (디스플레이 광고)
# ──────────────────────────────────────────────
NAVER_DA_PRICING = {
    "naver_main_timeboard": {
        "model": "CPT",
        "daily_rate_range": (15_000_000, 30_000_000),
        "zone": "top",
        "device": "pc",
    },
    "naver_main_rolling_board": {
        "model": "CPM",
        "cpm_range": (3_000, 8_000),
        "zone": "top",
        "device": "pc",
    },
    "naver_main_smart_channel": {
        "model": "CPM",
        "cpm_range": (2_000, 5_000),
        "zone": "top",
        "device": "mobile",
    },
    "naver_main_feed_da": {
        "model": "CPM",
        "cpm_range": (1_500, 4_000),
        "zone": "bottom",
        "device": "all",
    },
    "naver_main_branding_da": {
        "model": "CPT",
        "daily_rate_range": (8_000_000, 20_000_000),
        "zone": "middle",
        "device": "all",
    },
    "naver_main_shopping_da": {
        "model": "CPM",
        "cpm_range": (1_000, 3_000),
        "zone": "middle",
        "device": "all",
    },
}

# ──────────────────────────────────────────────
# 카카오 DA
# ──────────────────────────────────────────────
KAKAO_PRICING = {
    "kakao_bizboard_chat": {
        "model": "CPM",
        "cpm_range": (2_000, 6_000),
        "zone": "top",
        "device": "mobile",
    },
    "kakao_bizboard_daum": {
        "model": "CPM",
        "cpm_range": (1_500, 4_000),
        "zone": "top",
        "device": "all",
    },
    "kakao_content_da": {
        "model": "CPM",
        "cpm_range": (1_000, 3_000),
        "zone": "middle",
        "device": "all",
    },
}

# ──────────────────────────────────────────────
# 구글 GDN (애드센스)
# ──────────────────────────────────────────────
GOOGLE_GDN_PRICING = {
    "adsense_display": {
        "model": "CPC",
        "avg_ctr": 0.0005,  # 0.05%
        "industry_cpc": {
            "금융": 1_500,
            "법률": 2_000,
            "의료/뷰티": 800,
            "교육": 600,
            "IT/테크": 700,
            "쇼핑/커머스": 300,
            "여행": 500,
            "부동산": 1_000,
            "자동차": 900,
            "음식/외식": 200,
            "엔터테인먼트": 250,
            "뷰티/패션": 400,
            "기타": 400,
        },
        "zone": "middle",
    },
}

# ──────────────────────────────────────────────
# 메타 (Facebook / Instagram)
# ──────────────────────────────────────────────
META_PRICING = {
    "meta_feed_ad": {
        "model": "CPM",
        "cpm_range": (3_000, 12_000),
        "zone": "middle",
    },
    "meta_stories_ad": {
        "model": "CPM",
        "cpm_range": (2_000, 8_000),
        "zone": "top",
    },
    "meta_reels_ad": {
        "model": "CPV",
        "cpv_range": (30, 100),
        "zone": "middle",
    },
}

# ──────────────────────────────────────────────
# 유튜브
# ──────────────────────────────────────────────
YOUTUBE_PRICING = {
    "youtube_preroll": {
        "model": "CPV",
        "cpv_range": (20, 80),
        "zone": "top",
    },
    "youtube_promoted_search": {
        "model": "CPV",
        "cpv_range": (15, 60),
        "zone": "top",
    },
    "youtube_display_banner": {
        "model": "CPM",
        "cpm_range": (2_000, 5_000),
        "zone": "middle",
    },
}

# ──────────────────────────────────────────────
# 업종별 CPC 테이블 (네이버 검색 기준, 원)
# ──────────────────────────────────────────────
INDUSTRY_CPC_TABLE = {
    "금융": {"min": 800, "max": 5_000, "avg": 2_500},
    "법률": {"min": 1_500, "max": 8_000, "avg": 4_000},
    "의료/뷰티": {"min": 500, "max": 3_000, "avg": 1_200},
    "교육": {"min": 300, "max": 2_500, "avg": 800},
    "IT/테크": {"min": 400, "max": 3_000, "avg": 1_000},
    "쇼핑/커머스": {"min": 100, "max": 1_500, "avg": 500},
    "여행": {"min": 200, "max": 2_000, "avg": 700},
    "부동산": {"min": 500, "max": 4_000, "avg": 1_500},
    "자동차": {"min": 400, "max": 3_500, "avg": 1_200},
    "음식/외식": {"min": 100, "max": 1_000, "avg": 350},
    "엔터테인먼트": {"min": 100, "max": 800, "avg": 300},
    "뷰티/패션": {"min": 200, "max": 1_500, "avg": 600},
}

# ──────────────────────────────────────────────
# 매체별 일평균 페이지뷰 추정 (노출 기반 계산용)
# ──────────────────────────────────────────────
DAILY_PAGEVIEWS = {
    "naver_main": 30_000_000,       # 네이버 메인 일 PV
    "naver_search": 50_000_000,     # 네이버 검색 일 PV
    "facebook": 20_000_000,        # 페이스북 일 DAU (한국)
    "daum_main": 8_000_000,         # 다음 메인 일 PV
    "kakao_chat": 25_000_000,       # 카카오톡 일 DAU (비즈보드 노출)
    "yna_news": 3_000_000,          # 연합뉴스 일 PV
    "donga_news": 2_000_000,        # 동아일보 일 PV
}


# ──────────────────────────────────────────────
# 유틸리티
# ──────────────────────────────────────────────

def get_channel_pricing(channel: str) -> dict:
    """채널명으로 전체 단가 딕셔너리 반환."""
    _MAP = {
        "naver_search": NAVER_SEARCH_PRICING,
        "naver_da": NAVER_DA_PRICING,
        "kakao_da": KAKAO_PRICING,
        "google_gdn": GOOGLE_GDN_PRICING,
        "facebook": META_PRICING,
        "instagram": META_PRICING,
        "youtube_ads": YOUTUBE_PRICING,
    }
    return _MAP.get(channel, {})


def get_placement_pricing(channel: str, placement: str) -> dict | None:
    """채널 + 지면 코드로 단가 정보 반환."""
    pricing = get_channel_pricing(channel)
    return pricing.get(placement)


def get_industry_cpc(industry_name: str, channel: str = "naver_search") -> int:
    """업종명으로 평균 CPC 반환."""
    if channel == "google_gdn":
        gdn_pricing = GOOGLE_GDN_PRICING.get("adsense_display", {})
        return gdn_pricing.get("industry_cpc", {}).get(industry_name, 400)
    return INDUSTRY_CPC_TABLE.get(industry_name, {}).get("avg", 500)


def get_cpm_midpoint(cpm_range: tuple[int, int]) -> float:
    """CPM 범위의 중간값 반환 (보수적 추정)."""
    return (cpm_range[0] + cpm_range[1]) / 2


def get_cpt_midpoint(daily_rate_range: tuple[int, int]) -> float:
    """CPT 일 단가 범위의 중간값 반환."""
    return (daily_rate_range[0] + daily_rate_range[1]) / 2
