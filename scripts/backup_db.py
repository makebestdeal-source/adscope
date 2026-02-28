"""Daily SQLite backup with rotation. Run standalone or from scheduler."""

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DB_PATH = Path(os.getenv("DB_PATH", "adscope.db"))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "backups"))
MAX_BACKUPS = int(os.getenv("MAX_BACKUPS", "14"))


def backup_db():
    """Create a timestamped backup of the SQLite database."""
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        return None

    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"adscope_{ts}.db"

    # Use SQLite-safe copy (ensure WAL is checkpointed)
    try:
        import sqlite3
        src_conn = sqlite3.connect(str(DB_PATH))
        dst_conn = sqlite3.connect(str(dest))
        src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()
    except Exception:
        # Fallback to file copy
        shutil.copy2(DB_PATH, dest)

    size_mb = dest.stat().st_size / (1024 * 1024)
    print(f"Backup created: {dest} ({size_mb:.1f} MB)")

    # Rotate old backups
    backups = sorted(BACKUP_DIR.glob("adscope_*.db"), reverse=True)
    for old in backups[MAX_BACKUPS:]:
        old.unlink()
        print(f"Removed old backup: {old.name}")

    return str(dest)


if __name__ == "__main__":
    backup_db()
