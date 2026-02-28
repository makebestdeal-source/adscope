"""Instagram 모바일 크롤러 기본 구조 테스트."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crawler.instagram_mobile import InstagramMobileCrawler


def test_channel_name():
    crawler = InstagramMobileCrawler.__new__(InstagramMobileCrawler)
    assert crawler.channel == "instagram"


def test_keyword_independent():
    assert InstagramMobileCrawler.keyword_dependent is False


def test_build_ig_ads_dedup():
    crawler = InstagramMobileCrawler.__new__(InstagramMobileCrawler)
    captures = [
        {"advertiser": "brand_a", "body": "ad1", "url": "https://a.com", "image_url": None},
        {"advertiser": "brand_a", "body": "ad1", "url": "https://a.com", "image_url": None},
        {"advertiser": "brand_b", "body": "ad2", "url": "https://b.com", "image_url": None},
    ]
    result = crawler._build_ig_ads(captures)
    assert len(result) == 2
    assert result[0]["position"] == 1
    assert result[1]["position"] == 2


def test_scheduler_map_includes_instagram():
    from scheduler.scheduler import SUPPORTED_CRAWLER_MAP
    from crawler.instagram_catalog import InstagramCatalogCrawler
    assert "instagram" in SUPPORTED_CRAWLER_MAP
    assert SUPPORTED_CRAWLER_MAP["instagram"] is InstagramCatalogCrawler
