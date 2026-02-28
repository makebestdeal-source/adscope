"""광고 분류 엔진 — 마커 감지, 인하우스/유료 분류, 리타겟팅 감지, 위치 분류.

수집된 광고를 분석하여:
1. 광고 마커(ad marker) 감지 → 광고 여부 확인
2. 유료 vs 인하우스(자사 홍보) 분류
3. 리타겟팅 광고 감지
4. 위치(상단/중단/하단) 자동 분류
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse


# ──────────────────────────────────────────────
# 1. 광고 마커 감지 (R14)
# ──────────────────────────────────────────────

AD_MARKERS: dict[str, list[str]] = {
    "naver": [
        "adcr.naver.com", "ad.naver.com", "광고", "파워링크", "비즈사이트",
        "naver_direct", "searchad.naver.com", "adsystem.naver.com",
    ],
    "kakao": [
        "ad.daum.net", "kakaoad", "adfit", "광고", "비즈보드",
        "t1.kakaocdn.net/kakaomob", "track.tiara.kakao.com",
    ],
    "google": [
        "doubleclick.net", "googlesyndication.com", "adservice.google.com",
        "AdChoices", "googleads", "pagead2.googlesyndication.com",
        "tpc.googlesyndication.com",
    ],
    "meta": [
        "Sponsored", "광고", "paid partnership", "Paid",
    ],
    "instagram": [
        "Sponsored", "스폰서", "광고", "paid partnership",
    ],
    "youtube": [
        "광고", "Sponsored", "ad-showing", "video-ads",
    ],
    "network": [
        "criteo", "adroll", "rtbhouse", "taboola", "outbrain", "dable",
        "mobon", "adpopcorn", "cauly",
    ],
}

# 도메인 패턴 vs 텍스트 라벨 분리
_DOMAIN_MARKERS = {
    "adcr.naver.com", "ad.naver.com", "searchad.naver.com", "adsystem.naver.com",
    "ad.daum.net", "track.tiara.kakao.com",
    "doubleclick.net", "googlesyndication.com", "adservice.google.com",
    "pagead2.googlesyndication.com", "tpc.googlesyndication.com",
}


@dataclass
class AdMarkerResult:
    is_ad: bool = False
    ad_network: str | None = None       # "naver", "google_adsense", "criteo" 등
    marker_type: str = "none"           # "url_pattern", "text_label", "adchoices_icon"
    confidence: float = 0.0
    matched_markers: list[str] = field(default_factory=list)


def detect_ad_marker(
    url: str | None = None,
    text: str | None = None,
    extra_data: dict | None = None,
) -> AdMarkerResult:
    """광고 마커 기반 광고 여부 + 광고 네트워크 판별."""
    result = AdMarkerResult()
    url_lower = (url or "").lower()
    text_lower = (text or "").lower()
    extra = extra_data or {}

    # URL 패턴 체크
    for network, markers in AD_MARKERS.items():
        for marker in markers:
            marker_lower = marker.lower()
            if marker_lower in _DOMAIN_MARKERS and marker_lower in url_lower:
                result.is_ad = True
                result.ad_network = network
                result.marker_type = "url_pattern"
                result.confidence = 0.9
                result.matched_markers.append(marker)

    # 텍스트 라벨 체크
    for network, markers in AD_MARKERS.items():
        for marker in markers:
            marker_lower = marker.lower()
            if marker_lower not in _DOMAIN_MARKERS and marker_lower in text_lower:
                result.is_ad = True
                if not result.ad_network:
                    result.ad_network = network
                result.marker_type = result.marker_type or "text_label"
                result.confidence = max(result.confidence, 0.8)
                result.matched_markers.append(marker)

    # AdChoices "i" 아이콘 체크 (extra_data에서)
    if extra.get("has_adchoices_icon") or extra.get("has_ad_info_icon"):
        result.is_ad = True
        result.ad_network = result.ad_network or "google"
        result.marker_type = "adchoices_icon"
        result.confidence = max(result.confidence, 0.95)
        result.matched_markers.append("AdChoices_icon")

    # ad_type 기반 (크롤러가 이미 분류한 경우)
    ad_type = extra.get("ad_type", "")
    if ad_type in ("powerlink", "bizsite", "shopping_ad", "bizboard", "adsense"):
        result.is_ad = True
        result.confidence = max(result.confidence, 0.95)

    return result


# ──────────────────────────────────────────────
# 2. 유료 vs 인하우스(자사) 분류 (R8)
# ──────────────────────────────────────────────

# 광고 시스템 도메인 (인하우스 판정 제외)
_AD_SYSTEM_DOMAINS = {
    "adcr.naver.com", "ad.naver.com", "searchad.naver.com", "adsystem.naver.com",
    "ad.daum.net", "track.tiara.kakao.com",
}

INHOUSE_DOMAINS: dict[str, list[str]] = {
    "naver": [
        "navercorp.com", "nstore.naver.com", "series.naver.com",
        "webtoon.naver.com", "shopping.naver.com", "pay.naver.com",
        "happybean.naver.com", "campaign.naver.com",
        "clova.ai", "snow.me", "band.us", "line.me", "mybox.naver.com",
        "vibe.naver.com", "now.naver.com", "naver.me",
        # 추가: 플랫폼 내부 서비스 도메인
        "blog.naver.com", "cafe.naver.com", "map.naver.com",
        "place.naver.com", "m.place.naver.com", "booking.naver.com",
        "kin.naver.com", "news.naver.com", "finance.naver.com",
        "dict.naver.com", "papago.naver.com", "whale.naver.com",
        "works.naver.com", "smartplace.naver.com",
    ],
    "kakao": [
        "kakaocorp.com", "kakaobank.com", "kakaopay.com",
        "kakaogames.com", "kakaopage.com", "melon.com", "brunch.co.kr",
        "tistory.com", "kakaomakers.com", "kakaostyle.com",
        # 추가
        "kakao.com", "talk.kakao.com", "map.kakao.com",
    ],
}

# 하우스 광고 키워드: 정확히 플랫폼 내부 서비스만 매칭
# "네이버"는 너무 넓으므로 제거 — "네이버웹툰", "네이버재팬" 등 정당한 광고주가 걸림
INHOUSE_KEYWORDS: dict[str, list[str]] = {
    "naver": [
        "NAVER Direct", "네이버페이", "네이버 페이", "Naver Pay",
        "네이버쇼핑", "네이버 쇼핑",
        "네이버해피빈", "네이버 해피빈", "해피빈",
        "네이버시리즈", "네이버 시리즈",
        "네이버 멤버십", "네이버멤버십",
        "네이버 MY", "네이버MY",
        "네이버 블로그", "네이버블로그",
        "네이버 카페", "네이버카페",
        "네이버 지도", "네이버지도",
        "네이버 뉴스", "네이버뉴스",
        "클로바", "MYBOX", "바이브",
        "blog.naver", "cafe.naver", "map.naver", "m.place.naver",
        "place.naver", "booking.naver", "kin.naver",
    ],
    "kakao": [
        "카카오페이", "카카오 페이", "카카오뱅크", "카카오 뱅크",
        "카카오페이지", "카카오 페이지",
        "카카오톡", "카카오 톡",
        "카카오커뮤니티", "카카오 커뮤니티",
        "카카오카", "멜론", "카카오메이커스", "카카오스타일",
        "티스토리", "다음뉴스",
    ],
}


@dataclass
class InhouseResult:
    is_inhouse: bool = False
    inhouse_service: str | None = None  # "네이버페이", "카카오뱅크" 등
    platform: str | None = None         # "naver", "kakao"


def classify_inhouse(
    advertiser_name: str | None,
    url: str | None,
    channel: str,
) -> InhouseResult:
    """유료 광고 vs 인하우스(자사) 광고 분류."""
    result = InhouseResult()

    # 채널에서 플랫폼 판별
    platform = None
    if channel.startswith("naver"):
        platform = "naver"
    elif channel.startswith("kakao"):
        platform = "kakao"
    else:
        return result  # 네이버/카카오 외 채널은 인하우스 없음

    # URL 도메인 체크 (광고 시스템 도메인은 제외)
    if url:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # 광고 트래킹/시스템 도메인이면 인하우스 판정 스킵
            if any(ad_dom in domain for ad_dom in _AD_SYSTEM_DOMAINS):
                return result
            for inhouse_domain in INHOUSE_DOMAINS.get(platform, []):
                if inhouse_domain in domain:
                    result.is_inhouse = True
                    result.inhouse_service = inhouse_domain
                    result.platform = platform
                    return result
        except Exception:
            pass

    # 광고주명 체크
    if advertiser_name:
        name_lower = advertiser_name.strip()
        for keyword in INHOUSE_KEYWORDS.get(platform, []):
            if keyword in name_lower:
                result.is_inhouse = True
                result.inhouse_service = keyword
                result.platform = platform
                return result

    return result


# ──────────────────────────────────────────────
# 3. 리타겟팅 감지 (R6)
# ──────────────────────────────────────────────

RETARGETING_NETWORKS: dict[str, list[str]] = {
    "criteo": ["criteo.com", "criteo.net", "emailretargeting.com"],
    "adroll": ["adroll.com", "d.adroll.com"],
    "rtbhouse": ["rtbhouse.com", "creativecdn.com"],
    "facebook_pixel": ["facebook.com/tr", "connect.facebook.net"],
    "google_remarketing": [
        "googleads.g.doubleclick.net/pagead/viewthroughconversion",
        "www.googleadservices.com/pagead/conversion",
    ],
    "naver_gfa": ["nstat.naver.com", "ssl.pstatic.net/adimg"],
    "kakao_pixel": ["pixel.kakao.com"],
    "taboola": ["taboola.com", "taboolasyndication.com", "trc.taboola.com"],
    "dable": ["dable.io", "api.dable.io"],
    "mobon": ["mobon.net", "mobonads.co.kr"],
}


@dataclass
class RetargetingResult:
    is_retargeted: bool = False
    retargeting_network: str | None = None
    retargeting_type: str = "unknown"  # "site_retarget", "search_retarget", "dynamic"


def detect_retargeting(
    url: str | None = None,
    extra_data: dict | None = None,
) -> RetargetingResult:
    """리타겟팅 광고 감지."""
    result = RetargetingResult()
    url_lower = (url or "").lower()
    extra = extra_data or {}

    # URL에서 리타겟팅 네트워크 도메인 감지
    for network, domains in RETARGETING_NETWORKS.items():
        for domain in domains:
            if domain.lower() in url_lower:
                result.is_retargeted = True
                result.retargeting_network = network
                result.retargeting_type = "site_retarget"
                return result

    # extra_data의 tracking_urls/pixel_urls 체크
    tracking_urls = extra.get("tracking_urls", [])
    if isinstance(tracking_urls, str):
        tracking_urls = [tracking_urls]
    for tracking_url in tracking_urls:
        tracking_lower = tracking_url.lower()
        for network, domains in RETARGETING_NETWORKS.items():
            for domain in domains:
                if domain.lower() in tracking_lower:
                    result.is_retargeted = True
                    result.retargeting_network = network
                    result.retargeting_type = "site_retarget"
                    return result

    # 크롤러가 이미 판별한 경우
    if extra.get("is_retargeting") or extra.get("is_retargeted"):
        result.is_retargeted = True
        result.retargeting_network = extra.get("retargeting_network", "unknown")
        result.retargeting_type = extra.get("retargeting_type", "site_retarget")

    return result


# ──────────────────────────────────────────────
# 4. 위치 분류 (상단/중단/하단) (R1, 3A-3)
# ──────────────────────────────────────────────

def classify_position_zone(
    channel: str,
    device: str | None = None,
    position: int | None = None,
    ad_type: str | None = None,
    ad_placement: str | None = None,
) -> str:
    """광고 위치를 top/middle/bottom으로 분류."""

    # ── 네이버 검색 ──
    if channel == "naver_search":
        if ad_type == "bizsite":
            return "bottom"
        # 파워링크: 위치 기반
        if position is not None:
            if position <= 3:
                return "top"
            if position <= 6:
                return "middle"
            return "bottom"
        return "top"  # 파워링크 기본

    # ── 네이버 DA ──
    if channel == "naver_da":
        placement = (ad_placement or "").lower()
        if any(k in placement for k in ("timeboard", "smart_channel", "rolling_board")):
            return "top"
        if any(k in placement for k in ("branding", "shopping_da")):
            return "middle"
        if any(k in placement for k in ("feed", "content")):
            return "bottom"
        # 위치 좌표 기반 (extra_data.y_offset)
        return "unknown"

    # ── 카카오 DA ──
    if channel == "kakao_da":
        placement = (ad_placement or "").lower()
        if "bizboard" in placement:
            return "top"
        if "content" in placement:
            return "middle"
        return "bottom"

    # ── 구글 GDN ──
    if channel == "google_gdn":
        # GDN은 대부분 콘텐츠 중간/하단
        return "middle"

    # ── 페이스북 ──
    if channel == "facebook":
        placement = (ad_placement or "").lower()
        if "stories" in placement:
            return "top"
        if "reels" in placement:
            return "middle"
        return "middle"  # 피드 기본

    # ── 유튜브 검색 ──
    if channel == "youtube_ads":
        ad_t = (ad_type or "").lower()
        if "preroll" in ad_t or "instream" in ad_t:
            return "top"
        if "promoted" in ad_t:
            return "top"
        return "middle"

    # ── 인스타그램 ──
    if channel == "instagram":
        combined = ((ad_placement or "") + " " + (ad_type or "")).lower()
        if "stories" in combined:
            return "top"
        if "reels" in combined:
            return "middle"
        return "middle"

    # ── 구글 검색 ──
    if channel == "google_search_ads":
        if position is not None:
            if position <= 3:
                return "top"
            if position <= 7:
                return "middle"
            return "bottom"
        return "top"

    # ── 네이버 쇼핑 ──
    if channel == "naver_shopping":
        if position is not None:
            if position <= 3:
                return "top"
            if position <= 8:
                return "middle"
            return "bottom"
        return "top"

    # ── 틱톡 ──
    if channel == "tiktok_ads":
        return "middle"  # 피드 기반

    return "unknown"


# ──────────────────────────────────────────────
# 통합 분류 함수
# ──────────────────────────────────────────────

@dataclass
class ClassificationResult:
    """광고 분류 통합 결과."""
    # 마커
    is_ad: bool = False
    ad_network: str | None = None
    ad_marker_type: str = "none"
    # 인하우스
    is_inhouse: bool = False
    inhouse_service: str | None = None
    # 리타겟팅
    is_retargeted: bool = False
    retargeting_network: str | None = None
    # 위치
    position_zone: str = "unknown"


def classify_ad(
    channel: str,
    url: str | None = None,
    ad_text: str | None = None,
    advertiser_name: str | None = None,
    device: str | None = None,
    position: int | None = None,
    ad_type: str | None = None,
    ad_placement: str | None = None,
    extra_data: dict | None = None,
) -> ClassificationResult:
    """광고를 종합 분류하여 단일 결과 반환."""

    # 1. 마커 감지
    marker = detect_ad_marker(url=url, text=ad_text, extra_data=extra_data)

    # 2. 인하우스 분류
    inhouse = classify_inhouse(
        advertiser_name=advertiser_name,
        url=url,
        channel=channel,
    )

    # 3. 리타겟팅 감지
    retarget = detect_retargeting(url=url, extra_data=extra_data)

    # 4. 위치 분류
    zone = classify_position_zone(
        channel=channel,
        device=device,
        position=position,
        ad_type=ad_type,
        ad_placement=ad_placement,
    )

    return ClassificationResult(
        is_ad=marker.is_ad,
        ad_network=marker.ad_network,
        ad_marker_type=marker.marker_type,
        is_inhouse=inhouse.is_inhouse,
        inhouse_service=inhouse.inhouse_service,
        is_retargeted=retarget.is_retargeted,
        retargeting_network=retarget.retargeting_network,
        position_zone=zone,
    )
