"""AdScope: 전체 스케줄러 작업 병렬 실행.

1단계: fast_crawl (10채널 병렬 크롤링 + 캠페인 리빌드)
2단계: 후처리 작업 병렬 실행 (의존성 그룹별)
  - 독립 작업: Brand Monitor, Social Stats, AI Enrich, Advertiser Links, LII
  - 메타시그널 체인: SmartStore → Traffic → Activity → Aggregate
  - 뉴스 + 소셜임팩트: News → Social Impact (메타시그널 이후)
  - 캠페인 체인: Journey → Campaign Enrich → Lift → Marketing Schedule

Usage:
    python scripts/run_all_parallel.py
"""

import asyncio
import io
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
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")

_logs_dir = Path(_root) / "logs"
_logs_dir.mkdir(exist_ok=True)
logger.add(
    str(_logs_dir / "run_all_{time:YYYY-MM-DD}.log"),
    rotation="1 day", retention="7 days", level="DEBUG", encoding="utf-8",
)


async def run_task(name: str, coro_func, *args, **kwargs):
    """개별 작업을 실행하고 결과/에러를 반환."""
    t0 = time.time()
    try:
        result = await coro_func(*args, **kwargs)
        elapsed = time.time() - t0
        logger.info(f"[OK] {name} ({elapsed:.0f}s): {result}")
        return {"name": name, "status": "ok", "elapsed": elapsed, "result": result}
    except Exception as e:
        elapsed = time.time() - t0
        err_msg = str(e)[:200]
        logger.error(f"[FAIL] {name} ({elapsed:.0f}s): {err_msg}")
        return {"name": name, "status": "fail", "elapsed": elapsed, "error": err_msg}


# ──────────────────────────────────────────────
# 1단계: 크롤링 (fast_crawl 내부에서 이미 병렬 처리)
# ──────────────────────────────────────────────
async def phase1_crawl():
    """fast_crawl.py를 subprocess로 실행 (stdout 충돌 방지)."""
    logger.info("=" * 60)
    logger.info("  PHASE 1: Parallel Crawl (10 channels)")
    logger.info("=" * 60)

    import subprocess
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(Path(_root) / "scripts" / "fast_crawl.py"),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=_root,
    )

    # 실시간 출력 스트리밍
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        decoded = line.decode("utf-8", errors="replace").rstrip()
        if decoded:
            logger.info(f"[crawl] {decoded}")

    returncode = await proc.wait()
    if returncode != 0:
        logger.error(f"fast_crawl.py exited with code {returncode}")
    else:
        logger.info("fast_crawl.py completed successfully")


