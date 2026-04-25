from crawler.google_gdn import GoogleGDNCrawler
from crawler.google_search_ads import GoogleSearchAdsCrawler
from crawler.kakao_da import KakaoDACrawler
from crawler.landing_resolver import _is_infra_host
from crawler.naver_da import NaverDACrawler
from crawler.naver_search import _normalize_extracted_search_ad
from crawler.naver_shopping import (
    _build_fallback_shopping_ad,
    _derive_shopping_advertiser,
    _derive_shopping_display_url,
)
from crawler.tiktok_ads import _normalize_material
from crawler.youtube_ads import (
    YouTubeAdsCrawler,
    _extract_preview_landing_url,
    _extract_preview_text,
    _normalize_external_landing_url,
)


def test_naver_search_normalization_backfills_mobile_search_placement():
    ad = {
        "advertiser_name": "ader",
        "ad_text": "브랜드몰 brand.co.kr 할인 이벤트",
        "url": "https://ader.naver.com/v1/test",
        "display_url": None,
        "ad_type": "powerlink",
        "ad_placement": None,
    }

    normalized = _normalize_extracted_search_ad(dict(ad))

    assert normalized["display_url"] == "brand.co.kr"
    assert normalized["ad_placement"] == "naver_powerlink"


def test_naver_shopping_fallback_filters_ui_only_title():
    item = {
        "title": "재생시간 00:21 닫기",
        "href": "https://smartstore.naver.com/proval/products/1",
        "mall": "",
    }

    assert _build_fallback_shopping_ad(item, 1, "타이어", "html_adcr_url") is None


def test_naver_shopping_fallback_derives_advertiser_from_store_url():
    item = {
        "title": "메디테라 치약 특가",
        "href": "https://smartstore.naver.com/proval/products/1",
        "mall": "",
        "price": "12,300",
        "img_src": "https://example.com/thumb.jpg",
    }

    ad = _build_fallback_shopping_ad(item, 1, "치약", "page_link_scan")

    assert ad is not None
    assert ad["advertiser_name"] == "proval"
    assert ad["url"] == "https://smartstore.naver.com/proval/products/1"
    assert ad["extra_data"]["price"] == "12300"


def test_naver_shopping_fallback_derives_advertiser_from_title_domain_hint():
    item = {
        "title": "coupang.com sale",
        "href": "https://ad.search.naver.com/search.naver?where=ad&query=%EC%97%90%EC%96%B4%ED%8C%9F",
        "mall": "",
    }

    ad = _build_fallback_shopping_ad(item, 1, "airpods", "page_link_scan")

    assert ad is not None
    assert ad["advertiser_name"] == "coupang"


def test_naver_shopping_quality_helpers_use_ad_text_hints():
    ad_text = "NaverPay Repods brand.naver.com/repods official store"

    advertiser = _derive_shopping_advertiser(
        None,
        "https://m.ad.search.naver.com/search.naver?where=m_expd",
        ad_text=ad_text,
    )
    display_url = _derive_shopping_display_url(
        "https://m.ad.search.naver.com/search.naver?where=m_expd",
        ad_text=ad_text,
    )

    assert advertiser == "Repods"
    assert display_url == "brand.naver.com/repods"


def test_google_search_normalize_creatives_keeps_only_text_ads_with_real_landing():
    creatives = [
        {
            "advertiser_name": "주식회사 글루가",
            "creative_id": "bad-1",
            "format_type": 1,
            "text_content": '<img src="https://tpc.googlesyndication.com/archive/simgad/1">',
            "landing_url": None,
            "preview_url": "https://example.com/preview",
            "image_url": None,
        },
        {
            "advertiser_name": "브랜드",
            "creative_id": "good-1",
            "format_type": 1,
            "text_content": "대출 비교 서비스",
            "landing_url": "https://brand.example/loan",
            "preview_url": "https://example.com/preview",
            "image_url": None,
        },
    ]

    ads = GoogleSearchAdsCrawler._normalize_creatives(creatives, "대출")

    assert len(ads) == 1
    assert ads[0]["advertiser_name"] == "브랜드"
    assert ads[0]["ad_text"] == "대출 비교 서비스"
    assert ads[0]["display_url"] == "brand.example"


def test_google_gdn_normalize_creatives_skips_internal_only_rows():
    creatives = [
        {
            "advertiser_name": "Brand",
            "creative_id": "bad-1",
            "format_type": 3,
            "text_content": "gdn_transparency_3",
            "landing_url": None,
            "preview_url": "https://example.com/preview",
            "image_url": None,
        },
        {
            "advertiser_name": "Brand",
            "creative_id": "good-1",
            "format_type": 3,
            "text_content": "Display campaign text",
            "landing_url": "https://brand.example/display",
            "preview_url": "https://example.com/preview",
            "image_url": None,
        },
    ]

    ads = GoogleGDNCrawler._normalize_creatives(creatives, "display")

    assert len(ads) == 1
    assert ads[0]["url"] == "https://brand.example/display"
    assert ads[0]["ad_text"] == "Display campaign text"


