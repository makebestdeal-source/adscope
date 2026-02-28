"""One-shot cleanup: house ads, bad advertiser names, orphan campaigns, URL-less advertisers.

Usage: python scripts/cleanup_advertisers.py [--dry-run]
"""
import asyncio
import re
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from database import async_session
from sqlalchemy import text

# ── House ad patterns (platform internal services) ──
HOUSE_AD_NAMES = {
    # Naver internal
    "네이버", "NAVER",  # 플랫폼명 자체는 광고주가 아님 (잘못 매핑된 광고)
    "네이버페이", "네이버 페이", "Naver Pay",
    "네이버쇼핑", "네이버 쇼핑",
    "네이버해피빈", "네이버 해피빈", "해피빈",
    "네이버 멤버십", "네이버멤버십",
    "네이버 블로그", "네이버블로그",
    "네이버 카페", "네이버카페",
    "네이버 지도", "네이버지도",
    "네이버 뉴스", "네이버뉴스",
    "네이버 MY", "네이버MY",
    "NAVER Direct",
    # Kakao internal
    "카카오", "Kakao",  # 플랫폼명 자체
    "카카오페이", "카카오 페이",
    "카카오뱅크", "카카오 뱅크",
    "카카오톡", "카카오 톡",
    "카카오커뮤니티", "카카오 커뮤니티",
    "카카오카",
    "다음", "Daum",
}

HOUSE_AD_NAME_PATTERNS = [
    re.compile(r"^blog\.naver", re.IGNORECASE),
    re.compile(r"^cafe\.naver", re.IGNORECASE),
    re.compile(r"^map\.naver", re.IGNORECASE),
    re.compile(r"^m\.place\.naver", re.IGNORECASE),
    re.compile(r"^place\.naver", re.IGNORECASE),
    re.compile(r"^booking\.naver", re.IGNORECASE),
    re.compile(r"^kin\.naver", re.IGNORECASE),
    re.compile(r"^news\.naver", re.IGNORECASE),
]

# Exact names to keep (legitimate advertisers that contain "네이버" etc.)
WHITELIST = {
    "네이버웹툰", "네이버파이낸셜", "네이버클라우드",
    "네이버제트", "네이버재팬", "네이버웹툰이엔에스",
    "네이버 커넥트재단",
    "카카오게임즈", "카카오엔터테인먼트",
    "카카오모빌리티", "카카오브레인",
    "다음소프트", "다이소",  # "다음"으로 시작하지만 다른 회사
}

# ── Garbage advertiser patterns ──
GARBAGE_PATTERNS = [
    re.compile(r"^\[unknown-\d+\]$"),
    re.compile(r"^\[특가\]"),  # [특가] 팰리세이드HEV 월 납입료...
    re.compile(r"^\(c\)\s"),   # (c) 산이좋은사람들 저작권법...
    re.compile(r"^저작권"),
    re.compile(r"^Visit Instagram"),
    re.compile(r"^AD,\s*광고"),
    re.compile(r"^광고 닫기"),
]


def is_house_ad(name: str) -> bool:
    """Check if advertiser name matches house ad patterns."""
    if name in WHITELIST:
        return False
    # Exact match only (don't do substring to avoid false positives like "마리떼...네이버에서")
    if name in HOUSE_AD_NAMES:
        return True
    # Pattern match (starts with platform subdomain)
    for pat in HOUSE_AD_NAME_PATTERNS:
        if pat.match(name):
            return True
    # Names that START with house service name (e.g. "네이버페이 ... Naver Pay")
    for h in HOUSE_AD_NAMES:
        if name.startswith(h + " ") or name.startswith(h + "\t"):
            return True
    return False


def is_garbage_name(name: str) -> bool:
    """Check if name is clearly not a real advertiser."""
    for pat in GARBAGE_PATTERNS:
        if pat.search(name):
            return True
    # Extremely long ad-copy names (>25 chars with Korean sentence endings)
    if len(name) > 25 and re.search(r"(합니다|입니다|됩니다|만원대|가능$|보기$|확인$)", name):
        return True
    return False