# ──────────────────────────────────────────────
# 2단계: 후처리 작업 병렬 실행
# ──────────────────────────────────────────────
async def phase2_postprocess():
    logger.info("=" * 60)
    logger.info("  PHASE 2: Post-processing (parallel groups)")
    logger.info("=" * 60)

    results = []

    # ── 그룹 A: 완전 독립 작업 (동시 실행) ──
    logger.info("-- Group A: Independent tasks --")
    group_a_tasks = []

    # Brand Monitor
    async def _brand_monitor():
        from crawler.brand_monitor import BrandChannelMonitor
        from processor.brand_pipeline import save_brand_content
        from database.models import Advertiser
        from database import async_session
        from sqlalchemy import select
        import json as _json

        async with async_session() as session:
            stmt = select(Advertiser).where(Advertiser.official_channels.isnot(None))
            result = await session.execute(stmt)
            advertisers = result.scalars().all()
        if not advertisers:
            return {"advertisers": 0, "new_items": 0}
        total_new = 0
        async with BrandChannelMonitor() as monitor:
            for adv in advertisers:
                channels = adv.official_channels
                if isinstance(channels, str):
                    try: channels = _json.loads(channels)
                    except: continue
                if not channels or not isinstance(channels, dict): continue
                yt_url = channels.get("youtube")
                if yt_url:
                    try:
                        contents = await asyncio.wait_for(monitor.monitor_youtube_channel(yt_url), timeout=60)
                        async with async_session() as s:
                            n = await save_brand_content(s, adv.id, "youtube", yt_url, contents)
                            await s.commit()
                            total_new += n
                    except: pass
                ig_url = channels.get("instagram")
                if ig_url:
                    if not ig_url.startswith("http"):
                        ig_url = f"https://www.instagram.com/{ig_url.lstrip('@')}/"
                    try:
                        contents = await asyncio.wait_for(monitor.monitor_instagram_profile(ig_url), timeout=60)
                        async with async_session() as s:
                            n = await save_brand_content(s, adv.id, "instagram", ig_url, contents)
                            await s.commit()
                            total_new += n
                    except: pass
        return {"advertisers": len(advertisers), "new_items": total_new}

    # Social Stats
    async def _social_stats():
        from crawler.social_stats_crawler import SocialStatsCrawler
        from database.models import Advertiser, BrandChannelContent, ChannelStats
        from database import async_session
        from sqlalchemy import select, func
        from datetime import datetime, timedelta, timezone as tz
        import json as _json
        KST = tz(timedelta(hours=9))
        async with async_session() as session:
            stmt = select(Advertiser).where(Advertiser.official_channels.isnot(None))
            result = await session.execute(stmt)
            advertisers = result.scalars().all()
        if not advertisers:
            return {"collected": 0}
        collected = 0
        async with SocialStatsCrawler() as crawler:
            for adv in advertisers:
                channels = adv.official_channels
                if isinstance(channels, str):
                    try: channels = _json.loads(channels)
                    except: continue
                if not channels or not isinstance(channels, dict): continue
                yt_url = channels.get("youtube")
                if yt_url:
                    try:
                        stats = await crawler.collect_youtube_stats(yt_url)
                        if stats:
                            subs = stats.get("subscribers")
                            cutoff = datetime.now() - timedelta(days=30)
                            async with async_session() as s:
                                row_result = await s.execute(
                                    select(func.avg(BrandChannelContent.like_count), func.avg(BrandChannelContent.view_count))
                                    .where(BrandChannelContent.advertiser_id == adv.id, BrandChannelContent.platform == "youtube", BrandChannelContent.discovered_at >= cutoff)
                                )
                                avg_row = row_result.one()
                                avg_likes = round(avg_row[0], 1) if avg_row[0] else None
                                avg_views = round(avg_row[1], 1) if avg_row[1] else None
                                eng_rate = round((avg_likes / subs) * 100, 4) if subs and avg_likes else None
                                s.add(ChannelStats(advertiser_id=adv.id, platform="youtube", channel_url=yt_url,
                                    subscribers=subs, total_posts=stats.get("total_posts"), total_views=stats.get("total_views"),
                                    avg_likes=avg_likes, avg_views=avg_views, engagement_rate=eng_rate, collected_at=datetime.now()))
                                await s.commit()
                                collected += 1
                    except: pass
                ig_url = channels.get("instagram")
                if ig_url:
                    if not ig_url.startswith("http"):
                        ig_url = f"https://www.instagram.com/{ig_url.lstrip('@')}/"
                    try:
                        stats = await crawler.collect_instagram_stats(ig_url)
                        if stats:
                            fol = stats.get("followers")
                            cutoff = datetime.now() - timedelta(days=30)
                            async with async_session() as s:
                                row_result = await s.execute(
                                    select(func.avg(BrandChannelContent.like_count), func.avg(BrandChannelContent.view_count))
                                    .where(BrandChannelContent.advertiser_id == adv.id, BrandChannelContent.platform == "instagram", BrandChannelContent.discovered_at >= cutoff)
                                )
                                avg_row = row_result.one()
                                avg_likes = round(avg_row[0], 1) if avg_row[0] else None
                                avg_views = round(avg_row[1], 1) if avg_row[1] else None
                                eng_rate = round((avg_likes / fol) * 100, 4) if fol and avg_likes else None
                                s.add(ChannelStats(advertiser_id=adv.id, platform="instagram", channel_url=ig_url,
                                    followers=fol, total_posts=stats.get("total_posts"),
                                    avg_likes=avg_likes, avg_views=avg_views, engagement_rate=eng_rate, collected_at=datetime.now()))
                                await s.commit()
                                collected += 1
                    except: pass
        return {"collected": collected}

    # AI Enrich
    async def _ai_enrich():
        if not os.getenv("DEEPSEEK_API_KEY"):
            return {"skipped": "no DEEPSEEK_API_KEY"}
        from processor.ai_enricher import enrich_ads
        return await enrich_ads(limit=200)

    # Advertiser Link Collector
    async def _advertiser_links():
        from processor.advertiser_link_collector import collect_advertiser_links
        return await collect_advertiser_links(limit=100)

    # LII: Media Crawl + Collect + Score
    async def _lii_all():
        results = {}
        try:
            from processor.launch_mention_collector import crawl_media_sources, collect_launch_mentions
            results["media_crawl"] = await crawl_media_sources()
            results["mention_collect"] = await collect_launch_mentions()
        except Exception as e:
            results["lii_collect_error"] = str(e)[:100]
        try:
            from processor.launch_impact_scorer import calculate_launch_impact_scores
            results["impact_scores"] = await calculate_launch_impact_scores()
        except Exception as e:
            results["lii_score_error"] = str(e)[:100]
        return results

    # News Collection
    async def _news():
        from processor.news_collector import collect_news_mentions
        return await collect_news_mentions()

    group_a_tasks.append(run_task("Brand Monitor", _brand_monitor))
    group_a_tasks.append(run_task("Social Stats", _social_stats))
    group_a_tasks.append(run_task("AI Enrich", _ai_enrich))
    group_a_tasks.append(run_task("Advertiser Links", _advertiser_links))
    group_a_tasks.append(run_task("LII (Launch Impact)", _lii_all))
    group_a_tasks.append(run_task("News Collection", _news))

    # ── 그룹 B: 메타시그널 체인 (순차 의존성) ──
    async def _meta_signal_chain():
        chain_results = {}
        # 1. SmartStore
        try:
            from processor.smartstore_collector import collect_smartstore_signals
            chain_results["smartstore"] = await collect_smartstore_signals()
            from processor.smartstore_sales_estimator import update_sales_estimates
            chain_results["smartstore_sales"] = await update_sales_estimates()
        except Exception as e:
            chain_results["smartstore_error"] = str(e)[:100]
        # 2. Traffic
        try:
            from processor.traffic_estimator import estimate_traffic_signals
            chain_results["traffic"] = await estimate_traffic_signals()
        except Exception as e:
            chain_results["traffic_error"] = str(e)[:100]
        # 3. Activity
        try:
            from processor.activity_scorer import calculate_activity_scores
            chain_results["activity"] = await calculate_activity_scores()
        except Exception as e:
            chain_results["activity_error"] = str(e)[:100]
        # 4. Aggregate
        try:
            from processor.meta_signal_aggregator import aggregate_meta_signals
            chain_results["aggregate"] = await aggregate_meta_signals()
        except Exception as e:
            chain_results["aggregate_error"] = str(e)[:100]
        return chain_results

    group_a_tasks.append(run_task("Meta Signal Chain", _meta_signal_chain))

    # 그룹 A + B 병렬 실행
    group_ab_results = await asyncio.gather(*group_a_tasks, return_exceptions=True)
    results.extend(group_ab_results)

    # ── 그룹 C: Social Impact (News + Meta-signal 완료 후) ──
    logger.info("-- Group C: Social Impact (after News + Meta signals) --")
    try:
        r = await run_task("Social Impact Score", _social_impact)
        results.append(r)
    except:
        pass

    # ── 그룹 D: 캠페인 체인 (순차) ──
    logger.info("-- Group D: Campaign chain (sequential) --")
    r = await run_task("Campaign Chain", _campaign_chain)
    results.append(r)

    return results


