"""extra_data 필드 정규화 -- 채널별 상이한 스키마를 통합 표준 구조로 변환.

각 크롤러(Naver DA/Search, Kakao DA, Meta Library, Facebook Contact,
Instagram Mobile/Catalog, YouTube Ads/Surf, TikTok Ads, GDN, Coupang,
Naver Shopping)가 같은 의미의 데이터를 서로 다른 키명으로 저장한다.
이 모듈은 키 이름만 표준화하며, 값은 절대 변환하지 않는다.
"""

from __future__ import annotations


# ──────────────────────────────────────────────────────────
# 표준 키 매핑: 각 채널에서 사용하는 키 -> 표준 키
# ──────────────────────────────────────────────────────────
_KEY_ALIASES: dict[str, str] = {

    # ── 광고 식별 ──
    # 각 매체의 광고/크리에이티브/캠페인 고유 ID
    "ad_id": "ad_id",
    "creative_id": "creative_id",
    "campaign_id": "campaign_id",
    "material_id": "material_id",          # TikTok Creative Center 소재 ID
    "page_id": "page_id",                  # Meta 페이지 ID

    # ── 소스 정보 ──
    # 광고가 발견된 원본 페이지/요청 URL
    "source_url": "source_url",
    "page_url": "source_url",
    "source_page": "source_url",
    "source_request": "source_url",        # FB Contact redirect 요청 키

    # ── 감지 방법 ──
    # 크롤러가 광고를 탐지한 기술적 방법
    "detection_method": "detection_method",
    "crawl_mode": "crawl_mode",            # contact/api/browser 등 수집 모드 (detection_method와 의미 다름)

    # ── 랜딩/클릭 URL ──
    # 광고 클릭 시 이동하는 최종 목적지 URL (매체별 키명 통일)
    # Naver DA: click_url, Kakao DA: click_url, GDN: click_url/redirect_url,
    # Meta: landing_url, FB: target_url/cta_url, landing_resolver: landing_url
    "landing_url": "original_landing_url",
    "click_url": "original_landing_url",
    "redirect_url": "original_landing_url",
    "target_url": "original_landing_url",
    "cta_url": "original_landing_url",
    "final_url": "original_landing_url",       # GDN URL 파싱
    "destination_url": "original_landing_url",  # GDN URL 파싱
    "dest_url": "original_landing_url",         # GDN URL 파싱
    "clickurl": "original_landing_url",         # GDN URL 파싱 (camelCase 변형)
    "clickthrough_url": "original_landing_url", # GDN URL 파싱
    "landing_page": "original_landing_url",     # GDN URL 파싱
    "landingurl": "original_landing_url",       # GDN URL 파싱

    # ── 이미지 URL ──
    # 광고 크리에이티브의 원본 이미지 URL (썸네일/배너/커버 등)
    # Meta/FB/IG: image_url, Naver DA: banner_image, TikTok: cover_url
    "image_url": "original_image_url",
    "banner_image": "original_image_url",       # Naver DA 배너 이미지
    "cover_url": "original_image_url",          # TikTok 커버 이미지
    "cover_image": "original_image_url",        # TikTok 커버 이미지 (변형)
    "picture": "original_image_url",            # FB API picture 필드
    "full_picture": "original_image_url",       # FB API full_picture 필드

    # ── 상품 이미지 ──
    # 쇼핑 광고의 제품 이미지 (광고 크리에이티브와 구분)
    "product_image": "product_image_url",       # Naver Shopping, Coupang

    # ── 동영상 URL ──
    # 영상 광고의 원본 비디오 파일 URL
    "video_url": "creative_video_url",          # TikTok video
    "creative_url": "creative_video_url",       # 일반 크리에이티브 영상

    # ── 조회수 ──
    # 광고의 노출/조회 횟수. impression_count는 의미가 다르므로 별도 키 유지
    "view_count": "view_count",                 # YouTube Ads, brand_monitor
    "views": "view_count",                      # 일부 크롤러 변형

    # ── 노출수 (조회수와 구분) ──
    # impression = 매체 서버 기준 노출, view = 사용자 시청. 혼용 방지
    "impression_count": "impression_count",

    # ── 포맷 ──
    # 광고 크리에이티브 형식 (video, image, carousel 등)
    "format_type": "format_type",
    "ad_format": "format_type",
    "creative_type": "format_type",

    # ── 시작일 ──
    # 광고 게재 시작 시점 (타임스탬프 또는 날짜 문자열)
    # YouTube Ads: start_ts, Meta API: ad_delivery_start_time
    "start_ts": "ad_start_date",
    "start_date": "ad_start_date",
    "ad_delivery_start_time": "ad_start_date",
    "ad_creation_time": "ad_creation_time",     # Meta 전용: 광고 생성일 (시작일과 다름)

    # ── 종료일 ──
    # 광고 게재 종료 시점
    "end_ts": "ad_end_date",
    "end_date": "ad_end_date",
    "ad_delivery_stop_time": "ad_end_date",     # Meta API 종료일

    # ── 플랫폼 ──
    # 광고가 게재되는 매체 플랫폼 목록 (facebook, instagram 등)
    "publisher_platforms": "platforms",
    "platform": "platforms",

    # ── 광고 지면 상세 ──
    # 구체적인 광고 노출 위치 (예: naver_main_타임보드, GDN 슬롯 등)
    "placement": "ad_placement_detail",         # Naver DA 지면명

    # ── 미리보기 ──
    # 광고 미리보기/썸네일 URL
    "preview_url": "preview_url",
    "thumbnail_url": "preview_url",

    # ── 검색 키워드 ──
    # 광고 수집 시 사용한 검색어
    "search_keyword": "search_keyword",
    "keyword": "search_keyword",
}


