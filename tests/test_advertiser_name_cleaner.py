"""Context-aware advertiser name cleaning tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processor.advertiser_name_cleaner import clean_name_for_pipeline


def test_clean_naver_pay_brand_prefix():
    raw = "네이버페이        주영엔에스  brand.naver.com/jyns"
    assert clean_name_for_pipeline(raw) == "주영엔에스"


def test_clean_naver_login_ui_prefix():
    raw = "네이버 로그인 네이버 아이디로 로그인이 가능합니다. 서비스 자세히 보기       G마켓"
    assert clean_name_for_pipeline(raw) == "G마켓"


def test_clean_ad_redirect_placeholder_uses_ad_text():
    raw = "ader"
    ad_text = "네이버로그인          롯데렌터카비즈카  business.lotterental.com     법인 No.1 롯데렌터카"
    click_url = "https://ader.naver.com/v1/example"
    assert clean_name_for_pipeline(raw, ad_text=ad_text, click_url=click_url) == "롯데렌터카비즈카"


def test_clean_blog_placeholder_uses_context():
    raw = "blog"
    ad_text = "blog.naver.com/s1o1o1o1    하얀렌트카 / 수모터스  깨끗하고 착한가격(신용무관)"
    display_url = "blog.naver.com/s1o1o1o1"
    click_url = "https://ader.naver.com/v1/example"
    assert clean_name_for_pipeline(
        raw,
        ad_text=ad_text,
        display_url=display_url,
        click_url=click_url,
    ) == "하얀렌트카 / 수모터스"
