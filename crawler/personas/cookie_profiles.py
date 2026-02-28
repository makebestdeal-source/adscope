"""연령대별 쿠키 프로필 — 타겟팅 광고 수집을 위한 브라우징 시뮬레이션.

각 연령대×성별이 실제로 방문할 법한 사이트/브랜드 URL을 정의.
크롤링 시작 전 해당 사이트를 방문하여 쿠키를 축적함으로써
광고 플랫폼의 타겟팅 시스템이 해당 연령대에 맞는 광고를 노출하도록 유도.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CookieProfile:
    """연령대별 쿠키 시뮬레이션 프로필."""

    age_group: str
    gender: str
    # 워밍업 사이트 (크롤링 전 방문하여 쿠키 축적)
    warmup_urls: tuple[str, ...]
    # 관심 카테고리 (참고용 — 향후 키워드 확장에 활용)
    interest_categories: tuple[str, ...]
    # 대표 브랜드/제품 (참고용)
    brands: tuple[str, ...]


# ─────────────────────────────────────────────
# 12개 연령×성별 쿠키 프로필
# ─────────────────────────────────────────────

COOKIE_PROFILES: dict[tuple[str, str], CookieProfile] = {
    # ── 10대 남성 ──
    ("10대", "남성"): CookieProfile(
        age_group="10대",
        gender="남성",
        warmup_urls=(
            "https://www.musinsa.com/categories/item/001",  # 무신사 남성패션
            "https://www.nike.com/kr/",  # 나이키
            "https://m.game.naver.com/",  # 네이버 게임
            "https://www.adidas.co.kr/",  # 아디다스
            "https://www.youtube.com/feed/trending",  # 유튜브 트렌딩
        ),
        interest_categories=("패션", "게임", "스포츠", "전자기기"),
        brands=("Nike", "Adidas", "무신사", "Apple", "배달의민족"),
    ),
    # ── 10대 여성 ──
    ("10대", "여성"): CookieProfile(
        age_group="10대",
        gender="여성",
        warmup_urls=(
            "https://www.oliveyoung.co.kr/",  # 올리브영
            "https://www.musinsa.com/categories/item/002",  # 무신사 여성
            "https://www.stylenanda.com/",  # 스타일난다
            "https://www.daiso.co.kr/",  # 다이소
            "https://www.starbucks.co.kr/",  # 스타벅스
        ),
        interest_categories=("뷰티", "패션", "K-POP", "카페"),
        brands=("올리브영", "다이소", "이니스프리", "무신사", "스타벅스"),
    ),
    # ── 20대 남성 ──
    ("20대", "남성"): CookieProfile(
        age_group="20대",
        gender="남성",
        warmup_urls=(
            "https://www.musinsa.com/",  # 무신사
            "https://www.coupang.com/",  # 쿠팡
            "https://toss.im/",  # 토스
            "https://news.naver.com/section/105",  # IT/과학 뉴스
            "https://www.baemin.com/",  # 배달의민족
        ),
        interest_categories=("패션", "테크", "금융", "여행", "자동차"),
        brands=("무신사", "쿠팡", "토스", "삼성", "현대자동차"),
    ),
    # ── 20대 여성 ──
    ("20대", "여성"): CookieProfile(
        age_group="20대",
        gender="여성",
        warmup_urls=(
            "https://www.oliveyoung.co.kr/",  # 올리브영
            "https://www.kurly.com/",  # 마켓컬리
            "https://www.29cm.co.kr/",  # 29CM
            "https://www.zigzag.kr/",  # 지그재그
            "https://ohou.se/",  # 오늘의집
        ),
        interest_categories=("뷰티", "패션", "식품", "인테리어", "여행"),
        brands=("올리브영", "마켓컬리", "29CM", "쿠팡", "무신사"),
    ),
    # ── 30대 남성 ──
    ("30대", "남성"): CookieProfile(
        age_group="30대",
        gender="남성",
        warmup_urls=(
            "https://www.coupang.com/",  # 쿠팡
            "https://land.naver.com/",  # 네이버 부동산
            "https://toss.im/",  # 토스
            "https://auto.naver.com/",  # 네이버 자동차
            "https://news.naver.com/section/101",  # 경제 뉴스
            "https://finance.naver.com/",  # 네이버 금융
        ),
        interest_categories=("부동산", "금융/투자", "자동차", "테크", "육아"),
        brands=("쿠팡", "토스", "직방", "삼성전자", "현대자동차"),
    ),
    # ── 30대 여성 ──
    ("30대", "여성"): CookieProfile(
        age_group="30대",
        gender="여성",
        warmup_urls=(
            "https://www.kurly.com/",  # 마켓컬리
            "https://www.coupang.com/",  # 쿠팡
            "https://ohou.se/",  # 오늘의집
            "https://www.oliveyoung.co.kr/",  # 올리브영
            "https://baby.naver.com/",  # 네이버 아기
            "https://www.ssg.com/",  # SSG
        ),
        interest_categories=("식품", "육아", "인테리어", "뷰티", "건강"),
        brands=("마켓컬리", "쿠팡", "오늘의집", "올리브영", "SSG"),
    ),
    # ── 40대 남성 ──
    ("40대", "남성"): CookieProfile(
        age_group="40대",
        gender="남성",
        warmup_urls=(
            "https://www.coupang.com/",  # 쿠팡
            "https://finance.naver.com/",  # 네이버 금융
            "https://auto.naver.com/",  # 네이버 자동차
            "https://news.naver.com/",  # 네이버 뉴스
            "https://land.naver.com/",  # 네이버 부동산
        ),
        interest_categories=("금융/보험", "자동차", "골프", "부동산", "건강"),
        brands=("삼성", "현대차", "쿠팡", "네이버쇼핑", "KB국민"),
    ),
    # ── 40대 여성 ──
    ("40대", "여성"): CookieProfile(
        age_group="40대",
        gender="여성",
        warmup_urls=(
            "https://www.coupang.com/",  # 쿠팡
            "https://shopping.naver.com/",  # 네이버쇼핑
            "https://www.ssg.com/",  # SSG
            "https://www.kurly.com/",  # 마켓컬리
            "https://display.cjonstyle.com/",  # CJ온스타일
        ),
        interest_categories=("식품", "건강", "교육", "패션", "인테리어"),
        brands=("쿠팡", "SSG", "네이버쇼핑", "LG생활건강", "교원"),
    ),
    # ── 50대 남성 ──
    ("50대", "남성"): CookieProfile(
        age_group="50대",
        gender="남성",
        warmup_urls=(
            "https://shopping.naver.com/",  # 네이버쇼핑
            "https://news.naver.com/",  # 네이버 뉴스
            "https://www.samsung.com/sec/",  # 삼성
            "https://finance.naver.com/",  # 네이버 금융
            "https://www.hanatour.com/",  # 하나투어
        ),
        interest_categories=("건강/의료", "금융", "골프", "뉴스", "여행"),
        brands=("삼성", "LG", "네이버쇼핑", "GS샵", "하나투어"),
    ),
    # ── 50대 여성 ──
    ("50대", "여성"): CookieProfile(
        age_group="50대",
        gender="여성",
        warmup_urls=(
            "https://shopping.naver.com/",  # 네이버쇼핑
            "https://display.cjonstyle.com/",  # CJ온스타일
            "https://www.gsshop.com/",  # GS샵
            "https://www.coupang.com/",  # 쿠팡
            "https://www.hmall.com/",  # 현대홈쇼핑
        ),
        interest_categories=("건강식품", "홈쇼핑", "여행", "패션", "식품"),
        brands=("CJ온스타일", "GS샵", "네이버쇼핑", "쿠팡", "정관장"),
    ),
    # ── 60대 남성 ──
    ("60대", "남성"): CookieProfile(
        age_group="60대",
        gender="남성",
        warmup_urls=(
            "https://shopping.naver.com/",  # 네이버쇼핑
            "https://news.naver.com/",  # 네이버 뉴스
            "https://www.lotteon.com/",  # 롯데온
            "https://finance.naver.com/",  # 네이버 금융
            "https://www.hanatour.com/",  # 하나투어
        ),
        interest_categories=("건강", "뉴스", "여행", "금융", "골프"),
        brands=("삼성", "롯데온", "네이버쇼핑", "하나투어", "종근당"),
    ),
    # ── 60대 여성 ──
    ("60대", "여성"): CookieProfile(
        age_group="60대",
        gender="여성",
        warmup_urls=(
            "https://shopping.naver.com/",  # 네이버쇼핑
            "https://www.hmall.com/",  # 현대홈쇼핑
            "https://display.cjonstyle.com/",  # CJ온스타일
            "https://www.gsshop.com/",  # GS샵
            "https://www.coupang.com/",  # 쿠팡
        ),
        interest_categories=("건강식품", "홈쇼핑", "여행", "식품", "생활"),
        brands=("현대홈쇼핑", "CJ온스타일", "네이버쇼핑", "정관장", "풀무원"),
    ),
}

# ── 제어 그룹: 리타겟팅 비교용 ──
RETARGET_WARMUP_URLS = (
    "https://www.coupang.com/",
    "https://shopping.naver.com/",
    "https://www.ssg.com/",
    "https://www.musinsa.com/",
    "https://www.oliveyoung.co.kr/",
    "https://www.11st.co.kr/",
    "https://www.lotteon.com/",
)


def get_cookie_profile(age_group: str, gender: str) -> CookieProfile | None:
    """연령대×성별에 해당하는 쿠키 프로필 반환. 없으면 None."""
    return COOKIE_PROFILES.get((age_group, gender))


def get_warmup_urls(age_group: str | None, gender: str | None, is_retarget: bool = False) -> tuple[str, ...]:
    """워밍업 URL 반환. 제어 그룹 리타겟팅용 URL도 지원."""
    if is_retarget:
        return RETARGET_WARMUP_URLS
    if age_group and gender:
        profile = get_cookie_profile(age_group, gender)
        if profile:
            return profile.warmup_urls
    return ()
