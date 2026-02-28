"""광고 데이터 정규화 — 크롤링 원본 → DB 적재 가능 형태로 변환."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class NormalizedAd(BaseModel):
    """정규화된 개별 광고 데이터."""

    advertiser_name: str | None = None
    brand: str | None = None
    ad_text: str = ""
    ad_description: str | None = None
    position: int = 0
    url: str | None = None
    display_url: str | None = None
    ad_type: str = "text"
    verification_status: str | None = None
    verification_source: str | None = None
    # 6W 확장 필드
    product_name: str | None = None
    product_category: str | None = None
    ad_placement: str | None = None
    promotion_type: str | None = None
    creative_image_path: str | None = None
    extra_data: dict = Field(default_factory=dict)

    @field_validator("ad_text", mode="before")
    @classmethod
    def clean_text(cls, v: str | None) -> str:
        if not v:
            return ""
        return " ".join(v.split()).strip()

    @field_validator("advertiser_name", mode="before")
    @classmethod
    def clean_advertiser(cls, v: str | None) -> str | None:
        if not v:
            return None
        cleaned = v.strip().replace("광고", "").strip()
        return cleaned or None


class NormalizedSnapshot(BaseModel):
    """정규화된 스냅샷 데이터."""

    keyword: str
    persona_code: str
    device: str
    channel: str
    captured_at: datetime
    page_url: str | None = None
    screenshot_path: str | None = None
    crawl_duration_ms: int = 0
    ads: list[NormalizedAd] = Field(default_factory=list)


def normalize_crawl_result(raw: dict) -> NormalizedSnapshot:
    """크롤러 원본 결과를 정규화된 구조로 변환."""
    ads = [NormalizedAd(**ad) for ad in raw.get("ads", [])]

    return NormalizedSnapshot(
        keyword=raw["keyword"],
        persona_code=raw["persona_code"],
        device=raw["device"],
        channel=raw["channel"],
        captured_at=raw.get("captured_at", datetime.utcnow()),
        page_url=raw.get("page_url"),
        screenshot_path=raw.get("screenshot_path"),
        crawl_duration_ms=raw.get("crawl_duration_ms", 0),
        ads=ads,
    )
