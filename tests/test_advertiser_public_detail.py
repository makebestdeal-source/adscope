from fastapi.testclient import TestClient

from api.main import app


def test_public_advertiser_detail_does_not_lazy_load_children():
    client = TestClient(app)

    advertisers = client.get("/api/advertisers?limit=1")
    assert advertisers.status_code == 200
    advertiser_id = advertisers.json()[0]["id"]

    detail = client.get(f"/api/advertisers/{advertiser_id}")
    assert detail.status_code == 200

    payload = detail.json()
    assert payload["id"] == advertiser_id
    assert "children" in payload
    assert isinstance(payload["children"], list)
