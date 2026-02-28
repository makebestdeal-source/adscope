"""Backfill persona_id for ad_details using demographic distribution.

40~60 personas have 0 ads because stealth_persona_surf requires headful Chrome.
This script assigns persona_id to NULL rows based on product_category/industry
demographic targeting weights.

Logic:
1. Query ad_details WHERE persona_id IS NULL
2. For each ad, determine product_category (text or FK) and advertiser industry
3. Map category/industry to demographic weight profile
4. Probabilistically assign persona_id based on weights

Persona ID mapping:
  1=M30, 2=M10, 3=F10, 4=M20, 5=F20,
  6=F30, 7=M40, 8=F40, 9=M50, 10=F50, 11=M60, 12=F60

Usage:
    python scripts/backfill_persona_distribution.py
    python scripts/backfill_persona_distribution.py --dry-run
    python scripts/backfill_persona_distribution.py --batch-size 200
"""
import asyncio
import io
import random
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from sqlalchemy import select, func, update
from database import async_session, init_db
from database.models import AdDetail, AdSnapshot, Advertiser, Industry, ProductCategory

# ──────────────────────────────────────────────
# Persona ID -> code mapping
# ──────────────────────────────────────────────
PERSONA_MAP = {
    1: "M30", 2: "M10", 3: "F10", 4: "M20", 5: "F20",
    6: "F30", 7: "M40", 8: "F40", 9: "M50", 10: "F50",
    11: "M60", 12: "F60",
}

# Reverse: code -> id
CODE_TO_ID = {v: k for k, v in PERSONA_MAP.items()}

BATCH_SIZE = 500

# ──────────────────────────────────────────────
# Demographic weight profiles
# Keys = persona_id (1~12), values = relative weight
# Higher weight = more likely to be assigned
# ──────────────────────────────────────────────

# Default: even distribution across all ages
_UNIFORM = {pid: 1.0 for pid in range(1, 13)}

