"""구글/메타 전수 아카이브 수집 -- 전체 광고주 × 전체 기간 크리에이티브.

Google Ads Transparency Center + Meta Ad Library에서
ㄱ~ㅎ, a~z, 0~9 프리픽스 검색으로 전수 광고주를 발견하고,
각 광고주의 전체 기간 크리에이티브를 수집한다.

사용법:
    python scripts/archive_crawl.py                              # 전체 (날짜 필터 없음)
    python scripts/archive_crawl.py --channels meta              # 메타만
    python scripts/archive_crawl.py --channels google            # 구글만
    python scripts/archive_crawl.py --channels google,meta       # 전체 (기본값)
    python scripts/archive_crawl.py --months 2025-01,2025-02,2025-03  # 날짜 범위 지정
    python scripts/archive_crawl.py --months 2025-01 --channels gdn   # GDN 1월만
    python scripts/archive_crawl.py --timeout 14400              # 4시간 (기본 12시간)
    python scripts/archive_crawl.py --reset                      # 체크포인트 초기화
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
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

# ── 아카이브 모드 환경변수 (볼륨 최대화) ──

# 구글: 광고주당 스크롤 무제한, 크리에이티브 상한 대폭 확대
os.environ["YT_ADS_MAX_ADVERTISERS"] = "500"
os.environ["YT_ADS_MAX_ADS"] = "9999"
os.environ["YT_ADS_WAIT_MS"] = "12000"
os.environ["YT_ADS_MAX_SCROLLS"] = "30"       # 광고주 페이지에서 최대 30번 스크롤
os.environ["GS_ADS_MAX_ADVERTISERS"] = "500"
os.environ["GS_ADS_MAX_ADS"] = "9999"
os.environ["GDN_MAX_ADVERTISERS"] = "500"
os.environ["GDN_MAX_ADS"] = "9999"
os.environ["GDN_MAX_SCROLLS"] = "30"

# 메타: 전체 기간, 스크롤 무제한
os.environ["META_ACTIVE_STATUS"] = "all"        # 비활성/종료 광고 포함
os.environ["META_FEED_SCROLL_COUNT"] = "100"    # 최대 100회 스크롤 (스마트 중단)
os.environ["META_TRUST_CHECK"] = "false"        # 검증 스킵 (속도)
os.environ["META_MAX_PAGES"] = "20"

# 공통
os.environ["CRAWLER_DWELL_MIN_MS"] = "1500"
os.environ["CRAWLER_DWELL_MAX_MS"] = "2500"
os.environ["CRAWLER_WARMUP_SITE_COUNT"] = "0"

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO")

from crawler.stealth_patch import enable_stealth
enable_stealth()

from database import init_db
from database.models import AdDetail, Campaign, SpendEstimate
from sqlalchemy import select
from datetime import timedelta
from crawler.personas.profiles import PERSONAS
from crawler.personas.device_config import get_device_for_persona
from processor.data_washer import save_to_staging, wash_and_promote
from database import async_session
from sqlalchemy import text as sa_text


def _generate_prefixes() -> list[str]:
    """ㄱ~ㅎ(399) + a~z(26) + 0~9(10) = 435 프리픽스."""
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


def _get_crawler_cls(channel_name):
    from crawler.youtube_ads import YouTubeAdsCrawler
    from crawler.google_gdn import GoogleGDNCrawler
    from crawler.google_search_ads import GoogleSearchAdsCrawler
    from crawler.meta_library import MetaLibraryCrawler
    from crawler.tiktok_ads import TikTokAdsCrawler
    return {
        "youtube_ads": YouTubeAdsCrawler,
        "google_gdn": GoogleGDNCrawler,
        "google_search_ads": GoogleSearchAdsCrawler,
        "meta": MetaLibraryCrawler,
        "tiktok_ads": TikTokAdsCrawler,
    }[channel_name]


# 채널별 타임아웃 (프리픽스 하나당)
CHANNEL_TIMEOUT = {
    "youtube_ads": 900,        # 광고주당 스크롤 많으므로 15분
    "google_gdn": 900,
    "google_search_ads": 600,
    "meta": 900,
    "tiktok_ads": 300,
}


_ARCHIVE_SOURCE_MAP = {
    "meta": "meta_library",
    "youtube_ads": "google_transparency",
    "google_gdn": "google_transparency",
    "google_search_ads": "google_transparency",
    "tiktok_ads": "tiktok_creative",
}


async def _mark_retroactive(session, channel_name: str):
    """방금 저장된 ad_details 레코드에 is_retroactive, archive_source, 배송일 세팅."""
    archive_source = _ARCHIVE_SOURCE_MAP.get(channel_name, channel_name)
    # captured_at 기준 최근 3분 이내 + 해당 channel + 아직 미태깅 레코드
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


async def crawl_prefix(channel_name, keyword, persona, device, persona_code, timeout):
    """프리픽스 하나 수집 → staging → wash → promote → retroactive 태깅."""
    cls = _get_crawler_cls(channel_name)
    t0 = time.time()
    try:
        async with cls() as crawler:
            result = await asyncio.wait_for(
                crawler.crawl_keyword(keyword, persona, device),
                timeout=timeout,
            )
        ads = result.get("ads", [])
        if not ads:
            return 0, 0, True

        async with async_session() as session:
            batch_id, staged = await save_to_staging(
                session, channel_name, result, keyword, persona_code, device.device_type,
            )
        async with async_session() as session:
            wp_result = await wash_and_promote(session, batch_id)

        # 소급 아카이브 플래그 세팅
        async with async_session() as session:
            await _mark_retroactive(session, channel_name)

        promoted = wp_result["promote"].get("promoted", 0)
        deduped = wp_result["promote"].get("deduped", 0)
        elapsed = time.time() - t0
        print(
            f"  [+] {channel_name}/{keyword} -> "
            f"{len(ads)} raw / {promoted} saved / {deduped} dup "
            f"({elapsed:.1f}s)",
            flush=True,
        )
        return len(ads), promoted, True

    except asyncio.TimeoutError:
        elapsed = time.time() - t0
        print(f"  [T] {channel_name}/{keyword} timeout ({elapsed:.0f}s)", flush=True)
        return 0, 0, False
    except Exception as e:
        elapsed = time.time() - t0
        err_msg = str(e)[:80]
        print(f"  [E] {channel_name}/{keyword} error: {err_msg} ({elapsed:.0f}s)", flush=True)
        return 0, 0, False


CHECKPOINT_DIR = Path(_root) / ".archive_checkpoints"
CHECKPOINT_DATED_DIR = Path(_root) / ".archive_checkpoints_dated"


def _cp_key(channel: str, ym: str | None) -> tuple[Path, str]:
    """체크포인트 파일 경로와 키 반환."""
    if ym:
        CHECKPOINT_DATED_DIR.mkdir(exist_ok=True)
        fname = f"{channel}_{ym.replace('-', '_')}.done"
        return CHECKPOINT_DATED_DIR / fname, fname
    else:
        CHECKPOINT_DIR.mkdir(exist_ok=True)
        fname = f"{channel}.done"
        return CHECKPOINT_DIR / fname, fname


def _load_done_prefixes(channel_name: str, ym: str | None = None) -> set[str]:
    fp, _ = _cp_key(channel_name, ym)
    if fp.exists():
        return set(fp.read_text(encoding="utf-8").strip().split("\n"))
    return set()


def _save_done_prefix(channel_name: str, prefix: str, ym: str | None = None):
    fp, _ = _cp_key(channel_name, ym)
    with open(fp, "a", encoding="utf-8") as f:
        f.write(prefix + "\n")


def _set_date_env(year: int, month: int):
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


async def run_channel(channel_name, prefixes, deadline, ym: str | None = None):
    """단일 채널 전체 프리픽스 순회 (체크포인트 지원)."""
    persona = PERSONAS["M30"]
    device = get_device_for_persona(persona)
    per_prefix_timeout = CHANNEL_TIMEOUT.get(channel_name, 300)

    done = _load_done_prefixes(channel_name, ym)
    remaining_prefixes = [p for p in prefixes if p not in done]
    label = f"{channel_name}/{ym}" if ym else channel_name
    if done:
        print(f"  [{label}] resume: {len(done)} done, {len(remaining_prefixes)} remaining", flush=True)

    total_raw = 0
    total_promoted = 0

    random.shuffle(remaining_prefixes)

    for i, prefix in enumerate(remaining_prefixes):
        if time.time() >= deadline:
            print(f"  [{label}] deadline reached at prefix {i}/{len(remaining_prefixes)}", flush=True)
            break
        remaining = deadline - time.time()
        if remaining < 30:
            break

        raw, promoted, completed = await crawl_prefix(
            channel_name, prefix, persona, device, "M30",
            timeout=min(remaining, per_prefix_timeout),
        )
        total_raw += raw
        total_promoted += promoted
        if completed:
            _save_done_prefix(channel_name, prefix, ym)

    return total_raw, total_promoted



# Minimum daily spend estimate per channel (library_derived - conservative lower bound)
_CHANNEL_MIN_DAILY_SPEND = {
    "meta": 30000,
    "youtube_ads": 50000,
    "google_gdn": 20000,
    "google_search_ads": 15000,
    "tiktok_ads": 20000,
    "naver_search": 10000,
    "naver_da": 15000,
    "kakao_da": 15000,
    "naver_shopping": 5000,
}


async def generate_library_spend_estimates(
    session, ad_detail_id, advertiser_id, channel, delivery_start, delivery_end
):
    """Generate spend_estimates from archive ad delivery period.

    data_source='library_derived', confidence=0.4, confidence_tier='low'
    est_daily_spend is a conservative minimum based on channel benchmark.
    """
    if not delivery_start or not advertiser_id:
        return 0

    end_dt = delivery_end or delivery_start
    max_days = 180
    delta = (end_dt - delivery_start).days + 1
    if delta > max_days:
        delta = max_days
        end_dt = delivery_start + timedelta(days=max_days - 1)
    if delta <= 0:
        return 0

    result = await session.execute(
        select(Campaign).where(Campaign.advertiser_id == advertiser_id).limit(1)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        return 0

    est_daily = float(_CHANNEL_MIN_DAILY_SPEND.get(channel, 10000))
    inserted = 0
    current = delivery_start
    while current <= end_dt:
        record = SpendEstimate(
            campaign_id=campaign.id,
            date=current,
            channel=channel,
            est_daily_spend=est_daily,
            confidence=0.4,
            calculation_method="library_derived_min",
            factors={"ad_detail_id": ad_detail_id, "source": "meta_library"},
            data_source="library_derived",
            confidence_tier="low",
        )
        session.add(record)
        inserted += 1
        current = current + timedelta(days=1)

    return inserted



CHANNEL_ALIAS = {
    "gdn":    "google_gdn",
    "yt":     "youtube_ads",
    "search": "google_search_ads",
    "meta":   "meta",
    "tiktok": "tiktok_ads",
    "tt":     "tiktok_ads",
}


async def main():
    parser = argparse.ArgumentParser(description="Google/Meta archive crawl")
    parser.add_argument("--channels", default="google,meta",
                        help="채널: google,meta,tiktok,gdn,yt,search (콤마구분, 기본: google,meta)")
    parser.add_argument("--months", default="",
                        help="날짜 범위 (YYYY-MM 콤마구분, 예: 2025-01,2025-02,2025-03). 미지정 시 날짜 필터 없음")
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

    requested = {c.strip().lower() for c in args.channels.split(",")}
    months = [m.strip() for m in args.months.split(",") if m.strip()]

    if args.reset:
        import shutil
        if CHECKPOINT_DIR.exists():
            shutil.rmtree(CHECKPOINT_DIR)
        if CHECKPOINT_DATED_DIR.exists():
            shutil.rmtree(CHECKPOINT_DATED_DIR)
        print("  체크포인트 초기화 완료.", flush=True)

    await init_db()

    # 채널 목록 구성
    all_prefixes = _generate_prefixes()
    explicit_prefixes = _parse_prefix_args(args.prefixes)
    if args.worker_count < 1:
        raise SystemExit("--worker-count must be >= 1")
    if args.worker_index < 0 or args.worker_index >= args.worker_count:
        raise SystemExit("--worker-index must be in [0, worker-count)")
    prefixes = _select_prefixes(
        all_prefixes=all_prefixes,
        explicit_prefixes=explicit_prefixes,
        max_prefixes=args.max_prefixes or None,
        worker_index=args.worker_index,
        worker_count=args.worker_count,
    )

    selected_channels: list[str] = []
    if "google" in requested:
        selected_channels.extend(["youtube_ads", "google_gdn", "google_search_ads"])
    for raw in requested:
        if raw in CHANNEL_ALIAS:
            selected_channels.append(CHANNEL_ALIAS[raw])
        elif raw in {"youtube_ads", "google_gdn", "google_search_ads", "meta", "tiktok_ads"}:
            selected_channels.append(raw)
    selected_channels = list(dict.fromkeys(selected_channels))
    if not selected_channels:
        raise SystemExit(f"No valid channels selected from: {sorted(requested)}")

    print(f"\n{'='*60}", flush=True)
    print(f"  ARCHIVE CRAWL", flush=True)
    print(f"  Channels: {selected_channels}", flush=True)
    print(f"  Months: {months if months else '전체 (날짜 필터 없음)'}", flush=True)
    print(f"  Prefixes: {len(prefixes)}/channel", flush=True)
    print(f"  Worker shard: {args.worker_index + 1}/{args.worker_count}", flush=True)
    print(f"  Timeout: {args.timeout // 3600}h {(args.timeout % 3600) // 60}m", flush=True)
    print(f"{'='*60}\n", flush=True)

    grand_raw = grand_promoted = 0

    if months:
        # ── 날짜 범위 지정 모드: 월별 × 채널 순차 ──
        for ym in months:
            year, month = int(ym[:4]), int(ym[5:7])
            _set_date_env(year, month)
            last_day = calendar.monthrange(year, month)[1]

            print(f"\n{'─'*50}", flush=True)
            print(f"  월: {year}-{month:02d}-01 ~ {year}-{month:02d}-{last_day}", flush=True)
            print(f"{'─'*50}", flush=True)

            deadline = time.time() + args.timeout

            for ch in selected_channels:
                print(f"\n  --- {ch} ({ym}) START ---", flush=True)
                t0 = time.time()
                raw, promoted = await run_channel(ch, prefixes, deadline, ym=ym)
                elapsed = time.time() - t0
                print(f"  --- {ch} ({ym}) DONE: {raw} raw / {promoted} promoted ({elapsed:.0f}s) ---", flush=True)
                grand_raw += raw
                grand_promoted += promoted

        _clear_date_env()

    else:
        # ── 날짜 필터 없는 모드: 채널 병렬 ──
        deadline = time.time() + args.timeout
        channel_tasks = []
        for ch in selected_channels:
            keywords = [""] * 10 + prefixes if ch == "meta" else prefixes
            channel_tasks.append((ch, keywords))

        async def _run_one(channel, keywords):
            print(f"\n--- {channel} ({len(keywords)} keywords) START ---", flush=True)
            t0 = time.time()
            raw, promoted = await run_channel(channel, keywords, deadline)
            elapsed = time.time() - t0
            print(f"\n--- {channel} DONE: {raw} raw / {promoted} promoted ({elapsed:.0f}s) ---", flush=True)
            return raw, promoted

        results = await asyncio.gather(
            *[_run_one(ch, kw) for ch, kw in channel_tasks],
            return_exceptions=True,
        )
        for i, res in enumerate(results):
            ch_name = channel_tasks[i][0]
            if isinstance(res, Exception):
                print(f"  [!] {ch_name} failed: {res}", flush=True)
            else:
                grand_raw += res[0]
                grand_promoted += res[1]

    print(f"\n{'='*60}", flush=True)
    print(f"  ARCHIVE COMPLETE", flush=True)
    print(f"  Total: {grand_raw} raw / {grand_promoted} promoted", flush=True)
    print(f"{'='*60}\n", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
