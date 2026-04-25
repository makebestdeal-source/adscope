"""구글 Ads Transparency 날짜 범위 지정 아카이브 수집.

1개월 단위로 날짜 필터를 설정하고 전체 프리픽스 순회.
기본: 2025년 1~3월 (월별 3회 반복)

사용법:
    python scripts/archive_crawl_dated.py                        # 2025-01~03 전체
    python scripts/archive_crawl_dated.py --months 2025-01      # 1월만
    python scripts/archive_crawl_dated.py --channels gdn        # GDN만
    python scripts/archive_crawl_dated.py --reset               # 체크포인트 초기화
"""
import argparse
import asyncio
import calendar
import io
import json
import os
import random
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

# ── 아카이브 모드 환경변수 ──
os.environ["YT_ADS_MAX_ADVERTISERS"] = "500"
os.environ["YT_ADS_MAX_ADS"] = "9999"
os.environ["YT_ADS_WAIT_MS"] = "12000"
os.environ["YT_ADS_MAX_SCROLLS"] = "30"
os.environ["GS_ADS_MAX_ADVERTISERS"] = "500"
os.environ["GS_ADS_MAX_ADS"] = "9999"
os.environ["GDN_MAX_ADVERTISERS"] = "500"
os.environ["GDN_MAX_ADS"] = "9999"
os.environ["GDN_MAX_SCROLLS"] = "30"
os.environ["CRAWLER_DWELL_MIN_MS"] = "1500"
os.environ["CRAWLER_DWELL_MAX_MS"] = "2500"
os.environ["CRAWLER_WARMUP_SITE_COUNT"] = "0"
os.environ["META_TRUST_CHECK"] = "false"

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO")

from crawler.stealth_patch import enable_stealth
enable_stealth()

from database import init_db
from crawler.personas.profiles import PERSONAS
from crawler.personas.device_config import get_device_for_persona
from processor.data_washer import save_to_staging, wash_and_promote
from database import async_session
from sqlalchemy import text as sa_text


# ── 기본 월 목록 ──
DEFAULT_MONTHS = ["2025-01", "2025-02", "2025-03"]

# 채널 목록
CHANNEL_MAP = {
    "gdn":    "google_gdn",
    "yt":     "youtube_ads",
    "search": "google_search_ads",
}

CHANNEL_TIMEOUT = {
    "youtube_ads": 900,
    "google_gdn": 900,
    "google_search_ads": 600,
}

_ARCHIVE_SOURCE_MAP = {
    "youtube_ads": "google_transparency",
    "google_gdn": "google_transparency",
    "google_search_ads": "google_transparency",
}


def _get_crawler_cls(channel_name):
    from crawler.youtube_ads import YouTubeAdsCrawler
    from crawler.google_gdn import GoogleGDNCrawler
    from crawler.google_search_ads import GoogleSearchAdsCrawler
    return {
        "youtube_ads": YouTubeAdsCrawler,
        "google_gdn": GoogleGDNCrawler,
        "google_search_ads": GoogleSearchAdsCrawler,
    }[channel_name]


def _generate_prefixes() -> list[str]:
    prefixes = []
    for cho in range(19):
        for jung in range(21):
            code = 0xAC00 + (cho * 21 + jung) * 28
            prefixes.append(chr(code))
    prefixes.extend([chr(c) for c in range(ord('a'), ord('z') + 1)])
    prefixes.extend([str(i) for i in range(10)])
    return prefixes


def _parse_prefix_args(raw: str) -> list[str]:
    if not raw:
        return []
    values: list[str] = []
    for item in raw.split(","):
        token = item.strip()
        if token:
            values.append(token)
    return values


def _select_prefixes(
    all_prefixes: list[str],
    explicit_prefixes: list[str],
    max_prefixes: int | None,
    worker_index: int,
    worker_count: int,
) -> list[str]:
    if explicit_prefixes:
        selected = explicit_prefixes[:]
    else:
        selected = all_prefixes[:]

    if worker_count > 1:
        selected = [
            prefix for idx, prefix in enumerate(selected)
            if idx % worker_count == worker_index
        ]

    if max_prefixes is not None and max_prefixes > 0:
        selected = selected[:max_prefixes]

    return selected


