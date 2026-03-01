"""Ad Product Classifier - 채널x배치 조합으로 광고상품/목적/형식 자동분류.

pipeline.py에서 AdDetail 저장 전에 호출하여 campaign_purpose, ad_format_type,
ad_product_name 필드를 자동 채움.
"""

import re
from typing import Optional

# ─── 네이버 DA 배치 → 광고상품 매핑 ───
_NAVER_DA_PRODUCT_MAP = {
    "timeboard": "홈 프리미엄",
    "headline": "홈 프리미엄",
    "rolling": "홈 프리미엄",
    "right_ad": "배너광고",
    "da_public": "배너광고",
    "feed_ad": "성과형DA(GFA)",
    "search_home_ad": "성과형DA(GFA)",
    "issue_banner": "배너광고",
    "smart_channel": "스마트채널",
}

# ─── 카카오 DA 형식 → 광고상품 매핑 ───
_KAKAO_PRODUCT_MAP = {
    "native": "디스플레이 네이티브",
    "banner": "비즈보드",
    "video": "디스플레이 동영상",
    "bizboard": "비즈보드",
}

# ─── campaign_purpose 추론용 URL/텍스트 패턴 ───
_PURPOSE_URL_PATTERNS = [
    (re.compile(r"(shop|buy|cart|order|purchase|checkout|product)", re.I), "commerce"),
    (re.compile(r"(event|promo|campaign|contest|giveaway)", re.I), "event"),
    (re.compile(r"(sale|discount|coupon|deal|\d+%)", re.I), "promotion"),
]

_PURPOSE_TEXT_PATTERNS = [
    (re.compile(r"(출시|NEW|런칭|신제품|새로운|오픈)", re.I), "launch"),
    (re.compile(r"(할인|%|세일|특가|파격|최저가|무료배송)", re.I), "promotion"),
    (re.compile(r"(구매|주문|장바구니|쇼핑|지금\s*사|바로구매)", re.I), "commerce"),
    (re.compile(r"(이벤트|응모|경품|추첨|당첨)", re.I), "event"),
]

# ─── 채널 → ad_format_type 기본 매핑 ───
_CHANNEL_FORMAT_MAP = {
    "naver_search": "search",
    "naver_shopping": "shopping",
    "naver_da": "display",
    "kakao_da": "display",
    "google_gdn": "display",
    "youtube_ads": "video",
    "meta": "social",
    "tiktok_ads": "social",
}


def classify_ad_product(channel: str, ad_data: dict) -> dict:
    """채널+광고데이터로 ad_product_name, ad_format_type, campaign_purpose 결정.

    Args:
        channel: 크롤러 채널명 (e.g. "naver_search", "youtube_ads")
        ad_data: 크롤러가 반환한 개별 ad dict (extra_data 포함)

    Returns:
        {"ad_product_name": str|None, "ad_format_type": str|None,
         "campaign_purpose": str|None}
    """
    extra = ad_data.get("extra_data") or {}
    ad_type = ad_data.get("ad_type", "")
    url = ad_data.get("url", "") or ""
    ad_text = ad_data.get("ad_text", "") or ""
    placement = extra.get("placement", "") or ad_data.get("ad_placement", "") or ""

    product_name = _classify_product_name(channel, ad_type, extra, placement)
    format_type = _classify_format_type(channel, extra)
    purpose = _classify_purpose(channel, ad_type, url, ad_text, extra, placement)

    return {
        "ad_product_name": product_name,
        "ad_format_type": format_type,
        "campaign_purpose": purpose,
    }


