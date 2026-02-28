"""Backfill product_category_id for ads using AI batch classification.

Groups ads by advertiser, sends one AI call per advertiser (up to 20 ads each),
mapping to ProductCategory subcategories.

Usage:
    python scripts/backfill_product_category.py           # all
    python scripts/backfill_product_category.py --limit 100  # limit
"""
import asyncio
import io
import json
import os
import sys
from collections import defaultdict
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

from openai import AsyncOpenAI
from sqlalchemy import select, func
from database import async_session, init_db
from database.models import AdDetail, AdSnapshot, Advertiser, ProductCategory


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    await init_db()

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("DEEPSEEK_API_KEY not set")
        return

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=os.getenv("AI_ENRICH_BASE_URL", "https://api.deepseek.com"),
        timeout=60.0,
    )
    model = os.getenv("AI_ENRICH_MODEL", "deepseek-chat")

    # Load category map
    async with async_session() as s:
        cat_rows = (await s.execute(
            select(ProductCategory.id, ProductCategory.name, ProductCategory.parent_id)
        )).all()

    parents = {}
    children = defaultdict(list)
    cat_name_to_id = {}
    for cid, cname, pid in cat_rows:
        cat_name_to_id[cname] = cid
        if pid is None:
            parents[cid] = cname
        else:
            children[pid].append(cname)

    # Build category list for prompt
    cat_lines = []
    for pid, pname in sorted(parents.items()):
        ch = children.get(pid, [])
        cat_lines.append(f"- {pname}: {', '.join(ch)}")
    cat_list = "\n".join(cat_lines)

    # Load ads without product_category_id (prioritize those with advertiser_id)
    async with async_session() as s:
        rows = (await s.execute(
            select(AdDetail.id, AdDetail.advertiser_name_raw, AdDetail.ad_text,
                   AdDetail.ad_description, AdDetail.url, AdDetail.extra_data,
                   AdSnapshot.channel)
            .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
            .where(AdDetail.product_category_id.is_(None))
            .order_by(AdDetail.advertiser_id.is_(None).asc(), AdDetail.advertiser_id)
            .limit(args.limit)
        )).all()

    if not rows:
        print("No ads to backfill")
        return

    print(f"Found {len(rows)} ads without product_category_id")

    # Group by advertiser for batch processing
    groups = defaultdict(list)
    for r in rows:
        key = r.advertiser_name_raw or "unknown"
        groups[key].append(r)

    print(f"Grouped into {len(groups)} advertisers")

    total_updated = 0
    total_errors = 0

    for adv_name, ads in groups.items():
        # Build batch prompt with up to 20 ads
        ad_summaries = []
        for i, ad in enumerate(ads[:20]):
            extra = ad.extra_data or {}
            if isinstance(extra, str):
                try: extra = json.loads(extra)
                except: extra = {}
            ai = extra.get("ai_analysis", {})
            product = ai.get("product", "")
            industry = ai.get("industry", "")

            parts = [f"[{i+1}] id={ad.id}"]
            if adv_name and adv_name != "unknown":
                parts.append(f"adv={adv_name}")
            if product:
                parts.append(f"product={product}")
            if industry:
                parts.append(f"industry={industry}")
            if ad.ad_text:
                parts.append(f"text={ad.ad_text[:100]}")
            elif ad.ad_description:
                parts.append(f"desc={ad.ad_description[:100]}")
            if ad.url:
                parts.append(f"url={ad.url[:80]}")
            ad_summaries.append(" | ".join(parts))

        prompt = f"""아래 광고들의 제품/서비스 소분류 카테고리를 매칭하세요.

카테고리 목록:
{cat_list}

광고 목록:
{chr(10).join(ad_summaries)}

JSON 배열로 응답하세요. 각 항목: {{"id": 광고ID, "category": "소분류명"}}
매칭 불가시 category를 null로 설정.
반드시 위 소분류 이름 중 하나만 사용하세요."""

        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content.strip()
            # Extract JSON
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(l for l in lines if not l.startswith("```")).strip()
            start = text.find("[")
            end = text.rfind("]") + 1
            if start < 0:
                # Try as object with array value
                data = json.loads(text)
                if isinstance(data, dict):
                    # Find the array value
                    for v in data.values():
                        if isinstance(v, list):
                            results = v
                            break
                    else:
                        results = []
                else:
                    results = []
            else:
                results = json.loads(text[start:end])
        except Exception as e:
            print(f"  [!] {adv_name}: AI error - {str(e)[:80]}")
            total_errors += 1
            continue

        # Apply results
        update_count = 0
        async with async_session() as s:
            for item in results:
                ad_id = item.get("id")
                cat_name = item.get("category")
                if not ad_id or not cat_name:
                    continue
                cat_id = cat_name_to_id.get(cat_name)
                if not cat_id:
                    continue
                ad = (await s.execute(
                    select(AdDetail).where(AdDetail.id == ad_id)
                )).scalar_one_or_none()
                if ad and ad.product_category_id is None:
                    ad.product_category_id = cat_id
                    ad.product_category = cat_name
                    update_count += 1
            await s.commit()

        total_updated += update_count
        status = f"{update_count}/{len(ads[:20])}"
        print(f"  {adv_name:30s} | {status} updated")

        # Rate limit (free tier)
        await asyncio.sleep(0.5)

    print(f"\nTotal: {total_updated} ads updated, {total_errors} errors")


if __name__ == "__main__":
    asyncio.run(main())
