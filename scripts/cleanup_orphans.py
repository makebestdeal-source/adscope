"""고아 파일/데이터 정리 스크립트.

DB에 참조 없는 이미지/스크린샷 삭제, 빈 스냅샷 삭제, 오래된 스테이징 정리.

사용법:
    python scripts/cleanup_orphans.py            # dry-run (삭제 안 함, 리포트만)
    python scripts/cleanup_orphans.py --execute   # 실제 삭제 수행
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

from loguru import logger

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)

from database import init_db, async_session
from database.models import AdSnapshot, AdDetail, StagingAd, BrandChannelContent
from sqlalchemy import select, delete, func, text


def _normalize(p: str) -> str:
    """Normalize a path for cross-platform comparison.

    DB stores both backslash (Windows crawler) and forward-slash (social crawler).
    Normalize everything to forward-slash lowercase for comparison.
    """
    return os.path.normpath(p).replace("\\", "/").lower().strip()


def _format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


async def collect_referenced_paths(session) -> set:
    """Collect all file paths referenced in DB (normalized)."""
    referenced = set()

    # 1. ad_details.creative_image_path
    result = await session.execute(
        select(AdDetail.creative_image_path).where(
            AdDetail.creative_image_path.isnot(None),
            AdDetail.creative_image_path != "",
        )
    )
    for (path,) in result.all():
        referenced.add(_normalize(path))

    # 2. ad_details.screenshot_path
    result = await session.execute(
        select(AdDetail.screenshot_path).where(
            AdDetail.screenshot_path.isnot(None),
            AdDetail.screenshot_path != "",
        )
    )
    for (path,) in result.all():
        referenced.add(_normalize(path))

    # 3. ad_snapshots.screenshot_path
    result = await session.execute(
        select(AdSnapshot.screenshot_path).where(
            AdSnapshot.screenshot_path.isnot(None),
            AdSnapshot.screenshot_path != "",
        )
    )
    for (path,) in result.all():
        referenced.add(_normalize(path))

    # 4. brand_channel_contents.extra_data -> local_image_path
    result = await session.execute(
        select(BrandChannelContent.extra_data).where(
            BrandChannelContent.extra_data.isnot(None)
        )
    )
    for (extra,) in result.all():
        if extra is None:
            continue
        # extra_data can be dict (parsed JSON) or string
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except (json.JSONDecodeError, TypeError):
                continue
        if isinstance(extra, dict):
            lip = extra.get("local_image_path")
            if lip:
                referenced.add(_normalize(lip))

    logger.info(f"DB referenced paths: {len(referenced)}")
    return referenced


def _scan_dir(directory: str) -> list:
    """Recursively scan directory and return list of (relative_path, abs_path, size).

    relative_path is relative to project root (cwd), using the directory name
    as prefix (e.g. 'stored_images/youtube/...').
    """
    files = []
    base = Path(_root) / directory
    if not base.exists():
        return files
    for f in base.rglob("*"):
        if f.is_file():
            try:
                size = f.stat().st_size
            except OSError:
                size = 0
            # Build relative path from project root
            try:
                rel = str(f.relative_to(Path(_root)))
            except ValueError:
                rel = str(f)
            files.append((rel, str(f), size))
    return files


async def cleanup_orphan_images(session, referenced: set, dry_run=True) -> dict:
    """Delete images in stored_images/ not referenced in DB."""
    logger.info("--- Scanning stored_images/ for orphans ---")
    files = _scan_dir("stored_images")
    total_count = len(files)
    total_size = sum(s for _, _, s in files)

    orphan_count = 0
    orphan_size = 0
    deleted = []

    for rel, abspath, size in files:
        norm = _normalize(rel)
        if norm not in referenced:
            orphan_count += 1
            orphan_size += size
            if not dry_run:
                try:
                    os.remove(abspath)
                    deleted.append(rel)
                except OSError as e:
                    logger.warning(f"Failed to delete {abspath}: {e}")
            else:
                deleted.append(rel)

    action = "Would delete" if dry_run else "Deleted"
    logger.info(
        f"stored_images/: {total_count} files ({_format_size(total_size)}) total, "
        f"{orphan_count} orphans ({_format_size(orphan_size)})"
    )
    if orphan_count > 0 and orphan_count <= 20:
        for d in deleted:
            logger.info(f"  {action}: {d}")
    elif orphan_count > 20:
        for d in deleted[:10]:
            logger.info(f"  {action}: {d}")
        logger.info(f"  ... and {orphan_count - 10} more")

    return {
        "total_files": total_count,
        "total_size": total_size,
        "orphan_files": orphan_count,
        "orphan_size": orphan_size,
    }


async def cleanup_orphan_screenshots(session, referenced: set, dry_run=True) -> dict:
    """Delete screenshots in screenshots/ not referenced in DB."""
    logger.info("--- Scanning screenshots/ for orphans ---")
    files = _scan_dir("screenshots")
    total_count = len(files)
    total_size = sum(s for _, _, s in files)

    orphan_count = 0
    orphan_size = 0
    deleted = []

    for rel, abspath, size in files:
        norm = _normalize(rel)
        if norm not in referenced:
            orphan_count += 1
            orphan_size += size
            if not dry_run:
                try:
                    os.remove(abspath)
                    deleted.append(rel)
                except OSError as e:
                    logger.warning(f"Failed to delete {abspath}: {e}")
            else:
                deleted.append(rel)

    action = "Would delete" if dry_run else "Deleted"
    logger.info(
        f"screenshots/: {total_count} files ({_format_size(total_size)}) total, "
        f"{orphan_count} orphans ({_format_size(orphan_size)})"
    )
    if orphan_count > 0 and orphan_count <= 20:
        for d in deleted:
            logger.info(f"  {action}: {d}")
    elif orphan_count > 20:
        for d in deleted[:10]:
            logger.info(f"  {action}: {d}")
        logger.info(f"  ... and {orphan_count - 10} more")

    return {
        "total_files": total_count,
        "total_size": total_size,
        "orphan_files": orphan_count,
        "orphan_size": orphan_size,
    }


async def cleanup_empty_snapshots(session, dry_run=True) -> dict:
    """Delete ad_snapshots with 0 associated ad_details."""
    logger.info("--- Finding empty snapshots (0 ad_details) ---")

    # Find snapshot IDs with no details
    subq = select(AdDetail.snapshot_id).distinct()
    result = await session.execute(
        select(AdSnapshot.id).where(AdSnapshot.id.notin_(subq))
    )
    empty_ids = [row[0] for row in result.all()]

    count = len(empty_ids)
    logger.info(f"Empty snapshots: {count}")

    if count > 0 and not dry_run:
        # Delete in batches to avoid huge IN clause
        batch_size = 500
        for i in range(0, len(empty_ids), batch_size):
            batch = empty_ids[i : i + batch_size]
            await session.execute(
                delete(AdSnapshot).where(AdSnapshot.id.in_(batch))
            )
        await session.commit()
        logger.info(f"Deleted {count} empty snapshots")
    elif count > 0:
        logger.info(f"Would delete {count} empty snapshots")
        if count <= 20:
            for sid in empty_ids:
                logger.info(f"  snapshot_id={sid}")
        else:
            for sid in empty_ids[:10]:
                logger.info(f"  snapshot_id={sid}")
            logger.info(f"  ... and {count - 10} more")

    return {"empty_snapshots": count}


async def cleanup_old_staging(session, dry_run=True) -> dict:
    """Delete staging_ads with status in ('approved','rejected','promoted') and processed_at > 30 days."""
    logger.info("--- Finding old staging data ---")

    cutoff = datetime.utcnow() - timedelta(days=30)

    # Count
    result = await session.execute(
        select(func.count(StagingAd.id)).where(
            StagingAd.status.in_(["approved", "rejected", "promoted"]),
            StagingAd.processed_at.isnot(None),
            StagingAd.processed_at < cutoff,
        )
    )
    count = result.scalar() or 0

    logger.info(
        f"Old staging ads (processed > 30 days, status=approved/rejected/promoted): {count}"
    )

    if count > 0 and not dry_run:
        await session.execute(
            delete(StagingAd).where(
                StagingAd.status.in_(["approved", "rejected", "promoted"]),
                StagingAd.processed_at.isnot(None),
                StagingAd.processed_at < cutoff,
            )
        )
        await session.commit()
        logger.info(f"Deleted {count} old staging rows")
    elif count > 0:
        logger.info(f"Would delete {count} old staging rows")

    return {"old_staging": count}


def cleanup_empty_db_file() -> dict:
    """Delete database/adscope.db if it exists and is empty/small (< 4KB).

    The real database is at the project root adscope.db.
    """
    target = Path(_root) / "database" / "adscope.db"
    if target.exists():
        size = target.stat().st_size
        if size < 4096:
            logger.info(
                f"database/adscope.db exists ({size} bytes) - "
                f"this is NOT the real DB (root adscope.db is)"
            )
            return {"empty_db_file": True, "size": size}
        else:
            logger.warning(
                f"database/adscope.db is {_format_size(size)} - "
                f"unexpectedly large, skipping deletion"
            )
            return {"empty_db_file": False, "size": size}
    else:
        logger.info("database/adscope.db does not exist (OK)")
        return {"empty_db_file": False, "size": 0}


async def main():
    dry_run = "--execute" not in sys.argv

    if dry_run:
        logger.info("=== DRY RUN MODE (pass --execute to actually delete) ===")
    else:
        logger.info("=== EXECUTE MODE - files and data WILL be deleted ===")

    await init_db()

    async with async_session() as session:
        # Phase 1: Collect referenced paths
        referenced = await collect_referenced_paths(session)

        # Phase 2: Report initial sizes
        root_db = Path(_root) / "adscope.db"
        if root_db.exists():
            logger.info(f"Main DB (adscope.db): {_format_size(root_db.stat().st_size)}")

        # Phase 3: Run each cleanup
        results = {}

        results["images"] = await cleanup_orphan_images(session, referenced, dry_run)
        results["screenshots"] = await cleanup_orphan_screenshots(
            session, referenced, dry_run
        )
        results["empty_snapshots"] = await cleanup_empty_snapshots(session, dry_run)
        results["old_staging"] = await cleanup_old_staging(session, dry_run)

        # Empty DB file
        db_info = cleanup_empty_db_file()
        if db_info["empty_db_file"]:
            if not dry_run:
                try:
                    os.remove(str(Path(_root) / "database" / "adscope.db"))
                    logger.info("Deleted database/adscope.db (empty file)")
                except OSError as e:
                    logger.warning(f"Failed to delete database/adscope.db: {e}")
            else:
                logger.info("Would delete database/adscope.db (empty file)")
        results["empty_db"] = db_info

        # Phase 4: Summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("CLEANUP SUMMARY")
        logger.info("=" * 60)

        total_freed = 0

        img = results["images"]
        logger.info(
            f"  stored_images/: {img['orphan_files']}/{img['total_files']} orphans "
            f"({_format_size(img['orphan_size'])})"
        )
        total_freed += img["orphan_size"]

        ss = results["screenshots"]
        logger.info(
            f"  screenshots/:   {ss['orphan_files']}/{ss['total_files']} orphans "
            f"({_format_size(ss['orphan_size'])})"
        )
        total_freed += ss["orphan_size"]

        es = results["empty_snapshots"]
        logger.info(f"  Empty snapshots: {es['empty_snapshots']} rows")

        os_ = results["old_staging"]
        logger.info(f"  Old staging:     {os_['old_staging']} rows")

        db = results["empty_db"]
        if db["empty_db_file"]:
            logger.info(f"  database/adscope.db: {db['size']} bytes (empty)")

        logger.info(f"  Total disk space {'to free' if dry_run else 'freed'}: {_format_size(total_freed)}")
        logger.info("=" * 60)

        if dry_run and total_freed > 0:
            logger.info("Run with --execute to perform actual cleanup.")


if __name__ == "__main__":
    asyncio.run(main())
