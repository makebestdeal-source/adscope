"""주말 수집 조정 규칙 — 시즌별 키워드 강화."""

from datetime import date

# 금요일 저녁~토요일: 여행/맛집/문화 키워드 추가
FRIDAY_SATURDAY_BOOST_KEYWORDS = [
    "맛집", "카페", "영화", "전시회", "공연",
    "호텔", "펜션", "글램핑", "워터파크",
    "데이트", "브런치", "와인바",
]

# 일요일~월요일 오전: 금융/업무 키워드 강화
SUNDAY_MONDAY_BOOST_KEYWORDS = [
    "대출", "보험", "적금", "주식",
    "이직", "채용", "연봉", "자격증",
]


def get_weekend_boost_keywords(today: date | None = None) -> list[str]:
    """오늘 요일에 따라 추가 수집할 키워드 반환."""
    if today is None:
        today = date.today()

    weekday = today.weekday()  # 0=월, 4=금, 5=토, 6=일

    if weekday in (4, 5):  # 금, 토
        return FRIDAY_SATURDAY_BOOST_KEYWORDS
    elif weekday in (6, 0):  # 일, 월
        return SUNDAY_MONDAY_BOOST_KEYWORDS

    return []
