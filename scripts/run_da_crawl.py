"""naver_da + kakao_da 전용 8시간 연속 수집 스크립트.

naver_da (surf, M30+F30 동시) 와 kakao_da (all, M30) 를 deadline까지
반복 순회하며 병렬로 수집합니다.
"""
import asyncio
import io
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

# ── 수집 설정 ──
os.environ["CRAWLER_DWELL_MIN_MS"] = "1500"
os.environ["CRAWLER_DWELL_MAX_MS"] = "2500"
os.environ["KAKAO_MAX_MEDIA"] = "40"
os.environ["KAKAO_LANDING_RESOLVE_LIMIT"] = "0"
os.environ["NAVER_DA_CATEGORY_TABS"] = "6"
os.environ["MEDIA_COLLECTION_PROFILE"] = "full"

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO")

from crawler.stealth_patch import enable_stealth
enable_stealth()

from database import init_db
from database.models import AdSnapshot, AdDetail, Keyword, Persona, Advertiser, Industry
from sqlalchemy import select
from processor.advertiser_name_cleaner import clean_name_for_pipeline
from processor.korean_filter import is_korean_ad, clean_advertiser_name
from crawler.personas.profiles import PERSONAS
from crawler.personas.device_config import get_device_for_persona
from processor.creative_hasher import compute_creative_hash, compute_text_hash
from processor.extra_data_normalizer import normalize_extra_data
from scripts.fix_industry_classifications import is_garbage as _is_garbage_advertiser
from processor.landing_cache import get_cached_brand, cache_landing_result
from processor.data_washer import save_to_staging, wash_and_promote
from processor.channel_utils import is_contact as _is_contact

# ── 상수 ──
TOTAL_TIMEOUT = 28800   # 8시간 (초)
MAX_BROWSERS = 3        # 동시 브라우저 최대 수

# DA/피드 채널은 모바일웹 강제
FORCE_MOBILE_CHANNELS = {"naver_da", "kakao_da"}

# 채널별 단일 키워드 타임아웃 (초)
CHANNEL_TIMEOUT = {
    "naver_da": 900,    # 18개 지면 서핑
    "kakao_da": 3000,   # 미디어 순회
}

_browser_sem: asyncio.Semaphore | None = None


def _get_crawler_cls(channel_name: str):
    if channel_name == "naver_da":
        from crawler.naver_da import NaverDACrawler
        return NaverDACrawler
    if channel_name == "kakao_da":
        from crawler.kakao_da import KakaoDACrawler
        return KakaoDACrawler
    raise ValueError(f"Unknown channel: {channel_name}")


async def crawl_channel(channel_name: str, persona_code: str, device_type: str, keywords: list[str], deadline: float) -> dict:
    """단일 채널+페르소나: 키워드 순회하며 deadline까지 최대한 수집. staging 경유.

    브라우저 세마포어로 동시 브라우저 인스턴스 수를 MAX_BROWSERS로 제한.
    DA 채널은 접촉 채널이므로 deadline까지 반복 순회합니다.
    """
    global _browser_sem
    if _browser_sem is None:
        _browser_sem = asyncio.Semaphore(MAX_BROWSERS)

    cls = _get_crawler_cls(channel_name)
    persona = PERSONAS.get(persona_code, PERSONAS["M30"])
    device = get_device_for_persona(persona)
    per_kw_timeout = CHANNEL_TIMEOUT.get(channel_name, 120)

    total_ads = 0
    promoted_count = 0
    errors = []

    shuffled_kw = list(keywords)
    random.shuffle(shuffled_kw)

    round_num = 0
    while True:
        round_num += 1
        if time.time() >= deadline:
            break
        if round_num > 1:
            random.shuffle(shuffled_kw)
            print(f"  [R] {channel_name} round {round_num} ({persona_code})", flush=True)

        for kw in shuffled_kw:
            if time.time() >= deadline:
                break
            remaining = deadline - time.time()
            if remaining < 10:
                break

            t0 = time.time()
            try:
                async with _browser_sem:
                    async with cls() as crawler:
                        result = await asyncio.wait_for(
                            crawler.crawl_keyword(kw, persona, device),
                            timeout=min(remaining, per_kw_timeout),
                        )
                ads = result.get("ads", [])
                total_ads += len(ads)

                if ads:
                    from database import async_session
                    async with async_session() as session:
                        batch_id, staged = await save_to_staging(
                            session, channel_name, result, kw, persona_code, device_type,
                        )
                    async with async_session() as session:
                        wp_result = await wash_and_promote(session, batch_id)
                    w = wp_result["wash"]
                    p = wp_result["promote"]
                    promoted_count += p.get("promoted", 0)
                    dedup_count = p.get("deduped", 0)
                    elapsed = time.time() - t0
                    dedup_str = f"/{dedup_count}dup" if dedup_count else ""
                    print(
                        f"  [+] {channel_name}/{kw} ({persona_code}): "
                        f"{len(ads)} ads -> {w['approved']}ok/{w['rejected']}rej "
                        f"-> {p.get('promoted', 0)} new{dedup_str} ({elapsed:.0f}s)",
                        flush=True,
                    )
                else:
                    elapsed = time.time() - t0
                    print(f"  [+] {channel_name}/{kw} ({persona_code}): 0 ads ({elapsed:.0f}s)", flush=True)

            except asyncio.TimeoutError:
                print(f"  [T] {channel_name}/{kw} ({persona_code}): timeout ({time.time()-t0:.0f}s)", flush=True)
            except Exception as e:
                err_msg = str(e)[:120]
                errors.append(err_msg)
                print(f"  [!] {channel_name}/{kw} ({persona_code}): {err_msg}", flush=True)

    return {
        "channel": channel_name,
        "persona": persona_code,
        "total_ads": total_ads,
        "promoted": promoted_count,
        "errors": errors,
    }


