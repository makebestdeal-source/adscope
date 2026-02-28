from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processor import campaign_builder


def test_parse_excluded_channels_uses_default_when_missing():
    assert campaign_builder._parse_excluded_channels(
        None,
        default={"youtube_ads"},
    ) == {"youtube_ads"}


def test_parse_excluded_channels_parses_csv():
    assert campaign_builder._parse_excluded_channels(" google_gdn , kakao_da ,, ") == {
        "google_gdn",
        "kakao_da",
    }


def test_parse_excluded_channels_empty_string_disables_default():
    assert campaign_builder._parse_excluded_channels("", default={"youtube_ads"}) == set()


@pytest.mark.asyncio
async def test_rebuild_campaigns_uses_default_excluded_channels(monkeypatch):
    monkeypatch.delenv("CAMPAIGN_EXCLUDED_CHANNELS", raising=False)

    calls: dict[str, object] = {}

    async def fake_delete(excluded_channels):
        calls["delete"] = excluded_channels

    async def fake_backfill_ids():
        calls["backfill_ids"] = True
        return 2, 1

    async def fake_backfill_industries(excluded_channels=None):
        calls["industry"] = excluded_channels
        return 3

    async def fake_upsert(active_days=7, excluded_channels=None):
        calls["upsert"] = (active_days, excluded_channels)
        return 4, 5

    async def fake_counts():
        return 6, 7

    monkeypatch.setattr(campaign_builder, "_delete_excluded_campaign_data", fake_delete)
    monkeypatch.setattr(campaign_builder, "_backfill_advertiser_ids", fake_backfill_ids)
    monkeypatch.setattr(campaign_builder, "_backfill_advertiser_industries", fake_backfill_industries)
    monkeypatch.setattr(campaign_builder, "_upsert_campaigns_and_spend", fake_upsert)
    monkeypatch.setattr(campaign_builder, "_counts", fake_counts)

    stats = await campaign_builder.rebuild_campaigns_and_spend(active_days=9)

    assert calls["delete"] == {"youtube_ads"}
    assert calls["industry"] == {"youtube_ads"}
    assert calls["upsert"] == (9, {"youtube_ads"})
    assert stats == {
        "linked_details": 2,
        "created_advertisers": 1,
        "industry_backfilled": 3,
        "updated_campaigns": 4,
        "inserted_estimates": 5,
        "campaigns_total": 6,
        "spend_estimates_total": 7,
    }


@pytest.mark.asyncio
async def test_rebuild_campaigns_respects_env_excluded_channels(monkeypatch):
    monkeypatch.setenv("CAMPAIGN_EXCLUDED_CHANNELS", "google_gdn, kakao_da")

    calls: dict[str, object] = {}

    async def fake_delete(excluded_channels):
        calls["delete"] = excluded_channels

    async def fake_backfill_ids():
        return 0, 0

    async def fake_backfill_industries(excluded_channels=None):
        calls["industry"] = excluded_channels
        return 0

    async def fake_upsert(active_days=7, excluded_channels=None):
        calls["upsert"] = (active_days, excluded_channels)
        return 0, 0

    async def fake_counts():
        return 0, 0

    monkeypatch.setattr(campaign_builder, "_delete_excluded_campaign_data", fake_delete)
    monkeypatch.setattr(campaign_builder, "_backfill_advertiser_ids", fake_backfill_ids)
    monkeypatch.setattr(campaign_builder, "_backfill_advertiser_industries", fake_backfill_industries)
    monkeypatch.setattr(campaign_builder, "_upsert_campaigns_and_spend", fake_upsert)
    monkeypatch.setattr(campaign_builder, "_counts", fake_counts)

    await campaign_builder.rebuild_campaigns_and_spend(active_days=5)

    assert calls["delete"] == {"google_gdn", "kakao_da"}
    assert calls["industry"] == {"google_gdn", "kakao_da"}
    assert calls["upsert"] == (5, {"google_gdn", "kakao_da"})
