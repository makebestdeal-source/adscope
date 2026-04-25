"""Run social and meta-signal collection without launching ad crawlers.

This job is intentionally separate from fast_crawl/run_all_parallel so social
coverage can be refreshed more often without paying the full ad-crawl cost.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "adscope.db"
REPORT_JSON = ROOT / "cache" / "reports" / "social_signal_boost_latest.json"
REPORT_MD = ROOT / "cache" / "reports" / "social_signal_boost_latest.md"
KST = timezone(timedelta(hours=9))

sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _parse_channels(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if v}
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): str(v) for k, v in parsed.items() if v}


def _ig_url(value: str) -> str:
    if value.startswith("http"):
        return value
    return f"https://www.instagram.com/{value.lstrip('@')}/"


def coverage_snapshot() -> dict[str, Any]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        def one(sql: str) -> Any:
            return cur.execute(sql).fetchone()[0]

        return {
            "advertisers": one("SELECT COUNT(*) FROM advertisers"),
            "with_website": one(
                "SELECT COUNT(*) FROM advertisers WHERE website IS NOT NULL AND TRIM(website) != ''"
            ),
            "with_official_channels": one(
                """
                SELECT COUNT(*)
                FROM advertisers
                WHERE official_channels IS NOT NULL
                  AND TRIM(CAST(official_channels AS TEXT)) NOT IN ('', '{}', 'null')
                """
            ),
            "active_advertisers_90d": one(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT DISTINCT advertiser_id
                    FROM ad_details
                    WHERE advertiser_id IS NOT NULL
                      AND COALESCE(verification_status, '') != 'rejected'
                      AND last_seen_at >= datetime('now', '-90 days')
                )
                """
            ),
            "channel_stats": dict(
                cur.execute(
                    """
                    SELECT COUNT(*) AS rows,
                           COUNT(DISTINCT advertiser_id) AS advertisers,
                           MAX(collected_at) AS latest
                    FROM channel_stats
                    """
                ).fetchone()
            ),
            "brand_channel_contents": dict(
                cur.execute(
                    """
                    SELECT COUNT(*) AS rows,
                           COUNT(DISTINCT advertiser_id) AS advertisers,
                           MAX(discovered_at) AS latest
                    FROM brand_channel_contents
                    """
                ).fetchone()
            ),
            "news_mentions": dict(
                cur.execute(
                    """
                    SELECT COUNT(*) AS rows,
                           COUNT(DISTINCT advertiser_id) AS advertisers,
                           MAX(collected_at) AS latest
                    FROM news_mentions
                    """
                ).fetchone()
            ),
            "traffic_signals": dict(
                cur.execute(
                    """
                    SELECT COUNT(*) AS rows,
                           COUNT(DISTINCT advertiser_id) AS advertisers,
                           MAX(date) AS latest
                    FROM traffic_signals
                    """
                ).fetchone()
            ),
            "social_impact_scores": dict(
                cur.execute(
                    """
                    SELECT COUNT(*) AS rows,
                           COUNT(DISTINCT advertiser_id) AS advertisers,
                           MAX(date) AS latest
                    FROM social_impact_scores
                    """
                ).fetchone()
            ),
            "meta_signal_composites": dict(
                cur.execute(
                    """
                    SELECT COUNT(*) AS rows,
                           COUNT(DISTINCT advertiser_id) AS advertisers,
                           MAX(date) AS latest
                    FROM meta_signal_composites
                    """
                ).fetchone()
            ),
        }


