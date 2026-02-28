"""Standalone script to run brand channel monitoring.

1. Query advertisers with official_channels != NULL
2. For each: run appropriate monitor function (YouTube/Instagram)
3. Save via brand_pipeline
4. Print summary
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

from database import async_session, init_db
from database.models import Advertiser
from sqlalchemy import select
from crawler.brand_monitor import BrandChannelMonitor
from processor.brand_pipeline import save_brand_content


TOTAL_TIMEOUT = 900  # 15 minutes total


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
    print("  AdScope Brand Channel Monitor (parallel)")
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
    yt_results = {}  # adv_name -> {new, errors}
    ig_results = {}

    async with BrandChannelMonitor() as monitor:
        # ---- Phase 1: YouTube (parallel HTTP, semaphore=10) ----
        print("  Phase 1: YouTube (parallel)...", flush=True)
        sem = asyncio.Semaphore(10)

        async def fetch_yt(adv_id, adv_name, url):
            async with sem:
                try:
                    contents = await asyncio.wait_for(
                        monitor.monitor_youtube_channel(url), timeout=30,
                    )
                    async with async_session() as db:
                        new_count = await save_brand_content(
                            db, adv_id, "youtube", url, contents
                        )
                        await db.commit()
                    print(f"    YT {adv_name}: {len(contents)} found, {new_count} new", flush=True)
                    return adv_name, new_count, None
                except asyncio.TimeoutError:
                    print(f"    YT {adv_name}: timeout", flush=True)
                    return adv_name, 0, "timeout"
                except Exception as e:
                    err = str(e)[:100]
                    print(f"    YT {adv_name}: {err}", flush=True)
                    return adv_name, 0, err

        yt_raw = await asyncio.gather(
            *[fetch_yt(aid, name, url) for aid, name, url in yt_tasks],
            return_exceptions=True,
        )
        for item in yt_raw:
            if isinstance(item, Exception):
                continue
            name, new_count, err = item
            yt_results[name] = {"new": new_count, "error": err}

        yt_elapsed = time.time() - t_start
        yt_total = sum(r["new"] for r in yt_results.values())
        print(f"  Phase 1 done: {yt_total} new YouTube items in {yt_elapsed:.0f}s\n", flush=True)

        # ---- Phase 2: Instagram (sequential, shared session) ----
        print("  Phase 2: Instagram (sequential)...", flush=True)
        ig_start = time.time()
        deadline = t_start + TOTAL_TIMEOUT

        for adv_id, adv_name, ig_url in ig_tasks:
            if time.time() >= deadline:
                print("  [!] Time limit reached, stopping.", flush=True)
                break
            try:
                contents = await asyncio.wait_for(
                    monitor.monitor_instagram_profile(ig_url), timeout=30,
                )
                async with async_session() as db:
                    new_count = await save_brand_content(
                        db, adv_id, "instagram", ig_url, contents
                    )
                    await db.commit()
                print(f"    IG {adv_name}: {len(contents)} found, {new_count} new", flush=True)
                ig_results[adv_name] = {"new": new_count, "error": None}
            except asyncio.TimeoutError:
                print(f"    IG {adv_name}: timeout", flush=True)
                ig_results[adv_name] = {"new": 0, "error": "timeout"}
            except Exception as e:
                err = str(e)[:100]
                print(f"    IG {adv_name}: {err}", flush=True)
                ig_results[adv_name] = {"new": 0, "error": err}

        ig_elapsed = time.time() - ig_start
        ig_total = sum(r["new"] for r in ig_results.values())
        print(f"  Phase 2 done: {ig_total} new Instagram items in {ig_elapsed:.0f}s\n", flush=True)

    elapsed = time.time() - t_start

    # Summary
    print(f"{'=' * 60}")
    print(f"  RESULTS (total {elapsed:.0f}s)")
    print(f"{'=' * 60}")

    yt_errors = sum(1 for r in yt_results.values() if r["error"])
    ig_errors = sum(1 for r in ig_results.values() if r["error"])

    print(f"  YouTube:   {yt_total:4d} new items ({len(yt_results)} channels, {yt_errors} errors) [{yt_elapsed:.0f}s]")
    print(f"  Instagram: {ig_total:4d} new items ({len(ig_results)} profiles, {ig_errors} errors) [{ig_elapsed:.0f}s]")
    print(f"  TOTAL:     {yt_total + ig_total:4d} new items in {elapsed:.0f}s")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
