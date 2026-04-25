"""매체 선택 수집 실행기 (GUI 패널용)

Usage:
    python scripts/run_selected_channels.py --channels naver_search meta --timeout 3600
    python scripts/run_selected_channels.py --channels all --timeout 7200
"""
import argparse
import asyncio
import gc
import importlib.util
import io
import os
import random
import sys
import time
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

# ── 볼륨 설정 (fast_crawl.py와 동일) ──
os.environ["CRAWLER_DWELL_MIN_MS"] = "1500"
os.environ["CRAWLER_DWELL_MAX_MS"] = "2500"
os.environ["CRAWLER_DWELL_SCROLL_COUNT_MIN"] = "2"
os.environ["CRAWLER_DWELL_SCROLL_COUNT_MAX"] = "4"
os.environ["CRAWLER_INTER_PAGE_MIN_MS"] = "800"
os.environ["CRAWLER_INTER_PAGE_MAX_MS"] = "1500"
os.environ["CRAWLER_WARMUP_SITE_COUNT"] = "0"
os.environ["YOUTUBE_AD_WAIT_MS"] = "18000"
os.environ["YOUTUBE_PLAYER_SAMPLES"] = "20"
os.environ["YOUTUBE_SURF_SAMPLES"] = "30"
os.environ["YT_ADS_MAX_ADVERTISERS"] = "200"
os.environ["YT_ADS_MAX_ADS"] = "600"
os.environ["GS_ADS_MAX_ADVERTISERS"] = "100"
os.environ["GS_ADS_MAX_ADS"] = "400"
os.environ["NAVER_SHOP_MAX_ADS"] = "100"
os.environ["GDN_MAX_ADVERTISERS"] = "100"
os.environ["GDN_MAX_ADS"] = "400"
os.environ["META_TRUST_CHECK"] = "false"
os.environ["META_FEED_SCROLL_COUNT"] = "30"
os.environ["META_MAX_PAGES"] = "10"
os.environ["INSTAGRAM_EXPLORE_CLICKS"] = "30"
os.environ["INSTAGRAM_REELS_SWIPES"] = "40"
os.environ["FB_CONTACT_MAX_PAGES"] = "12"
os.environ["FB_CONTACT_SCROLL_ROUNDS"] = "20"
os.environ["KAKAO_MAX_MEDIA"] = "16"
os.environ["MEDIA_COLLECTION_PROFILE"] = "full"
os.environ["KAKAO_LANDING_RESOLVE_LIMIT"] = "0"
os.environ["NAVER_DA_CATEGORY_TABS"] = "6"

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO")

# ── fast_crawl.py를 모듈로 임포트하여 핵심 함수/변수 재사용 ──
_fc_path = str(Path(_root) / "scripts" / "fast_crawl.py")
_fc_spec = importlib.util.spec_from_file_location("fast_crawl", _fc_path)
_fc = importlib.util.module_from_spec(_fc_spec)
_fc_spec.loader.exec_module(_fc)

CHANNEL_TASKS_BASE   = _fc.CHANNEL_TASKS_BASE
CHANNEL_PERSONA_COUNT = _fc.CHANNEL_PERSONA_COUNT
CHANNEL_TIMEOUT       = _fc.CHANNEL_TIMEOUT
DEMO_PERSONAS         = _fc.DEMO_PERSONAS
MAX_BROWSERS          = _fc.MAX_BROWSERS
crawl_channel         = _fc.crawl_channel

# 지원 채널 전체 목록
ALL_CHANNELS = {
    "naver_search", "naver_da", "naver_shopping",
    "kakao_da", "google_gdn", "google_search_ads",
    "youtube_ads", "youtube_surf", "meta", "meta_feed", "tiktok_ads",
}


def build_filtered_tasks(selected: set[str]):
    """선택된 채널만 포함하는 태스크 목록 생성."""
    from processor.channel_utils import CONTACT_CHANNELS
    from crawler.personas.profiles import PERSONAS

    filtered_base = [(ch, kw) for ch, kw in CHANNEL_TASKS_BASE if ch in selected]
    catalog_tasks = [(ch, kw) for ch, kw in filtered_base if ch not in CONTACT_CHANNELS]
    contact_tasks = [(ch, kw) for ch, kw in filtered_base if ch in CONTACT_CHANNELS]

    tasks = []

    # 카탈로그 (headless, 페르소나 무관)
    for channel, keywords in catalog_tasks:
        tasks.append((channel, None, "pc", keywords))

    # 접촉 (headful, 페르소나 배정)
    FORCE_MOBILE = {"naver_da", "kakao_da", "meta_feed"}
    shuffled = list(DEMO_PERSONAS)
    random.shuffle(shuffled)
    idx = 0

    for channel, keywords in contact_tasks:
        n = CHANNEL_PERSONA_COUNT.get(channel, 1)
        for _ in range(n):
            if idx >= len(shuffled):
                idx = 0
                random.shuffle(shuffled)
            code = shuffled[idx]
            persona = PERSONAS[code]
            if channel in FORCE_MOBILE:
                device = "mobile"
            else:
                device = "mobile" if "mobile" in persona.primary_device else "pc"
            tasks.append((channel, code, device, keywords))
            idx += 1

    return tasks, catalog_tasks, contact_tasks


