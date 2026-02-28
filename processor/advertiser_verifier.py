"""광고주명 검증 엔진 — 품질 검증, 정규화, 신뢰도 점수.

DB 삽입 전 광고주명을 검증하여 가비지 데이터 유입을 차단.
pipeline.py, campaign_builder.py에서 사용.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from processor.korean_filter import has_foreign_script, clean_advertiser_name as _clean_adv_name


class NameQuality(str, Enum):
    VALID = "valid"
    REJECTED = "rejected"
    CLEANED = "cleaned"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INVALID = "invalid"


@dataclass
class VerificationResult:
    original_name: str
    cleaned_name: str | None = None
    quality: NameQuality = NameQuality.VALID
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    rejection_reason: str | None = None
    is_known_advertiser: bool = False


# ──────────────────────────────────────────────
# 규칙 데이터
# ──────────────────────────────────────────────

# 광고 시스템 도메인 (광고주명으로 잡히면 가비지)
AD_SYSTEM_DOMAINS = {
    "doubleclick.net", "googlesyndication.com", "adservice.google.com",
    "googleads.g.doubleclick.net", "pagead2.googlesyndication.com",
    "tpc.googlesyndication.com", "safeframe.googlesyndication.com",
    "adcr.naver.com", "ad.naver.com", "searchad.naver.com",
    "adsystem.naver.com", "siape.veta.naver.com", "ader.naver.com",
    "ad.daum.net", "track.tiara.kakao.com",
    "criteo.com", "adroll.com", "rtbhouse.com",
    "taboola.com", "dable.io", "mobon.net",
    # 추가 인프라 도메인
    "widerplanet.com", "tribalfusion.com", "teads.tv",
    "appier.net", "fbsbx.com", "images.dable.io",
}

# 비광고 UI 요소 (pipeline.py NON_AD_ADVERTISER_NAMES 확장)
NON_AD_ELEMENTS = {
    # 네이버 UI
    "네이버 로그인", "네이버로그인", "네이버 톡톡", "네이버톡톡",
    "네이버페이", "NAVER", "네이버 뉴스", "네이버뉴스",
    "네이버 지도", "네이버지도",
    # 네이버 내부 서비스 (하우스 광고)
    "네이버 해피빈", "네이버해피빈", "해피빈", "네이버 해피빈 가볼까",
    # 카카오/구글 UI
    "카카오 로그인", "구글 로그인", "로그인",
    # 검색결과 UI 텍스트 / CTA (광고주 아님)
    "더보기", "더알아보기", "더 알아보기", "접기", "관련뉴스", "이미지검색",
    "검색해보세요", "검색해 보세요", "가볼까",
    "지도", "쇼핑", "뉴스", "사전", "블로그",
    # 크롤러 기본값/플레이스홀더
    "unknown_advertiser", "gdn_display_ad", "display_ad",
    "youtube_video_ad", "youtube_promoted",
}

# URL/도메인 패턴
_URL_PATTERN = re.compile(
    r"^(https?://|www\.)"             # starts with http/www
    r"|^[a-zA-Z0-9][\w.-]+\.[a-z]{2,}$"  # looks like domain.tld
    r"|[\w.-]+\.(com|net|co\.kr|kr|org|io|ai)(/|$)",
    re.IGNORECASE,
)

# 광고시스템 해시 패턴 (예: 9525216b1e63718bf8426bea9f8195e4.safeframe...)
_HASH_PATTERN = re.compile(r"^[0-9a-f]{16,}\.", re.IGNORECASE)

# 카카오 DA 광고코드 패턴 (예: kakao_ad_DAN-xxx, kakao_ad_0Qb49)
_KAKAO_AD_CODE = re.compile(r"^kakao_ad_", re.IGNORECASE)

# GDN 광고코드 패턴 (예: GDN-30637657, GDN-4742661576)
_GDN_AD_CODE = re.compile(r"^GDN-\d+$", re.IGNORECASE)

# 인스타그램 협찬 표기 패턴 (예: "username 페이지는 BrandName과(와) 함께합니다")
_INSTAGRAM_SPONSORED = re.compile(r"페이지는\s+.+과\(와\)\s*함께합니다$")

# 네이버 검색광고 전체 광고문구 (광고주명+URL+설명이 합쳐진 형태)
# 2+ 연속공백이 포함되면 검색광고 전체 텍스트가 잘못 잡힌 것
_NAVER_SEARCH_AD_TEXT = re.compile(r"\s{2,}")

# 네이버 로그인/UI 텍스트가 포함된 긴 문자열
_NAVER_UI_PREFIX = re.compile(
    r"^(네이버\s*(로그인|아이디)|NAVER\s+Direct|KEYWORDAD)",
    re.IGNORECASE,
)

# 네이버페이 인하우스 prefix (DA 광고에서 광고주명 앞에 붙는 플랫폼 텍스트)
_NAVER_PAY_PREFIXES = [
    "네이버페이 네이버 아이디 하나로 간편구매 Naver Pay 서비스 보기",
    "네이버페이 네이버 페이드 하나로 간편결제 Naver Pay 간편 결제",
    "네이버페이 네이버 아이디 하나로 간편결제 Naver Pay",
]

# 숫자/코드만 있는 이름 (예: "Fmx-0205-10", "NDP_SF")
_CODE_ONLY = re.compile(r"^[A-Z0-9_-]{3,}$", re.IGNORECASE)

# 문장형 광고주명 (주어+서술어 패턴, 종결어미로 끝남)
_SENTENCE_ENDINGS = re.compile(
    r"(입니다|합니다|하세요|습니다|됩니다|드립니다|있습|보세요|알아보기|확인!?)$"
)

# URL이 결합된 광고주명에서 URL 부분을 분리
# 패턴: "브랜드명  domain.com", "브랜드명  m.domain.com/path"
_EMBEDDED_URL = re.compile(
    r"\s+"                              # 공백 구분자
    r"(?:https?://|m\.|www\.)?"         # optional protocol/subdomain
    r"[a-zA-Z0-9가-힣][\w.-]*"          # domain name
    r"\."                               # dot
    r"(?:com|net|co\.kr|kr|org|io|ai)"  # TLD
    r"(?:/\S*)?$",                      # optional path
    re.IGNORECASE,
)

# 법인 접미사 제거 -- 괄호로 감싸진 형태만 매칭 (단독 한글자 "주"/"유" 오탈방지)
_CORP_SUFFIXES = re.compile(
    r"\s*[\(\(]\s*"
    r"(?:주식회사|주|株|㈜|유|유한회사|사단법인|재단법인|합자|합명)"
    r"\s*[\)\)]"
    r"|\s*(?:주식회사|㈜|유한회사|사단법인|재단법인)\s*"
    r"|\s+(?:Inc\.?|Corp\.?|Ltd\.?|LLC|Co\.?,?\s*Ltd\.?)\s*$",
    re.IGNORECASE,
)

_EXCESS_SPACE = re.compile(r"\s{2,}")

MAX_NAME_LENGTH = 50
MIN_NAME_LENGTH = 2


# ──────────────────────────────────────────────
# 검증 함수
# ──────────────────────────────────────────────

def validate_name(name: str | None) -> VerificationResult:
    """규칙 기반 광고주명 품질 검증."""
    if not name or not name.strip():
        return VerificationResult(
            original_name=name or "",
            quality=NameQuality.REJECTED,
            confidence=ConfidenceLevel.INVALID,
            rejection_reason="empty_name",
        )

    stripped = name.strip()

    # 네이버페이 인하우스 prefix 제거 → 실제 광고주명 추출
    for prefix in _NAVER_PAY_PREFIXES:
        if prefix in stripped:
            after = stripped.split(prefix, 1)[1].strip()
            # After: "BRAND  domain.com    description"
            parts = re.split(r"\s{4,}", after)
            if parts:
                stripped = parts[0].strip()  # "BRAND  domain.com"
            break

    # 50자 초과 시 첫 의미 단위만 추출 (광고문구 전체가 잡힌 케이스)
    if len(stripped) > MAX_NAME_LENGTH:
        parts = re.split(r"\s{2,}", stripped)
        if parts and len(parts[0]) >= MIN_NAME_LENGTH:
            stripped = parts[0].strip()

    # blog.naver.com URL을 광고주명에서 제거
    stripped = re.sub(r"\s*blog\.naver\.com/\S*", "", stripped).strip()
    stripped = re.sub(r"\s*smartstore\.naver\.com/\S*", "", stripped).strip()
    stripped = re.sub(r"\s*brand\.naver\.com/\S*", "", stripped).strip()

    # 길이 체크
    if len(stripped) < MIN_NAME_LENGTH:
        return VerificationResult(
            original_name=name,
            quality=NameQuality.REJECTED,
            confidence=ConfidenceLevel.INVALID,
            rejection_reason=f"too_short:{len(stripped)}",
        )

    if len(stripped) > MAX_NAME_LENGTH:
        return VerificationResult(
            original_name=name,
            quality=NameQuality.REJECTED,
            confidence=ConfidenceLevel.INVALID,
            rejection_reason=f"too_long:{len(stripped)}",
        )

    # 외국어 스크립트 감지 (베트남어/조지아어/아랍어/태국어/키릴/데바나가리)
    if has_foreign_script(stripped):
        return VerificationResult(
            original_name=name,
            quality=NameQuality.REJECTED,
            confidence=ConfidenceLevel.INVALID,
            rejection_reason="foreign_script",
        )

    # Zero-width / emoji / fullwidth 정제
    sanitized = _clean_adv_name(stripped)
    if sanitized and sanitized != stripped:
        stripped = sanitized

    # 광고시스템 해시
    if _HASH_PATTERN.match(stripped):
        return VerificationResult(
            original_name=name,
            quality=NameQuality.REJECTED,
            confidence=ConfidenceLevel.INVALID,
            rejection_reason="ad_system_hash",
        )

    # 카카오 DA 광고코드
    if _KAKAO_AD_CODE.match(stripped):
        return VerificationResult(
            original_name=name,
            quality=NameQuality.REJECTED,
            confidence=ConfidenceLevel.INVALID,
            rejection_reason="kakao_ad_code",
        )

    # GDN 광고코드
    if _GDN_AD_CODE.match(stripped):
        return VerificationResult(
            original_name=name,
            quality=NameQuality.REJECTED,
            confidence=ConfidenceLevel.INVALID,
            rejection_reason="gdn_ad_code",
        )

    # 광고시스템 도메인 포함 -- URL 패턴보다 먼저 체크
    name_lower = stripped.lower()
    for domain in AD_SYSTEM_DOMAINS:
        if domain in name_lower:
            return VerificationResult(
                original_name=name,
                quality=NameQuality.REJECTED,
                confidence=ConfidenceLevel.INVALID,
                rejection_reason=f"ad_system_domain:{domain}",
            )

    # URL이 결합된 광고주명 → URL 부분 분리 후 브랜드명만 보존
    if _EMBEDDED_URL.search(stripped):
        brand_part = _EMBEDDED_URL.sub("", stripped).strip()
        if brand_part and len(brand_part) >= MIN_NAME_LENGTH:
            stripped = brand_part  # URL 제거 후 브랜드명으로 계속 진행
        # brand_part가 비면 아래 URL 체크에서 reject

    # URL/도메인 패턴 -- 전체가 URL만인 경우 reject (브랜드명 없음)
    if _URL_PATTERN.search(stripped):
        return VerificationResult(
            original_name=name,
            quality=NameQuality.REJECTED,
            confidence=ConfidenceLevel.INVALID,
            rejection_reason="url_or_domain",
        )

    # 비광고 UI 요소
    if stripped in NON_AD_ELEMENTS:
        return VerificationResult(
            original_name=name,
            quality=NameQuality.REJECTED,
            confidence=ConfidenceLevel.INVALID,
            rejection_reason="non_ad_element",
        )

    # 인스타그램 협찬 표기 ("xxx 페이지는 yyy과(와) 함께합니다")
    if _INSTAGRAM_SPONSORED.search(stripped):
        return VerificationResult(
            original_name=name,
            quality=NameQuality.REJECTED,
            confidence=ConfidenceLevel.INVALID,
            rejection_reason="instagram_sponsored_text",
        )

    # 네이버 검색광고 전체 문구 (광고주+URL+설명이 합쳐진 긴 텍스트)
    if len(stripped) > 20 and _NAVER_SEARCH_AD_TEXT.search(stripped):
        return VerificationResult(
            original_name=name,
            quality=NameQuality.REJECTED,
            confidence=ConfidenceLevel.INVALID,
            rejection_reason="naver_search_ad_text",
        )

    # 네이버 UI 접두사가 포함된 문자열
    if _NAVER_UI_PREFIX.match(stripped):
        return VerificationResult(
            original_name=name,
            quality=NameQuality.REJECTED,
            confidence=ConfidenceLevel.INVALID,
            rejection_reason="naver_ui_text",
        )

    # 문장형 이름 (종결어미로 끝나는 문장, 길이 15자+)
    if len(stripped) > 15 and _SENTENCE_ENDINGS.search(stripped):
        return VerificationResult(
            original_name=name,
            quality=NameQuality.REJECTED,
            confidence=ConfidenceLevel.INVALID,
            rejection_reason="sentence_name",
        )

    # 통과 → 정규화
    cleaned = normalize_name(stripped)
    quality = NameQuality.CLEANED if cleaned != stripped else NameQuality.VALID

    return VerificationResult(
        original_name=name,
        cleaned_name=cleaned,
        quality=quality,
        confidence=ConfidenceLevel.LOW,
    )


def normalize_name(name: str) -> str:
    """유효 광고주명 정리 -- Unicode NFC + URL 분리 + 법인 접미사 제거 + 공백 정리."""
    result = unicodedata.normalize("NFC", name)
    # URL이 결합된 광고주명에서 URL 부분 제거 (예: "기아나라  기아나라.com" → "기아나라")
    result = _EMBEDDED_URL.sub("", result)
    result = _CORP_SUFFIXES.sub("", result)
    result = _EXCESS_SPACE.sub(" ", result)
    result = result.strip().rstrip(",").strip()
    return result


def score_confidence(
    result: VerificationResult,
    known_names: set[str] | None = None,
    occurrence_count: int = 0,
) -> VerificationResult:
    """마스터 DB 매칭 + 등장 빈도 기반 신뢰도 점수."""
    if result.quality == NameQuality.REJECTED:
        result.confidence = ConfidenceLevel.INVALID
        return result

    effective = (result.cleaned_name or result.original_name).lower().strip()
    known = known_names or set()

    if effective in known:
        result.confidence = ConfidenceLevel.HIGH
        result.is_known_advertiser = True
    elif occurrence_count >= 3:
        result.confidence = ConfidenceLevel.MEDIUM
    else:
        result.confidence = ConfidenceLevel.LOW

    return result


def verify_advertiser_name(
    name: str | None,
    known_names: set[str] | None = None,
    occurrence_count: int = 0,
) -> VerificationResult:
    """광고주명 전체 검증: validate → normalize → score.

    pipeline.py, campaign_builder.py에서 사용하는 메인 진입점.
    """
    result = validate_name(name)
    if result.quality != NameQuality.REJECTED:
        result = score_confidence(result, known_names, occurrence_count)
    return result
