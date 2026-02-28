"""Deep analysis of Threads.net GraphQL API for ad/partnership data.

Key finding: Threads.net GraphQL returns `paid_partnership` markers
without login. This test extracts actual advertiser data from those
responses.
"""
import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")
os.environ["CRAWLER_WARMUP_SITE_COUNT"] = "0"

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="DEBUG")

from playwright.async_api import async_playwright, Response


async def main():
    print("=" * 60)
    print("  Threads.net GraphQL Deep Analysis")
    print("=" * 60)

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )

    ctx = await browser.new_context(
        viewport={"width": 390, "height": 844},
        user_agent=(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Mobile/15E148 Safari/604.1"
        ),
        is_mobile=True, has_touch=True,
        device_scale_factor=3,
        locale="ko-KR", timezone_id="Asia/Seoul",
    )

    await ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    """)

    page = await ctx.new_page()

    all_graphql: list[dict] = []
    paid_partnership_items: list[dict] = []
    sponsored_items: list[dict] = []

    async def on_response(response: Response):
        url = response.url
        try:
            if response.status != 200:
                return
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return

            if ("threads.net" in url or "threads.com" in url) and "/graphql" in url:
                body = await response.text()
                if not body or len(body) < 100:
                    return

                data = json.loads(body)
                all_graphql.append({
                    "url": url[:200],
                    "size": len(body),
                    "data": data,
                })

                # Recursively search for ad/partnership markers
                _walk_for_ads(data, url, paid_partnership_items, sponsored_items, depth=0)

        except Exception as exc:
            logger.debug(f"Response error: {exc}")

    page.on("response", on_response)

    # Visit Threads pages with more scrolling
    urls = [
        "https://www.threads.net/",
    ]

    for url in urls:
        try:
            print(f"\n  Visiting: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            current = page.url
            print(f"  Final URL: {current[:80]}")

            if "login" in current.lower():
                print("  -> Redirected to login")
                continue

            # Extensive scrolling to load many posts
            await page.wait_for_timeout(3000)
            print("  Scrolling to load more content...")
            for i in range(25):
                await page.evaluate(f"window.scrollBy(0, {600 + i * 50})")
                await page.wait_for_timeout(1200)
                if (i + 1) % 5 == 0:
                    print(f"    Scroll {i+1}/25 - GraphQL responses: {len(all_graphql)}, "
                          f"partnerships: {len(paid_partnership_items)}, "
                          f"sponsored: {len(sponsored_items)}")

            await page.wait_for_timeout(3000)

        except Exception as exc:
            print(f"  Error: {str(exc)[:100]}")

    # Analysis
    print(f"\n{'=' * 60}")
    print(f"  RESULTS")
    print(f"{'=' * 60}")
    print(f"  GraphQL responses: {len(all_graphql)}")
    print(f"  Paid partnership items: {len(paid_partnership_items)}")
    print(f"  Sponsored items: {len(sponsored_items)}")

    # Show paid partnership details
    if paid_partnership_items:
        print(f"\n  PAID PARTNERSHIP ITEMS:")
        for item in paid_partnership_items[:20]:
            print(f"    User: {item.get('username', 'unknown')}")
            print(f"    Text: {item.get('text', '')[:100]}")
            print(f"    Sponsor: {item.get('sponsor', 'N/A')}")
            print(f"    ---")

    # Show sponsored details
    if sponsored_items:
        print(f"\n  SPONSORED ITEMS:")
        for item in sponsored_items[:20]:
            print(f"    User: {item.get('username', 'unknown')}")
            print(f"    Text: {item.get('text', '')[:100]}")
            print(f"    ---")

    # Dump sample GraphQL response structure
    if all_graphql:
        largest = max(all_graphql, key=lambda x: x["size"])
        print(f"\n  Largest GraphQL response: {largest['size']} bytes")
        if isinstance(largest["data"], dict):
            print(f"  Top-level keys: {list(largest['data'].keys())}")
            # Dig into the data structure
            data = largest["data"]
            if "data" in data:
                inner = data["data"]
                if isinstance(inner, dict):
                    print(f"  data keys: {list(inner.keys())}")
                    for k, v in inner.items():
                        if isinstance(v, dict):
                            print(f"    data.{k} keys: {list(v.keys())[:10]}")
                            if "edges" in v:
                                edges = v["edges"]
                                if isinstance(edges, list) and len(edges) > 0:
                                    print(f"    data.{k}.edges: {len(edges)} items")
                                    first = edges[0]
                                    if isinstance(first, dict) and "node" in first:
                                        node = first["node"]
                                        if isinstance(node, dict):
                                            print(f"    data.{k}.edges[0].node keys: {list(node.keys())[:15]}")

    # Save full data for analysis
    output = {
        "graphql_count": len(all_graphql),
        "paid_partnerships": paid_partnership_items,
        "sponsored": sponsored_items,
        "graphql_summaries": [{
            "url": g["url"],
            "size": g["size"],
            "top_keys": list(g["data"].keys()) if isinstance(g["data"], dict) else [],
        } for g in all_graphql],
    }

    # Also save a sample response for analysis
    if all_graphql:
        largest = max(all_graphql, key=lambda x: x["size"])
        output["sample_response"] = largest["data"]

    output_path = Path(_root) / "scripts" / "threads_graphql_analysis.json"
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\n  Full analysis saved to: {output_path}")

    await page.close()
    await ctx.close()
    await browser.close()
    await pw.stop()


def _walk_for_ads(obj, url, partnerships, sponsored, depth=0):
    """Recursively walk JSON for ad/partnership markers."""
    if depth > 20:
        return
    if isinstance(obj, dict):
        # Check for paid_partnership
        has_pp = obj.get("text_post_app_info", {})
        if isinstance(has_pp, dict):
            is_pp = has_pp.get("is_paid_partnership")
            share_info = has_pp.get("share_info", {})
            if is_pp:
                username = ""
                text = ""
                sponsor = ""

                user = obj.get("user") or obj.get("owner") or {}
                if isinstance(user, dict):
                    username = user.get("username", "")

                caption = obj.get("caption") or {}
                if isinstance(caption, dict):
                    text = caption.get("text", "")
                elif isinstance(caption, str):
                    text = caption

                # Look for sponsor info
                sp = has_pp.get("sponsor_user") or has_pp.get("branded_content_sponsor")
                if isinstance(sp, dict):
                    sponsor = sp.get("username", "")

                partnerships.append({
                    "username": username,
                    "text": text[:300],
                    "sponsor": sponsor,
                    "source_url": url[:100],
                })

        # Check direct ad flags
        if obj.get("is_ad") or obj.get("is_sponsored"):
            username = ""
            text = ""
            user = obj.get("user") or obj.get("owner") or {}
            if isinstance(user, dict):
                username = user.get("username", "")
            caption = obj.get("caption") or {}
            if isinstance(caption, dict):
                text = caption.get("text", "")

            sponsored.append({
                "username": username,
                "text": text[:300],
                "source_url": url[:100],
            })

        # Also check for paid_partnership flag at node level
        if obj.get("is_paid_partnership"):
            username = ""
            text = ""
            user = obj.get("user") or obj.get("owner") or {}
            if isinstance(user, dict):
                username = user.get("username", "")
            caption = obj.get("caption") or {}
            if isinstance(caption, dict):
                text = caption.get("text", "")

            partnerships.append({
                "username": username,
                "text": text[:300],
                "sponsor": "",
                "source_url": url[:100],
                "flag": "is_paid_partnership",
            })

        for v in obj.values():
            _walk_for_ads(v, url, partnerships, sponsored, depth + 1)

    elif isinstance(obj, list):
        for item in obj:
            _walk_for_ads(item, url, partnerships, sponsored, depth + 1)


if __name__ == "__main__":
    asyncio.run(main())