async def main(selected_channels: set[str], total_timeout: int):
    from database import init_db
    from processor.channel_utils import CONTACT_CHANNELS

    await init_db()

    tasks, catalog_tasks, contact_tasks = build_filtered_tasks(selected_channels)

    print("=" * 60, flush=True)
    print(f"  AdScope 선택 채널 수집 -- {len(tasks)} tasks", flush=True)
    print(f"  채널: {', '.join(sorted(selected_channels))}", flush=True)
    print(f"  카탈로그: {len(catalog_tasks)} | 접촉: {len(contact_tasks)}", flush=True)
    print(f"  Max browsers: {MAX_BROWSERS} | Timeout: {total_timeout}s ({total_timeout//60}분)", flush=True)
    print("=" * 60, flush=True)

    deadline = time.time() + total_timeout
    t_start  = time.time()
    results  = []

    _cat_tasks = [(ch, p, d, kw) for ch, p, d, kw in tasks if ch not in CONTACT_CHANNELS]
    _con_tasks = [(ch, p, d, kw) for ch, p, d, kw in tasks if ch in CONTACT_CHANNELS]

    # Wave 1: 카탈로그 (3개씩 배치)
    if _cat_tasks:
        MAX_BATCH = 3
        print(f"\n  == Wave 1: 카탈로그 ({len(_cat_tasks)} tasks) ==", flush=True)
        for i in range(0, len(_cat_tasks), MAX_BATCH):
            if time.time() >= deadline:
                print("  [!] Deadline — Wave 1 중단", flush=True)
                break
            batch = _cat_tasks[i:i + MAX_BATCH]
            coros = []
            for ch, p, d, kw in batch:
                print(f"  Starting {ch} ({len(kw)} kw)...", flush=True)
                coros.append(crawl_channel(ch, p, d, kw, deadline))
            batch_results = await asyncio.gather(*coros, return_exceptions=True)
            results.extend(batch_results)
            if i + MAX_BATCH < len(_cat_tasks):
                gc.collect()
                await asyncio.sleep(2)

    # Wave 2: 접촉 (3개씩 배치)
    if _con_tasks and time.time() < deadline:
        MAX_BATCH = 3
        print(f"\n  == Wave 2: 접촉 ({len(_con_tasks)} tasks) ==", flush=True)
        for i in range(0, len(_con_tasks), MAX_BATCH):
            if time.time() >= deadline:
                print("  [!] Deadline — Wave 2 중단", flush=True)
                break
            batch = _con_tasks[i:i + MAX_BATCH]
            coros = []
            for ch, p, d, kw in batch:
                print(f"  Starting {ch} [{p}/{d}] ({len(kw)} kw)...", flush=True)
                coros.append(crawl_channel(ch, p, d, kw, deadline))
            batch_results = await asyncio.gather(*coros, return_exceptions=True)
            results.extend(batch_results)
            if i + MAX_BATCH < len(_con_tasks):
                gc.collect()
                await asyncio.sleep(5)

    # 결과 요약
    elapsed = time.time() - t_start
    print(f"\n{'=' * 60}", flush=True)
    print(f"  RESULTS (총 {elapsed:.0f}s)", flush=True)
    print(f"{'=' * 60}", flush=True)

    grand_ads = grand_promoted = 0
    for r in results:
        if isinstance(r, Exception):
            print(f"  [X] {r}", flush=True)
            continue
        ch       = r["channel"]
        persona  = r.get("persona", "-")
        ads      = r["total_ads"]
        promoted = r.get("promoted", 0)
        errs     = len(r["errors"])
        grand_ads      += ads
        grand_promoted += promoted
        status = "OK" if promoted > 0 else ("ERR" if errs > 0 else "EMPTY")
        print(
            f"  {ch:20s} | {(persona or '-'):4s} | {ads:4d} ads "
            f"| {promoted:4d} promoted | {status}",
            flush=True,
        )

    print(f"\n  TOTAL: {grand_ads} collected -> {grand_promoted} promoted", flush=True)

    if grand_promoted > 0:
        print("\n  캠페인 & 지출 재계산 중...", flush=True)
        try:
            from processor.campaign_builder import rebuild_campaigns_and_spend
            stats = await rebuild_campaigns_and_spend(active_days=30)
            print(
                f"  Campaigns: {stats['campaigns_total']} | "
                f"Spend: {stats['spend_estimates_total']} | "
                f"New advertisers: {stats['created_advertisers']}",
                flush=True,
            )
        except Exception as e:
            print(f"  [!] 캠페인 재계산 실패: {str(e)[:100]}", flush=True)

    print("=" * 60, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AdScope 선택 채널 수집")
    parser.add_argument(
        "--channels", nargs="+", required=True,
        help="수집할 채널 목록 (all 또는 채널명 나열)",
    )
    parser.add_argument(
        "--timeout", type=int, default=7200,
        help="최대 실행 시간(초), 기본 7200(2시간)",
    )
    args = parser.parse_args()

    if "all" in args.channels:
        selected = ALL_CHANNELS
    else:
        selected = set(args.channels) & ALL_CHANNELS
        invalid = set(args.channels) - ALL_CHANNELS - {"all"}
        if invalid:
            print(f"[!] 알 수 없는 채널 무시: {invalid}", flush=True)

    if not selected:
        print("[!] 유효한 채널이 없습니다.", flush=True)
        sys.exit(1)

    asyncio.run(main(selected, args.timeout))