async def main():
    await init_db()

    deadline = time.time() + TOTAL_TIMEOUT
    t_start = time.time()

    # ── 태스크 정의 ──
    # naver_da: keyword="surf", M30 + F30 동시
    # kakao_da: keyword="all", M30
    tasks_cfg = [
        ("naver_da",  "M30", "mobile", ["surf"]),
        ("naver_da",  "F30", "mobile", ["surf"]),
        ("kakao_da",  "M30", "mobile", ["all"]),
    ]

    print("=" * 60, flush=True)
    print(f"  AdScope DA Crawl -- naver_da(x2) + kakao_da(x1)", flush=True)
    print(f"  Max browsers: {MAX_BROWSERS} | Timeout: {TOTAL_TIMEOUT}s (8h)", flush=True)
    print(f"  Tasks:", flush=True)
    for ch, persona, dev, kw in tasks_cfg:
        print(f"    {ch} [{persona}/{dev}] kw={kw}", flush=True)
    print("=" * 60, flush=True)

    coros = [
        crawl_channel(ch, persona, dev, kw, deadline)
        for ch, persona, dev, kw in tasks_cfg
    ]
    results = await asyncio.gather(*coros, return_exceptions=True)

    # ── 결과 요약 ──
    elapsed_total = time.time() - t_start
    print(f"\n{'=' * 60}", flush=True)
    print(f"  RESULTS (total {elapsed_total:.0f}s)", flush=True)
    print(f"{'=' * 60}", flush=True)

    grand_total = 0
    grand_promoted = 0
    channel_summary: dict[str, dict] = {}

    for r in results:
        if isinstance(r, Exception):
            print(f"  [X] Exception: {str(r)[:100]}", flush=True)
            continue
        ch = r["channel"]
        persona = r.get("persona", "?")
        ads = r["total_ads"]
        promoted = r.get("promoted", 0)
        errs = len(r["errors"])
        grand_total += ads
        grand_promoted += promoted

        if ch not in channel_summary:
            channel_summary[ch] = {"ads": 0, "promoted": 0, "personas": [], "errors": 0}
        channel_summary[ch]["ads"] += ads
        channel_summary[ch]["promoted"] += promoted
        channel_summary[ch]["errors"] += errs
        if persona:
            channel_summary[ch]["personas"].append(persona)

        status = "OK" if promoted > 0 else ("ERR" if errs > 0 else "EMPTY")
        print(
            f"  {ch:20s} | {(persona or '-'):4s} | {ads:4d} ads | {promoted:4d} promoted | {errs} errors | {status}",
            flush=True,
        )

    print(f"\n  {'─' * 58}", flush=True)
    print(f"  {'CHANNEL':20s} | {'PERSONAS':12s} | {'ADS':>5s} | {'PROMOTED':>8s}", flush=True)
    print(f"  {'─' * 58}", flush=True)
    for ch, s in sorted(channel_summary.items()):
        p_str = ",".join(s["personas"]) if s["personas"] else "-"
        print(f"  {ch:20s} | {p_str:12s} | {s['ads']:5d} | {s['promoted']:8d}", flush=True)
    print(f"  {'─' * 58}", flush=True)

    print(f"\n  TOTAL: {grand_total} collected -> {grand_promoted} promoted to live DB", flush=True)

    if grand_promoted > 0:
        print("\n  Rebuilding campaigns & spend estimates...", flush=True)
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
            print(f"  [!] Campaign rebuild failed: {str(e)[:100]}", flush=True)

    print(f"  Refresh http://localhost:3001 to see results", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
