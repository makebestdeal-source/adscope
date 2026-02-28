"""페르소나 프로필 정의 — 14명 (12명 인구통계 + 2명 제어그룹).

Phase 3B: 연령대별 미디어 이용 패턴 기반 페르소나 확장.
10~60대 × 남녀 = 12명 + CTRL_CLEAN + CTRL_RETARGET = 14명.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PersonaProfile:
    code: str
    age_group: str | None
    gender: str | None
    login_type: str  # "naver" | "none"
    description: str
    # 네이버 로그인 쿠키 키 (환경변수에서 로드)
    cookie_env_key: str | None = None
    # ── Phase 3B 확장 필드 ──
    targeting_category: str = "demographic"  # "demographic", "control"
    is_clean: bool = False  # True면 쿠키 워밍업 스킵
    primary_device: str = "mobile_galaxy"  # "mobile_iphone", "mobile_galaxy", "pc"


# 14명 페르소나 — 비로그인, 쿠키 워밍업으로 타겟팅 유도
PERSONAS: dict[str, PersonaProfile] = {
    # ── 10대 (아이폰 위주, 방과후~심야 활동) ──
    "M10": PersonaProfile(
        code="M10",
        age_group="10대",
        gender="남성",
        login_type="none",
        description="10대 남성 — 방과후+심야, 게임·스포츠 관심",
        targeting_category="demographic",
        primary_device="mobile_iphone",
    ),
    "F10": PersonaProfile(
        code="F10",
        age_group="10대",
        gender="여성",
        login_type="none",
        description="10대 여성 — 방과후+저녁, 뷰티·패션·K-POP",
        targeting_category="demographic",
        primary_device="mobile_iphone",
    ),
    # ── 20대 (아이폰 위주, 점심+퇴근+심야) ──
    "M20": PersonaProfile(
        code="M20",
        age_group="20대",
        gender="남성",
        login_type="none",
        description="20대 남성 — 점심+퇴근+심야, 테크·패션",
        targeting_category="demographic",
        primary_device="mobile_iphone",
    ),
    "F20": PersonaProfile(
        code="F20",
        age_group="20대",
        gender="여성",
        login_type="none",
        description="20대 여성 — 점심+퇴근+저녁, 뷰티·식품·패션",
        targeting_category="demographic",
        primary_device="mobile_iphone",
    ),
    # ── 30대 (갤럭시 위주, 출퇴근+점심+저녁) ──
    "M30": PersonaProfile(
        code="M30",
        age_group="30대",
        gender="남성",
        login_type="none",
        description="30대 남성 — 출퇴근+점심, 부동산·금융·자동차",
        targeting_category="demographic",
        primary_device="mobile_galaxy",
    ),
    "F30": PersonaProfile(
        code="F30",
        age_group="30대",
        gender="여성",
        login_type="none",
        description="30대 여성 — 오전+점심+저녁, 육아·식품·인테리어",
        targeting_category="demographic",
        primary_device="mobile_galaxy",
    ),
    # ── 40대 (갤럭시 위주, 출근+점심+저녁) ──
    "M40": PersonaProfile(
        code="M40",
        age_group="40대",
        gender="남성",
        login_type="none",
        description="40대 남성 — 출근+점심+저녁, 금융·자동차·골프",
        targeting_category="demographic",
        primary_device="mobile_galaxy",
    ),
    "F40": PersonaProfile(
        code="F40",
        age_group="40대",
        gender="여성",
        login_type="none",
        description="40대 여성 — 오전+오후+저녁, 교육·건강·식품",
        targeting_category="demographic",
        primary_device="mobile_galaxy",
    ),
    # ── 50대 (PC 위주, 이른아침+점심+저녁) ──
    "M50": PersonaProfile(
        code="M50",
        age_group="50대",
        gender="남성",
        login_type="none",
        description="50대 남성 — 이른아침+점심+저녁, 건강·금융·뉴스",
        targeting_category="demographic",
        primary_device="pc",
    ),
    "F50": PersonaProfile(
        code="F50",
        age_group="50대",
        gender="여성",
        login_type="none",
        description="50대 여성 — 오전+오전2+저녁, 건강식품·홈쇼핑",
        targeting_category="demographic",
        primary_device="pc",
    ),
    # ── 60대 (PC 위주, 이른아침+오전+저녁) ──
    "M60": PersonaProfile(
        code="M60",
        age_group="60대",
        gender="남성",
        login_type="none",
        description="60대 남성 — 이른아침+오전+저녁, 건강·뉴스·여행",
        targeting_category="demographic",
        primary_device="pc",
    ),
    "F60": PersonaProfile(
        code="F60",
        age_group="60대",
        gender="여성",
        login_type="none",
        description="60대 여성 — 오전+오전2+저녁, 홈쇼핑·건강식품",
        targeting_category="demographic",
        primary_device="pc",
    ),
    # ── 제어 그룹 ──
    "CTRL_CLEAN": PersonaProfile(
        code="CTRL_CLEAN",
        age_group=None,
        gender=None,
        login_type="none",
        description="깨끗한 브라우저 — 타겟팅 없는 기준점",
        targeting_category="control",
        is_clean=True,
        primary_device="pc",
    ),
    "CTRL_RETARGET": PersonaProfile(
        code="CTRL_RETARGET",
        age_group=None,
        gender=None,
        login_type="none",
        description="쇼핑쿠키 주입 — 리타겟팅 비교용",
        targeting_category="control",
        is_clean=False,
        primary_device="mobile_galaxy",
    ),
}
