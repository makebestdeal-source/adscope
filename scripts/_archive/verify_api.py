"""Smoke-check core API endpoints against the local FastAPI app."""

from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.main import app


def _assert_ok(client: TestClient, path: str):
    response = client.get(path)
    if response.status_code != 200:
        raise RuntimeError(f"{path} -> {response.status_code} {response.text[:200]}")
    return response.json()


def main():
    with TestClient(app) as client:
        _assert_ok(client, "/health")
        snapshots = _assert_ok(client, "/api/ads/snapshots?limit=3")
        advertisers = _assert_ok(client, "/api/advertisers?limit=3")
        campaigns = _assert_ok(client, "/api/campaigns?limit=3")
        _assert_ok(client, "/api/spend/summary?days=7")
        _assert_ok(client, "/api/spend/estimates?limit=3")
        _assert_ok(client, "/api/trends?limit=3")
        _assert_ok(client, "/api/trends/keywords/top?days=7&limit=5")

        if snapshots:
            _assert_ok(client, f"/api/ads/snapshots/{snapshots[0]['id']}")

        if advertisers:
            advertiser_id = advertisers[0]["id"]
            _assert_ok(client, f"/api/advertisers/{advertiser_id}")
            _assert_ok(client, f"/api/advertisers/{advertiser_id}/campaigns")

        if campaigns:
            campaign_id = campaigns[0]["id"]
            _assert_ok(client, f"/api/campaigns/{campaign_id}")
            _assert_ok(client, f"/api/campaigns/{campaign_id}/spend?limit=5")

    print("API_SMOKE_OK")


if __name__ == "__main__":
    main()