# ──────────────────────────────────────────────────────────
# 보존 키: 그대로 유지 (표준 매핑하지 않음)
# 채널별 고유 데이터, 검증 정보, 파생 분석 결과 등
# ──────────────────────────────────────────────────────────
_PRESERVED_KEYS: set[str] = {
    # 검증/신뢰도
    "verification_status",
    "verification_source",
    "google_transparency_status",
    "cross_verification_sources",
    "rejection_reason",

    # 광고주 정보
    "original_advertiser_name",
    "advertiser_source",

    # 랜딩 분석 결과 (AI enricher 산출물)
    "landing_analysis",
    "landing_domain",
    "landing_title",
    "landing_resolved",
    "og_title",

    # GDN 전용 식별자
    "gpt_advertiser_id",
    "gpt_campaign_id",
    "gpt_creative_id",
    "gdn_original_id",
    "ad_src",
    "slot_hint",
    "marker_text",
    "size",

    # Meta/FB 전용
    "spend_lower",
    "spend_upper",
    "currency",
    "impressions_lower",
    "impressions_upper",
    "estimated_audience_size",
    "demographic_distribution",
    "delivery_by_region",
    "bylines",
    "redirect_urls",
    "fingerprint",
    "pixel_event",

    # TikTok 전용
    "industry",
    "objective",
    "like_count",
    "cost_level",
    "ctr",
    "duration",
    "is_search_ad",

    # Instagram 전용 (브랜디드 콘텐츠)
    "partnership_type",
    "sponsor_username",
    "poster_username",
    "brand_username",
    "coauthor_usernames",

    # 수집 컨텍스트
    "source_channel",
    "mobile_web",
    "is_contact",
    "surf_mode",
    "platform_filter",
    "profile_name",
    "redirect_resolved",

    # 쇼핑 전용
    "price",
    "rating",

    # Kakao 전용
    "unit_id",
    "dsp_name",
}


def normalize_extra_data(extra_data: dict | None, channel: str | None = None) -> dict:
    """extra_data를 표준 스키마로 정규화.

    - 키 이름을 표준 키로 매핑
    - 보존 키는 그대로 유지
    - 원본 채널 정보 추가

    Args:
        extra_data: 원본 extra_data dict (None 허용)
        channel: 채널명 (원본 출처 태깅용)

    Returns:
        정규화된 dict
    """
    if not extra_data:
        return {}

    normalized: dict = {}

    for key, value in extra_data.items():
        if value is None:
            continue

        # 보존 키는 그대로
        if key in _PRESERVED_KEYS:
            normalized[key] = value
            continue

        # 별칭 매핑
        standard_key = _KEY_ALIASES.get(key, key)
        if standard_key in normalized:
            # 이미 있는 키 -> 기존 값 우선 유지
            continue
        normalized[standard_key] = value

    # 채널 출처 태깅
    if channel and "source_channel" not in normalized:
        normalized["source_channel"] = channel

    return normalized
