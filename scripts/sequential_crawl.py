"""순차 수집 -- OOM 방지를 위해 채널 1개씩 순서대로 실행.

브라우저 1개만 띄우고, 각 채널 완료 후 GC + 메모리 정리.
fast_crawl.py와 동일한 채널/키워드 사용, 실행만 순차.

Usage:
    python scripts/sequential_crawl.py
    python scripts/sequential_crawl.py --channels naver_search,youtube_ads
    python scripts/sequential_crawl.py --skip-postprocess
"""
import asyncio
import gc
import io
import json
import os
import random
import sys
import time
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
# NOTE: stdout UTF-8 래핑은 fast_crawl import 시 자동 처리됨

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

# ── 메모리 절약 설정 (fast_crawl 대비 축소) ──
os.environ["CRAWLER_DWELL_MIN_MS"] = "1500"
os.environ["CRAWLER_DWELL_MAX_MS"] = "2500"
os.environ["CRAWLER_DWELL_SCROLL_COUNT_MIN"] = "2"
os.environ["CRAWLER_DWELL_SCROLL_COUNT_MAX"] = "4"
os.environ["CRAWLER_INTER_PAGE_MIN_MS"] = "800"
os.environ["CRAWLER_INTER_PAGE_MAX_MS"] = "1500"
os.environ["CRAWLER_WARMUP_SITE_COUNT"] = "0"
# 유튜브
os.environ["YOUTUBE_AD_WAIT_MS"] = "18000"
os.environ["YOUTUBE_PLAYER_SAMPLES"] = "20"
os.environ["YOUTUBE_SURF_SAMPLES"] = "30"
os.environ["YT_ADS_MAX_ADVERTISERS"] = "200"
os.environ["YT_ADS_MAX_ADS"] = "600"
# 구글검색
os.environ["GS_ADS_MAX_ADVERTISERS"] = "100"
os.environ["GS_ADS_MAX_ADS"] = "400"
# 네이버쇼핑
os.environ["NAVER_SHOP_MAX_ADS"] = "100"
# GDN
os.environ["GDN_MAX_ADVERTISERS"] = "100"
os.environ["GDN_MAX_ADS"] = "400"
# 메타
os.environ["META_TRUST_CHECK"] = "false"
os.environ["META_FEED_SCROLL_COUNT"] = "30"
os.environ["META_MAX_PAGES"] = "10"
os.environ["INSTAGRAM_EXPLORE_CLICKS"] = "30"
os.environ["INSTAGRAM_REELS_SWIPES"] = "40"
os.environ["FB_CONTACT_MAX_PAGES"] = "12"
os.environ["FB_CONTACT_SCROLL_ROUNDS"] = "20"
# 카카오
os.environ["KAKAO_MAX_MEDIA"] = "16"
os.environ["MEDIA_COLLECTION_PROFILE"] = "full"
os.environ["KAKAO_LANDING_RESOLVE_LIMIT"] = "0"
# 네이버 DA
os.environ["NAVER_DA_CATEGORY_TABS"] = "6"

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO")

from crawler.stealth_patch import enable_stealth
enable_stealth()

from database import init_db

# fast_crawl에서 필요한 것들 재사용
from scripts.fast_crawl import (
    CHANNEL_TASKS_BASE,
    CHANNEL_PERSONA_COUNT,
    CHANNEL_TIMEOUT,
    DEMO_PERSONAS,
    build_persona_tasks,
    crawl_channel,
    _get_crawler_cls,
)
from processor.channel_utils import CONTACT_CHANNELS

# 브라우저 1개만!
import scripts.fast_crawl as _fc
_fc.MAX_BROWSERS = 1
_fc._browser_sem = None  # 재초기화 강제

TOTAL_TIMEOUT = 7200  # 2시간


def _parse_args():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--channels", type=str, default="",
                        help="콤마 구분 채널 목록 (비우면 전체)")
    parser.add_argument("--skip-postprocess", action="store_true",
                        help="후처리 스킵")
    parser.add_argument("--timeout", type=int, default=TOTAL_TIMEOUT,
                        help="Total crawl timeout in seconds")
    return parser.parse_args()