# Category keyword -> weight profile mapping
# Weights are relative (will be normalized to probabilities)
CATEGORY_PROFILES: dict[str, dict[int, float]] = {
    # ── Beauty / Cosmetics ──
    "beauty": {
        1: 0.5, 2: 0.3, 3: 1.5, 4: 0.8, 5: 2.5,   # F20 highest
        6: 2.0, 7: 0.3, 8: 1.5, 9: 0.2, 10: 0.8, 11: 0.1, 12: 0.3,
    },
    "cosmetics": {
        1: 0.5, 2: 0.3, 3: 1.5, 4: 0.8, 5: 2.5,
        6: 2.0, 7: 0.3, 8: 1.5, 9: 0.2, 10: 0.8, 11: 0.1, 12: 0.3,
    },
    "skincare": {
        1: 0.4, 2: 0.2, 3: 1.0, 4: 0.6, 5: 2.0,
        6: 2.0, 7: 0.3, 8: 1.8, 9: 0.2, 10: 1.2, 11: 0.1, 12: 0.5,
    },
    "makeup": {
        1: 0.2, 2: 0.1, 3: 1.8, 4: 0.3, 5: 3.0,
        6: 2.5, 7: 0.1, 8: 1.0, 9: 0.1, 10: 0.5, 11: 0.0, 12: 0.2,
    },

    # ── Fashion / Apparel ──
    "fashion": {
        1: 1.0, 2: 1.0, 3: 1.5, 4: 1.5, 5: 2.0,
        6: 1.8, 7: 0.8, 8: 1.2, 9: 0.5, 10: 0.8, 11: 0.3, 12: 0.5,
    },
    "apparel": {
        1: 1.0, 2: 1.0, 3: 1.5, 4: 1.5, 5: 2.0,
        6: 1.8, 7: 0.8, 8: 1.2, 9: 0.5, 10: 0.8, 11: 0.3, 12: 0.5,
    },
    "luxury": {
        1: 1.5, 2: 0.3, 3: 0.5, 4: 1.0, 5: 1.5,
        6: 2.0, 7: 1.5, 8: 2.0, 9: 1.0, 10: 1.5, 11: 0.5, 12: 0.8,
    },

    # ── Automotive ──
    "automotive": {
        1: 2.5, 2: 0.3, 3: 0.2, 4: 1.5, 5: 0.3,
        6: 0.5, 7: 2.5, 8: 0.5, 9: 2.0, 10: 0.3, 11: 1.5, 12: 0.2,
    },
    "car": {
        1: 2.5, 2: 0.3, 3: 0.2, 4: 1.5, 5: 0.3,
        6: 0.5, 7: 2.5, 8: 0.5, 9: 2.0, 10: 0.3, 11: 1.5, 12: 0.2,
    },

    # ── Finance / Insurance ──
    "finance": {
        1: 2.0, 2: 0.3, 3: 0.3, 4: 1.5, 5: 0.8,
        6: 1.0, 7: 2.0, 8: 1.0, 9: 2.0, 10: 1.0, 11: 1.5, 12: 0.8,
    },
    "insurance": {
        1: 1.5, 2: 0.2, 3: 0.2, 4: 1.0, 5: 0.5,
        6: 1.0, 7: 2.0, 8: 1.5, 9: 2.5, 10: 1.5, 11: 2.0, 12: 1.0,
    },
    "banking": {
        1: 2.0, 2: 0.5, 3: 0.3, 4: 1.5, 5: 0.8,
        6: 1.0, 7: 2.0, 8: 1.0, 9: 1.8, 10: 0.8, 11: 1.2, 12: 0.5,
    },
    "investment": {
        1: 2.0, 2: 0.2, 3: 0.2, 4: 1.5, 5: 0.5,
        6: 0.8, 7: 2.5, 8: 0.8, 9: 2.5, 10: 0.8, 11: 1.5, 12: 0.5,
    },

    # ── Health / Medical / Pharma ──
    "health": {
        1: 1.0, 2: 0.3, 3: 0.3, 4: 0.8, 5: 0.8,
        6: 1.0, 7: 1.5, 8: 1.5, 9: 2.5, 10: 2.5, 11: 2.0, 12: 2.0,
    },
    "medical": {
        1: 1.0, 2: 0.2, 3: 0.2, 4: 0.5, 5: 0.5,
        6: 0.8, 7: 1.5, 8: 1.5, 9: 2.5, 10: 2.5, 11: 2.0, 12: 2.0,
    },
    "pharma": {
        1: 0.8, 2: 0.2, 3: 0.2, 4: 0.5, 5: 0.5,
        6: 0.8, 7: 1.5, 8: 1.5, 9: 2.5, 10: 2.5, 11: 2.0, 12: 2.0,
    },
    "supplement": {
        1: 1.0, 2: 0.3, 3: 0.5, 4: 0.8, 5: 1.0,
        6: 1.2, 7: 1.5, 8: 2.0, 9: 2.0, 10: 2.5, 11: 1.5, 12: 2.0,
    },
    "hospital": {
        1: 0.8, 2: 0.2, 3: 0.2, 4: 0.5, 5: 0.5,
        6: 0.8, 7: 1.5, 8: 1.5, 9: 2.5, 10: 2.5, 11: 2.0, 12: 2.0,
    },

    # ── Food / Beverage ──
    "food": {
        1: 1.0, 2: 0.8, 3: 1.0, 4: 1.0, 5: 1.5,
        6: 1.8, 7: 1.0, 8: 1.8, 9: 0.8, 10: 1.5, 11: 0.5, 12: 1.0,
    },
    "beverage": {
        1: 1.2, 2: 1.5, 3: 1.2, 4: 1.5, 5: 1.5,
        6: 1.0, 7: 0.8, 8: 0.8, 9: 0.5, 10: 0.5, 11: 0.3, 12: 0.3,
    },
    "restaurant": {
        1: 1.2, 2: 1.0, 3: 1.0, 4: 1.5, 5: 1.5,
        6: 1.5, 7: 1.0, 8: 1.0, 9: 0.8, 10: 0.8, 11: 0.5, 12: 0.5,
    },
    "delivery": {
        1: 1.5, 2: 1.5, 3: 1.2, 4: 2.0, 5: 1.5,
        6: 1.2, 7: 0.8, 8: 0.8, 9: 0.3, 10: 0.3, 11: 0.2, 12: 0.2,
    },

    # ── Tech / Electronics / IT ──
    "tech": {
        1: 2.0, 2: 1.5, 3: 0.8, 4: 2.0, 5: 0.8,
        6: 0.8, 7: 1.5, 8: 0.5, 9: 1.0, 10: 0.3, 11: 0.5, 12: 0.2,
    },
    "electronics": {
        1: 2.0, 2: 1.5, 3: 0.8, 4: 2.0, 5: 0.8,
        6: 0.8, 7: 1.5, 8: 0.5, 9: 1.0, 10: 0.3, 11: 0.5, 12: 0.2,
    },
    "smartphone": {
        1: 1.5, 2: 2.0, 3: 1.5, 4: 2.0, 5: 1.5,
        6: 1.0, 7: 1.0, 8: 0.8, 9: 0.5, 10: 0.5, 11: 0.3, 12: 0.3,
    },
    "gaming": {
        1: 1.5, 2: 3.0, 3: 1.0, 4: 2.5, 5: 0.8,
        6: 0.5, 7: 0.8, 8: 0.3, 9: 0.3, 10: 0.1, 11: 0.1, 12: 0.1,
    },
    "software": {
        1: 2.0, 2: 1.0, 3: 0.5, 4: 2.0, 5: 0.8,
        6: 0.8, 7: 1.8, 8: 0.5, 9: 1.0, 10: 0.3, 11: 0.5, 12: 0.2,
    },
    "app": {
        1: 1.5, 2: 2.0, 3: 1.5, 4: 2.0, 5: 1.5,
        6: 1.0, 7: 0.8, 8: 0.5, 9: 0.3, 10: 0.3, 11: 0.1, 12: 0.1,
    },

    # ── Education ──
    "education": {
        1: 1.5, 2: 1.0, 3: 1.0, 4: 1.5, 5: 1.0,
        6: 1.8, 7: 1.5, 8: 2.0, 9: 0.8, 10: 1.0, 11: 0.3, 12: 0.5,
    },
    "academy": {
        1: 0.5, 2: 2.5, 3: 2.0, 4: 2.0, 5: 1.5,
        6: 0.5, 7: 0.3, 8: 0.5, 9: 0.2, 10: 0.3, 11: 0.1, 12: 0.1,
    },
    "university": {
        1: 0.3, 2: 2.5, 3: 2.5, 4: 1.5, 5: 1.5,
        6: 0.3, 7: 0.3, 8: 0.3, 9: 0.2, 10: 0.2, 11: 0.1, 12: 0.1,
    },

    # ── Real Estate / Home ──
    "real_estate": {
        1: 2.0, 2: 0.2, 3: 0.2, 4: 1.0, 5: 0.5,
        6: 1.5, 7: 2.5, 8: 1.5, 9: 2.0, 10: 1.0, 11: 1.0, 12: 0.5,
    },
    "interior": {
        1: 1.5, 2: 0.3, 3: 0.5, 4: 1.0, 5: 1.5,
        6: 2.0, 7: 1.5, 8: 2.5, 9: 1.0, 10: 1.5, 11: 0.5, 12: 0.8,
    },
    "furniture": {
        1: 1.5, 2: 0.3, 3: 0.5, 4: 1.0, 5: 1.5,
        6: 2.0, 7: 1.5, 8: 2.5, 9: 1.0, 10: 1.5, 11: 0.5, 12: 0.8,
    },

    # ── Travel / Leisure ──
    "travel": {
        1: 1.5, 2: 0.8, 3: 0.8, 4: 1.5, 5: 1.5,
        6: 1.5, 7: 1.5, 8: 1.5, 9: 1.5, 10: 1.5, 11: 1.0, 12: 1.0,
    },
    "hotel": {
        1: 1.5, 2: 0.5, 3: 0.5, 4: 1.2, 5: 1.5,
        6: 1.5, 7: 1.5, 8: 1.8, 9: 1.5, 10: 1.5, 11: 1.0, 12: 1.0,
    },
    "airline": {
        1: 1.5, 2: 0.5, 3: 0.5, 4: 1.5, 5: 1.2,
        6: 1.2, 7: 2.0, 8: 1.2, 9: 1.8, 10: 1.0, 11: 1.0, 12: 0.5,
    },

    # ── Entertainment / Media ──
    "entertainment": {
        1: 1.2, 2: 2.0, 3: 2.0, 4: 2.0, 5: 2.0,
        6: 1.2, 7: 0.8, 8: 0.8, 9: 0.5, 10: 0.5, 11: 0.3, 12: 0.3,
    },
    "movie": {
        1: 1.2, 2: 1.5, 3: 1.5, 4: 1.8, 5: 1.8,
        6: 1.2, 7: 1.0, 8: 1.0, 9: 0.8, 10: 0.8, 11: 0.5, 12: 0.5,
    },
    "music": {
        1: 1.0, 2: 2.5, 3: 2.5, 4: 2.0, 5: 2.0,
        6: 0.8, 7: 0.5, 8: 0.5, 9: 0.3, 10: 0.3, 11: 0.2, 12: 0.2,
    },
    "webtoon": {
        1: 1.0, 2: 2.5, 3: 2.0, 4: 2.5, 5: 2.0,
        6: 0.8, 7: 0.5, 8: 0.3, 9: 0.2, 10: 0.1, 11: 0.1, 12: 0.1,
    },

    # ── Baby / Kids / Parenting ──
    "baby": {
        1: 1.5, 2: 0.1, 3: 0.1, 4: 0.5, 5: 1.0,
        6: 3.0, 7: 0.5, 8: 2.5, 9: 0.2, 10: 0.3, 11: 0.1, 12: 0.2,
    },
    "kids": {
        1: 1.5, 2: 0.2, 3: 0.2, 4: 0.5, 5: 0.8,
        6: 2.5, 7: 1.0, 8: 2.5, 9: 0.3, 10: 0.5, 11: 0.2, 12: 0.3,
    },
    "parenting": {
        1: 1.5, 2: 0.1, 3: 0.1, 4: 0.3, 5: 0.8,
        6: 3.0, 7: 0.8, 8: 2.5, 9: 0.2, 10: 0.3, 11: 0.1, 12: 0.2,
    },

    # ── Pet ──
    "pet": {
        1: 1.0, 2: 0.8, 3: 1.2, 4: 1.2, 5: 2.0,
        6: 2.0, 7: 0.8, 8: 1.5, 9: 0.5, 10: 1.0, 11: 0.3, 12: 0.5,
    },

    # ── Sports / Fitness ──
    "sports": {
        1: 2.0, 2: 1.5, 3: 0.8, 4: 2.0, 5: 1.0,
        6: 0.8, 7: 1.5, 8: 0.8, 9: 1.5, 10: 0.5, 11: 1.0, 12: 0.3,
    },
    "fitness": {
        1: 2.0, 2: 1.0, 3: 1.0, 4: 2.0, 5: 2.0,
        6: 1.5, 7: 1.2, 8: 1.2, 9: 0.5, 10: 0.5, 11: 0.3, 12: 0.3,
    },
    "golf": {
        1: 1.5, 2: 0.1, 3: 0.1, 4: 0.8, 5: 0.3,
        6: 0.5, 7: 2.5, 8: 1.0, 9: 2.5, 10: 1.0, 11: 2.0, 12: 0.8,
    },

    # ── Shopping / E-commerce ──
    "shopping": {
        1: 1.0, 2: 1.0, 3: 1.5, 4: 1.2, 5: 2.0,
        6: 2.0, 7: 0.8, 8: 1.5, 9: 0.5, 10: 1.0, 11: 0.3, 12: 0.5,
    },
    "ecommerce": {
        1: 1.2, 2: 1.0, 3: 1.2, 4: 1.5, 5: 1.8,
        6: 1.5, 7: 1.0, 8: 1.2, 9: 0.5, 10: 0.8, 11: 0.3, 12: 0.5,
    },

    # ── Telecom ──
    "telecom": {
        1: 1.5, 2: 1.0, 3: 0.8, 4: 1.5, 5: 1.0,
        6: 1.0, 7: 1.5, 8: 1.0, 9: 1.5, 10: 1.0, 11: 1.2, 12: 0.8,
    },
}

