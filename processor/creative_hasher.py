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


def compute_text_hash(advertiser_name: str | None, ad_text: str | None, url: str | None) -> str | None:
    """텍스트 기반 광고 식별 해시 — 이미지 없는 광고의 중복 체크용.

    Args:
        advertiser_name: 광고주명
        ad_text: 광고 텍스트
        url: 랜딩 URL

    Returns:
        64자 hex 해시 문자열 또는 None (모든 필드가 비어있으면)
    """
    parts = [
        (advertiser_name or "").strip().lower(),
        (ad_text or "").strip()[:200],  # 처음 200자만
        (url or "").strip().lower().split("?")[0],  # 쿼리 파라미터 제외
    ]
    combined = "|".join(parts)
    if not combined.replace("|", ""):
        return None
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()
