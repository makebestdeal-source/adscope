"""Master Index API — 매체/광고주 인덱스 관리."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_current_user, require_paid
from pydantic import BaseModel
from typing import Optional
from database import async_session
from sqlalchemy import text
import json

router = APIRouter(prefix="/api/master", tags=["master-index"],
    dependencies=[Depends(get_current_user)])


# ── Pydantic Models ──

class AdPlatformCreate(BaseModel):
    operator_name: str
    platform_name: str
    service_name: Optional[str] = None
    platform_type: Optional[str] = None
    sub_type: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    billing_types: Optional[list[str]] = None
    min_budget: Optional[float] = None
    is_self_serve: bool = True
    is_active: bool = True
    monthly_reach: Optional[str] = None
    notes: Optional[str] = None

class AdPlatformUpdate(BaseModel):
    operator_name: Optional[str] = None
    platform_name: Optional[str] = None
    service_name: Optional[str] = None
    platform_type: Optional[str] = None
    sub_type: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    billing_types: Optional[list[str]] = None
    min_budget: Optional[float] = None
    is_self_serve: Optional[bool] = None
    is_active: Optional[bool] = None
    monthly_reach: Optional[str] = None
    notes: Optional[str] = None

class AdvertiserCreate(BaseModel):
    name: str
    industry_id: Optional[int] = None
    parent_id: Optional[int] = None
    advertiser_type: Optional[str] = None  # group/company/brand/product
    brand_name: Optional[str] = None
    website: Optional[str] = None
    aliases: Optional[list[str]] = None
    description: Optional[str] = None
    headquarters: Optional[str] = None
    is_public: bool = False
    official_channels: Optional[dict] = None
    data_source: str = "manual"

class AdvertiserUpdate(BaseModel):
    name: Optional[str] = None
    industry_id: Optional[int] = None
    parent_id: Optional[int] = None
    advertiser_type: Optional[str] = None
    brand_name: Optional[str] = None
    website: Optional[str] = None
    aliases: Optional[list[str]] = None
    description: Optional[str] = None
    headquarters: Optional[str] = None
    is_public: Optional[bool] = None
    official_channels: Optional[dict] = None
    data_source: Optional[str] = None


# ═══════════════════════════════════════════
# AD PLATFORMS CRUD
# ═══════════════════════════════════════════

@router.get("/platforms")
async def list_platforms(
    platform_type: Optional[str] = None,
    sub_type: Optional[str] = None,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List ad platforms with filtering."""
    async with async_session() as session:
        conditions = []
        params = {}

        if platform_type:
            conditions.append("platform_type = :pt")
            params["pt"] = platform_type
        if sub_type:
            conditions.append("sub_type = :st")
            params["st"] = sub_type
        if is_active is not None:
            conditions.append("is_active = :ia")
            params["ia"] = 1 if is_active else 0
        if search:
            conditions.append("(operator_name LIKE :q OR platform_name LIKE :q OR service_name LIKE :q)")
            params["q"] = f"%{search}%"

        where = " AND ".join(conditions)
        where_clause = f"WHERE {where}" if where else ""

        # Count
        count_result = await session.execute(
            text(f"SELECT COUNT(*) FROM ad_platforms {where_clause}"), params
        )
        total = count_result.scalar() or 0

        # Fetch
        offset = (page - 1) * page_size
        params["limit"] = page_size
        params["offset"] = offset
        result = await session.execute(
            text(f"""SELECT id, operator_name, platform_name, service_name, platform_type, sub_type,
                     url, description, billing_types, min_budget, is_self_serve, is_active,
                     country, monthly_reach, data_source, notes, created_at, updated_at
                     FROM ad_platforms {where_clause}
                     ORDER BY operator_name, platform_name
                     LIMIT :limit OFFSET :offset"""),
            params,
        )
        rows = result.fetchall()

        items = []
        for r in rows:
            bt = r[8]
            if bt and isinstance(bt, str):
                try:
                    bt = json.loads(bt)
                except Exception:
                    bt = []
            items.append({
                "id": r[0], "operator_name": r[1], "platform_name": r[2],
                "service_name": r[3], "platform_type": r[4], "sub_type": r[5],
                "url": r[6], "description": r[7], "billing_types": bt or [],
                "min_budget": r[9], "is_self_serve": bool(r[10]), "is_active": bool(r[11]),
                "country": r[12], "monthly_reach": r[13], "data_source": r[14],
                "notes": r[15], "created_at": str(r[16]) if r[16] else None,
                "updated_at": str(r[17]) if r[17] else None,
            })

        return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/platforms/types")