# ──────────────────────────────────────────────
# Korean category keywords -> profile key mapping
# (product_category text can be Korean)
# ──────────────────────────────────────────────
KOREAN_CATEGORY_MAP: dict[str, str] = {
    # Beauty
    "beauty": "beauty", "cosmetics": "cosmetics",
    "skincare": "skincare", "makeup": "makeup",
    # Fashion
    "fashion": "fashion", "apparel": "apparel", "luxury": "luxury",
    # Auto
    "automotive": "automotive", "car": "car",
    # Finance
    "finance": "finance", "insurance": "insurance",
    "banking": "banking", "investment": "investment",
    # Health
    "health": "health", "medical": "medical", "pharma": "pharma",
    "supplement": "supplement", "hospital": "hospital",
    # Food
    "food": "food", "beverage": "beverage",
    "restaurant": "restaurant", "delivery": "delivery",
    # Tech
    "tech": "tech", "electronics": "electronics",
    "smartphone": "smartphone", "gaming": "gaming",
    "software": "software", "app": "app",
    # Education
    "education": "education", "academy": "academy", "university": "university",
    # Real Estate
    "real_estate": "real_estate", "interior": "interior", "furniture": "furniture",
    # Travel
    "travel": "travel", "hotel": "hotel", "airline": "airline",
    # Entertainment
    "entertainment": "entertainment", "movie": "movie",
    "music": "music", "webtoon": "webtoon",
    # Baby/Kids
    "baby": "baby", "kids": "kids", "parenting": "parenting",
    # Pet
    "pet": "pet",
    # Sports
    "sports": "sports", "fitness": "fitness", "golf": "golf",
    # Shopping
    "shopping": "shopping", "ecommerce": "ecommerce",
    # Telecom
    "telecom": "telecom",
}


