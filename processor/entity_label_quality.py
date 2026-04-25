"""Reusable quality checks for advertiser and campaign labels.

These rules catch crawler/parser leakage where person names, CTA copy, or
library/creative identifiers are stored as business-facing labels.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


class LabelQuality(str, Enum):
    VALID = "valid"
    INVALID = "invalid"


@dataclass(frozen=True)
class LabelQualityResult:
    original_label: str
    quality: LabelQuality
    reason: str | None = None
    evidence: str | None = None


_KOREAN_CORP_HINTS = (
    "주식회사",
    "(주)",
    "㈜",
    "유한회사",
    "법인",
    "그룹",
    "전자",
    "카드",
    "은행",
    "보험",
    "증권",
    "몰",
    "스토어",
    "마켓",
    "푸드",
    "뷰티",
    "미디어",
    "커머스",
    "랩",
    "랩스",
    "코리아",
)
_ENGLISH_CORP_HINTS = (
    "inc",
    "corp",
    "co",
    "ltd",
    "llc",
    "group",
    "korea",
    "store",
    "shop",
    "mall",
    "media",
    "labs",
)
_KOREAN_SURNAMES = set(
    "김이박최정강조윤장임한오서신권황안송전홍유고문양손배조백허남심노하곽성차주우구민류나진지엄채원천방공현태기사두"
)
_KOREAN_COMPOUND_SURNAMES = {
    "남궁",
    "황보",
    "제갈",
    "사공",
    "선우",
    "서문",
    "독고",
    "동방",
}
_KNOWN_PERSON_LABELS = {
    "김민수",
    "이해수",
    "태경호",
    "문한수",
    "최설아",
}
_ENGLISH_FIRST_NAMES = {
    "james",
    "john",
    "robert",
    "michael",
    "william",
    "david",
    "richard",
    "joseph",
    "thomas",
    "daniel",
    "paul",
    "mark",
    "george",
    "kevin",
    "brian",
    "sarah",
    "jessica",
    "emily",
    "ashley",
    "amanda",
    "jennifer",
    "lisa",
    "mary",
    "susan",
    "kim",
    "minji",
    "jiyoung",
    "jihoon",
    "sumin",
    "seoyeon",
    "hyunjin",
    "jisu",
}

_KNOWN_NON_PERSON_LABELS = {
    "오토카",
    "윤선생",
    "박문각",
    "안다르",
    "정관장",
    "나이키",
    "나비엔",
    "이투스",
    "이사몰",
    "유가네",
    "고혼진",
    "두레블",
    "구스켓",
    "이응이",
    "유세린",
    "조블핀",
    "오프온",
    "하늘론",
    "사라바",
    "오로쉬",
    "공단기",
    "나비잠",
    "오랄비",
    "차오르",
    "하이폰",
    "고고런",
    "고로롱",
    "방구맨",
    "사커붐",
    "이달심",
    "이사뿐",
    "이유팡",
    "이컬리",
    "이타가",
    "오필리",
    "유쉴드",
}
_KOREAN_BRAND_SUFFIXES = (
    "몰",
    "샵",
    "스토어",
    "스",
    "뷰",
    "카",
    "진",
    "키",
    "랩",
    "넷",
    "컴",
)

_CTA_LABELS = {
    "learn more",
    "shop now",
    "sign up",
    "subscribe",
    "download",
    "apply now",
    "book now",
    "contact us",
    "send message",
    "visit website",
    "watch more",
    "get offer",
    "더보기",
    "자세히 보기",
    "자세히보기",
    "알아보기",
    "구매하기",
    "신청하기",
    "가입하기",
    "다운로드",
    "문의하기",
    "바로가기",
    "예약하기",
    "상담하기",
    "쇼핑하기",
}

_LONG_NUMERIC_ID = re.compile(r"^\d{8,}$")
_CREATIVE_ID = re.compile(r"^[Cc][Rr]\d{4,}$")
_CHANNEL_ID = re.compile(
    r"^(?:google_search|google_search_ads|google_gdn|gdn_transparency|google_gdn_transparency|"
    r"youtube_transparency|youtube_ads|meta_library|"
    r"facebook_library|tiktok_creative|naver_search|naver_shopping|kakao_da)[_-]\d+$",
    re.IGNORECASE,
)
_RAW_LIBRARY_ID = re.compile(
    r"^(?:library|ad|creative|campaign|material|page)[\s_-]*(?:id)?[\s:#_-]*\d{6,}$",
    re.IGNORECASE,
)
_LIBRARY_ID_TEXT = re.compile(
    r"(?:library|라이브러리|광고|ad|creative|campaign|material)[\s_-]*id\s*[:#-]?\s*\d{6,}",
    re.IGNORECASE,
)
_UUIDISH = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_HASHISH = re.compile(r"^[0-9a-f]{16,}$", re.IGNORECASE)
_KOREAN_PERSON = re.compile(r"^[가-힣]{2,4}$")
_ENGLISH_PERSON = re.compile(r"^[A-Z][a-z]{2,20}\s+[A-Z][a-z]{2,20}$")
_DURATION_ONLY = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?\s*/\s*\d{1,2}:\d{2}(?::\d{2})?$")
_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\ufeff]")
_META_LIBRARY_PREFIX = re.compile(
    r"^(?:활성|비활성)?\s*라이브러리\s*ID\s*:\s*\d{6,}.*?(?:광고 상세 정보 보기|요약 세부 사항 보기)\s*",
    re.IGNORECASE | re.DOTALL,
)

_COMMON_KOREAN_GIVEN_NAMES = {
    "가은",
    "경호",
    "다은",
    "도윤",
    "동현",
    "설아",
    "한수",
    "해수",
    "민수",
    "민준",
    "서연",
    "서윤",
    "수빈",
    "수현",
    "시우",
    "예은",
    "예준",
    "유진",
    "은지",
    "정훈",
    "주원",
    "지민",
    "지수",
    "지우",
    "지윤",
    "지훈",
    "하은",
    "현수",
    "현우",
    "혜진",
}


def _compact(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip())


def _has_corp_hint(label: str) -> bool:
    lower = label.lower()
    return any(hint in label for hint in _KOREAN_CORP_HINTS) or any(
        re.search(rf"\b{re.escape(hint)}\.?\b", lower) for hint in _ENGLISH_CORP_HINTS
    )


def _person_name_evidence(label: str) -> str | None:
    if _has_corp_hint(label):
        return None

    compact = label.replace(" ", "")
    if compact in _KNOWN_PERSON_LABELS:
        return "explicit_person_blacklist"
    if compact in _KNOWN_NON_PERSON_LABELS:
        return None
    if len(compact) == 3 and compact.endswith(_KOREAN_BRAND_SUFFIXES):
        return None
    if "앤" in compact or "&" in label:
        return None
    if (
        _KOREAN_PERSON.match(compact)
        and len(compact) == 3
        and compact[0] in _KOREAN_SURNAMES
        and compact[1:] in _COMMON_KOREAN_GIVEN_NAMES
    ):
        return "korean_surname_common_given_name"
    if (
        _KOREAN_PERSON.match(compact)
        and len(compact) == 4
        and compact[:2] in _KOREAN_COMPOUND_SURNAMES
        and compact[2:] in _COMMON_KOREAN_GIVEN_NAMES
    ):
        return "korean_compound_surname_common_given_name"

    if _ENGLISH_PERSON.match(label):
        first = label.split(" ", 1)[0].lower()
        if first in _ENGLISH_FIRST_NAMES:
            return "english_common_first_last_name"

    return None


def _channel_evidence(evidence: str, channel: str | None) -> str:
    if not channel:
        return evidence
    return f"{evidence};channel={channel}"


def validate_entity_label(
    label: str | None,
    field: str = "label",
    channel: str | None = None,
) -> LabelQualityResult:
    """Validate a human-facing advertiser/campaign label.

    Returns INVALID when the value is likely a parser artifact rather than a
    brand, advertiser, or campaign label.
    """
    original = label or ""
    stripped = _compact(original)
    if not stripped:
        return LabelQualityResult(original, LabelQuality.INVALID, "empty_label", None)

    lower = stripped.lower()
    if lower in _CTA_LABELS:
        return LabelQualityResult(original, LabelQuality.INVALID, "generic_cta_label", stripped)

    if _LONG_NUMERIC_ID.match(stripped):
        return LabelQualityResult(original, LabelQuality.INVALID, "long_numeric_id", stripped)
    if _CREATIVE_ID.match(stripped):
        return LabelQualityResult(original, LabelQuality.INVALID, "creative_id_label", stripped)
    if _CHANNEL_ID.match(stripped):
        return LabelQualityResult(original, LabelQuality.INVALID, "channel_library_id", stripped)
    if _RAW_LIBRARY_ID.match(stripped) or _LIBRARY_ID_TEXT.search(stripped):
        return LabelQualityResult(original, LabelQuality.INVALID, "raw_library_id", stripped)
    if _UUIDISH.match(stripped):
        return LabelQualityResult(original, LabelQuality.INVALID, "uuid_label", stripped)
    if _HASHISH.match(stripped):
        return LabelQualityResult(original, LabelQuality.INVALID, "hash_label", stripped)

    person_evidence = _person_name_evidence(stripped)
    if person_evidence:
        return LabelQualityResult(
            original,
            LabelQuality.INVALID,
            f"personal_name_{field}",
            _channel_evidence(person_evidence, channel),
        )

    return LabelQualityResult(original, LabelQuality.VALID, None, None)


def validate_material_text(text: str | None) -> LabelQualityResult:
    """Validate user-facing ad copy/title text.

    This catches parser artifacts that should never be shown as campaign copy,
    such as `youtube_transparency_3`, `google_search_123`, raw library IDs, or
    bare video duration strings.
    """
    original = text or ""
    stripped = _compact(_ZERO_WIDTH.sub(" ", original))
    if not stripped:
        return LabelQualityResult(original, LabelQuality.INVALID, "empty_material_text", None)

    if _DURATION_ONLY.match(stripped):
        return LabelQualityResult(original, LabelQuality.INVALID, "duration_only_text", stripped)

    if _LONG_NUMERIC_ID.match(stripped):
        return LabelQualityResult(original, LabelQuality.INVALID, "long_numeric_id", stripped)
    if _CREATIVE_ID.match(stripped):
        return LabelQualityResult(original, LabelQuality.INVALID, "creative_id_label", stripped)
    if _CHANNEL_ID.match(stripped):
        return LabelQualityResult(original, LabelQuality.INVALID, "channel_library_id", stripped)
    if _RAW_LIBRARY_ID.match(stripped) or _LIBRARY_ID_TEXT.search(stripped):
        return LabelQualityResult(original, LabelQuality.INVALID, "raw_library_id", stripped)
    if _UUIDISH.match(stripped) or _HASHISH.match(stripped):
        return LabelQualityResult(original, LabelQuality.INVALID, "hash_label", stripped)

    return LabelQualityResult(original, LabelQuality.VALID, None, None)


def repair_material_text(text: str | None, extra_data: dict | None = None) -> str | None:
    """Return safe display copy or None when text is just crawler noise."""
    extra = extra_data if isinstance(extra_data, dict) else {}
    original = text or ""
    cleaned = _compact(_ZERO_WIDTH.sub(" ", original))

    for key in (
        "matched_video_title",
        "video_title",
        "creative_title",
        "ad_title",
        "title",
        "headline",
    ):
        value = extra.get(key)
        if isinstance(value, str) and value.strip():
            candidate = _compact(_ZERO_WIDTH.sub(" ", value))
            if validate_material_text(candidate).quality == LabelQuality.VALID:
                return candidate

    landing = extra.get("landing_analysis")
    if isinstance(landing, dict):
        page_title = landing.get("page_title")
        if isinstance(page_title, str) and page_title.strip():
            candidate = _compact(_ZERO_WIDTH.sub(" ", page_title))
            if validate_material_text(candidate).quality == LabelQuality.VALID:
                return candidate

    stripped = _META_LIBRARY_PREFIX.sub("", cleaned).strip()
    if stripped != cleaned and stripped:
        return stripped if validate_material_text(stripped).quality == LabelQuality.VALID else None

    return cleaned if validate_material_text(cleaned).quality == LabelQuality.VALID else None
