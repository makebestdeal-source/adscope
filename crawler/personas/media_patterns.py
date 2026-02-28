"""연령대별 미디어 이용 패턴 데이터.

기반 자료:
- 한국인터넷진흥원(KISA) 인터넷이용실태조사 2025
- 나스미디어 NPR(Netizen Profile Research) 2025
- 메조미디어 타겟 오디언스 리포트 2025
- 방송통신위원회 미디어이용행태조사

각 연령대×성별의 실제 인터넷 이용 패턴을 코드화하여
페르소나 스케줄러가 현실적인 시간대에 수집하도록 함.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MediaUsagePattern:
    """연령대별 미디어 이용 패턴."""

    age_group: str
    gender: str

    # ── 이용 시간/빈도 ──
    daily_internet_hours: float  # 일 평균 인터넷 이용시간 (시간)
    mobile_ratio: float  # 모바일 비중 (0~1)
    daily_access_count: int  # 일 평균 접속 횟수

    # ── 피크 시간대 (HH:MM) — 3개씩 ──
    peak_hours_weekday: tuple[str, ...]  # 평일 피크 시간대
    peak_hours_weekend: tuple[str, ...]  # 주말 피크 시간대

    # ── 플랫폼 친화도 (0~1) ──
    platform_affinity: dict[str, float] = field(default_factory=dict)

    # ── 디바이스 선호 ──
    device_preference: str = "galaxy"  # "iphone" | "galaxy" | "pc"
    iphone_ratio: float = 0.30  # 해당 연령의 아이폰 비율


# ─────────────────────────────────────────────
# 12개 연령×성별 미디어 이용 패턴
# ─────────────────────────────────────────────

MEDIA_PATTERNS: dict[tuple[str, str], MediaUsagePattern] = {
    # ── 10대 ──
    ("10대", "남성"): MediaUsagePattern(
        age_group="10대",
        gender="남성",
        daily_internet_hours=4.2,
        mobile_ratio=0.85,
        daily_access_count=25,
        peak_hours_weekday=("16:30", "21:00", "23:00"),
        peak_hours_weekend=("11:00", "15:00", "22:00"),
        platform_affinity={
            "youtube": 0.95,
            "instagram": 0.60,
            "naver": 0.50,
            "tiktok": 0.70,
            "google": 0.40,
            "kakao": 0.30,
        },
        device_preference="iphone",
        iphone_ratio=0.52,
    ),
    ("10대", "여성"): MediaUsagePattern(
        age_group="10대",
        gender="여성",
        daily_internet_hours=4.5,
        mobile_ratio=0.90,
        daily_access_count=30,
        peak_hours_weekday=("16:00", "20:30", "22:30"),
        peak_hours_weekend=("10:30", "14:00", "21:30"),
        platform_affinity={
            "instagram": 0.95,
            "youtube": 0.85,
            "tiktok": 0.80,
            "naver": 0.50,
            "kakao": 0.30,
            "google": 0.30,
        },
        device_preference="iphone",
        iphone_ratio=0.58,
    ),
    # ── 20대 ──
    ("20대", "남성"): MediaUsagePattern(
        age_group="20대",
        gender="남성",
        daily_internet_hours=5.0,
        mobile_ratio=0.80,
        daily_access_count=28,
        peak_hours_weekday=("12:00", "18:30", "22:30"),
        peak_hours_weekend=("11:00", "15:00", "23:00"),
        platform_affinity={
            "youtube": 0.90,
            "naver": 0.70,
            "instagram": 0.65,
            "google": 0.50,
            "kakao": 0.50,
            "tiktok": 0.40,
        },
        device_preference="iphone",
        iphone_ratio=0.55,
    ),
    ("20대", "여성"): MediaUsagePattern(
        age_group="20대",
        gender="여성",
        daily_internet_hours=5.5,
        mobile_ratio=0.85,
        daily_access_count=32,
        peak_hours_weekday=("12:00", "18:00", "22:00"),
        peak_hours_weekend=("10:00", "14:30", "21:00"),
        platform_affinity={
            "instagram": 0.95,
            "youtube": 0.85,
            "naver": 0.70,
            "kakao": 0.55,
            "tiktok": 0.50,
            "google": 0.35,
        },
        device_preference="iphone",
        iphone_ratio=0.60,
    ),
    # ── 30대 ──
    ("30대", "남성"): MediaUsagePattern(
        age_group="30대",
        gender="남성",
        daily_internet_hours=4.5,
        mobile_ratio=0.70,
        daily_access_count=22,
        peak_hours_weekday=("08:00", "12:30", "22:00"),
        peak_hours_weekend=("10:00", "14:00", "21:00"),
        platform_affinity={
            "naver": 0.85,
            "youtube": 0.80,
            "kakao": 0.60,
            "google": 0.45,
            "instagram": 0.30,
            "facebook": 0.15,
        },
        device_preference="galaxy",
        iphone_ratio=0.35,
    ),
    ("30대", "여성"): MediaUsagePattern(
        age_group="30대",
        gender="여성",
        daily_internet_hours=4.8,
        mobile_ratio=0.75,
        daily_access_count=25,
        peak_hours_weekday=("09:30", "12:00", "21:30"),
        peak_hours_weekend=("10:00", "15:00", "21:00"),
        platform_affinity={
            "naver": 0.85,
            "instagram": 0.75,
            "youtube": 0.70,
            "kakao": 0.65,
            "google": 0.35,
            "facebook": 0.20,
        },
        device_preference="galaxy",
        iphone_ratio=0.40,
    ),
    # ── 40대 ──
    ("40대", "남성"): MediaUsagePattern(
        age_group="40대",
        gender="남성",
        daily_internet_hours=3.8,
        mobile_ratio=0.60,
        daily_access_count=18,
        peak_hours_weekday=("07:30", "12:00", "21:00"),
        peak_hours_weekend=("09:00", "14:00", "20:30"),
        platform_affinity={
            "naver": 0.90,
            "youtube": 0.75,
            "kakao": 0.65,
            "google": 0.40,
            "facebook": 0.20,
            "instagram": 0.10,
        },
        device_preference="galaxy",
        iphone_ratio=0.25,
    ),
    ("40대", "여성"): MediaUsagePattern(
        age_group="40대",
        gender="여성",
        daily_internet_hours=4.0,
        mobile_ratio=0.65,
        daily_access_count=20,
        peak_hours_weekday=("09:00", "13:00", "20:00"),
        peak_hours_weekend=("09:30", "13:30", "20:00"),
        platform_affinity={
            "naver": 0.90,
            "youtube": 0.70,
            "kakao": 0.70,
            "instagram": 0.35,
            "google": 0.30,
            "facebook": 0.25,
        },
        device_preference="galaxy",
        iphone_ratio=0.28,
    ),
    # ── 50대 ──
    ("50대", "남성"): MediaUsagePattern(
        age_group="50대",
        gender="남성",
        daily_internet_hours=3.0,
        mobile_ratio=0.50,
        daily_access_count=14,
        peak_hours_weekday=("06:30", "12:00", "20:00"),
        peak_hours_weekend=("08:00", "13:00", "19:30"),
        platform_affinity={
            "naver": 0.95,
            "youtube": 0.65,
            "kakao": 0.60,
            "daum": 0.40,
            "google": 0.25,
            "facebook": 0.15,
        },
        device_preference="pc",
        iphone_ratio=0.15,
    ),
    ("50대", "여성"): MediaUsagePattern(
        age_group="50대",
        gender="여성",
        daily_internet_hours=3.2,
        mobile_ratio=0.55,
        daily_access_count=15,
        peak_hours_weekday=("08:00", "10:30", "20:00"),
        peak_hours_weekend=("09:00", "14:00", "19:30"),
        platform_affinity={
            "naver": 0.95,
            "kakao": 0.70,
            "youtube": 0.60,
            "daum": 0.45,
            "google": 0.20,
            "instagram": 0.15,
        },
        device_preference="pc",
        iphone_ratio=0.18,
    ),
    # ── 60대 ──
    ("60대", "남성"): MediaUsagePattern(
        age_group="60대",
        gender="남성",
        daily_internet_hours=2.2,
        mobile_ratio=0.40,
        daily_access_count=10,
        peak_hours_weekday=("07:00", "10:00", "19:00"),
        peak_hours_weekend=("08:00", "11:00", "19:00"),
        platform_affinity={
            "naver": 0.95,
            "youtube": 0.55,
            "daum": 0.50,
            "kakao": 0.50,
            "google": 0.15,
            "facebook": 0.10,
        },
        device_preference="pc",
        iphone_ratio=0.08,
    ),
    ("60대", "여성"): MediaUsagePattern(
        age_group="60대",
        gender="여성",
        daily_internet_hours=2.0,
        mobile_ratio=0.45,
        daily_access_count=10,
        peak_hours_weekday=("07:30", "10:30", "19:30"),
        peak_hours_weekend=("08:30", "11:00", "19:00"),
        platform_affinity={
            "naver": 0.95,
            "kakao": 0.65,
            "youtube": 0.50,
            "daum": 0.50,
            "google": 0.10,
            "instagram": 0.05,
        },
        device_preference="pc",
        iphone_ratio=0.10,
    ),
}


def get_pattern(age_group: str, gender: str) -> MediaUsagePattern:
    """연령대×성별에 해당하는 미디어 이용 패턴 반환."""
    key = (age_group, gender)
    if key not in MEDIA_PATTERNS:
        raise KeyError(f"미디어 패턴 없음: {age_group} {gender}")
    return MEDIA_PATTERNS[key]


def get_peak_hours(age_group: str, gender: str, day_type: str = "weekday") -> tuple[str, ...]:
    """연령대×성별의 피크 시간대 반환."""
    pattern = get_pattern(age_group, gender)
    if day_type == "weekend":
        return pattern.peak_hours_weekend
    return pattern.peak_hours_weekday
