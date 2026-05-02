"""광고 소재 이미지 해시 — 중복 제거용 perceptual hash 유틸리티."""

import hashlib
from pathlib import Path

from loguru import logger


def compute_creative_hash(image_path: str | None) -> str | None:
    """이미지 파일의 content hash를 계산.

    PIL의 phash가 없는 환경에서도 동작하도록
    파일 내용 기반 SHA-256 해시를 사용.

    Args:
        image_path: 이미지 파일 경로 (None이면 None 반환)

    Returns:
        64자 hex 해시 문자열 또는 None
    """
    if not image_path:
        return None

    path = Path(image_path)
    if not path.exists():
        return None

    try:
        data = path.read_bytes()
        if len(data) < 100:  # 너무 작은 파일은 유효하지 않음
            return None
        return hashlib.sha256(data).hexdigest()
    except Exception as e:
        logger.debug(f"[creative_hasher] 해시 계산 실패: {image_path} - {e}")
        return None


_TRACKING_DOMAINS = {
    "ader.naver.com",       # 네이버 검색광고 per-impression 추적 URL
    "ader.kakao.com",       # 카카오 추적 URL
    "googleadservices.com", # 구글 광고 클릭 추적
    "doubleclick.net",
}


def _normalize_url(url: str | None) -> str:
    """광고 노출마다 달라지는 추적 URL을 도메인으로만 축약.

    ader.naver.com/v1/UNIQUE_TOKEN 같이 경로 자체가 per-impression인 경우
    도메인만 남겨 동일 광고주·소재를 같은 해시로 묶는다.
    일반 URL은 쿼리 파라미터만 제거 후 반환.
    """
    if not url:
        return ""
    u = url.strip().lower()
    # 프로토콜 제거 후 도메인 추출
    without_proto = u.replace("https://", "").replace("http://", "")
    domain = without_proto.split("/")[0]
    if domain in _TRACKING_DOMAINS:
        return domain  # 추적 도메인은 도메인만 사용
    return u.split("?")[0]  # 일반 URL은 쿼리 파라미터만 제거


def compute_text_hash(advertiser_name: str | None, ad_text: str | None, url: str | None) -> str | None:
    """텍스트 기반 광고 식별 해시 — 이미지 없는 광고의 중복 체크용.

    Args:
        advertiser_name: 광고주명
        ad_text: 광고 텍스트
        url: 랜딩 URL (추적 도메인은 도메인만 사용)

    Returns:
        64자 hex 해시 문자열 또는 None (모든 필드가 비어있으면)
    """
    parts = [
        (advertiser_name or "").strip().lower(),
        (ad_text or "").strip()[:200],  # 처음 200자만
        _normalize_url(url),
    ]
    combined = "|".join(parts)
    if not combined.replace("|", ""):
        return None
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()
