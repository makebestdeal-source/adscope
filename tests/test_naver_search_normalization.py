from types import SimpleNamespace

import pytest

from crawler.naver_search import NaverSearchCrawler, _normalize_extracted_search_ad


def test_normalize_extracted_search_ad_backfills_display_url_from_click_url():
    ad = {
        "advertiser_name": "ader",
        "ad_text": "rocket delivery",
        "url": "https://m.coupang.com/vm/products/123",
        "display_url": None,
    }

    normalized = _normalize_extracted_search_ad(dict(ad))

    assert normalized["advertiser_name"] == "coupang"
    assert normalized["display_url"] == "m.coupang.com"


def test_normalize_extracted_search_ad_extracts_embedded_domain_from_raw_name():
    ad = {
        "advertiser_name": "Brand  brand.com",
        "ad_text": "brand sale",
        "url": None,
        "display_url": None,
    }

    normalized = _normalize_extracted_search_ad(dict(ad))

    assert normalized["advertiser_name"] == "Brand"
    assert normalized["display_url"] == "brand.com"


@pytest.mark.asyncio
async def test_crawl_keyword_normalizes_ads_and_captures_list_items(monkeypatch):
    class FakeResponse:
        def __init__(self, html: str):
            self.url = "https://search.naver.com/search.naver?query=test"
            self.status = 200
            self.headers = {"content-type": "text/html; charset=utf-8"}
            self._html = html

        async def text(self):
            return self._html

    class FakePage:
        def __init__(self, html: str):
            self.url = ""
            self._html = html
            self._response_cb = None

        def on(self, event: str, callback):
            if event == "response":
                self._response_cb = callback

        async def goto(self, url: str, wait_until: str = "domcontentloaded"):
            self.url = url
            if self._response_cb is not None:
                await self._response_cb(FakeResponse(self._html))

        async def close(self):
            return None

    class FakeContext:
        def __init__(self, html: str):
            self._html = html

        async def new_page(self):
            return FakePage(self._html)

        async def close(self):
            return None

    async def fake_create_context(self, persona, device):
        return FakeContext("<html><body>mock naver response</body></html>" * 80)

    async def fake_parse_pc(self, page, html):
        return [
            {
                "advertiser_name": "ader",
                "ad_text": "rocket delivery",
                "ad_description": "daily deals",
                "url": "https://m.coupang.com/vm/products/123",
                "display_url": None,
                "position": 1,
                "ad_type": "powerlink",
            }
        ]

    capture_calls = {"count": 0}

    async def fake_capture_list_items(self, page, ads, keyword, persona_code, is_mobile):
        capture_calls["count"] += 1
        ads[0]["creative_image_path"] = "captured.png"

    async def fake_dwell(self, page):
        return None

    monkeypatch.setattr(NaverSearchCrawler, "_create_context", fake_create_context)
    monkeypatch.setattr(NaverSearchCrawler, "_parse_pc_from_html", fake_parse_pc)
    monkeypatch.setattr(NaverSearchCrawler, "_capture_ad_list_items", fake_capture_list_items)
    monkeypatch.setattr(NaverSearchCrawler, "_dwell_on_page", fake_dwell)

    crawler = NaverSearchCrawler()
    persona = SimpleNamespace(code="P1")
    device = SimpleNamespace(is_mobile=False, device_type="pc")

    result = await crawler.crawl_keyword("loan", persona, device)

    assert capture_calls["count"] == 1
    assert len(result["ads"]) == 1
    assert result["ads"][0]["advertiser_name"] == "coupang"
    assert result["ads"][0]["display_url"] == "m.coupang.com"
    assert result["ads"][0]["creative_image_path"] == "captured.png"