def _set_date_env(year: int, month: int):
    """크롤러가 읽는 날짜 범위 환경변수 세팅."""
    last_day = calendar.monthrange(year, month)[1]
    os.environ["CRAWL_DATE_START_YEAR"] = str(year)
    os.environ["CRAWL_DATE_START_MONTH"] = str(month)
    os.environ["CRAWL_DATE_START_DAY"] = "1"
    os.environ["CRAWL_DATE_END_YEAR"] = str(year)
    os.environ["CRAWL_DATE_END_MONTH"] = str(month)
    os.environ["CRAWL_DATE_END_DAY"] = str(last_day)


def _clear_date_env():
    for k in ["CRAWL_DATE_START_YEAR", "CRAWL_DATE_START_MONTH", "CRAWL_DATE_START_DAY",
              "CRAWL_DATE_END_YEAR", "CRAWL_DATE_END_MONTH", "CRAWL_DATE_END_DAY"]:
        os.environ.pop(k, None)


def _parse_archive_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    if text.isdigit():
        try:
            return datetime.fromtimestamp(int(text), UTC).date()
        except (ValueError, OSError):
            return None

    normalized = text.replace("Z", "+00:00")
    try:
        if len(normalized) >= 10:
            return date.fromisoformat(normalized[:10])
    except ValueError:
        return None
    return None


def _ad_overlaps_month(ad: dict, month_start: date, month_end: date) -> bool:
    extra = ad.get("extra_data") or {}
    start_date = (
        _parse_archive_date(ad.get("ad_delivery_start"))
        or _parse_archive_date(extra.get("ad_delivery_start_time"))
        or _parse_archive_date(extra.get("ad_start_date"))
        or _parse_archive_date(extra.get("start_ts"))
    )
    end_date = (
        _parse_archive_date(ad.get("ad_delivery_end"))
        or _parse_archive_date(extra.get("ad_delivery_end_time"))
        or _parse_archive_date(extra.get("ad_delivery_stop_time"))
        or _parse_archive_date(extra.get("ad_end_date"))
        or _parse_archive_date(extra.get("end_ts"))
    )

    if start_date and start_date > month_end:
        return False
    if end_date and end_date < month_start:
        return False
    return True


def _filter_ads_for_month(ads: list[dict], month_start: date, month_end: date) -> list[dict]:
    return [ad for ad in ads if _ad_overlaps_month(ad, month_start, month_end)]


# ── 체크포인트 (월별) ──
CHECKPOINT_DIR = Path(_root) / ".archive_checkpoints_dated"


def _cp_key(channel: str, ym: str) -> str:
    return f"{channel}_{ym.replace('-', '_')}"


def _load_done(channel: str, ym: str) -> set[str]:
    CHECKPOINT_DIR.mkdir(exist_ok=True)
    fp = CHECKPOINT_DIR / f"{_cp_key(channel, ym)}.done"
    if fp.exists():
        return set(fp.read_text(encoding="utf-8").strip().split("\n"))
    return set()


def _save_done(channel: str, ym: str, prefix: str):
    fp = CHECKPOINT_DIR / f"{_cp_key(channel, ym)}.done"
    with open(fp, "a", encoding="utf-8") as f:
        f.write(prefix + "\n")