def _mem_mb():
    """현재 프로세스 RSS (MB)."""
    try:
        import psutil
        return psutil.Process().memory_info().rss / (1024 * 1024)
    except ImportError:
        return -1


async def main():
    args = _parse_args()
    total_timeout = args.timeout
    await init_db()

    only_channels = set(args.channels.split(",")) if args.channels else set()

    persona_tasks = build_persona_tasks()

    # 필터링
    if only_channels:
        persona_tasks = [(ch, p, d, kw) for ch, p, d, kw in persona_tasks
                         if ch in only_channels]

    # 카탈로그 먼저, 접촉 나중에
    catalog_tasks = [(ch, p, d, kw) for ch, p, d, kw in persona_tasks
                     if ch not in CONTACT_CHANNELS]
    contact_tasks = [(ch, p, d, kw) for ch, p, d, kw in persona_tasks
                     if ch in CONTACT_CHANNELS]
    all_tasks = catalog_tasks + contact_tasks

    print("=" * 60)
    print(f"  AdScope Sequential Crawl -- {len(all_tasks)} tasks (1 at a time)")
    print(f"  Catalog: {len(catalog_tasks)} | Contact: {len(contact_tasks)}")
    print(f"  Memory: {_mem_mb():.0f} MB | Timeout: {total_timeout}s")
    print("=" * 60)

    deadline = time.time() + total_timeout
    t_start = time.time()
    results = []

    for idx, (channel, persona_code, device, keywords) in enumerate(all_tasks, 1):
        if time.time() >= deadline:
            print(f"\n  [!] Deadline reached, skipping remaining {len(all_tasks) - idx + 1} tasks")
            break

        mem = _mem_mb()
        kw_count = len(keywords)
        kind = "contact" if channel in CONTACT_CHANNELS else "catalog"
        print(f"\n  [{idx}/{len(all_tasks)}] {channel} ({persona_code}/{device}) "
              f"-- {kw_count} kw, {kind}, mem={mem:.0f}MB", flush=True)

        try:
            result = await crawl_channel(channel, persona_code, device, keywords, deadline)
            results.append(result)
            ads = result.get("total_ads", 0)
            promoted = result.get("promoted", 0)
            errs = len(result.get("errors", []))
            print(f"  -> {ads} ads, {promoted} promoted, {errs} errors", flush=True)
        except Exception as e:
            print(f"  -> EXCEPTION: {str(e)[:150]}", flush=True)
            results.append({"channel": channel, "persona": persona_code,
                            "total_ads": 0, "promoted": 0, "errors": [str(e)[:150]]})

        # ── 메모리 정리 (핵심!) ──
        gc.collect()
        await asyncio.sleep(2)  # 브라우저 프로세스 정리 대기

    # ── 결과 요약 ──
    elapsed_total = time.time() - t_start
    print(f"\n{'=' * 60}")
    print(f"  RESULTS (total {elapsed_total:.0f}s)")
    print(f"{'=' * 60}")

    grand_total = 0
    grand_promoted = 0
    channel_summary = {}

    for r in results:
        if isinstance(r, Exception):
            print(f"  [X] Exception: {str(r)[:100]}")
            continue
        ch = r["channel"]
        ads = r["total_ads"]
        promoted = r.get("promoted", 0)
        errs = len(r.get("errors", []))
        grand_total += ads
        grand_promoted += promoted

        if ch not in channel_summary:
            channel_summary[ch] = {"ads": 0, "promoted": 0, "personas": [], "errors": 0}
        channel_summary[ch]["ads"] += ads
        channel_summary[ch]["promoted"] += promoted
        channel_summary[ch]["errors"] += errs
        if r.get("persona"):
            channel_summary[ch]["personas"].append(r["persona"])

    print(f"\n  {'CHANNEL':20s} | {'PERSONAS':12s} | {'ADS':>5s} | {'PROMOTED':>8s}")
    print(f"  {'─' * 58}")
    for ch, s in sorted(channel_summary.items()):
        p_str = ",".join(s["personas"]) if s["personas"] else "-"
        print(f"  {ch:20s} | {p_str:12s} | {s['ads']:5d} | {s['promoted']:8d}")
    print(f"  {'─' * 58}")
    print(f"\n  TOTAL: {grand_total} collected -> {grand_promoted} promoted")
    print(f"  Final memory: {_mem_mb():.0f} MB")

    # Campaign & spend rebuild
    if grand_promoted > 0:
        print("\n  Rebuilding campaigns & spend estimates...", flush=True)
        try:
            from processor.campaign_builder import rebuild_campaigns_and_spend
            stats = await rebuild_campaigns_and_spend(active_days=30)
            print(f"  Campaigns: {stats['campaigns_total']} | "
                  f"Spend: {stats['spend_estimates_total']} | "
                  f"New advertisers: {stats['created_advertisers']}")
        except Exception as e:
            print(f"  [!] Campaign rebuild failed: {str(e)[:100]}")

    # 후처리
    if not args.skip_postprocess and grand_promoted > 0:
        print("\n  Running post-processing (sequential)...", flush=True)
        await _run_postprocess()

    print(f"\n  Refresh http://localhost:3001 to see results")
    print("=" * 60)