def _classify_product_name(channel: str, ad_type: str, extra: dict, placement: str) -> Optional[str]:
    """채널별 규칙으로 광고상품명 결정."""

    # ── 네이버 검색 ──
    if channel == "naver_search":
        if ad_type == "powerlink":
            return "파워링크"
        if ad_type == "bizsite":
            return "비즈사이트"
        if ad_type == "brand_search":
            return "브랜드검색"
        return "파워링크"  # default

    # ── 네이버 쇼핑 ──
    if channel == "naver_shopping":
        sub = extra.get("ad_type", "")
        if sub == "powerlink":
            return "쇼핑검색 파워링크"
        return "쇼핑검색"

    # ── 네이버 DA ──
    if channel == "naver_da":
        pl = placement.lower().replace("naver_main_", "").replace("naver_", "")
        return _NAVER_DA_PRODUCT_MAP.get(pl, "네이버 DA")

    # ── 유튜브 ──
    if channel == "youtube_ads":
        fmt = extra.get("format_type", "")
        duration = extra.get("duration") or extra.get("video_duration")
        if duration is not None:
            try:
                dur = float(duration)
                if dur <= 6:
                    return "범퍼광고"
                if dur <= 15:
                    return "논스킵 인스트림"
            except (ValueError, TypeError):
                pass
        if "short" in fmt.lower():
            return "쇼츠 광고"
        if "bumper" in fmt.lower():
            return "범퍼광고"
        return "트루뷰 인스트림"

    # ── 메타 (Facebook/Instagram) ──
    if channel in ("meta", "facebook", "meta_library", "instagram", "instagram_catalog"):
        platforms = extra.get("platforms") or extra.get("publisher_platforms") or []
        is_ig = "instagram" in str(platforms).lower() or "instagram" in channel
        # format detection
        fmt = extra.get("format_type", "")
        image_count = extra.get("image_count", 1)
        has_video = extra.get("video_url") or "video" in fmt.lower()

        ad_pl = placement.lower()
        if "reel" in ad_pl:
            return "릴스 광고"
        if "stories" in ad_pl or "story" in ad_pl:
            return "스토리 광고"
        if "explore" in ad_pl:
            return "탐색탭 광고"
        if "marketplace" in ad_pl:
            return "마켓플레이스 광고"

        if has_video:
            return "피드 동영상" if not is_ig else "IG 피드 동영상"
        if image_count and image_count > 1:
            return "캐러셀(슬라이드)"
        return "피드 이미지" if not is_ig else "IG 피드 이미지"

    # ── 카카오 DA ──
    if channel == "kakao_da":
        fmt = (extra.get("format_type") or "").lower()
        return _KAKAO_PRODUCT_MAP.get(fmt, "카카오 디스플레이")

    # ── 틱톡 ──
    if channel == "tiktok_ads":
        objective = (extra.get("objective") or extra.get("objective_key") or "").lower()
        if "reach" in objective or "brand" in objective:
            return "TopView"
        if "search" in str(extra.get("is_search_ad", "")):
            return "검색광고"
        return "인피드"

    # ── GDN ──
    if channel == "google_gdn":
        creative_type = extra.get("creative_type", "")
        if "responsive" in creative_type.lower():
            return "GDN 반응형"
        return "GDN 디스플레이"

    return None


def _classify_format_type(channel: str, extra: dict) -> Optional[str]:
    """채널에서 ad_format_type 결정."""
    base = _CHANNEL_FORMAT_MAP.get(channel)
    if base:
        return base

    # fallback: extra_data.format_type 참조
    fmt = (extra.get("format_type") or "").lower()
    if "video" in fmt:
        return "video"
    if "native" in fmt or "social" in fmt:
        return "social"
    if "banner" in fmt or "display" in fmt:
        return "display"

    return None


def _classify_purpose(
    channel: str, ad_type: str, url: str, ad_text: str,
    extra: dict, placement: str,
) -> Optional[str]:
    """campaign_purpose 자동추론."""

    # 리타겟팅 네트워크가 있으면 retargeting
    if extra.get("retargeting_network"):
        return "retargeting"

    # TikTok objective 매핑
    objective = (extra.get("objective") or extra.get("objective_key") or "").lower()
    if objective:
        if "conversion" in objective:
            return "commerce"
        if "awareness" in objective or "reach" in objective:
            return "branding"
        if "traffic" in objective:
            return "performance"
        if "engagement" in objective:
            return "awareness"

    # 보장형 DA (타임보드/마스트헤드 등) = branding
    premium_placements = {"timeboard", "headline", "rolling", "masthead"}
    if any(p in placement.lower() for p in premium_placements):
        return "branding"

    # 쇼핑 채널 = commerce
    if channel in ("naver_shopping",):
        return "commerce"

    # URL 패턴
    for pattern, purpose in _PURPOSE_URL_PATTERNS:
        if pattern.search(url):
            return purpose

    # 텍스트 패턴
    for pattern, purpose in _PURPOSE_TEXT_PATTERNS:
        if pattern.search(ad_text):
            return purpose

    # 성과형 DA = performance
    if channel in ("google_gdn",) or "gfa" in placement.lower():
        return "performance"

    return "awareness"  # 기본값
