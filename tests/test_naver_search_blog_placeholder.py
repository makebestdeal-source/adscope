from crawler.naver_search import _normalize_extracted_search_ad


def test_normalize_extracted_search_ad_uses_brand_like_ad_text_for_blog_placeholder():
    ad = {
        "advertiser_name": "blog",
        "ad_text": "\uc5d0\uc774\uc2a4\uce68\ub300 \ub86f\ub370\ubc31\ud654\uc810 \uc7a0\uc2e4\uc810",
        "url": "https://ader.naver.com/v1/example",
        "display_url": None,
    }

    normalized = _normalize_extracted_search_ad(dict(ad))

    assert normalized["advertiser_name"] == ad["ad_text"]