async def main():
    dry_run = "--dry-run" in sys.argv

    stats = {
        "house_deleted": 0,
        "garbage_deleted": 0,
        "orphan_campaigns_deleted": 0,
        "orphan_ad_details_deleted": 0,
        "name_cleaned": 0,
    }

    async with async_session() as session:
        # ── 1. Get all advertisers ──
        result = await session.execute(text("SELECT id, name FROM advertisers ORDER BY id"))
        advertisers = result.fetchall()
        print(f"Total advertisers: {len(advertisers)}")

        house_ids = []
        garbage_ids = []

        for aid, name in advertisers:
            if not name:
                garbage_ids.append(aid)
                continue
            if is_house_ad(name):
                house_ids.append((aid, name))
            elif is_garbage_name(name):
                garbage_ids.append(aid)

        # ── 2. Delete house ad advertisers ──
        print(f"\n=== House ads to delete: {len(house_ids)} ===")
        for aid, name in house_ids:
            r = await session.execute(
                text("SELECT COUNT(*) FROM ad_details WHERE advertiser_id = :id"), {"id": aid}
            )
            ad_cnt = r.scalar() or 0
            print(f"  [{aid}] {name} ({ad_cnt} ads)")
            if not dry_run:
                # Delete related data
                await session.execute(
                    text("DELETE FROM spend_estimates WHERE campaign_id IN (SELECT id FROM campaigns WHERE advertiser_id = :id)"),
                    {"id": aid}
                )
                await session.execute(text("DELETE FROM campaigns WHERE advertiser_id = :id"), {"id": aid})
                await session.execute(text("DELETE FROM ad_details WHERE advertiser_id = :id"), {"id": aid})
                await session.execute(text("DELETE FROM advertisers WHERE id = :id"), {"id": aid})
                stats["house_deleted"] += 1

        # ── 3. Delete garbage name advertisers ──
        print(f"\n=== Garbage names to delete: {len(garbage_ids)} ===")
        for aid in garbage_ids:
            r = await session.execute(
                text("SELECT name FROM advertisers WHERE id = :id"), {"id": aid}
            )
            row = r.fetchone()
            name = row[0] if row else "?"
            print(f"  [{aid}] {name}")
            if not dry_run:
                await session.execute(
                    text("DELETE FROM spend_estimates WHERE campaign_id IN (SELECT id FROM campaigns WHERE advertiser_id = :id)"),
                    {"id": aid}
                )
                await session.execute(text("DELETE FROM campaigns WHERE advertiser_id = :id"), {"id": aid})
                await session.execute(text("DELETE FROM ad_details WHERE advertiser_id = :id"), {"id": aid})
                await session.execute(text("DELETE FROM advertisers WHERE id = :id"), {"id": aid})
                stats["garbage_deleted"] += 1

        # ── 4. Clean orphan campaigns (advertiser_id points to deleted advertiser) ──
        r = await session.execute(text("""
            SELECT c.id FROM campaigns c
            LEFT JOIN advertisers a ON a.id = c.advertiser_id
            WHERE a.id IS NULL
        """))
        orphan_camp_ids = [row[0] for row in r.fetchall()]
        print(f"\n=== Orphan campaigns to delete: {len(orphan_camp_ids)} ===")
        if orphan_camp_ids and not dry_run:
            for cid in orphan_camp_ids:
                await session.execute(text("DELETE FROM spend_estimates WHERE campaign_id = :id"), {"id": cid})
                await session.execute(text("DELETE FROM campaign_lifts WHERE campaign_id = :id"), {"id": cid})
                await session.execute(text("DELETE FROM journey_events WHERE campaign_id = :id"), {"id": cid})
                await session.execute(text("DELETE FROM campaigns WHERE id = :id"), {"id": cid})
            stats["orphan_campaigns_deleted"] = len(orphan_camp_ids)

        # ── 5. Clean orphan ad_details (advertiser_id points to deleted advertiser) ──
        r = await session.execute(text("""
            SELECT COUNT(*) FROM ad_details d
            LEFT JOIN advertisers a ON a.id = d.advertiser_id
            WHERE a.id IS NULL
        """))
        orphan_ads = r.scalar() or 0
        print(f"\n=== Orphan ad_details: {orphan_ads} ===")
        if orphan_ads > 0 and not dry_run:
            await session.execute(text("""
                DELETE FROM ad_details WHERE advertiser_id NOT IN (SELECT id FROM advertisers)
            """))
            stats["orphan_ad_details_deleted"] = orphan_ads

        # ── 6. Run advertiser_name_cleaner ──
        print("\n=== Running advertiser name cleaner ===")
        if not dry_run:
            from processor.advertiser_name_cleaner import clean_advertiser_names
            clean_stats = await clean_advertiser_names()
            stats["name_cleaned"] = clean_stats.get("cleaned", 0) + clean_stats.get("merged", 0) + clean_stats.get("deleted", 0)
            print(f"  Cleaned: {clean_stats}")

        if not dry_run:
            await session.commit()

    print(f"\n{'=== DRY RUN ===' if dry_run else '=== DONE ==='}")
    print(f"  House ads deleted: {stats['house_deleted']}")
    print(f"  Garbage names deleted: {stats['garbage_deleted']}")
    print(f"  Orphan campaigns deleted: {stats['orphan_campaigns_deleted']}")
    print(f"  Orphan ad_details deleted: {stats['orphan_ad_details_deleted']}")
    print(f"  Name cleaning: {stats['name_cleaned']}")


if __name__ == "__main__":
    asyncio.run(main())
