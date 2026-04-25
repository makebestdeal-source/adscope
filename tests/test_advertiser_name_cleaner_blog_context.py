"""Extra context-fallback tests for placeholder advertiser names."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processor.advertiser_name_cleaner import clean_name_for_pipeline


def test_clean_blog_placeholder_uses_brand_like_ad_text_without_domain():
    raw = "blog"
    ad_text = "\uc5d0\uc774\uc2a4\uce68\ub300 \ub86f\ub370\ubc31\ud654\uc810 \uc7a0\uc2e4\uc810"
    click_url = "https://ader.naver.com/v1/example"

    assert clean_name_for_pipeline(raw, ad_text=ad_text, click_url=click_url) == ad_text


def test_clean_blog_placeholder_skips_query_like_ad_text_without_domain():
    raw = "blog"
    ad_text = "\uad11\uad50 \uc624\ud53c\uc2a4\ud154 \uc6d4\uc138"
    click_url = "https://ader.naver.com/v1/example"

    assert clean_name_for_pipeline(raw, ad_text=ad_text, click_url=click_url) == "blog"