async def _run_postprocess():
    """후처리 작업도 순차 실행 (OOM 방지)."""
    tasks = [
        ("AI Enrich", _pp_ai_enrich),
        ("Advertiser Links", _pp_advertiser_links),
        ("News Collection", _pp_news),
        ("Meta Signal Chain", _pp_meta_signals),
        ("Campaign Chain", _pp_campaign_chain),
    ]

    for name, func in tasks:
        gc.collect()
        print(f"\n  [PP] {name}...", flush=True)
        t0 = time.time()
        try:
            result = await func()
            print(f"  [PP] {name} OK ({time.time()-t0:.0f}s): {result}", flush=True)
        except Exception as e:
            print(f"  [PP] {name} FAIL ({time.time()-t0:.0f}s): {str(e)[:120]}", flush=True)


async def _pp_ai_enrich():
    if not os.getenv("DEEPSEEK_API_KEY"):
        return "skipped (no key)"
    from processor.ai_enricher import enrich_ads
    return await enrich_ads(limit=200)


async def _pp_advertiser_links():
    from processor.advertiser_link_collector import collect_advertiser_links
    return await collect_advertiser_links(limit=100)


async def _pp_news():
    from processor.news_collector import collect_news_mentions
    return await collect_news_mentions()


async def _pp_meta_signals():
    results = {}
    try:
        from processor.smartstore_collector import collect_smartstore_signals
        results["smartstore"] = await collect_smartstore_signals()
        from processor.smartstore_sales_estimator import update_sales_estimates
        results["smartstore_sales"] = await update_sales_estimates()
    except Exception as e:
        results["smartstore_error"] = str(e)[:100]
    try:
        from processor.traffic_estimator import estimate_traffic_signals
        results["traffic"] = await estimate_traffic_signals()
    except Exception as e:
        results["traffic_error"] = str(e)[:100]
    try:
        from processor.activity_scorer import calculate_activity_scores
        results["activity"] = await calculate_activity_scores()
    except Exception as e:
        results["activity_error"] = str(e)[:100]
    try:
        from processor.meta_signal_aggregator import aggregate_meta_signals
        results["aggregate"] = await aggregate_meta_signals()
    except Exception as e:
        results["aggregate_error"] = str(e)[:100]
    return results


async def _pp_campaign_chain():
    results = {}
    try:
        from processor.journey_ingestor import ingest_journey_events
        results["journey"] = await ingest_journey_events()
    except Exception as e:
        results["journey_error"] = str(e)[:100]
    try:
        from processor.campaign_enricher import enrich_campaign_metadata
        results["campaign_enrich"] = await enrich_campaign_metadata(limit=50)
    except Exception as e:
        results["campaign_enrich_error"] = str(e)[:100]
    try:
        from processor.lift_calculator import calculate_campaign_lifts
        results["lift"] = await calculate_campaign_lifts()
    except Exception as e:
        results["lift_error"] = str(e)[:100]
    try:
        from processor.marketing_schedule_builder import update_marketing_schedule
        results["marketing_schedule"] = await update_marketing_schedule(days_back=2)
    except Exception as e:
        results["marketing_schedule_error"] = str(e)[:100]
    return results


if __name__ == "__main__":
    asyncio.run(main())
