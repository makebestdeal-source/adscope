"""AI-based campaign metadata enrichment.

Analyzes ad creatives linked to each campaign and uses DeepSeek (via OpenRouter)
to extract structured campaign metadata: campaign_name, objective, model_info.

Usage:
    python -m processor.campaign_enricher               # enrich pending (up to 100)
    python -m processor.campaign_enricher --limit 50    # limit batch
    python -m processor.campaign_enricher --force        # re-enrich non-manual campaigns

Env:
    OPENROUTER_API_KEY  -- required
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path

import httpx
from sqlalchemy import select

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from database import async_session
from database.models import Campaign, AdDetail, AdSnapshot, Advertiser

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "deepseek/deepseek-chat"


async def _ai_analyze(texts: list[str], advertiser_name: str, channel: str) -> dict:
    """Call DeepSeek to extract campaign metadata from ad texts."""
    if not OPENROUTER_API_KEY:
        return {}

    combined = "\n---\n".join(texts[:20])  # limit to 20 texts
    prompt = f"""Analyze these ad creatives from advertiser "{advertiser_name}" on channel "{channel}".
Extract the following in JSON format:
- campaign_name: A descriptive campaign name in Korean (max 50 chars)
- objective: One of [brand_awareness, traffic, engagement, conversion, retention]
- model_info: Celebrity or influencer name if mentioned, else null

Ad texts:
{combined}

Respond ONLY with valid JSON, no markdown."""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 300,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            # Strip markdown code fences if present
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            return json.loads(content)
    except Exception:
        return {}


async def enrich_campaign_metadata(limit: int = 100, force: bool = False) -> dict[str, int]:
    """Enrich pending campaigns with AI-generated metadata."""
    enriched_count = 0
    skipped = 0

    async with async_session() as session:
        q = select(Campaign).where(Campaign.enrichment_status != "manual_override")
        if not force:
            q = q.where(Campaign.enrichment_status == "pending")
        q = q.limit(limit)

        campaigns = (await session.execute(q)).scalars().all()

        for c in campaigns:
            # Gather ad texts for this campaign
            detail_q = (
                select(AdDetail.ad_text, AdDetail.ad_description, AdDetail.product_name)
                .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
                .where(AdDetail.advertiser_id == c.advertiser_id)
                .where(AdSnapshot.channel == c.channel)
                .where(AdDetail.ad_text.isnot(None))
                .limit(30)
            )
            details = (await session.execute(detail_q)).all()

            if not details:
                skipped += 1
                continue

            # Get advertiser name
            adv = (await session.execute(
                select(Advertiser.name).where(Advertiser.id == c.advertiser_id)
            )).scalar_one_or_none()
            adv_name = adv or "Unknown"

            # Prepare texts
            texts = []
            for ad_text, ad_desc, prod_name in details:
                parts = [ad_text or ""]
                if ad_desc:
                    parts.append(ad_desc)
                if prod_name:
                    parts.append(f"[Product: {prod_name}]")
                texts.append(" | ".join(parts))

            # AI extraction
            ai_result = await _ai_analyze(texts, adv_name, c.channel)

            if ai_result:
                if ai_result.get("campaign_name") and not c.campaign_name:
                    c.campaign_name = ai_result["campaign_name"][:300]
                if ai_result.get("objective") and not c.objective:
                    obj = ai_result["objective"]
                    if obj in ("brand_awareness", "traffic", "engagement", "conversion", "retention"):
                        c.objective = obj
                if ai_result.get("model_info") and not c.model_info:
                    c.model_info = ai_result["model_info"][:200]

            # Fallback: generate campaign_name if AI didn't provide one
            if not c.campaign_name:
                channel_kr = {
                    "naver_search": "naver search",
                    "naver_da": "naver DA",
                    "kakao_da": "kakao DA",
                    "google_gdn": "Google GDN",
                    "facebook": "Facebook",
                    "instagram": "Instagram",
                    "youtube_ads": "YouTube",
                    "tiktok_ads": "TikTok",
                    "naver_shopping": "naver shopping",
                }.get(c.channel, c.channel)
                prod = c.product_service or ""
                c.campaign_name = f"{adv_name} {channel_kr} {prod}".strip()[:300]

            # Fallback objective based on channel
            if not c.objective:
                c.objective = {
                    "naver_search": "traffic",
                    "naver_shopping": "conversion",
                    "facebook": "engagement",
                    "instagram": "engagement",
                    "youtube_ads": "brand_awareness",
                }.get(c.channel, "brand_awareness")

            c.enrichment_status = "enriched"
            c.enriched_at = datetime.now(UTC)
            enriched_count += 1

        await session.commit()

    return {"enriched": enriched_count, "skipped": skipped}


async def main():
    import argparse
    from dotenv import load_dotenv
    load_dotenv(Path(_root) / ".env")

    # Reload env after dotenv
    global OPENROUTER_API_KEY
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    from database import init_db
    await init_db()

    result = await enrich_campaign_metadata(limit=args.limit, force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
