"""Public (no-auth) endpoints — preview data for non-logged-in visitors."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy import func, select

from database import async_session
from database.models import AdDetail, AdSnapshot, Advertiser

router = APIRouter(prefix="/public", tags=["public"])

CHANNEL_LABELS: dict[str, str] = {
    "naver_search": "네이버 검색",
    "naver_da": "네이버 DA",
    "naver_shopping": "네이버 쇼핑",
    "google_search_ads": "구글 검색",
    "google_gdn": "구글 GDN",
    "youtube_ads": "유튜브",
    "youtube_surf": "유튜브 서프",
    "meta": "메타",
    "meta_feed": "메타 피드",
    "kakao_da": "카카오 DA",
    "tiktok_ads": "틱톡",
}


def _obscure(name: str) -> str:
    """Partially hide a brand name — show first char + ●● for the rest."""
    if not name:
        return "●●●"
    if len(name) == 1:
        return name + "●"
    if len(name) == 2:
        return name[0] + "●"
    return name[0] + "●" * (len(name) - 1)


@router.get("/stats")
async def get_public_stats():
    """Public summary stats — no authentication required.

    Returns aggregate numbers and a partially-obfuscated top-10 advertiser
    ranking so that anonymous visitors can see the service has real data.
    """
    cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)
    cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)

    async with async_session() as session:
        # ── 전체 카운트 ──
        total_ads = (
            await session.scalar(select(func.count()).select_from(AdDetail))
        ) or 0
        total_advertisers = (
            await session.scalar(select(func.count()).select_from(Advertiser))
        ) or 0
        active_7d = (
            await session.scalar(
                select(func.count(func.distinct(AdDetail.advertiser_id)))
                .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
                .where(AdSnapshot.captured_at >= cutoff_7d)
                .where(AdDetail.advertiser_id.isnot(None))
            )
        ) or 0

        # ── 채널별 30일 수집 현황 ──
        channel_rows = await session.execute(
            select(AdSnapshot.channel, func.count().label("cnt"))
            .where(AdSnapshot.captured_at >= cutoff_30d)
            .group_by(AdSnapshot.channel)
            .order_by(func.count().desc())
        )
        by_channel = {row.channel: row.cnt for row in channel_rows}

        # ── TOP 10 광고주 (7일) — 상위 3개만 이름 공개 ──
        top_rows = await session.execute(
            select(
                Advertiser.name,
                func.count(AdDetail.id).label("cnt"),
            )
            .join(AdDetail, AdDetail.advertiser_id == Advertiser.id)
            .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
            .where(AdSnapshot.captured_at >= cutoff_7d)
            .group_by(Advertiser.id, Advertiser.name)
            .order_by(func.count(AdDetail.id).desc())
            .limit(10)
        )
        top_advertisers = []
        for i, row in enumerate(top_rows):
            locked = i >= 3
            top_advertisers.append(
                {
                    "rank": i + 1,
                    "name": _obscure(row.name) if locked else row.name,
                    "locked": locked,
                }
            )

    return {
        "total_ads": total_ads,
        "total_advertisers": total_advertisers,
        "active_7d": active_7d,
        "total_channels": len(by_channel),
        "by_channel": by_channel,
        "top_advertisers": top_advertisers,
    }
