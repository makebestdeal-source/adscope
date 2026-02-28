"""Backfill product_category for remaining NULL rows.
Sends advertiser name + any available text to AI.
Includes broader category hints for advertisers the AI may know.
"""
import asyncio
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

from openai import AsyncOpenAI
from sqlalchemy import select
from database import async_session, init_db
from database.models import AdDetail, AdSnapshot, ProductCategory


async def main():
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

    cat_lines = []
    for pid, pname in sorted(parents.items()):
        ch = children.get(pid, [])
        cat_lines.append(f"- {pname}: {', '.join(ch)}")
    cat_list = "\n".join(cat_lines)

    # Load remaining NULL rows
    async with async_session() as s:
        rows = (await s.execute(
            select(AdDetail.id, AdDetail.advertiser_name_raw, AdDetail.ad_text,
                   AdDetail.ad_description, AdDetail.url, AdDetail.extra_data,
                   AdSnapshot.channel)
            .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
            .where(AdDetail.product_category_id.is_(None))
        )).all()

    if not rows:
        print("No ads to backfill")
        return

    print(f"Found {len(rows)} ads without product_category_id")

    # Group by advertiser
    groups = defaultdict(list)
    for r in rows:
        key = r.advertiser_name_raw or "unknown"
        groups[key].append(r)

    print(f"Grouped into {len(groups)} advertisers")

    total_updated = 0
    total_errors = 0
    total_null = 0

    for adv_name, ads in groups.items():
        ad_summaries = []
        for i, ad in enumerate(ads[:20]):
            extra = ad.extra_data or {}
            if isinstance(extra, str):
                try:
                    extra = json.loads(extra)
                except Exception:
                    extra = {}

            parts = [f"[{i+1}] id={ad.id}"]
            if adv_name and adv_name != "unknown":
                parts.append(f"광고주={adv_name}")

            # Add channel context
            if ad.channel:
                parts.append(f"채널={ad.channel}")

            # Add image_url hint from extra_data (FB/IG)
            if extra.get("image_url"):
                parts.append(f"image_url={extra['image_url'][:80]}")

            # Add useful text (skip video timestamps)
            text = ad.ad_text or ""
            desc = ad.ad_description or ""
            if text and not text.startswith("0:") and "youtube_transparency" not in text:
                parts.append(f"텍스트={text[:120]}")
            elif desc and not desc.startswith("0:"):
                parts.append(f"설명={desc[:120]}")

            if ad.url and "adstransparency" not in (ad.url or ""):
                parts.append(f"url={ad.url[:80]}")

            ad_summaries.append(" | ".join(parts))

        prompt = f"""아래 한국 디지털 광고들의 제품/서비스 소분류 카테고리를 매칭하세요.
광고주 이름만 있어도 추론해서 매칭하세요. 예: "세이브더칠드런"은 사회/공익이라 매칭불가, "Sungboon Editor"는 뷰티/화장품.
Facebook/Instagram 인플루언서 광고는 광고주명에서 브랜드를 추론하세요.

카테고리 목록:
{cat_list}

광고 목록:
{chr(10).join(ad_summaries)}

JSON 배열로 응답하세요. 각 항목: {{"id": 광고ID, "category": "소분류명"}}
매칭 불가시(공익단체, 정부기관, 뉴스 등) category를 null로 설정.
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
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(l for l in lines if not l.startswith("```")).strip()
            start = text.find("[")
            end = text.rfind("]") + 1
            if start < 0:
                data = json.loads(text)
                if isinstance(data, dict):
                    results = []
                    for v in data.values():
                        if isinstance(v, list):
                            results = v
                            break
                else:
                    results = []
            else:
                results = json.loads(text[start:end])
        except Exception as e:
            print(f"  [!] {adv_name}: AI error - {str(e)[:80]}")
            total_errors += 1
            continue

        update_count = 0
        null_count = 0
        async with async_session() as s:
            for item in results:
                ad_id = item.get("id")
                cat_name = item.get("category")
                if not ad_id:
                    continue
                if not cat_name:
                    null_count += 1
                    continue
                cat_id = cat_name_to_id.get(cat_name)
                if not cat_id:
                    # Try case-insensitive match
                    for k, v in cat_name_to_id.items():
                        if k.lower() == cat_name.lower():
                            cat_id = v
                            cat_name = k
                            break
                if not cat_id:
                    print(f"    [warn] Unknown cat: {cat_name!r}")
                    null_count += 1
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
        total_null += null_count
        status = f"{update_count}/{len(ads[:20])} updated, {null_count} null"
        print(f"  {adv_name[:40]:40s} | {status}")

        await asyncio.sleep(0.3)

    print(f"\nTotal: {total_updated} updated, {total_null} null/unmatched, {total_errors} errors")

    # Final count
    import sqlite3
    conn = sqlite3.connect(f"{_root}/adscope.db")
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM ad_details").fetchone()[0]
    filled = c.execute("SELECT COUNT(*) FROM ad_details WHERE product_category IS NOT NULL AND product_category != ''").fetchone()[0]
    print(f"\nFinal: product_category {filled}/{total} ({filled*100//total}%)")


if __name__ == "__main__":
    asyncio.run(main())