async def _mark_retroactive(session, channel_name: str):
    archive_source = _ARCHIVE_SOURCE_MAP.get(channel_name, channel_name)
    await session.execute(sa_text("""
        UPDATE ad_details
        SET
            is_retroactive = 1,
            archive_source  = :archive_source,
            ad_delivery_start = CASE
                WHEN json_extract(extra_data, '$.ad_delivery_start_time') IS NOT NULL
                THEN substr(json_extract(extra_data, '$.ad_delivery_start_time'), 1, 10)
                WHEN json_extract(extra_data, '$.start_ts') IS NOT NULL
                THEN date(CAST(json_extract(extra_data, '$.start_ts') AS INTEGER), 'unixepoch')
                ELSE NULL
            END,
            ad_delivery_end = CASE
                WHEN json_extract(extra_data, '$.ad_delivery_end_time') IS NOT NULL
                THEN substr(json_extract(extra_data, '$.ad_delivery_end_time'), 1, 10)
                WHEN json_extract(extra_data, '$.ad_delivery_stop_time') IS NOT NULL
                THEN substr(json_extract(extra_data, '$.ad_delivery_stop_time'), 1, 10)
                WHEN json_extract(extra_data, '$.end_ts') IS NOT NULL
                THEN date(CAST(json_extract(extra_data, '$.end_ts') AS INTEGER), 'unixepoch')
                ELSE NULL
            END
        WHERE snapshot_id IN (
            SELECT id FROM ad_snapshots
            WHERE channel = :channel
              AND captured_at >= datetime('now', '-180 seconds')
        )
          AND (is_retroactive IS NULL OR is_retroactive = 0)
    """), {"archive_source": archive_source, "channel": channel_name})
    await session.commit()


async def crawl_prefix(
    channel_name,
    keyword,
    persona,
    device,
    persona_code,
    timeout,
    month_start: date,
    month_end: date,
):
    cls = _get_crawler_cls(channel_name)
    t0 = time.time()
    try:
        async with cls() as crawler:
            result = await asyncio.wait_for(
                crawler.crawl_keyword(keyword, persona, device),
                timeout=timeout,
            )
        ads = result.get("ads", [])
        filtered_ads = _filter_ads_for_month(ads, month_start, month_end)
        filtered_out = len(ads) - len(filtered_ads)
        if filtered_out:
            print(
                f"  [F] {channel_name}/{keyword} filtered {filtered_out} ads outside "
                f"{month_start.isoformat()}..{month_end.isoformat()}",
                flush=True,
            )
        result["ads"] = filtered_ads
        ads = filtered_ads
        if not ads:
            return 0, 0, True

        async with async_session() as session:
            batch_id, staged = await save_to_staging(
                session, channel_name, result, keyword, persona_code, device.device_type,
            )
        async with async_session() as session:
            wp_result = await wash_and_promote(session, batch_id)
        async with async_session() as session:
            await _mark_retroactive(session, channel_name)

        promoted = wp_result["promote"].get("promoted", 0)
        deduped = wp_result["promote"].get("deduped", 0)
        elapsed = time.time() - t0
        print(
            f"  [+] {channel_name}/{keyword} -> "
            f"{len(ads)} raw / {promoted} saved / {deduped} dup ({elapsed:.1f}s)",
            flush=True,
        )
        return len(ads), promoted, True

    except asyncio.TimeoutError:
        elapsed = time.time() - t0
        print(f"  [T] {channel_name}/{keyword} timeout ({elapsed:.0f}s)", flush=True)
        return 0, 0, False
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [E] {channel_name}/{keyword} error: {str(e)[:80]} ({elapsed:.0f}s)", flush=True)
        return 0, 0, False


async def run_channel_month(channel_name, ym, prefixes, deadline):
    persona = PERSONAS["M30"]
    device = get_device_for_persona(persona)
    per_prefix_timeout = CHANNEL_TIMEOUT.get(channel_name, 600)
    year, month = int(ym[:4]), int(ym[5:7])
    month_start = date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])

    done = _load_done(channel_name, ym)
    remaining = [p for p in prefixes if p not in done]
    if done:
        print(f"  [{channel_name}/{ym}] resume: {len(done)} done, {len(remaining)} remaining", flush=True)

    total_raw = total_promoted = 0
    random.shuffle(remaining)

    for i, prefix in enumerate(remaining):
        if time.time() >= deadline:
            print(f"  [{channel_name}/{ym}] deadline at {i}/{len(remaining)}", flush=True)
            break
        left = deadline - time.time()
        if left < 30:
            break

        raw, promoted, completed = await crawl_prefix(
            channel_name, prefix, persona, device, "M30",
            timeout=min(left, per_prefix_timeout),
            month_start=month_start,
            month_end=month_end,
        )
        total_raw += raw
        total_promoted += promoted
        if completed:
            _save_done(channel_name, ym, prefix)

    return total_raw, total_promoted