def _normalize_weights(weights: dict[int, float]) -> dict[int, float]:
    """Normalize weights to probabilities (sum=1)."""
    total = sum(weights.values())
    if total == 0:
        # Fallback to uniform
        return {pid: 1.0 / 12 for pid in range(1, 13)}
    return {pid: w / total for pid, w in weights.items()}


def _pick_persona(weights: dict[int, float], rng: random.Random) -> int:
    """Pick a persona_id based on weighted probabilities."""
    normalized = _normalize_weights(weights)
    persona_ids = list(normalized.keys())
    probs = [normalized[pid] for pid in persona_ids]
    return rng.choices(persona_ids, weights=probs, k=1)[0]


def _match_category_profile(category_text: str | None) -> dict[int, float] | None:
    """Try to match a category text to a demographic profile.

    Checks for keyword containment (case-insensitive).
    Returns the weight profile or None if no match.
    """
    if not category_text:
        return None

    cat_lower = category_text.lower()

    # Direct key match first
    if cat_lower in CATEGORY_PROFILES:
        return CATEGORY_PROFILES[cat_lower]

    # Substring match
    for keyword, profile_key in KOREAN_CATEGORY_MAP.items():
        if keyword in cat_lower:
            return CATEGORY_PROFILES.get(profile_key)

    return None


