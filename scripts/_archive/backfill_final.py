"""Final backfill pass with forced matching hints for hard cases."""
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


# Force mappings for advertisers we know
FORCED_MAPPINGS = {
    # advertiser_name_raw -> (product_category, product_category_id)
    # These will be looked up dynamically
}

# Advertiser name keyword -> category subname hints (for AI prompt)
HINTS = {
    "삼성물산": "유통/쇼핑 또는 부동산 (삼성물산은 건설/유통 대기업)",
    "worldconto": "여행/레저 (여행 예약 사이트)",
    "한국gpt협회": "교육 (AI/IT 교육 관련)",
    "대전경찰청": None,  # 정부기관 - skip
    "긴급소식통": None,  # 뉴스 - skip
    "현대엔지니어링": "부동산 (건설사 아파트 분양)",
    "Hyundai Engineering": "부동산 (건설사 아파트 분양)",
    "세이브더칠드런": None,  # 공익단체 - skip
    "초록우산": None,  # 공익단체 - skip
    "모두드림": "교육",
    "운세위키": "엔터테인먼트",
    "커넥트현대": "자동차",
    "모두드림": "교육",
    "월컨투": "여행/레저",
}


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
        print("No ads to backfill - all done!")
        return

    print(f"Found {len(rows)} ads without product_category_id")

    groups = defaultdict(list)
    for r in rows:
        key = r.advertiser_name_raw or "unknown"
        groups[key].append(r)

    total_updated = 0
    total_skip = 0

    for adv_name, ads in groups.items():
        # Check if this advertiser should be skipped
        skip = False
        hint = ""
        for kw, h in HINTS.items():
            if kw in adv_name:
                if h is None:
                    skip = True
                else:
                    hint = h
                break

        if skip:
            print(f"  SKIP {adv_name[:40]}")
            total_skip += len(ads)
            continue

        ad_summaries = []
        for i, ad in enumerate(ads[:20]):
            extra = ad.extra_data or {}
            if isinstance(extra, str):
                try:
                    extra = json.loads(extra)
                except Exception:
                    extra = {}

            parts = [f"[{i+1}] id={ad.id}"]
            parts.append(f"광고주={adv_name}")
            if ad.channel:
                parts.append(f"채널={ad.channel}")

            text = ad.ad_text or ""
            desc = ad.ad_description or ""
            if text and not text.startswith("0:") and "youtube_transparency" not in text:
                parts.append(f"텍스트={text[:120]}")
            elif desc and not desc.startswith("0:"):
                parts.append(f"설명={desc[:120]}")

            if ad.url and "adstransparency" not in (ad.url or "") and "naver.com" not in (ad.url or ""):
                parts.append(f"url={ad.url[:80]}")

            ad_summaries.append(" | ".join(parts))

        hint_text = f"\n힌트: {adv_name} - {hint}" if hint else ""

        prompt = f"""아래 한국 디지털 광고들의 제품/서비스 소분류 카테고리를 매칭하세요.
광고주 이름을 기반으로 최선의 카테고리를 추론하세요. 너무 엄격하게 생각하지 말고, 가장 가까운 카테고리를 선택하세요.{hint_text}

카테고리 목록:
{cat_list}

광고 목록:
{chr(10).join(ad_summaries)}

JSON 배열로 응답하세요. 각 항목: {{"id": 광고ID, "category": "소분류명"}}
공익단체/정부기관/뉴스 등 절대 매칭 불가시만 null. 나머지는 최선의 카테고리 선택.
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
                results = []
                if isinstance(data, dict):
                    for v in data.values():
                        if isinstance(v, list):
                            results = v
                            break
            else:
                results = json.loads(text[start:end])
        except Exception as e:
            print(f"  [!] {adv_name}: AI error - {str(e)[:80]}")
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
                    for k, v in cat_name_to_id.items():
                        if k.lower() == cat_name.lower():
                            cat_id = v
                            cat_name = k
                            break
                if not cat_id:
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
        status = f"{update_count}/{len(ads[:20])} updated, {null_count} null"
        print(f"  {adv_name[:40]:40s} | {status}")

        await asyncio.sleep(0.3)

    print(f"\nTotal: {total_updated} updated, {total_skip} skipped (non-classifiable)")

    # Final count
    import sqlite3
    conn = sqlite3.connect(f"{_root}/adscope.db")
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM ad_details").fetchone()[0]
    filled = c.execute("SELECT COUNT(*) FROM ad_details WHERE product_category IS NOT NULL AND product_category != ''").fetchone()[0]
    null_left = total - filled
    print(f"\nFinal: product_category {filled}/{total} ({filled*100//total}%) -- {null_left} still NULL")


if __name__ == "__main__":
    asyncio.run(main())
