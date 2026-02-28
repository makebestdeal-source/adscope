"""Backfill Instagram thumbnails from shortcode /media/ endpoint.

Uses Instagram's public /p/{shortcode}/media/?size=l redirect to get fresh CDN URLs.
Downloads immediately and saves as local WebP.
Updates brand_channel_contents.extra_data with local_image_path.
"""

import asyncio
import io
import json
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import aiohttp
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
STORE_DIR = ROOT / "stored_images" / "instagram"
DB_PATH = ROOT / "adscope.db"


async def download_via_shortcode(
    session: aiohttp.ClientSession,
    shortcode: str,
    dest: Path,
) -> bool:
    """Download IG thumbnail via /p/{shortcode}/media/?size=l redirect."""
    url = f"https://www.instagram.com/p/{shortcode}/media/?size=l"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                return False
            data = await resp.read()
            if len(data) < 500:
                return False

        img = Image.open(io.BytesIO(data))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")

        # Resize thumbnails to max 600px for storage efficiency
        max_dim = 600
        if img.width > max_dim or img.height > max_dim:
            ratio = min(max_dim / img.width, max_dim / img.height)
            img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="WebP", quality=75, method=4)

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(buf.getvalue())
        return True
    except Exception:
        return False


async def main():
    import aiosqlite

    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row

    rows = await db.execute_fetchall(
        """SELECT id, content_id, thumbnail_url, extra_data, discovered_at
           FROM brand_channel_contents
           WHERE platform = 'instagram'
             AND content_id IS NOT NULL
             AND content_id != ''
        """
    )
    print(f"Total IG content: {len(rows)}")

    # Filter already downloaded
    to_download = []
    already_done = 0
    for row in rows:
        ed = row["extra_data"]
        if ed:
            try:
                d = json.loads(ed) if isinstance(ed, str) else ed
                lp = d.get("local_image_path")
                if lp and os.path.exists(lp):
                    already_done += 1
                    continue
            except (json.JSONDecodeError, TypeError):
                pass
        to_download.append(row)

    print(f"Already done: {already_done}, To download: {len(to_download)}")
    if not to_download:
        await db.close()
        return

    BATCH = 10
    success = 0
    failed = 0

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "image/*,*/*",
    }
    connector = aiohttp.TCPConnector(limit=5, ssl=False)

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        for i in range(0, len(to_download), BATCH):
            batch = to_download[i : i + BATCH]
            coros = []
            dests = []

            for row in batch:
                sc = row["content_id"]
                disc = row["discovered_at"]
                date_str = str(disc)[:10].replace("-", "") if disc else "unknown"
                dest = STORE_DIR / date_str / "thumbnail" / f"{sc}.webp"
                dests.append(dest)

                if dest.exists():
                    coros.append(asyncio.coroutine(lambda: True)() if False else asyncio.sleep(0))
                else:
                    coros.append(download_via_shortcode(session, sc, dest))

            results = await asyncio.gather(*coros, return_exceptions=True)

            for j, row in enumerate(batch):
                dest = dests[j]
                ok = dest.exists()

                if ok:
                    ed = row["extra_data"]
                    try:
                        d = json.loads(ed) if (isinstance(ed, str) and ed) else {}
                    except (json.JSONDecodeError, TypeError):
                        d = {}
                    d["local_image_path"] = str(dest)
                    await db.execute(
                        "UPDATE brand_channel_contents SET extra_data = ? WHERE id = ?",
                        (json.dumps(d, ensure_ascii=False), row["id"]),
                    )
                    success += 1
                else:
                    failed += 1

            await db.commit()

            # Rate limit: 1 sec delay between batches
            await asyncio.sleep(1.0)

            done = i + len(batch)
            pct = done / len(to_download) * 100
            print(f"  [{done}/{len(to_download)}] {pct:.0f}% | ok={success} fail={failed}")

    await db.close()
    print(f"\nDone! success={success}, failed={failed}")


if __name__ == "__main__":
    asyncio.run(main())