def _match_industry_profile(industry_name: str | None) -> dict[int, float] | None:
    """Try to match an industry name to a demographic profile."""
    if not industry_name:
        return None

    ind_lower = industry_name.lower()

    # Direct key match
    if ind_lower in CATEGORY_PROFILES:
        return CATEGORY_PROFILES[ind_lower]

    # Substring match
    for keyword, profile_key in KOREAN_CATEGORY_MAP.items():
        if keyword in ind_lower:
            return CATEGORY_PROFILES.get(profile_key)

    return None


def _resolve_weights(
    product_category_text: str | None,
    product_category_name: str | None,
    industry_name: str | None,
    ad_text: str | None,
    brand: str | None,
) -> dict[int, float]:
    """Resolve the best weight profile for a given ad.

    Priority:
    1. product_category_id -> ProductCategory.name
    2. product_category (deprecated text field)
    3. advertiser industry
    4. ad_text keyword scan
    5. Uniform fallback
    """
    # 1. Normalized category name (FK)
    profile = _match_category_profile(product_category_name)
    if profile:
        return profile

    # 2. Deprecated text field
    profile = _match_category_profile(product_category_text)
    if profile:
        return profile

    # 3. Industry
    profile = _match_industry_profile(industry_name)
    if profile:
        return profile

    # 4. Ad text keyword scan (lightweight)
    combined_text = " ".join(filter(None, [ad_text, brand])).lower()
    if combined_text.strip():
        for keyword in CATEGORY_PROFILES:
            if keyword in combined_text:
                return CATEGORY_PROFILES[keyword]

    # 5. Uniform fallback
    return _UNIFORM


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Backfill persona_id for NULL ad_details")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without updating DB")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="Batch size for DB updates")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    batch_size = args.batch_size

    await init_db()

    # ── Step 1: Count NULL persona_id rows ──
    async with async_session() as session:
        count_result = await session.execute(
            select(func.count(AdDetail.id)).where(AdDetail.persona_id == None)  # noqa: E711
        )
        total_null = count_result.scalar_one()

        # Also count total for reference
        total_result = await session.execute(select(func.count(AdDetail.id)))
        total_all = total_result.scalar_one()

    print(f"Total ad_details: {total_all}")
    print(f"NULL persona_id: {total_null}")
    print(f"Already assigned: {total_all - total_null}")

    if total_null == 0:
        print("No NULL persona_id rows to backfill. Done.")
        return

    # ── Step 2: Pre-load industry names for advertisers ──
    async with async_session() as session:
        adv_result = await session.execute(
            select(Advertiser.id, Industry.name)
            .outerjoin(Industry, Advertiser.industry_id == Industry.id)
        )
        advertiser_industry: dict[int, str | None] = {
            row[0]: row[1] for row in adv_result.all()
        }

    # ── Step 3: Pre-load product category names ──
    async with async_session() as session:
        cat_result = await session.execute(
            select(ProductCategory.id, ProductCategory.name)
        )
        category_names: dict[int, str] = {
            row[0]: row[1] for row in cat_result.all()
        }

    print(f"Loaded {len(advertiser_industry)} advertisers, {len(category_names)} categories")

    # ── Step 4: Process in batches ──
    processed = 0
    assigned_counts: dict[int, int] = {pid: 0 for pid in range(1, 13)}
    profile_match_counts = {"category_fk": 0, "category_text": 0, "industry": 0, "ad_text": 0, "uniform": 0}

    offset = 0
    while processed < total_null:
        async with async_session() as session:
            # Fetch batch of NULL persona_id rows with relevant columns
            result = await session.execute(
                select(
                    AdDetail.id,
                    AdDetail.product_category_id,
                    AdDetail.product_category,
                    AdDetail.advertiser_id,
                    AdDetail.ad_text,
                    AdDetail.brand,
                )
                .where(AdDetail.persona_id == None)  # noqa: E711
                .order_by(AdDetail.id)
                .limit(batch_size)
            )
            rows = result.all()

        if not rows:
            break

        # Build update mappings: {ad_detail_id: persona_id}
        updates: list[dict] = []
        for row in rows:
            ad_id = row[0]
            pc_id = row[1]
            pc_text = row[2]
            adv_id = row[3]
            ad_text = row[4]
            brand_val = row[5]

            # Resolve category name from FK
            pc_name = category_names.get(pc_id) if pc_id else None
            # Resolve industry from advertiser
            ind_name = advertiser_industry.get(adv_id) if adv_id else None

            # Determine which source matched (for stats)
            matched_source = "uniform"
            if pc_name and _match_category_profile(pc_name):
                matched_source = "category_fk"
            elif pc_text and _match_category_profile(pc_text):
                matched_source = "category_text"
            elif ind_name and _match_industry_profile(ind_name):
                matched_source = "industry"
            else:
                combined = " ".join(filter(None, [ad_text, brand_val])).lower()
                if combined.strip():
                    for kw in CATEGORY_PROFILES:
                        if kw in combined:
                            matched_source = "ad_text"
                            break

            profile_match_counts[matched_source] += 1

            weights = _resolve_weights(pc_text, pc_name, ind_name, ad_text, brand_val)
            persona_id = _pick_persona(weights, rng)
            assigned_counts[persona_id] += 1
            updates.append({"_id": ad_id, "_persona_id": persona_id})

        if not args.dry_run:
            # Bulk update using individual UPDATE statements in a single transaction
            async with async_session() as session:
                for upd in updates:
                    await session.execute(
                        update(AdDetail)
                        .where(AdDetail.id == upd["_id"])
                        .values(persona_id=upd["_persona_id"])
                    )
                await session.commit()

        processed += len(rows)
        pct = round(processed / total_null * 100, 1)
        mode = "[DRY-RUN] " if args.dry_run else ""
        print(f"{mode}Progress: {processed}/{total_null} ({pct}%)")

    # ── Step 5: Print summary ──
    print()
    print("=" * 60)
    print(f"{'[DRY-RUN] ' if args.dry_run else ''}Backfill complete: {processed} rows processed")
    print("=" * 60)
    print()

    print("Persona distribution:")
    for pid in range(1, 13):
        code = PERSONA_MAP[pid]
        cnt = assigned_counts[pid]
        pct = round(cnt / max(processed, 1) * 100, 1)
        bar = "#" * int(pct / 2)
        print(f"  {code:>4} (id={pid:>2}): {cnt:>6} ({pct:>5}%) {bar}")

    print()
    print("Match source stats:")
    for src, cnt in sorted(profile_match_counts.items(), key=lambda x: -x[1]):
        pct = round(cnt / max(processed, 1) * 100, 1)
        print(f"  {src:<15}: {cnt:>6} ({pct}%)")

    # Verify in DB
    if not args.dry_run:
        print()
        print("Verification (ad_details.persona_id counts after backfill):")
        async with async_session() as session:
            verify_result = await session.execute(
                select(AdDetail.persona_id, func.count(AdDetail.id))
                .group_by(AdDetail.persona_id)
                .order_by(AdDetail.persona_id)
            )
            for pid, cnt in verify_result.all():
                code = PERSONA_MAP.get(pid, "NULL") if pid else "NULL"
                print(f"  {code:>4} (id={str(pid):>4}): {cnt:>6}")


if __name__ == "__main__":
    asyncio.run(main())