async def platform_type_summary():
    """Get platform type distribution."""
    async with async_session() as session:
        result = await session.execute(text("""
            SELECT platform_type, COUNT(*) as cnt FROM ad_platforms
            WHERE is_active = 1
            GROUP BY platform_type ORDER BY cnt DESC
        """))
        return [{"type": r[0] or "unknown", "count": r[1]} for r in result.fetchall()]


@router.get("/platforms/{platform_id}")
async def get_platform(platform_id: int):
    """Get single platform detail."""
    async with async_session() as session:
        result = await session.execute(
            text("SELECT * FROM ad_platforms WHERE id = :id"), {"id": platform_id}
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(404, "Platform not found")
        cols = result.keys()
        data = dict(zip(cols, row))
        if data.get("billing_types") and isinstance(data["billing_types"], str):
            try:
                data["billing_types"] = json.loads(data["billing_types"])
            except Exception:
                pass
        return data


@router.post("/platforms")
async def create_platform(body: AdPlatformCreate):
    """Create a new ad platform."""
    async with async_session() as session:
        bt = json.dumps(body.billing_types, ensure_ascii=False) if body.billing_types else None
        await session.execute(text("""
            INSERT INTO ad_platforms (operator_name, platform_name, service_name, platform_type, sub_type,
                url, description, billing_types, min_budget, is_self_serve, is_active, country,
                monthly_reach, data_source, notes, created_at, updated_at)
            VALUES (:op, :pn, :sn, :pt, :st, :url, :desc, :bt, :mb, :ss, :ia, 'KR', :mr, :ds, :notes,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """), {
            "op": body.operator_name, "pn": body.platform_name, "sn": body.service_name,
            "pt": body.platform_type, "st": body.sub_type, "url": body.url,
            "desc": body.description, "bt": bt, "mb": body.min_budget,
            "ss": 1 if body.is_self_serve else 0, "ia": 1 if body.is_active else 0,
            "mr": body.monthly_reach, "ds": "manual", "notes": body.notes,
        })
        await session.commit()
        return {"status": "created"}


@router.put("/platforms/{platform_id}")
async def update_platform(platform_id: int, body: AdPlatformUpdate):
    """Update an ad platform."""
    async with async_session() as session:
        # Check exists
        r = await session.execute(text("SELECT id FROM ad_platforms WHERE id = :id"), {"id": platform_id})
        if not r.fetchone():
            raise HTTPException(404, "Platform not found")

        updates = []
        params = {"id": platform_id}
        data = body.model_dump(exclude_unset=True)
        for key, val in data.items():
            if key == "billing_types" and val is not None:
                val = json.dumps(val, ensure_ascii=False)
            elif key in ("is_self_serve", "is_active") and val is not None:
                val = 1 if val else 0
            updates.append(f"{key} = :{key}")
            params[key] = val

        if not updates:
            return {"status": "no changes"}

        updates.append("updated_at = CURRENT_TIMESTAMP")
        set_clause = ", ".join(updates)
        await session.execute(text(f"UPDATE ad_platforms SET {set_clause} WHERE id = :id"), params)
        await session.commit()
        return {"status": "updated"}


@router.delete("/platforms/{platform_id}")
async def delete_platform(platform_id: int):
    """Delete an ad platform."""
    async with async_session() as session:
        r = await session.execute(text("SELECT id FROM ad_platforms WHERE id = :id"), {"id": platform_id})
        if not r.fetchone():
            raise HTTPException(404, "Platform not found")
        await session.execute(text("DELETE FROM ad_platforms WHERE id = :id"), {"id": platform_id})
        await session.commit()
        return {"status": "deleted"}


# ═══════════════════════════════════════════
# ADVERTISERS CRUD (enhanced for master index)
# ═══════════════════════════════════════════

@router.get("/advertisers")
async def list_master_advertisers(
    industry_id: Optional[int] = None,
    advertiser_type: Optional[str] = None,
    search: Optional[str] = None,
    has_website: Optional[bool] = None,
    has_channels: Optional[bool] = None,
    data_source: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List advertisers with enhanced master index filtering."""
    async with async_session() as session:
        conditions = []
        params = {}

        if industry_id:
            conditions.append("a.industry_id = :iid")
            params["iid"] = industry_id
        if advertiser_type:
            conditions.append("a.advertiser_type = :at")
            params["at"] = advertiser_type
        if search:
            conditions.append("(a.name LIKE :q OR a.brand_name LIKE :q OR a.website LIKE :q)")
            params["q"] = f"%{search}%"
        if has_website is True:
            conditions.append("a.website IS NOT NULL AND a.website != ''")
        elif has_website is False:
            conditions.append("(a.website IS NULL OR a.website = '')")
        if has_channels is True:
            conditions.append("a.official_channels IS NOT NULL AND a.official_channels != '{}' AND a.official_channels != 'null'")
        if data_source:
            conditions.append("a.data_source = :ds")
            params["ds"] = data_source

        where = " AND ".join(conditions)
        where_clause = f"WHERE {where}" if where else ""

        count_result = await session.execute(
            text(f"SELECT COUNT(*) FROM advertisers a {where_clause}"), params
        )
        total = count_result.scalar() or 0

        offset = (page - 1) * page_size
        params["limit"] = page_size
        params["offset"] = offset

        result = await session.execute(text(f"""
            SELECT a.id, a.name, a.industry_id, i.name as industry_name,
                   a.parent_id, a.advertiser_type, a.brand_name, a.website,
                   a.aliases, a.official_channels, a.description,
                   a.headquarters, a.is_public, a.data_source,
                   a.created_at, a.updated_at,
                   (SELECT COUNT(*) FROM ad_details WHERE advertiser_id = a.id) as ad_count
            FROM advertisers a
            LEFT JOIN industries i ON i.id = a.industry_id
            {where_clause}
            ORDER BY a.name
            LIMIT :limit OFFSET :offset
        """), params)
        rows = result.fetchall()

        items = []
        for r in rows:
            aliases = r[8]
            if aliases and isinstance(aliases, str):
                try:
                    aliases = json.loads(aliases)
                except Exception:
                    aliases = []
            channels = r[9]
            if channels and isinstance(channels, str):
                try:
                    channels = json.loads(channels)
                except Exception:
                    channels = {}
            items.append({
                "id": r[0], "name": r[1], "industry_id": r[2], "industry_name": r[3],
                "parent_id": r[4], "advertiser_type": r[5], "brand_name": r[6],
                "website": r[7], "aliases": aliases or [], "official_channels": channels or {},
                "description": r[10], "headquarters": r[11], "is_public": bool(r[12]) if r[12] is not None else False,
                "data_source": r[13],
                "created_at": str(r[14]) if r[14] else None,
                "updated_at": str(r[15]) if r[15] else None,
                "ad_count": r[16] or 0,
            })

        # Get industries for filter dropdown
        ind_result = await session.execute(text("SELECT id, name FROM industries ORDER BY name"))
        industries = [{"id": r[0], "name": r[1]} for r in ind_result.fetchall()]

        return {"total": total, "page": page, "page_size": page_size, "items": items, "industries": industries}


@router.get("/advertisers/stats")
async def advertiser_index_stats():
    """Summary stats for advertiser index."""
    async with async_session() as session:
        result = await session.execute(text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN website IS NOT NULL AND website != '' THEN 1 ELSE 0 END) as has_website,
                SUM(CASE WHEN official_channels IS NOT NULL AND official_channels != '{}' AND official_channels != 'null' THEN 1 ELSE 0 END) as has_channels,
                SUM(CASE WHEN industry_id IS NOT NULL THEN 1 ELSE 0 END) as has_industry,
                SUM(CASE WHEN advertiser_type IS NOT NULL THEN 1 ELSE 0 END) as has_type
            FROM advertisers
        """))
        row = result.fetchone()
        return {
            "total": row[0] or 0,
            "has_website": row[1] or 0,
            "has_channels": row[2] or 0,
            "has_industry": row[3] or 0,
            "has_type": row[4] or 0,
        }