def test_youtube_normalize_creatives_skips_rows_without_real_landing():
    creatives = [
        {
            "advertiser_name": "브랜드A",
            "creative_id": "yt-good",
            "format_type": 3,
            "landing_url": "https://brand.example/video",
            "text_content": "브랜드A 영상 광고",
            "preview_url": "https://example.com/preview",
            "image_url": None,
            "start_ts": "1700000000",
            "end_ts": "1700000100",
        },
        {
            "advertiser_name": "브랜드B",
            "creative_id": "yt-bad",
            "format_type": 3,
            "landing_url": None,
            "text_content": "브랜드B 영상 광고",
            "preview_url": "https://example.com/preview",
            "image_url": None,
            "start_ts": "1700000000",
            "end_ts": "1700000100",
        },
    ]

    ads = YouTubeAdsCrawler._normalize_creatives(creatives, "브랜드")

    assert len(ads) == 1
    assert ads[0]["url"] == "https://brand.example/video"
    assert ads[0]["display_url"] == "brand.example"
    assert ads[0]["ad_text"] == "브랜드A 영상 광고"


def test_google_landing_normalizer_decodes_google_redirects():
    url = (
        "https://googleads.g.doubleclick.net/pcs/click"
        "?adurl=https%3A%2F%2Fbrand.example%2Floan"
    )

    assert _normalize_external_landing_url(url) == "https://brand.example/loan"


def test_preview_payload_extracts_landing_and_text():
    payload = (
        "destination_url: '\\x27https://brand.example/product\\x27',"
        "'headline': '보험료 계산해보기',"
        "'description': '지금 바로 확인'"
    )

    assert _extract_preview_landing_url(payload) == "https://brand.example/product"
    assert _extract_preview_text(payload) == "보험료 계산해보기"


def test_tiktok_normalize_material_uses_extended_advertiser_fields():
    material = {
        "business_name": "Luxe Organix",
        "ad_title": "신제품 PDRN 출시",
        "landing_page_url": "https://luxeorganix.ph/pdrn",
        "objective_key": "campaign_objective_traffic",
        "industry_key": "beauty",
        "video_info": {},
        "id": "7615597647411789832",
    }

    ad = _normalize_material(material, 1)

    assert ad is not None
    assert ad["advertiser_name"] == "Luxe Organix"
    assert ad["display_url"] == "luxeorganix.ph"
    assert ad["extra_data"]["url_source"] == "landing_page"


def test_tiktok_normalize_material_uses_nested_video_info_fields():
    material = {
        "ad_title": "Creator launch",
        "objective_key": "campaign_objective_traffic",
        "industry_key": "beauty",
        "video_info": {
            "nickname": "GlowHouse",
        },
        "id": "7615597647411789833",
    }

    ad = _normalize_material(material, 1)

    assert ad is not None
    assert ad["advertiser_name"] == "GlowHouse"


def test_kakao_click_destination_prefers_captured_network_landing():
    crawler = KakaoDACrawler()
    click_url = "https://tr.ad.daum.net/clk?foo=bar"
    crawler._network_landings = {click_url: "https://brand.example/product"}
    crawler._redirect_map = {}

    resolved_url, resolved_domain = crawler._resolve_click_destination(click_url)

    assert resolved_url == "https://brand.example/product"
    assert resolved_domain == "brand.example"


def test_kakao_click_destination_extracts_embedded_external_url():
    crawler = KakaoDACrawler()
    click_url = "https://ka.ad.daum.net/click/https://foresthospital.co.kr/jongno/main/main.html?foo=bar"
    crawler._network_landings = {}
    crawler._redirect_map = {}

    resolved_url, resolved_domain = crawler._resolve_click_destination(click_url)

    assert resolved_url == "https://foresthospital.co.kr/jongno/main/main.html?foo=bar"
    assert resolved_domain == "foresthospital.co.kr"


def test_naver_da_process_raw_ads_skips_internal_asset_urls():
    crawler = NaverDACrawler()

    ads = crawler._process_raw_ads(
        [
            {
                "click_url": "https://ssl.pstatic.net/melona/libs/assets/css/pc/main/min/main_image_rolling_830.min.css?20221021",
                "advertiser_name": "NDP_SF",
                "ad_text": "NDP_SF",
                "adomain": None,
            }
        ],
        "main",
        source="network",
    )

    assert ads == []


def test_landing_resolver_treats_kakao_tracking_hosts_as_infra():
    assert _is_infra_host("tr.ad.daum.net") is True
    assert _is_infra_host("adfit.kakao.com") is True
