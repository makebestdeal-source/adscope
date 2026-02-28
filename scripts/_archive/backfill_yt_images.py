"""YouTube Ads 이미지 백필 — TC 광고주 페이지 RPC에서 simgad 이미지 매칭 후 다운로드."""
import asyncio
import io
import os
import re
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from collections import defaultdict

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx
from PIL import Image

DB_PATH = "adscope.db"
TC_URL = "https://adstransparency.google.com/"


def get_targets() -> dict[str, list[tuple[int, str]]]:
    """광고주별로 이미지 없는 YT ads의 (ad_id, creative_id) 목록 반환."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    rows = c.execute("""
        SELECT d.id, a.name, d.extra_data
        FROM ad_details d
        JOIN ad_snapshots s ON d.snapshot_id = s.id
        LEFT JOIN advertisers a ON d.advertiser_id = a.id
        WHERE s.channel = 'youtube_ads'
          AND (d.creative_image_path IS NULL OR d.creative_image_path = '')
          AND d.extra_data IS NOT NULL AND d.extra_data != ''
    """).fetchall()
    conn.close()

    # advertiser_name -> [(ad_id, creative_id), ...]
    by_adv: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for r in rows:
        try:
            ed = json.loads(r[2])
            cid = ed.get("creative_id", "")
            if cid:
                by_adv[r[1] or "unknown"].append((r[0], cid))
        except Exception:
            pass
    return dict(by_adv)


def _extract_image_urls(rpc_data: list[dict]) -> dict[str, str]:
    """RPC 응답에서 creative_id -> image_url 매핑 추출."""
    mapping: dict[str, str] = {}
    for data in rpc_data:
        for item in data.get("1", []):
            if not isinstance(item, dict):
                continue
            cid = item.get("2", "")
            ri = item.get("3", {})
            if isinstance(ri, dict):
                inner_3 = ri.get("3", {})
                if isinstance(inner_3, dict):
                    html_str = inner_3.get("2", "")
                    if isinstance(html_str, str):
                        m = re.search(r'src="(https?://[^"]+)"', html_str)
                        if m:
                            mapping[cid] = m.group(1)
    return mapping


async def download_image(client: httpx.AsyncClient, url: str, ad_id: int, out_dir: Path) -> str | None:
    """이미지 다운로드 -> WebP 변환 -> 저장 경로 반환."""
    try:
        resp = await client.get(url, timeout=15)
        if resp.status_code != 200 or len(resp.content) < 500:
            return None

        buf = io.BytesIO(resp.content)
        img = Image.open(buf)
        if img.mode == "RGBA":
            img = img.convert("RGB")
        if img.width > 600:
            ratio = 600 / img.width
            img = img.resize((600, int(img.height * ratio)), Image.LANCZOS)

        fname = f"yt_{ad_id}.webp"
        fpath = out_dir / fname
        img.save(str(fpath), "WEBP", quality=80)
        return str(fpath).replace("\\", "/")
    except Exception:
        return None


async def process_advertiser(
    browser_ctx, adv_name: str, ads: list[tuple[int, str]],
    out_dir: Path, conn: sqlite3.Connection, stats: dict
):
    """TC에서 광고주 검색 -> RPC 캡처 -> creative_id 매칭 -> 이미지 다운로드."""
    rpc_data: list[dict] = []
    page = await browser_ctx.new_page()

    async def on_resp(resp):
        try:
            if resp.status == 200 and "json" in resp.headers.get("content-type", ""):
                if "SearchCreatives" in resp.url:
                    data = await resp.json()
                    rpc_data.append(data)
                elif "SearchSuggestions" in resp.url:
                    data = await resp.json()
                    # SearchSuggestions에서 광고주 ID 추출
                    rpc_data.append({"_suggestions": data})
        except Exception:
            pass

    page.on("response", on_resp)

    try:
        # 1) TC 메인 페이지
        await page.goto(TC_URL + "?region=KR&platform=YOUTUBE", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)

        # 2) 검색
        search_name = adv_name.replace("(주)", "").replace("(주)", "").strip()[:20]
        selectors = ["search-input input.input-area", "search-input input", "input.input-area"]
        search_ok = False
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    await loc.first.click()
                    await page.wait_for_timeout(300)
                    await loc.first.type(search_name, delay=60)
                    await page.wait_for_timeout(3000)
                    search_ok = True
                    break
            except Exception:
                continue

        if not search_ok:
            stats["search_fail"] += 1
            return

        # 3) Suggestions에서 광고주 ID 추출
        adv_id = None
        for data in rpc_data:
            if "_suggestions" in data:
                sug = data["_suggestions"]
                for item in sug.get("1", []):
                    info = item.get("1", {})
                    if isinstance(info, dict):
                        name = info.get("1", "")
                        # 이름이 유사하면 사용
                        if search_name.lower() in name.lower() or name.lower() in adv_name.lower():
                            adv_id = info.get("2")
                            break
                if adv_id:
                    break

        if not adv_id:
            # 첫 번째 suggestion 사용
            for data in rpc_data:
                if "_suggestions" in data:
                    sug = data["_suggestions"]
                    items = sug.get("1", [])
                    if items:
                        info = items[0].get("1", {})
                        adv_id = info.get("2")
                    break

        if not adv_id:
            stats["no_adv_id"] += 1
            return

        # 4) 광고주 페이지 방문 -> RPC에서 크리에이티브 수집
        rpc_data.clear()
        adv_url = f"{TC_URL}advertiser/{adv_id}?region=KR"
        await page.goto(adv_url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(6000)

        # 스크롤 다운으로 더 많은 크리에이티브 로드
        for _ in range(3):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

        # 5) RPC에서 creative_id -> image_url 매핑 추출
        image_map = _extract_image_urls(rpc_data)

        if not image_map:
            stats["no_images"] += 1
            return

        # 6) 매칭 + 다운로드
        matched = 0
        cid_set = {cid for _, cid in ads}

        async with httpx.AsyncClient(follow_redirects=True) as client:
            for ad_id, cid in ads:
                img_url = image_map.get(cid)
                if not img_url:
                    continue
                matched += 1
                saved = await download_image(client, img_url, ad_id, out_dir)
                if saved:
                    # DB에 image_url도 함께 저장
                    conn.execute(
                        "UPDATE ad_details SET creative_image_path = ? WHERE id = ?",
                        (saved, ad_id),
                    )
                    # extra_data에 image_url 추가
                    try:
                        row = conn.execute("SELECT extra_data FROM ad_details WHERE id = ?", (ad_id,)).fetchone()
                        if row and row[0]:
                            ed = json.loads(row[0])
                            ed["image_url"] = img_url
                            conn.execute(
                                "UPDATE ad_details SET extra_data = ? WHERE id = ?",
                                (json.dumps(ed, ensure_ascii=False), ad_id),
                            )
                    except Exception:
                        pass
                    stats["ok"] += 1
                else:
                    stats["dl_fail"] += 1

        stats["matched"] += matched
        stats["unmatched"] += len(ads) - matched
        conn.commit()

    except Exception as e:
        stats["error"] += 1
        stats["last_error"] = str(e)[:80]
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def main():
    targets = get_targets()
    total_ads = sum(len(v) for v in targets.values())
    print(f"Advertisers: {len(targets)}, Total ads needing images: {total_ads}")
    if not targets:
        return

    from playwright.async_api import async_playwright

    date_dir = datetime.now().strftime("%Y%m%d")
    out_dir = Path("stored_images/youtube_ads") / date_dir / "creative"
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    stats = {
        "ok": 0, "dl_fail": 0, "matched": 0, "unmatched": 0,
        "search_fail": 0, "no_adv_id": 0, "no_images": 0,
        "error": 0, "last_error": "",
    }

    # 동일 광고주의 다른 이름 변형을 합치기 (삼성생명보험, 삼성생명보험(주) -> 합침)
    merged: dict[str, list[tuple[int, str]]] = {}
    for name, ads in targets.items():
        # 기본 이름 (괄호 제거)
        base = re.sub(r"\s*\(.*?\)\s*", "", name or "").strip()
        if base not in merged:
            merged[base] = []
        merged[base].extend(ads)

    print(f"Merged to {len(merged)} unique advertisers")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 1200, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )

        for i, (adv_name, ads) in enumerate(merged.items()):
            print(f"\n[{i+1}/{len(merged)}] {adv_name} ({len(ads)} ads)")
            await process_advertiser(ctx, adv_name, ads, out_dir, conn, stats)
            print(
                f"  ok={stats['ok']} matched={stats['matched']} "
                f"unmatched={stats['unmatched']} dl_fail={stats['dl_fail']}"
            )
            # Rate limit
            await asyncio.sleep(2)

        await browser.close()

    conn.commit()
    conn.close()

    print(f"\n=== Done ===")
    print(f"Downloaded: {stats['ok']}")
    print(f"Matched: {stats['matched']} / Unmatched: {stats['unmatched']}")
    print(f"DL failures: {stats['dl_fail']}")
    print(f"Search fail: {stats['search_fail']}, No adv ID: {stats['no_adv_id']}")
    print(f"No images: {stats['no_images']}, Errors: {stats['error']}")
    if stats["last_error"]:
        print(f"Last error: {stats['last_error']}")


if __name__ == "__main__":
    asyncio.run(main())