@router.post("/advertisers")
async def create_master_advertiser(body: AdvertiserCreate):
    """Create a new advertiser in the master index."""
    async with async_session() as session:
        # Check duplicate name
        r = await session.execute(
            text("SELECT id FROM advertisers WHERE name = :name"), {"name": body.name}
        )
        if r.fetchone():
            raise HTTPException(409, f"Advertiser '{body.name}' already exists")

        aliases_json = json.dumps(body.aliases, ensure_ascii=False) if body.aliases else None
        channels_json = json.dumps(body.official_channels, ensure_ascii=False) if body.official_channels else None

        await session.execute(text("""
            INSERT INTO advertisers (name, industry_id, parent_id, advertiser_type, brand_name,
                website, aliases, description, headquarters, is_public, official_channels,
                data_source, created_at, updated_at)
            VALUES (:name, :iid, :pid, :at, :bn, :web, :aliases, :desc, :hq, :pub, :ch, :ds,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """), {
            "name": body.name, "iid": body.industry_id, "pid": body.parent_id,
            "at": body.advertiser_type, "bn": body.brand_name, "web": body.website,
            "aliases": aliases_json, "desc": body.description, "hq": body.headquarters,
            "pub": 1 if body.is_public else 0, "ch": channels_json, "ds": body.data_source,
        })
        await session.commit()

        r2 = await session.execute(text("SELECT id FROM advertisers WHERE name = :name"), {"name": body.name})
        new_id = r2.scalar()
        return {"status": "created", "id": new_id}