async def _social_impact():
    from processor.social_impact_scorer import calculate_social_impact_scores
    return await calculate_social_impact_scores()


async def _campaign_chain():
    chain_results = {}
    # 1. Journey ingest
    try:
        from processor.journey_ingestor import ingest_journey_events
        chain_results["journey"] = await ingest_journey_events()
    except Exception as e:
        chain_results["journey_error"] = str(e)[:100]
    # 2. Campaign enrich
    try:
        from processor.campaign_enricher import enrich_campaign_metadata
        chain_results["campaign_enrich"] = await enrich_campaign_metadata(limit=50)
    except Exception as e:
        chain_results["campaign_enrich_error"] = str(e)[:100]
    # 3. Lift calculate
    try:
        from processor.lift_calculator import calculate_campaign_lifts
        chain_results["lift"] = await calculate_campaign_lifts()
    except Exception as e:
        chain_results["lift_error"] = str(e)[:100]
    # 4. Marketing schedule
    try:
        from processor.marketing_schedule_builder import update_marketing_schedule
        chain_results["marketing_schedule"] = await update_marketing_schedule(days_back=2)
    except Exception as e:
        chain_results["marketing_schedule_error"] = str(e)[:100]
    return chain_results


# ──────────────────────────────────────────────
# 메인 실행
# ──────────────────────────────────────────────
async def phase3_r2_upload():
    """크롤 후 신규 이미지를 Cloudflare R2에 자동 업로드."""
    logger.info("=" * 60)
    logger.info("  PHASE 3: R2 Image Upload (new files only)")
    logger.info("=" * 60)
    import subprocess
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(Path(_root) / "scripts" / "upload_images_to_r2.py"),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=_root,
    )
    lines_shown = 0
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        decoded = line.decode("utf-8", errors="replace").rstrip()
        if decoded and lines_shown < 20:
            logger.info(f"[r2] {decoded}")
            lines_shown += 1
    await proc.wait()
    if proc.returncode != 0:
        logger.warning(f"R2 upload exited with code {proc.returncode} (non-fatal)")
    else:
        logger.info("R2 image upload completed")


