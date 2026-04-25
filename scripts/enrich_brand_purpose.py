"""brand / campaign_purpose AI 일괄 분류 (Anthropic Haiku).

ad_details 중 brand IS NULL 또는 campaign_purpose IS NULL 인 레코드를
광고주명 + 광고문구 + URL + 채널 정보로 Claude Haiku에 분류 요청.

Usage:
    python scripts/enrich_brand_purpose.py              # 전체 실행
    python scripts/enrich_brand_purpose.py --limit 120  # 120건만 테스트
    python scripts/enrich_brand_purpose.py --dry-run    # DB 업데이트 없이 샘플 출력
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import sqlite3
from openai import AsyncOpenAI
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

DB_PATH = ROOT / "adscope.db"
API_KEY = os.getenv("OPENROUTER_API_KEY", "")
BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "deepseek/deepseek-chat"
BATCH_SIZE = 60
CONCURRENCY = 4
SLEEP_BETWEEN = 1.0

PURPOSE_VALUES = [
    "awareness", "branding", "performance", "commerce",
    "launch", "promotion", "retargeting", "event",
]

SYSTEM_PROMPT = """당신은 한국 디지털 광고 전문 분석가입니다.
광고 정보를 보고 두 가지를 추출하세요.

1. **brand** (브랜드/제품명):
   - 광고에서 실제로 홍보하는 브랜드 또는 제품/서비스명
   - 광고주가 대기업 계열사면 구체적 브랜드명 (예: 삼성전자→갤럭시, CJ제일제당→비비고)
   - 광고주 자체가 브랜드면 광고주명 그대로 (예: 쿠팡→쿠팡, 배달의민족→배달의민족)
   - 확실하지 않으면 광고주명을 그대로 사용

2. **campaign_purpose** — 반드시 아래 중 하나:
   - awareness: 브랜드/제품 인지도 제고, 전환 없음
   - branding: 브랜드 이미지/신뢰도 강화
   - performance: 클릭·전환·구매·회원가입·앱설치 유도
   - commerce: 직접 구매/쇼핑/결제 유도 (가격·상품 나열)
   - launch: 신제품/신서비스 출시 알림
   - promotion: 할인·이벤트·쿠폰·경품 강조
   - retargeting: 재방문·장바구니 복귀 유도
   - event: 시즌행사·챌린지·응모·경연

판단 힌트:
- 검색광고(naver_search, google_search_ads): 대부분 performance
- 쇼핑광고(naver_shopping): commerce
- "지금 구매/신청", "무료체험", "앱 다운로드" → performance
- "신제품 출시", "New", "런칭" → launch
- "% 할인", "쿠폰", "이벤트" → promotion
- SNS/동영상에서 가격·클릭 없으면 branding

반드시 JSON 배열로만 응답 (다른 텍스트 금지):
[{"id": 정수, "brand": "브랜드명", "campaign_purpose": "값"}]"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_targets(conn, limit: int | None = None) -> list[dict]:
    sql = """
        SELECT d.id, d.advertiser_name_raw, d.ad_text, d.ad_description,
               d.url, d.display_url, s.channel
        FROM ad_details d
        JOIN ad_snapshots s ON d.snapshot_id = s.id
        WHERE (d.brand IS NULL OR d.campaign_purpose IS NULL)
        ORDER BY d.id
    """
    if limit:
        sql += f" LIMIT {limit}"
    return [dict(r) for r in conn.execute(sql).fetchall()]


def build_batch_prompt(ads: list[dict]) -> str:
    lines = []
    for ad in ads:
        ch = ad.get("channel", "")
        adv = (ad.get("advertiser_name_raw") or "")[:50]
        txt = (ad.get("ad_text") or "")[:150]
        desc = (ad.get("ad_description") or "")[:80]
        url = (ad.get("display_url") or ad.get("url") or "")[:60]
        lines.append(
            f'id={ad["id"]} | 채널={ch} | 광고주={adv} | 텍스트={txt} | 설명={desc} | url={url}'
        )
    return "\n".join(lines)


async def call_api(client: AsyncOpenAI, ads: list[dict]) -> list[dict]:
    user_msg = build_batch_prompt(ads)
    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            max_tokens=3000,
            timeout=60,
        )
        raw = resp.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as e:
        print(f"  [API 오류] {e}", flush=True)
        return []


def apply_results(conn, results: list[dict], dry_run: bool) -> int:
    updated = 0
    for item in results:
        ad_id = item.get("id")
        brand = (item.get("brand") or "").strip() or None
        purpose = (item.get("campaign_purpose") or "").strip().lower()
        if purpose not in PURPOSE_VALUES:
            purpose = None
        if not ad_id:
            continue
        if dry_run:
            print(f"  [DRY] id={ad_id} brand={brand!r} purpose={purpose!r}")
            updated += 1
            continue
        conn.execute(
            """UPDATE ad_details
               SET brand = COALESCE(brand, ?),
                   campaign_purpose = COALESCE(campaign_purpose, ?)
               WHERE id = ?""",
            (brand, purpose, ad_id),
        )
        updated += 1
    if not dry_run:
        conn.commit()
    return updated


async def run(limit: int | None, dry_run: bool):
    client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)

    conn = get_db()
    targets = fetch_targets(conn, limit)
    total = len(targets)
    batches = [targets[i:i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    print(f"처리 대상: {total}건 / 배치: {len(batches)}개 / 모델: {MODEL}", flush=True)

    if not targets:
        print("처리할 대상이 없습니다.")
        conn.close()
        return

    sem = asyncio.Semaphore(CONCURRENCY)
    grand_total = 0
    done_batches = 0
    t0 = time.time()

    async def process_batch(batch: list[dict]):
        nonlocal grand_total, done_batches
        async with sem:
            results = await call_api(client, batch)
            n = apply_results(conn, results, dry_run)
            grand_total += n
            done_batches += 1
            elapsed = time.time() - t0
            speed = done_batches / elapsed * 60
            pct = done_batches / len(batches) * 100
            print(
                f"  [{done_batches}/{len(batches)} {pct:.0f}%] +{n}건 "
                f"(누적 {grand_total}건, {speed:.1f}배치/분)",
                flush=True,
            )
            await asyncio.sleep(SLEEP_BETWEEN)

    await asyncio.gather(*[process_batch(b) for b in batches])

    conn.close()
    elapsed = time.time() - t0
    print(f"\n완료: {grand_total}건 업데이트 / {elapsed:.0f}초 소요", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not API_KEY:
        print("ANTHROPIC_API_KEY 환경변수가 없습니다.")
        sys.exit(1)

    asyncio.run(run(args.limit, args.dry_run))