def load_signal_targets(limit: int) -> list[dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                a.id,
                a.name,
                a.official_channels,
                (
                    SELECT MAX(d.last_seen_at)
                    FROM ad_details d
                    WHERE d.advertiser_id = a.id
                      AND COALESCE(d.verification_status, '') != 'rejected'
                ) AS last_ad_at,
                (
                    SELECT MAX(b.discovered_at)
                    FROM brand_channel_contents b
                    WHERE b.advertiser_id = a.id
                ) AS content_at,
                (
                    SELECT MAX(c.collected_at)
                    FROM channel_stats c
                    WHERE c.advertiser_id = a.id
                ) AS stats_at
            FROM advertisers a
            WHERE a.official_channels IS NOT NULL
              AND TRIM(CAST(a.official_channels AS TEXT)) NOT IN ('', '{}', 'null')
            ORDER BY
                CASE
                  WHEN last_ad_at >= datetime('now', '-90 days') THEN 0
                  WHEN last_ad_at IS NOT NULL THEN 1
                  ELSE 2
                END,
                COALESCE(content_at, '1970-01-01') ASC,
                COALESCE(stats_at, '1970-01-01') ASC,
                a.id ASC
            LIMIT ?
            """,
            (max(0, limit),),
        ).fetchall()
    return [dict(row) for row in rows]


async def run_step(name: str, func, *args, **kwargs) -> dict[str, Any]:
    started = time.time()
    logger.info("[step] {} start", name)
    try:
        result = await func(*args, **kwargs)
        elapsed = round(time.time() - started, 1)
        logger.info("[step] {} ok ({}s): {}", name, elapsed, result)
        return {"name": name, "status": "ok", "elapsed": elapsed, "result": _jsonable(result)}
    except Exception as exc:
        elapsed = round(time.time() - started, 1)
        logger.exception("[step] {} failed", name)
        return {"name": name, "status": "fail", "elapsed": elapsed, "error": str(exc)[:300]}


async def discover_channels(limit: int) -> dict[str, Any]:
    from processor.social_channel_discoverer import discover_social_channels

    return await discover_social_channels(limit=limit)


async def collect_brand_content(limit: int, per_channel_timeout: int) -> dict[str, Any]:
    from crawler.brand_monitor import BrandChannelMonitor
    from database import async_session
    from processor.brand_pipeline import save_brand_content

    targets = load_signal_targets(limit)
    stats = {
        "targets": len(targets),
        "processed": 0,
        "new_items": 0,
        "youtube_channels": 0,
        "instagram_channels": 0,
        "errors": 0,
    }

    async with BrandChannelMonitor() as monitor:
        for target in targets:
            channels = _parse_channels(target.get("official_channels"))
            if not channels:
                continue
            stats["processed"] += 1

            yt_url = channels.get("youtube")
            if yt_url:
                try:
                    contents = await asyncio.wait_for(
                        monitor.monitor_youtube_channel(yt_url),
                        timeout=per_channel_timeout,
                    )
                    async with async_session() as session:
                        new_count = await save_brand_content(
                            session, int(target["id"]), "youtube", yt_url, contents
                        )
                        await session.commit()
                    stats["youtube_channels"] += 1
                    stats["new_items"] += new_count
                except Exception:
                    stats["errors"] += 1

            ig = channels.get("instagram")
            if ig:
                ig_url = _ig_url(ig)
                try:
                    contents = await asyncio.wait_for(
                        monitor.monitor_instagram_profile(ig_url),
                        timeout=per_channel_timeout,
                    )
                    async with async_session() as session:
                        new_count = await save_brand_content(
                            session, int(target["id"]), "instagram", ig_url, contents
                        )
                        await session.commit()
                    stats["instagram_channels"] += 1
                    stats["new_items"] += new_count
                except Exception:
                    stats["errors"] += 1

            await asyncio.sleep(0.3)

    return stats


async def _compute_engagement(advertiser_id: int, platform: str, audience: int | None) -> dict[str, Any]:
    from database import async_session
    from database.models import BrandChannelContent
    from sqlalchemy import func, select

    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=30)
    async with async_session() as session:
        row = (
            await session.execute(
                select(
                    func.avg(BrandChannelContent.like_count),
                    func.avg(BrandChannelContent.view_count),
                ).where(
                    BrandChannelContent.advertiser_id == advertiser_id,
                    BrandChannelContent.platform == platform,
                    BrandChannelContent.discovered_at >= cutoff,
                )
            )
        ).one()

    avg_likes = round(row[0], 1) if row[0] else None
    avg_views = round(row[1], 1) if row[1] else None
    engagement_rate = None
    if audience and audience > 0 and avg_likes is not None:
        engagement_rate = round((avg_likes / audience) * 100, 4)
    return {"avg_likes": avg_likes, "avg_views": avg_views, "engagement_rate": engagement_rate}


async def _save_channel_stats(
    advertiser_id: int,
    platform: str,
    channel_url: str,
    stats: dict[str, Any],
    engagement: dict[str, Any],
) -> None:
    from database import async_session
    from database.models import ChannelStats

    async with async_session() as session:
        session.add(
            ChannelStats(
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
                collected_at=datetime.now(KST).replace(tzinfo=None),
            )
        )
        await session.commit()


async def collect_channel_stats(limit: int, per_channel_timeout: int) -> dict[str, Any]:
    from crawler.social_stats_crawler import SocialStatsCrawler

    targets = load_signal_targets(limit)
    stats = {
        "targets": len(targets),
        "youtube_success": 0,
        "instagram_success": 0,
        "errors": 0,
    }

    async with SocialStatsCrawler() as crawler:
        for target in targets:
            adv_id = int(target["id"])
            channels = _parse_channels(target.get("official_channels"))
            if not channels:
                continue

            yt_url = channels.get("youtube")
            if yt_url:
                try:
                    yt_stats = await asyncio.wait_for(
                        crawler.collect_youtube_stats(yt_url),
                        timeout=per_channel_timeout,
                    )
                    if yt_stats:
                        audience = yt_stats.get("subscribers")
                        engagement = await _compute_engagement(adv_id, "youtube", audience)
                        await _save_channel_stats(adv_id, "youtube", yt_url, yt_stats, engagement)
                        stats["youtube_success"] += 1
                except Exception:
                    stats["errors"] += 1

            ig = channels.get("instagram")
            if ig:
                ig_url = _ig_url(ig)
                try:
                    ig_stats = await asyncio.wait_for(
                        crawler.collect_instagram_stats(ig_url),
                        timeout=per_channel_timeout,
                    )
                    if ig_stats:
                        audience = ig_stats.get("followers")
                        engagement = await _compute_engagement(adv_id, "instagram", audience)
                        await _save_channel_stats(adv_id, "instagram", ig_url, ig_stats, engagement)
                        stats["instagram_success"] += 1
                except Exception:
                    stats["errors"] += 1

            await asyncio.sleep(0.3)

    return stats


async def collect_news(limit: int, articles: int) -> dict[str, Any]:
    if not os.getenv("NAVER_SEARCH_CLIENT_ID") or not os.getenv("NAVER_SEARCH_CLIENT_SECRET"):
        return {"skipped": "missing NAVER_SEARCH_CLIENT_ID/SECRET"}
    from processor.news_collector import collect_news_mentions

    return await collect_news_mentions(max_advertisers=limit, articles_per_brand=articles)


async def collect_trends(limit: int, days: int) -> dict[str, Any]:
    if not os.getenv("NAVER_DATALAB_CLIENT_ID") or not os.getenv("NAVER_DATALAB_CLIENT_SECRET"):
        return {"skipped": "missing NAVER_DATALAB_CLIENT_ID/SECRET"}
    from processor.search_trend_collector import collect_search_trends

    return await collect_search_trends(max_advertisers=limit, days=days)


async def recompute_scores() -> dict[str, Any]:
    results: dict[str, Any] = {}

    try:
        from processor.activity_scorer import calculate_activity_scores

        results["activity_scores"] = await calculate_activity_scores()
    except Exception as exc:
        results["activity_scores_error"] = str(exc)[:200]

    try:
        from processor.meta_signal_aggregator import aggregate_meta_signals

        results["meta_signal_composites"] = await aggregate_meta_signals()
    except Exception as exc:
        results["meta_signal_composites_error"] = str(exc)[:200]

    try:
        from processor.social_impact_scorer import calculate_social_impact_scores

        results["social_impact_scores"] = await calculate_social_impact_scores()
    except Exception as exc:
        results["social_impact_scores_error"] = str(exc)[:200]

    try:
        from processor.social_ranking_calculator import calculate_social_rankings

        results["social_category_rankings"] = await calculate_social_rankings()
    except Exception as exc:
        results["social_category_rankings_error"] = str(exc)[:200]

    return results


def write_report(report: dict[str, Any]) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    before = report["before"]
    after = report["after"]
    lines = [
        "# Social Signal Boost",
        "",
        f"- started_at: {report['started_at']}",
        f"- finished_at: {report['finished_at']}",
        f"- elapsed_seconds: {report['elapsed_seconds']}",
        "",
        "## Coverage",
        "",
        "| Metric | Before | After |",
        "|---|---:|---:|",
        f"| official channel advertisers | {before['with_official_channels']} | {after['with_official_channels']} |",
        f"| channel stats advertisers | {before['channel_stats']['advertisers']} | {after['channel_stats']['advertisers']} |",
        f"| brand content advertisers | {before['brand_channel_contents']['advertisers']} | {after['brand_channel_contents']['advertisers']} |",
        f"| news mention advertisers | {before['news_mentions']['advertisers']} | {after['news_mentions']['advertisers']} |",
        f"| traffic signal advertisers | {before['traffic_signals']['advertisers']} | {after['traffic_signals']['advertisers']} |",
        "",
        "## Steps",
        "",
        "| Step | Status | Elapsed | Result |",
        "|---|---|---:|---|",
    ]
    for step in report["steps"]:
        result = step.get("result", step.get("error", ""))
        result_text = json.dumps(result, ensure_ascii=False)[:500]
        lines.append(
            f"| {step['name']} | {step['status']} | {step['elapsed']}s | `{result_text}` |"
        )
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run social/meta signal boost")
    parser.add_argument("--discover-limit", type=int, default=500)
    parser.add_argument("--content-limit", type=int, default=80)
    parser.add_argument("--stats-limit", type=int, default=120)
    parser.add_argument("--news-limit", type=int, default=150)
    parser.add_argument("--news-articles", type=int, default=10)
    parser.add_argument("--trend-limit", type=int, default=100)
    parser.add_argument("--trend-days", type=int, default=30)
    parser.add_argument("--per-channel-timeout", type=int, default=45)
    parser.add_argument("--skip-discovery", action="store_true")
    parser.add_argument("--skip-content", action="store_true")
    parser.add_argument("--skip-stats", action="store_true")
    parser.add_argument("--skip-news", action="store_true")
    parser.add_argument("--skip-trends", action="store_true")
    parser.add_argument("--skip-scores", action="store_true")
    args = parser.parse_args()

    from database import init_db

    await init_db()
    started = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    t0 = time.time()
    before = coverage_snapshot()
    steps: list[dict[str, Any]] = []

    logger.info("Social signal boost started")
    logger.info("Before coverage: {}", before)

    if not args.skip_discovery and args.discover_limit > 0:
        steps.append(await run_step("discover_social_channels", discover_channels, args.discover_limit))
    if not args.skip_content and args.content_limit > 0:
        steps.append(
            await run_step(
                "collect_brand_content",
                collect_brand_content,
                args.content_limit,
                args.per_channel_timeout,
            )
        )
    if not args.skip_stats and args.stats_limit > 0:
        steps.append(
            await run_step(
                "collect_channel_stats",
                collect_channel_stats,
                args.stats_limit,
                args.per_channel_timeout,
            )
        )
    if not args.skip_news and args.news_limit > 0:
        steps.append(await run_step("collect_news", collect_news, args.news_limit, args.news_articles))
    if not args.skip_trends and args.trend_limit > 0:
        steps.append(await run_step("collect_search_trends", collect_trends, args.trend_limit, args.trend_days))
    if not args.skip_scores:
        steps.append(await run_step("recompute_scores", recompute_scores))

    after = coverage_snapshot()
    report = {
        "started_at": started,
        "finished_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round(time.time() - t0, 1),
        "before": before,
        "after": after,
        "steps": steps,
    }
    write_report(report)

    logger.info("After coverage: {}", after)
    logger.info("Report: {}", REPORT_MD)


if __name__ == "__main__":
    asyncio.run(main())
