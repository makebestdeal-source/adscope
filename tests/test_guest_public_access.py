from fastapi.testclient import TestClient

from api.main import app


def test_guest_can_access_public_read_only_routes_and_not_private_ones():
    client = TestClient(app)

    public_paths = [
        "/api/advertisers?limit=1",
        "/api/ads/gallery?limit=1&source=ads",
        "/api/ads/gallery?limit=1&source=social",
        "/api/campaigns/enriched?limit=1",
        "/api/analytics/sov/keyword-landscape?keyword=%EC%82%BC%EC%84%B1&days=30",
        "/api/brand-channels/stats/summary",
        "/api/brand-channels/recent-uploads?days=30&limit=1",
        "/api/brand-channels/content-analysis?days=30",
        "/api/buzz/overview?days=30",
        "/api/industries",
        "/api/meta-signals/top-active?days=30&limit=5",
        "/api/products/categories?days=30",
        "/api/social-channels/overview",
        "/api/social-channels/rankings?days=30&limit=1",
        "/api/social-impact/top-impact?days=30&limit=5",
        "/api/social-ranking/industries",
        "/api/advertiser-trends/summary?days=30&limit=5",
        "/api/launch-impact/ranking?days=30&limit=5",
        "/api/impact/by-advertiser/20721",
    ]

    for path in public_paths:
        response = client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"

    private_paths = [
        "/api/advertisers/favorites",
        "/api/download/advertiser-list",
        "/api/export/social",
        "/api/export/social.xlsx",
    ]

    for path in private_paths:
        response = client.get(path)
        assert response.status_code == 401, f"{path} returned {response.status_code}"
