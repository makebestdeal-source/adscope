"""오래된 스크린샷/이미지 정리 스크립트.

사용법:
    python scripts/cleanup_images.py --days 90
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processor.image_store import get_image_store


async def main():
    parser = argparse.ArgumentParser(description="Clean up old screenshot images")
    parser.add_argument("--days", type=int, default=90, help="Delete images older than N days")
    args = parser.parse_args()

    store = get_image_store()
    print(f"Image store: {store}")
    print(f"Cleaning up images older than {args.days} days...")

    deleted = await store.cleanup(older_than_days=args.days)
    print(f"Deleted {deleted} files")


if __name__ == "__main__":
    asyncio.run(main())