@router.put("/advertisers/{advertiser_id}")
async def update_master_advertiser(advertiser_id: int, body: AdvertiserUpdate):
    """Update advertiser in master index."""
    async with async_session() as session:
        r = await session.execute(text("SELECT id FROM advertisers WHERE id = :id"), {"id": advertiser_id})
        if not r.fetchone():
            raise HTTPException(404, "Advertiser not found")

        updates = []
        params = {"id": advertiser_id}
        data = body.model_dump(exclude_unset=True)
        for key, val in data.items():
            if key == "aliases" and val is not None:
                val = json.dumps(val, ensure_ascii=False)
            elif key == "official_channels" and val is not None:
                val = json.dumps(val, ensure_ascii=False)
            elif key == "is_public" and val is not None:
                val = 1 if val else 0
            updates.append(f"{key} = :{key}")
            params[key] = val

        if not updates:
            return {"status": "no changes"}

        updates.append("updated_at = CURRENT_TIMESTAMP")
        set_clause = ", ".join(updates)
        await session.execute(text(f"UPDATE advertisers SET {set_clause} WHERE id = :id"), params)
        await session.commit()
        return {"status": "updated"}


@router.delete("/advertisers/{advertiser_id}")
async def delete_master_advertiser(advertiser_id: int):
    """Delete advertiser (with cascade cleanup)."""
    async with async_session() as session:
        r = await session.execute(text("SELECT id, name FROM advertisers WHERE id = :id"), {"id": advertiser_id})
        row = r.fetchone()
        if not row:
            raise HTTPException(404, "Advertiser not found")

        # Check dependencies
        ad_count = (await session.execute(
            text("SELECT COUNT(*) FROM ad_details WHERE advertiser_id = :id"), {"id": advertiser_id}
        )).scalar() or 0

        if ad_count > 0:
            # Soft delete — just remove from index but keep data
            # Actually delete related campaigns and ads
            await session.execute(
                text("DELETE FROM spend_estimates WHERE campaign_id IN (SELECT id FROM campaigns WHERE advertiser_id = :id)"),
                {"id": advertiser_id}
            )
            await session.execute(text("DELETE FROM campaigns WHERE advertiser_id = :id"), {"id": advertiser_id})
            await session.execute(text("DELETE FROM ad_details WHERE advertiser_id = :id"), {"id": advertiser_id})

        await session.execute(text("DELETE FROM advertisers WHERE id = :id"), {"id": advertiser_id})
        await session.commit()
        return {"status": "deleted", "name": row[1], "ads_removed": ad_count}


@router.post("/advertisers/bulk-import")
async def bulk_import_advertisers(items: list[AdvertiserCreate]):
    """Bulk import advertisers."""
    async with async_session() as session:
        inserted = 0
        skipped = 0
        for item in items:
            r = await session.execute(
                text("SELECT id FROM advertisers WHERE name = :name"), {"name": item.name}
            )
            if r.fetchone():
                skipped += 1
                continue

            aliases_json = json.dumps(item.aliases, ensure_ascii=False) if item.aliases else None
            channels_json = json.dumps(item.official_channels, ensure_ascii=False) if item.official_channels else None

            await session.execute(text("""
                INSERT INTO advertisers (name, industry_id, parent_id, advertiser_type, brand_name,
                    website, aliases, description, headquarters, is_public, official_channels,
                    data_source, created_at, updated_at)
                VALUES (:name, :iid, :pid, :at, :bn, :web, :aliases, :desc, :hq, :pub, :ch, :ds,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """), {
                "name": item.name, "iid": item.industry_id, "pid": item.parent_id,
                "at": item.advertiser_type, "bn": item.brand_name, "web": item.website,
                "aliases": aliases_json, "desc": item.description, "hq": item.headquarters,
                "pub": 1 if item.is_public else 0, "ch": channels_json, "ds": item.data_source,
            })
            inserted += 1

        await session.commit()
        return {"inserted": inserted, "skipped": skipped, "total": len(items)}