async def main():
    from database import init_db
    await init_db()

    overall_start = time.time()

    logger.info("=" * 70)
    logger.info("  AdScope: ALL SCHEDULER TASKS - PARALLEL EXECUTION")
    logger.info("=" * 70)

    # Phase 1: Crawling
    t1 = time.time()
    try:
        await phase1_crawl()
    except Exception as e:
        logger.error(f"Phase 1 (crawl) failed: {str(e)[:200]}")
    crawl_elapsed = time.time() - t1
    logger.info(f"Phase 1 (crawl) completed in {crawl_elapsed:.0f}s")

    # Phase 2: Post-processing
    t2 = time.time()
    try:
        pp_results = await phase2_postprocess()
    except Exception as e:
        logger.error(f"Phase 2 (post-process) failed: {str(e)[:200]}")
        pp_results = []
    pp_elapsed = time.time() - t2

    # Phase 3: R2 Image Upload (신규 이미지 자동 업로드)
    t3 = time.time()
    try:
        await phase3_r2_upload()
    except Exception as e:
        logger.error(f"Phase 3 (R2 upload) failed: {str(e)[:200]}")
    r2_elapsed = time.time() - t3

    # ── 최종 결과 ──
    total_elapsed = time.time() - overall_start
    logger.info("=" * 70)
    logger.info(f"  ALL TASKS COMPLETED ({total_elapsed:.0f}s total)")
    logger.info(f"  Phase 1 (crawl): {crawl_elapsed:.0f}s")
    logger.info(f"  Phase 2 (post-process): {pp_elapsed:.0f}s")
    logger.info(f"  Phase 3 (R2 upload): {r2_elapsed:.0f}s")
    logger.info("=" * 70)

    ok_count = sum(1 for r in pp_results if isinstance(r, dict) and r.get("status") == "ok")
    fail_count = sum(1 for r in pp_results if isinstance(r, dict) and r.get("status") == "fail")
    logger.info(f"  Post-process results: {ok_count} OK / {fail_count} FAIL")

    for r in pp_results:
        if isinstance(r, dict):
            status_icon = "[OK]" if r["status"] == "ok" else "[FAIL]"
            logger.info(f"  {status_icon} {r['name']}: {r.get('elapsed', 0):.0f}s")

    logger.info("=" * 70)
    logger.info("  Refresh http://localhost:3001 to see updated results")
    logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
