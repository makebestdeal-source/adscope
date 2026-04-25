"""Seed major advertisers from internal seeds plus ADIC top advertisers.

Sources:
- data/advertiser_seed.json
- scripts/seed_advertisers_expanded.py
- adic_ad_expenses top advertisers in the current DB

This script is idempotent and safe to run multiple times.

Usage:
    python scripts/seed_major_advertisers.py
    python scripts/seed_major_advertisers.py --adic-top-n 300
    python scripts/seed_major_advertisers.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import io
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from database import async_session, init_db  # noqa: E402
from database.models import Advertiser, Industry  # noqa: E402
from processor.advertiser_verifier import normalize_name  # noqa: E402

SEED_JSON_PATH = ROOT / "data" / "advertiser_seed.json"
EXPANDED_SEED_PATH = ROOT / "scripts" / "seed_advertisers_expanded.py"
DB_PATH = ROOT / "adscope.db"


def _norm(value: str | None) -> str:
    if not value:
        return ""
    normalized = normalize_name(value)
    return normalized.lower().strip()


def _ensure_https(value: str | None) -> str | None:
    if not value:
        return value
    value = value.strip()
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return value
    return f"https://{value}"


def _load_json_seed() -> tuple[list[dict], list[dict]]:
    data = json.loads(SEED_JSON_PATH.read_text(encoding="utf-8"))
    return data.get("industries", []), data.get("advertisers", [])


def _load_expanded_seed() -> list[dict]:
    spec = importlib.util.spec_from_file_location("seed_advertisers_expanded", EXPANDED_SEED_PATH)
    if spec is None or spec.loader is None:
        return []
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "ADVERTISERS", [])


def _load_adic_top(top_n: int) -> tuple[int | None, list[dict]]:
    import sqlite3

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    year = conn.execute(
        "SELECT MAX(year) FROM adic_ad_expenses WHERE medium = 'total'"
    ).fetchone()[0]
    rows = conn.execute(
        """
        SELECT advertiser_name, ROUND(SUM(amount), 0) AS total_amount
        FROM adic_ad_expenses
        WHERE medium = 'total' AND year = ?
        GROUP BY advertiser_name
        ORDER BY total_amount DESC, advertiser_name ASC
        LIMIT ?
        """,
        (year, top_n),
    ).fetchall()
    conn.close()
    return year, [dict(row) for row in rows]


def _merge_aliases(*alias_groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in alias_groups:
        for alias in group or []:
            alias = (alias or "").strip()
            if not alias:
                continue
            key = alias.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(alias)
    return merged


def _build_candidate_pool(adic_top_n: int) -> tuple[dict[str, dict], int | None]:
    industries, json_advertisers = _load_json_seed()
    expanded_advertisers = _load_expanded_seed()
    adic_year, adic_rows = _load_adic_top(adic_top_n)

    industry_defaults = {item["name"]: item for item in industries}
    candidates: dict[str, dict] = {}

    def upsert_candidate(name: str, payload: dict) -> None:
        key = _norm(name)
        if not key:
            return
        existing = candidates.get(key)
        if existing is None:
            candidates[key] = payload
            return

        existing["aliases"] = _merge_aliases(existing.get("aliases", []), payload.get("aliases", []))
        existing["sources"] = sorted(set(existing.get("sources", [])) | set(payload.get("sources", [])))

        for field in ["industry_name", "industry_id", "advertiser_type", "brand_name", "website"]:
            if not existing.get(field) and payload.get(field):
                existing[field] = payload[field]

        if payload.get("official_channels") and not existing.get("official_channels"):
            existing["official_channels"] = payload["official_channels"]

    for item in json_advertisers:
        name = item["name"].strip()
        industry_name = item.get("industry")
        upsert_candidate(
            name,
            {
                "name": name,
                "industry_name": industry_name,
                "industry_defaults": industry_defaults.get(industry_name),
                "advertiser_type": item.get("type"),
                "brand_name": item.get("brand"),
                "website": _ensure_https(item.get("website")),
                "aliases": _merge_aliases(item.get("aliases", [])),
                "official_channels": item.get("channels") or {},
                "sources": ["seed_json"],
            },
        )

    for item in expanded_advertisers:
        name = item["name"].strip()
        upsert_candidate(
            name,
            {
                "name": name,
                "industry_id": item.get("industry_id"),
                "advertiser_type": item.get("advertiser_type"),
                "website": _ensure_https(item.get("website")),
                "aliases": [],
                "official_channels": {},
                "sources": ["seed_expanded"],
            },
        )

    for item in adic_rows:
        raw_name = (item["advertiser_name"] or "").strip()
        canonical_name = normalize_name(raw_name) or raw_name
        aliases = [raw_name] if canonical_name != raw_name else []
        upsert_candidate(
            canonical_name,
            {
                "name": canonical_name,
                "aliases": aliases,
                "sources": [f"adic_top_{adic_year}"],
            },
        )

    return candidates, adic_year


async def _upsert_industries(session, industries: list[dict]) -> dict[str, int]:
    result = await session.execute(select(Industry))
    existing = {row.name: row for row in result.scalars().all()}

    for item in industries:
        name = item["name"]
        row = existing.get(name)
        if row is None:
            row = Industry(
                name=name,
                avg_cpc_min=item.get("avg_cpc_min"),
                avg_cpc_max=item.get("avg_cpc_max"),
            )
            session.add(row)
            existing[name] = row
        else:
            if item.get("avg_cpc_min") and row.avg_cpc_min is None:
                row.avg_cpc_min = item["avg_cpc_min"]
            if item.get("avg_cpc_max") and row.avg_cpc_max is None:
                row.avg_cpc_max = item["avg_cpc_max"]

    await session.flush()
    result = await session.execute(select(Industry))
    return {row.name: row.id for row in result.scalars().all()}


async def main(dry_run: bool = False, adic_top_n: int = 300) -> None:
    await init_db()

    industries, _ = _load_json_seed()
    candidates, adic_year = _build_candidate_pool(adic_top_n=adic_top_n)

    print(f"[seed-major] candidate pool: {len(candidates)} advertisers")
    if adic_year:
        print(f"[seed-major] includes ADIC top {adic_top_n} from {adic_year}")

    async with async_session() as session:
        industry_map = await _upsert_industries(session, industries)

        result = await session.execute(select(Advertiser))
        existing_rows = result.scalars().all()
        existing_by_norm = {_norm(row.name): row for row in existing_rows}

        stats = defaultdict(int)
        now = datetime.now(timezone.utc)

        for key, candidate in candidates.items():
            existing = existing_by_norm.get(key)
            alias_list = _merge_aliases(candidate.get("aliases", []))
            source = ",".join(candidate.get("sources", []))
            industry_id = candidate.get("industry_id")
            if industry_id is None and candidate.get("industry_name"):
                industry_id = industry_map.get(candidate["industry_name"])

            if existing is None:
                advertiser = Advertiser(
                    name=candidate["name"],
                    industry_id=industry_id,
                    advertiser_type=candidate.get("advertiser_type"),
                    brand_name=candidate.get("brand_name"),
                    website=candidate.get("website"),
                    aliases=alias_list,
                    official_channels=candidate.get("official_channels") or {},
                    data_source=source,
                    profile_updated_at=now,
                )
                session.add(advertiser)
                existing_by_norm[key] = advertiser
                stats["created"] += 1
                continue

            changed = False

            if not existing.industry_id and industry_id:
                existing.industry_id = industry_id
                changed = True
            if not existing.advertiser_type and candidate.get("advertiser_type"):
                existing.advertiser_type = candidate["advertiser_type"]
                changed = True
            if not existing.brand_name and candidate.get("brand_name"):
                existing.brand_name = candidate["brand_name"]
                changed = True
            if not existing.website and candidate.get("website"):
                existing.website = candidate["website"]
                changed = True
            if candidate.get("official_channels") and not existing.official_channels:
                existing.official_channels = candidate["official_channels"]
                changed = True

            merged_aliases = _merge_aliases(existing.aliases or [], alias_list)
            if merged_aliases != (existing.aliases or []):
                existing.aliases = merged_aliases
                changed = True

            merged_sources = sorted(
                set(filter(None, (existing.data_source or "").split(","))) | set(candidate.get("sources", []))
            )
            merged_source_text = ",".join(merged_sources)
            if merged_source_text and merged_source_text != (existing.data_source or ""):
                existing.data_source = merged_source_text
                changed = True

            if changed:
                existing.profile_updated_at = now
                stats["updated"] += 1
            else:
                stats["unchanged"] += 1

        await session.flush()

        result = await session.execute(select(Advertiser))
        refreshed_rows = result.scalars().all()
        refreshed_by_norm = {_norm(row.name): row for row in refreshed_rows}
        for row in refreshed_rows:
            for alias in row.aliases or []:
                alias_key = _norm(alias)
                if alias_key and alias_key not in refreshed_by_norm:
                    refreshed_by_norm[alias_key] = row

        adic_names = (
            await session.execute(
                text(
                    """
                    SELECT advertiser_name
                    FROM adic_ad_expenses
                    WHERE advertiser_id IS NULL
                    GROUP BY advertiser_name
                    """
                )
            )
        ).scalars().all()

        for raw_name in adic_names:
            raw_name = (raw_name or "").strip()
            if not raw_name:
                continue
            canonical_name = normalize_name(raw_name) or raw_name
            advertiser = refreshed_by_norm.get(_norm(canonical_name)) or refreshed_by_norm.get(_norm(raw_name))
            if advertiser is None:
                stats["adic_unlinked_names"] += 1
                continue

            result = await session.execute(
                text(
                    """
                    UPDATE adic_ad_expenses
                    SET advertiser_id = :advertiser_id
                    WHERE advertiser_id IS NULL
                      AND advertiser_name = :advertiser_name
                    """
                ),
                {"advertiser_id": advertiser.id, "advertiser_name": raw_name},
            )
            linked_rows = int(result.rowcount or 0)
            if linked_rows > 0:
                stats["adic_linked_rows"] += linked_rows
                stats["adic_linked_names"] += 1

        total_after = len(existing_by_norm)

        if dry_run:
            await session.rollback()
            print("[seed-major] dry-run: rolled back changes")
        else:
            await session.commit()
            print("[seed-major] committed changes")

        print(
            "[seed-major] created={created} updated={updated} unchanged={unchanged} total_after={total}".format(
                created=stats["created"],
                updated=stats["updated"],
                unchanged=stats["unchanged"],
                total=total_after,
            )
        )
        print(
            "[seed-major] adic_linked_rows={rows} adic_linked_names={names} adic_unlinked_names={unlinked}".format(
                rows=stats["adic_linked_rows"],
                names=stats["adic_linked_names"],
                unlinked=stats["adic_unlinked_names"],
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed major advertisers from seeds + ADIC")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    parser.add_argument("--adic-top-n", type=int, default=300, help="ADIC top advertiser pool size")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run, adic_top_n=args.adic_top_n))