async def main():
    parser = argparse.ArgumentParser(description="Google 날짜 범위 아카이브 수집")
    parser.add_argument("--months", default=",".join(DEFAULT_MONTHS),
                        help="수집 월 (YYYY-MM 콤마구분, 기본: 2025-01~03)")
    parser.add_argument("--channels", default="gdn,yt,search",
                        help="채널: gdn,yt,search (기본: 전체)")
    parser.add_argument("--timeout", type=int, default=43200,
                        help="월별 총 타임아웃(초), 기본 12시간")
    parser.add_argument("--reset", action="store_true",
                        help="체크포인트 초기화")
    parser.add_argument("--prefixes", default="",
                        help="명시할 prefix 목록 (콤마구분). 예: 가,나,a,1")
    parser.add_argument("--max-prefixes", type=int, default=0,
                        help="앞에서부터 최대 prefix 수만 실행 (파일럿/저부하용)")
    parser.add_argument("--worker-index", type=int, default=0,
                        help="샤드 실행용 worker index (0-base)")
    parser.add_argument("--worker-count", type=int, default=1,
                        help="샤드 실행용 전체 worker 수")
    args = parser.parse_args()

    months = [m.strip() for m in args.months.split(",")]
    channel_keys = [c.strip() for c in args.channels.split(",")]
    channels = [CHANNEL_MAP[k] for k in channel_keys if k in CHANNEL_MAP]
    if args.worker_count < 1:
        raise SystemExit("--worker-count must be >= 1")
    if args.worker_index < 0 or args.worker_index >= args.worker_count:
        raise SystemExit("--worker-index must be in [0, worker-count)")
    if not channels:
        raise SystemExit(f"No valid channels selected from: {channel_keys}")

    if args.reset and CHECKPOINT_DIR.exists():
        import shutil
        shutil.rmtree(CHECKPOINT_DIR)
        print("  체크포인트 초기화 완료.", flush=True)

    await init_db()
    prefixes = _select_prefixes(
        all_prefixes=_generate_prefixes(),
        explicit_prefixes=_parse_prefix_args(args.prefixes),
        max_prefixes=args.max_prefixes or None,
        worker_index=args.worker_index,
        worker_count=args.worker_count,
    )

    print(f"\n{'='*60}", flush=True)
    print(f"  GOOGLE DATED ARCHIVE CRAWL", flush=True)
    print(f"  Months: {months}", flush=True)
    print(f"  Channels: {channels}", flush=True)
    print(f"  Prefixes: {len(prefixes)}/month/channel", flush=True)
    print(f"  Worker shard: {args.worker_index + 1}/{args.worker_count}", flush=True)
    print(f"  Timeout per month: {args.timeout // 3600}h {(args.timeout % 3600) // 60}m", flush=True)
    print(f"{'='*60}\n", flush=True)

    grand_raw = grand_promoted = 0

    for ym in months:
        year, month = int(ym[:4]), int(ym[5:7])
        _set_date_env(year, month)
        last_day = calendar.monthrange(year, month)[1]

        print(f"\n{'─'*50}", flush=True)
        print(f"  월: {year}-{month:02d}-01 ~ {year}-{month:02d}-{last_day}", flush=True)
        print(f"{'─'*50}", flush=True)

        month_deadline = time.time() + args.timeout

        # 채널별 순차 실행 (날짜 env가 모듈 로드 후 동적으로 읽힘)
        for ch in channels:
            print(f"\n  --- {ch} ({ym}) START ---", flush=True)
            t0 = time.time()
            raw, promoted = await run_channel_month(ch, ym, prefixes, month_deadline)
            elapsed = time.time() - t0
            print(
                f"  --- {ch} ({ym}) DONE: {raw} raw / {promoted} promoted ({elapsed:.0f}s) ---",
                flush=True,
            )
            grand_raw += raw
            grand_promoted += promoted

    _clear_date_env()

    print(f"\n{'='*60}", flush=True)
    print(f"  DATED ARCHIVE COMPLETE", flush=True)
    print(f"  Total: {grand_raw} raw / {grand_promoted} promoted", flush=True)
    print(f"{'='*60}\n", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
