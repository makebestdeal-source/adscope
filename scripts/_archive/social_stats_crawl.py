"""Standalone script to collect social channel stats (subscribers/followers).

1. Query advertisers with official_channels
2. Collect YouTube subscriber count + Instagram follower count
3. Compute engagement_rate from recent BrandChannelContent
4. Save to ChannelStats table
"""
import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO")

from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from database import async_session, init_db
from database.models import Advertiser, BrandChannelContent, ChannelStats
from crawler.social_stats_crawler import SocialStatsCrawler


TOTAL_TIMEOUT = 900  # 15 minutes total
KST = timezone(timedelta(hours=9))


async def compute_engagement(
    advertiser_id: int,
    platform: str,
    followers_or_subs: int | None,
) -> dict:
    """Compute avg_likes, avg_views, engagement_rate from recent BrandChannelContent."""
    cutoff = datetime.now(KST) - timedelta(days=30)

    async with async_session() as session:
        stmt = (
            select(
                func.avg(BrandChannelContent.like_count).label("avg_likes"),
                func.avg(BrandChannelContent.view_count).label("avg_views"),
                func.count(BrandChannelContent.id).label("post_count"),
            )
            .where(
                BrandChannelContent.advertiser_id == advertiser_id,
                BrandChannelContent.platform == platform,
                BrandChannelContent.discovered_at >= cutoff,
            )
        )
        result = await session.execute(stmt)
        row = result.one()

    avg_likes = round(row.avg_likes, 1) if row.avg_likes else None
    avg_views = round(row.avg_views, 1) if row.avg_views else None

    # Engagement rate: (avg_likes / followers) * 100
    engagement_rate = None
    if followers_or_subs and followers_or_subs > 0 and avg_likes is not None:
        engagement_rate = round((avg_likes / followers_or_subs) * 100, 4)

    return {
        "avg_likes": avg_likes,
        "avg_views": avg_views,
        "engagement_rate": engagement_rate,
    }


async def save_channel_stats(
    advertiser_id: int,
    platform: str,
    channel_url: str,
    stats: dict,
    engagement: dict,
) -> None:
    """Insert a new ChannelStats snapshot row."""
    async with async_session() as session:
        row = ChannelStats(
            advertiser_id=advertiser_id,
            platform=platform,
            channel_url=channel_url,
            subscribers=stats.get("subscribers") if platform == "youtube" else None,
            followers=stats.get("followers") if platform == "instagram" else None,
            total_posts=stats.get("total_posts"),
            total_views=stats.get("total_views"),
            avg_likes=engagement.get("avg_likes"),
            avg_views=engagement.get("avg_views"),
            engagement_rate=engagement.get("engagement_rate"),
            collected_at=datetime.now(KST),
        )
        session.add(row)
        await session.commit()


def _parse_channels(adv) -> dict | None:
    """Parse official_channels from advertiser."""
    channels = adv.official_channels
    if isinstance(channels, str):
        try:
            channels = json.loads(channels)
        except (json.JSONDecodeError, TypeError):
            return None
    if not channels or not isinstance(channels, dict):
        return None
    return channels


