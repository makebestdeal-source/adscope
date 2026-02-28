"""광고 소재 이미지 백필 스크립트.

extra_data에 image_url이 있지만 creative_image_path가 없는 광고를 찾아
이미지를 다운로드하고 WebP로 변환하여 stored_images/에 저장.
"""

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "adscope.db"
STORED_DIR = ROOT / "stored_images"


async def backfill():
    from processor.image_store import get_image_store

    store = get_image_store()
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # FB/IG 광고 중 creative_image_path 없고 extra_data에 image_url 있는 건
    rows = c.execute("""
        SELECT d.id, d.extra_data, s.channel
        FROM ad_details d
        JOIN ad_snapshots s ON d.snapshot_id = s.id
        WHERE (d.creative_image_path IS NULL OR d.creative_image_path = '')
          AND d.extra_data IS NOT NULL
          AND d.extra_data != ''
          AND s.channel IN ('facebook', 'instagram', 'naver_da', 'kakao_da', 'youtube_ads', 'google_search_ads', 'naver_search', 'naver_shopping', 'tiktok_ads', 'google_gdn')
    """).fetchall()

    print(f"Found {len(rows)} ads with missing images and extra_data")

    downloaded = 0
    skipped = 0
    failed = 0

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for ad_id, extra_raw, channel in rows:
            try:
                data = json.loads(extra_raw) if isinstance(extra_raw, str) else extra_raw
            except (json.JSONDecodeError, TypeError):
                skipped += 1
                continue

            # image URL 추출 (여러 키 시도)
            img_url = None
            for key in ["image_url", "original_image_url", "preview_url", "banner_image",
                        "cover_url", "full_picture", "picture", "product_image",
                        "thumbnail_url", "video_thumbnail", "creative_url", "media_url"]:
                val = data.get(key)
                if val and isinstance(val, str) and val.startswith("http"):
                    img_url = val
                    break

            if not img_url:
                skipped += 1
                continue

            try:
                resp = await client.get(img_url)
                if resp.status_code != 200:
                    failed += 1
                    continue

                content = resp.content
                if len(content) < 500:  # too small, probably error page
                    failed += 1
                    continue

                # 임시 파일에 저장 후 image_store로 변환
                ext = ".jpg"
                if content[:4] == b"\x89PNG":
                    ext = ".png"
                elif content[:4] == b"RIFF":
                    ext = ".webp"
                elif content[:3] == b"GIF":
                    ext = ".gif"

                with tempfile.NamedTemporaryFile(suffix=ext, delete=False, dir=str(ROOT / "screenshots")) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name

                stored_path = await store.save(tmp_path, channel, "creative")

                # DB 업데이트
                c.execute(
                    "UPDATE ad_details SET creative_image_path = ? WHERE id = ?",
                    (stored_path, ad_id),
                )
                downloaded += 1

                # 임시 파일 삭제
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

                if downloaded % 50 == 0:
                    conn.commit()
                    print(f"  Progress: {downloaded} downloaded, {failed} failed, {skipped} skipped")

            except Exception as e:
                failed += 1
                continue

    conn.commit()
    conn.close()

    print(f"\n=== Image Backfill Complete ===")
    print(f"  Downloaded: {downloaded}")
    print(f"  Failed: {failed}")
    print(f"  Skipped (no URL): {skipped}")


if __name__ == "__main__":
    asyncio.run(backfill())