async def main():
    await init_db()

    print("=" * 60)
    print("  AdScope Social Channel Stats Collector (parallel)")
    print("=" * 60)

    # Query advertisers with official_channels
    async with async_session() as session:
        stmt = select(Advertiser).where(Advertiser.official_channels.isnot(None))
        result = await session.execute(stmt)
        advertisers = result.scalars().all()

    if not advertisers:
        print("  No advertisers with official_channels found.")
        print("=" * 60)
        return

    # Prepare work lists
    yt_tasks = []  # (adv_id, adv_name, yt_url)
    ig_tasks = []  # (adv_id, adv_name, ig_url)

    for adv in advertisers:
        channels = _parse_channels(adv)
        if not channels:
            continue
        yt_url = channels.get("youtube")
        if yt_url:
            yt_tasks.append((adv.id, adv.name, yt_url))
        ig_url = channels.get("instagram")
        if ig_url:
            if not ig_url.startswith("http"):
                handle = ig_url.lstrip("@")
                ig_url = f"https://www.instagram.com/{handle}/"
            ig_tasks.append((adv.id, adv.name, ig_url))

    print(f"  YouTube: {len(yt_tasks)} channels | Instagram: {len(ig_tasks)} profiles")
    print("")

    t_start = time.time()
    yt_success = 0
    ig_success = 0
    yt_errors = 0
    ig_errors = 0

    async with SocialStatsCrawler() as crawler:
        # ---- Phase 1: YouTube stats (parallel HTTP, semaphore=10) ----
        print("  Phase 1: YouTube stats (parallel)...", flush=True)
        sem = asyncio.Semaphore(10)

        async def fetch_yt_stats(adv_id, adv_name, url):
            async with sem:
                try:
                    stats = await asyncio.wait_for(
                        crawler.collect_youtube_stats(url), timeout=20,
                    )
                    if stats:
                        subs = stats.get("subscribers")
                        engagement = await compute_engagement(adv_id, "youtube", subs)
                        await save_channel_stats(adv_id, "youtube", url, stats, engagement)
                        print(f"    YT {adv_name}: {subs or '?'} subs", flush=True)
                        return True, None
                    return False, None
                except asyncio.TimeoutError:
                    return False, "timeout"
                except Exception as e:
                    return False, str(e)[:80]

        yt_raw = await asyncio.gather(
            *[fetch_yt_stats(aid, name, url) for aid, name, url in yt_tasks],
            return_exceptions=True,
        )
        for item in yt_raw:
            if isinstance(item, Exception):
                yt_errors += 1
                continue
            ok, err = item
            if ok:
                yt_success += 1
            if err:
                yt_errors += 1

        yt_elapsed = time.time() - t_start
        print(f"  Phase 1 done: {yt_success}/{len(yt_tasks)} YouTube in {yt_elapsed:.0f}s\n", flush=True)

        # ---- Phase 2: Instagram stats (sequential, shared session) ----
        print("  Phase 2: Instagram stats (sequential)...", flush=True)
        ig_start = time.time()
        deadline = t_start + TOTAL_TIMEOUT

        for adv_id, adv_name, ig_url in ig_tasks:
            if time.time() >= deadline:
                print("  [!] Time limit reached, stopping.", flush=True)
                break
            try:
                stats = await asyncio.wait_for(
                    crawler.collect_instagram_stats(ig_url), timeout=20,
                )
                if stats:
                    followers = stats.get("followers")
                    engagement = await compute_engagement(adv_id, "instagram", followers)
                    await save_channel_stats(adv_id, "instagram", ig_url, stats, engagement)
                    print(f"    IG {adv_name}: {followers or '?'} followers", flush=True)
                    ig_success += 1
                else:
                    print(f"    IG {adv_name}: no data", flush=True)
            except asyncio.TimeoutError:
                ig_errors += 1
                print(f"    IG {adv_name}: timeout", flush=True)
            except Exception as e:
                ig_errors += 1
                print(f"    IG {adv_name}: {str(e)[:80]}", flush=True)

        ig_elapsed = time.time() - ig_start
        print(f"  Phase 2 done: {ig_success}/{len(ig_tasks)} Instagram in {ig_elapsed:.0f}s\n", flush=True)

    elapsed = time.time() - t_start

    # Summary
    print(f"{'=' * 60}")
    print(f"  RESULTS (total {elapsed:.0f}s)")
    print(f"{'=' * 60}")
    print(f"  YouTube:   {yt_success:3d}/{len(yt_tasks)} collected ({yt_errors} errors) [{yt_elapsed:.0f}s]")
    print(f"  Instagram: {ig_success:3d}/{len(ig_tasks)} collected ({ig_errors} errors) [{ig_elapsed:.0f}s]")
    print(f"  Total:     {yt_success + ig_success}/{len(yt_tasks) + len(ig_tasks)} in {elapsed:.0f}s")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
