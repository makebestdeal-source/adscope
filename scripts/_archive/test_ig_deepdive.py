"""Deep-dive into promising Instagram alternative approaches.

Focus on:
1. Facebook Audience Network on Korean sites - extract actual ad data
2. Threads.net API responses - check for sponsored content markers
3. Instagram embeds GraphQL - parse the captured responses
4. Korean publisher sites with Meta pixel - extract advertiser data
"""
import asyncio
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

os.environ["CRAWLER_WARMUP_SITE_COUNT"] = "0"

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO")

from playwright.async_api import async_playwright, Response, Request, Page


async def create_browser():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--disable-infobars",
        ],
    )
    return pw, browser


async def create_context(browser, mobile=True):
    if mobile:
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
    else:
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            locale="ko-KR", timezone_id="Asia/Seoul",
        )

    await ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', {
            get: () => ['ko-KR', 'ko', 'en-US', 'en']
        });
        if (!window.chrome) window.chrome = {};
        if (!window.chrome.runtime) window.chrome.runtime = {
            connect: () => {}, sendMessage: () => {}
        };
    """)
    return ctx


# Ad infra domains that are NOT real advertisers
_AD_INFRA_DOMAINS = {
    "facebook.com", "facebook.net", "fbcdn.net", "fb.com",
    "instagram.com", "meta.com",
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "gstatic.com", "googleapis.com", "google.com", "google-analytics.com",
    "google.co.kr", "googletagmanager.com", "googletagservices.com",
    "criteo.com", "criteo.net", "bidswitch.net", "adsrvr.org",
    "amazon-adsystem.com", "taboola.com", "outbrain.com",
    "safeframe.googlesyndication.com",
}


def _is_ad_infra(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
        return any(d in host for d in _AD_INFRA_DOMAINS)
    except Exception:
        return False


def _extract_landing(raw_url: str) -> str | None:
    """Extract real landing URL from tracking redirect."""
    if not raw_url:
        return None
    try:
        parsed = urlparse(raw_url)
        query = parse_qs(parsed.query)
        for key in ("u", "url", "next", "redirect_url", "dl", "r", "adurl"):
            vals = query.get(key)
            if vals:
                candidate = unquote(vals[0]).strip()
                if candidate.startswith("http") and not _is_ad_infra(candidate):
                    return candidate
        return raw_url if raw_url.startswith("http") else None
    except Exception:
        return raw_url


# ================================================================
# DEEP DIVE 1: Audience Network on Korean sites
# ================================================================

async def deepdive_audience_network(browser) -> dict:
    """Extract actual advertiser data from Korean sites with FB/Meta ads."""
    print("\n" + "=" * 60)
    print("DEEP DIVE: Facebook Audience Network on Korean Sites")
    print("=" * 60)

    ctx = await create_context(browser, mobile=True)
    page = await ctx.new_page()

    extracted_ads: list[dict] = []
    fb_pixel_data: list[dict] = []
    meta_tracking: list[dict] = []
    landing_urls: list[str] = []

    async def on_response(response: Response):
        url = response.url
        try:
            # 1) an.facebook.com - Audience Network ad delivery
            if "an.facebook.com" in url:
                try:
                    ct = response.headers.get("content-type", "")
                    if response.status == 200 and ("json" in ct or "javascript" in ct):
                        body = await response.text()
                        if body:
                            logger.debug(f"AN response ({len(body)} chars): {url[:80]}")
                            # Try JSON parse
                            try:
                                data = json.loads(body)
                                extracted_ads.append({
                                    "source": "an.facebook.com",
                                    "data": data,
                                    "url": url[:200],
                                })
                            except json.JSONDecodeError:
                                # JS response - look for ad data patterns
                                _parse_js_for_ads(body, url, extracted_ads)
                except Exception:
                    pass

            # 2) Facebook tracking pixel - contains advertiser info
            if "facebook.com/tr" in url or "pixel.facebook.com" in url:
                try:
                    parsed = urlparse(url)
                    params = parse_qs(parsed.query)
                    pixel_id = params.get("id", [""])[0]
                    ev = params.get("ev", [""])[0]
                    dl_url = params.get("dl", [""])[0]

                    if pixel_id or dl_url:
                        entry = {
                            "pixel_id": pixel_id,
                            "event": ev,
                            "dl_url": dl_url,
                            "referer": params.get("rl", [""])[0],
                        }
                        # Extract content data
                        for k in params:
                            if k.startswith("cd["):
                                entry[k] = params[k][0]
                        fb_pixel_data.append(entry)

                        # Extract landing URL
                        if dl_url and not _is_ad_infra(dl_url):
                            landing_urls.append(dl_url)
                except Exception:
                    pass

            # 3) connect.facebook.net - SDK with ad config
            if "connect.facebook.net" in url:
                try:
                    if response.status == 200:
                        ct = response.headers.get("content-type", "")
                        if "javascript" in ct:
                            body = await response.text()
                            if body and len(body) < 500000:
                                # Look for fbPixelId or ad placement config
                                pixel_ids = re.findall(
                                    r'["\'](\d{15,16})["\']', body[:5000]
                                )
                                if pixel_ids:
                                    meta_tracking.append({
                                        "source": "connect.facebook.net",
                                        "pixel_ids": list(set(pixel_ids))[:5],
                                    })
                except Exception:
                    pass

            # 4) Google Ad Manager / DFP ad responses (may contain Meta advertiser data)
            if "securepubads.g.doubleclick.net/gampad/ads" in url:
                try:
                    if response.status == 200:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct or "javascript" in ct:
                            body = await response.text()
                            if body:
                                _parse_dfp_for_meta_ads(body, url, extracted_ads)
                except Exception:
                    pass

            # 5) Redirect tracking with landing URLs
            if response.status in (301, 302, 303, 307, 308):
                location = response.headers.get("location", "")
                if location.startswith("http") and not _is_ad_infra(location):
                    landing_urls.append(location)

        except Exception:
            pass

    def on_request(request: Request):
        url = request.url
        # Capture outgoing ad tracking requests
        if "facebook.com/tr" in url or "/tr?" in url:
            landing = _extract_landing(url)
            if landing and not _is_ad_infra(landing):
                landing_urls.append(landing)

    page.on("response", on_response)
    page.on("request", on_request)

    # Korean sites to visit - selected for Meta pixel usage
    korean_sites = [
        ("https://m.wikitree.co.kr/", "wikitree"),
        ("https://m.insight.co.kr/", "insight"),
        ("https://www.instiz.net/", "instiz"),
        ("https://theqoo.net/", "theqoo"),
        ("https://www.ppomppu.co.kr/zboard/", "ppomppu"),
        ("https://www.fmkorea.com/", "fmkorea"),
        ("https://m.ruliweb.com/", "ruliweb"),
        ("https://pann.nate.com/", "pann"),
        ("https://www.clien.net/service/", "clien"),
        ("https://biz.chosun.com/", "chosun_biz"),
        ("https://m.mk.co.kr/", "mk"),
        ("https://m.hankyung.com/", "hankyung"),
    ]

    sites_visited = 0
    for site_url, site_name in korean_sites:
        try:
            print(f"\n  [{site_name}] {site_url}")
            resp = await page.goto(
                site_url, wait_until="domcontentloaded", timeout=15000,
            )
            sites_visited += 1

            if resp:
                print(f"    Status: {resp.status}")

            await page.wait_for_timeout(3000)

            # Scroll extensively to trigger ads
            for i in range(8):
                await page.evaluate(f"window.scrollBy(0, {500 + i * 150})")
                await page.wait_for_timeout(1000)

            # Check for article links and visit one (more ad exposure)
            try:
                article_link = await page.evaluate("""() => {
                    const links = document.querySelectorAll('a[href*="article"], a[href*="view"]');
                    const valid = Array.from(links).filter(a => {
                        const t = (a.textContent || '').trim();
                        return t.length > 10 && t.length < 200;
                    });
                    return valid.length > 0 ? valid[0].href : null;
                }""")
                if article_link:
                    print(f"    Visiting article: {article_link[:60]}...")
                    await page.goto(
                        article_link, wait_until="domcontentloaded", timeout=12000,
                    )
                    await page.wait_for_timeout(2000)
                    for i in range(5):
                        await page.evaluate(f"window.scrollBy(0, {400 + i * 100})")
                        await page.wait_for_timeout(800)
            except Exception:
                pass

            await page.wait_for_timeout(1500)

        except Exception as exc:
            print(f"    Error: {str(exc)[:100]}")

    # Process results
    print(f"\n{'=' * 40}")
    print(f"  AUDIENCE NETWORK RESULTS")
    print(f"{'=' * 40}")
    print(f"  Sites visited: {sites_visited}")
    print(f"  AN responses: {len(extracted_ads)}")
    print(f"  FB pixel events: {len(fb_pixel_data)}")
    print(f"  Meta tracking entries: {len(meta_tracking)}")
    print(f"  Landing URLs: {len(landing_urls)}")

    # Deduplicate and filter landing URLs
    unique_landings = set()
    for url in landing_urls:
        try:
            domain = urlparse(url).netloc.lower()
            if domain and not any(d in domain for d in _AD_INFRA_DOMAINS):
                unique_landings.add(url)
        except Exception:
            pass

    print(f"  Unique non-infra landing URLs: {len(unique_landings)}")
    for url in list(unique_landings)[:10]:
        print(f"    - {url[:100]}")

    # Show pixel data
    if fb_pixel_data:
        print(f"\n  Facebook Pixel Events:")
        for p in fb_pixel_data[:10]:
            print(f"    pixel={p.get('pixel_id', '?')[:10]} "
                  f"event={p.get('event', '?')} "
                  f"dl={p.get('dl_url', '?')[:60]}")

    if meta_tracking:
        print(f"\n  Meta Tracking SDK:")
        for t in meta_tracking[:5]:
            print(f"    {t}")

    # Build advertiser list from pixel data
    advertisers = set()
    for p in fb_pixel_data:
        dl = p.get("dl_url", "")
        if dl and not _is_ad_infra(dl):
            try:
                domain = urlparse(dl).netloc
                if domain:
                    advertisers.add(domain)
            except Exception:
                pass

    for url in unique_landings:
        try:
            domain = urlparse(url).netloc
            if domain:
                advertisers.add(domain)
        except Exception:
            pass

    print(f"\n  Unique advertiser domains: {len(advertisers)}")
    for adv in list(advertisers)[:15]:
        print(f"    - {adv}")

    await page.close()
    await ctx.close()

    return {
        "approach": "audience_network_deepdive",
        "sites_visited": sites_visited,
        "an_responses": len(extracted_ads),
        "pixel_events": len(fb_pixel_data),
        "landing_urls": len(unique_landings),
        "advertiser_domains": list(advertisers),
    }


# ================================================================
# DEEP DIVE 2: Threads.net API capture
# ================================================================

async def deepdive_threads(browser) -> dict:
    """Deep analysis of Threads.net API responses for ad markers."""
    print("\n" + "=" * 60)
    print("DEEP DIVE: Threads.net API Responses")
    print("=" * 60)

    ctx = await create_context(browser, mobile=True)
    page = await ctx.new_page()

    api_responses: list[dict] = []
    all_json_data: list[dict] = []

    async def on_response(response: Response):
        url = response.url
        try:
            if response.status != 200:
                return
            ct = response.headers.get("content-type", "")
            if "json" not in ct and "javascript" not in ct:
                return

            # Capture all API responses from threads.net
            if ("threads.net" in url or "threads.com" in url) and (
                "/api/" in url or "/graphql" in url or "query" in url
            ):
                body = await response.text()
                if not body:
                    return

                api_responses.append({
                    "url": url[:200],
                    "size": len(body),
                })

                try:
                    data = json.loads(body)
                    all_json_data.append(data)

                    # Check for ad markers
                    data_str = json.dumps(data)
                    ad_markers = [
                        "is_ad", "is_sponsored", "sponsor",
                        "ad_id", "promoted", "boosted",
                        "paid_partnership", "branded_content",
                    ]
                    found = [m for m in ad_markers if m in data_str.lower()]
                    if found:
                        print(f"    *** AD MARKERS FOUND: {found} in {url[:60]}")

                    # Look for post data structure
                    if "threads" in data_str.lower()[:200] or "text_post" in data_str.lower()[:500]:
                        # Check if any thread items have ad markers
                        _check_threads_items(data, url)

                except json.JSONDecodeError:
                    pass

        except Exception:
            pass

    page.on("response", on_response)

    # Visit Threads pages
    urls = [
        "https://www.threads.net/",
        "https://www.threads.net/search?q=samsung&serp_type=default",
        "https://www.threads.net/search?q=nike&serp_type=default",
        "https://www.threads.net/search?q=korea+shopping&serp_type=default",
    ]

    for url in urls:
        try:
            print(f"\n  Visiting: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            current = page.url.lower()
            print(f"    Final: {current[:80]}")

            if "login" in current:
                print(f"    -> Redirected to login")
                continue

            await page.wait_for_timeout(3000)

            # Extensive scrolling
            for i in range(15):
                await page.evaluate(f"window.scrollBy(0, {500 + i * 80})")
                await page.wait_for_timeout(800)

            await page.wait_for_timeout(2000)

        except Exception as exc:
            print(f"    Error: {str(exc)[:100]}")

    print(f"\n  API responses captured: {len(api_responses)}")
    for resp in api_responses[:10]:
        print(f"    - {resp['url'][:80]} ({resp['size']} bytes)")

    print(f"  JSON data objects: {len(all_json_data)}")

    # Analyze JSON structure
    if all_json_data:
        print(f"\n  JSON structure analysis:")
        for i, data in enumerate(all_json_data[:5]):
            if isinstance(data, dict):
                keys = list(data.keys())[:10]
                print(f"    [{i}] Top keys: {keys}")

    await page.close()
    await ctx.close()

    return {
        "approach": "threads_deepdive",
        "api_responses": len(api_responses),
        "json_data": len(all_json_data),
    }


# ================================================================
# DEEP DIVE 3: Instagram embed GraphQL analysis
# ================================================================

async def deepdive_embeds(browser) -> dict:
    """Deep analysis of Instagram embed GraphQL responses."""
    print("\n" + "=" * 60)
    print("DEEP DIVE: Instagram Embed GraphQL Responses")
    print("=" * 60)

    ctx = await create_context(browser, mobile=False)
    page = await ctx.new_page()

    graphql_responses: list[dict] = []
    embed_data: list[dict] = []

    async def on_response(response: Response):
        url = response.url
        try:
            if response.status != 200:
                return
            ct = response.headers.get("content-type", "")

            # Capture Instagram GraphQL/API responses
            if ("instagram.com" in url and
                    ("/graphql/" in url or "/api/v1/" in url)):
                if "json" in ct:
                    body = await response.text()
                    if not body:
                        return

                    graphql_responses.append({
                        "url": url[:200],
                        "size": len(body),
                    })

                    try:
                        data = json.loads(body)
                        data_str = json.dumps(data)

                        # Check for ad/sponsor markers
                        ad_markers = [
                            '"is_ad"', '"is_sponsored"', '"ad_id"',
                            '"sponsor"', '"branded_content"',
                            '"paid_partnership"',
                        ]
                        found = [m for m in ad_markers if m in data_str]
                        if found:
                            print(f"    *** AD MARKERS: {found} in {url[:60]}")

                        # Extract media shortcode data
                        if "shortcode_media" in data_str or "xdt_shortcode_media" in data_str:
                            embed_data.append({
                                "url": url[:200],
                                "has_ad_markers": bool(found),
                                "keys": list(data.keys())[:10] if isinstance(data, dict) else [],
                            })

                    except json.JSONDecodeError:
                        pass

            # Also capture embed-specific endpoints
            if "instagram.com" in url and "embed" in url:
                if "json" in ct or "javascript" in ct:
                    try:
                        body = await response.text()
                        if body and len(body) > 100:
                            graphql_responses.append({
                                "url": url[:200],
                                "size": len(body),
                                "type": "embed_resource",
                            })
                    except Exception:
                        pass

        except Exception:
            pass

    page.on("response", on_response)

    # First, get real shortcodes from a public profile
    print("  Getting shortcodes from public profiles...")
    shortcodes = []
    try:
        await page.goto(
            "https://www.instagram.com/samsung/",
            wait_until="domcontentloaded", timeout=15000,
        )
        await page.wait_for_timeout(2000)
        # Dismiss popups
        try:
            await page.evaluate("""() => {
                const overlay = document.querySelector('div[class*="RnEpo"]');
                if (overlay) overlay.remove();
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    if (/Not Now|Close/i.test(b.textContent)) b.click();
                }
            }""")
        except Exception:
            pass

        await page.wait_for_timeout(1000)
        links = await page.evaluate("""() => {
            const anchors = document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]');
            return Array.from(anchors).slice(0, 10).map(a => {
                const parts = a.href.split('/');
                const idx = parts.indexOf('p') !== -1 ? parts.indexOf('p') : parts.indexOf('reel');
                return { type: idx !== -1 ? parts[idx] : 'p', code: parts[idx + 1] };
            }).filter(x => x.code && x.code.length > 5);
        }""")
        if links:
            shortcodes = links
            print(f"  Found {len(shortcodes)} shortcodes")
    except Exception as exc:
        print(f"  Shortcode discovery error: {str(exc)[:80]}")

    # Also get from other brands
    for brand in ["nike", "adidas", "cocacola"]:
        try:
            await page.goto(
                f"https://www.instagram.com/{brand}/",
                wait_until="domcontentloaded", timeout=10000,
            )
            await page.wait_for_timeout(1500)
            try:
                await page.evaluate("""() => {
                    const overlay = document.querySelector('div[class*="RnEpo"]');
                    if (overlay) overlay.remove();
                    const btns = document.querySelectorAll('button');
                    for (const b of btns) {
                        if (/Not Now|Close/i.test(b.textContent)) b.click();
                    }
                }""")
            except Exception:
                pass

            more_links = await page.evaluate("""() => {
                const anchors = document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]');
                return Array.from(anchors).slice(0, 5).map(a => {
                    const parts = a.href.split('/');
                    const idx = parts.indexOf('p') !== -1 ? parts.indexOf('p') : parts.indexOf('reel');
                    return { type: idx !== -1 ? parts[idx] : 'p', code: parts[idx + 1] };
                }).filter(x => x.code && x.code.length > 5);
            }""")
            if more_links:
                shortcodes.extend(more_links)
        except Exception:
            pass

    print(f"  Total shortcodes: {len(shortcodes)}")

    # Visit embed pages
    for item in shortcodes[:10]:
        code = item.get("code", "")
        ptype = item.get("type", "p")
        embed_url = f"https://www.instagram.com/{ptype}/{code}/embed/"
        try:
            print(f"  Embed: {embed_url[:60]}")
            await page.goto(embed_url, wait_until="domcontentloaded", timeout=10000)
            await page.wait_for_timeout(3000)

            # Check embed content
            try:
                info = await page.evaluate("""() => {
                    return {
                        title: document.title,
                        hasVideo: !!document.querySelector('video'),
                        hasImage: !!document.querySelector('img[src*="scontent"]'),
                        bodyLen: document.body ? document.body.innerText.length : 0,
                        iframes: Array.from(document.querySelectorAll('iframe'))
                            .map(f => f.src).filter(s => s),
                    }
                }""")
                print(f"    video={info.get('hasVideo')}, img={info.get('hasImage')}, "
                      f"body={info.get('bodyLen')}")
            except Exception:
                pass

        except Exception as exc:
            print(f"    Error: {str(exc)[:80]}")

    print(f"\n  GraphQL responses: {len(graphql_responses)}")
    for resp in graphql_responses[:10]:
        print(f"    - {resp['url'][:80]} ({resp['size']} bytes) "
              f"{resp.get('type', '')}")

    print(f"  Embed data entries: {len(embed_data)}")

    await page.close()
    await ctx.close()

    return {
        "approach": "embeds_deepdive",
        "graphql_responses": len(graphql_responses),
        "embed_data": len(embed_data),
        "shortcodes_found": len(shortcodes),
    }


# ================================================================
# DEEP DIVE 4: Meta pixel on Korean news/community sites
# ================================================================

async def deepdive_meta_pixel(browser) -> dict:
    """Extract advertiser data from Meta pixel implementations on Korean sites."""
    print("\n" + "=" * 60)
    print("DEEP DIVE: Meta Pixel Advertiser Extraction")
    print("=" * 60)

    ctx = await create_context(browser, mobile=True)
    page = await ctx.new_page()

    pixel_advertisers: list[dict] = []
    ad_tracking_events: list[dict] = []

    async def on_response(response: Response):
        url = response.url
        try:
            # Look for Meta pixel tracking calls with advertiser data
            if "facebook.com/tr" in url:
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                pixel_id = params.get("id", [""])[0]
                ev = params.get("ev", [""])[0]
                dl = params.get("dl", [""])[0]
                rl = params.get("rl", [""])[0]

                if pixel_id:
                    entry = {
                        "pixel_id": pixel_id,
                        "event": ev,
                        "page_url": dl[:100] if dl else "",
                        "referrer": rl[:100] if rl else "",
                    }
                    # Extract custom data fields
                    for k, v in params.items():
                        if k.startswith("cd["):
                            entry[k] = v[0][:100] if v else ""
                    ad_tracking_events.append(entry)

            # Look for Instagram-specific ad serving
            if ("i.instagram.com" in url or "graph.instagram.com" in url):
                ct = response.headers.get("content-type", "")
                if response.status == 200 and "json" in ct:
                    try:
                        body = await response.text()
                        if body and ("ad_id" in body or "is_ad" in body or "sponsored" in body):
                            print(f"    *** IG ad data in: {url[:80]}")
                    except Exception:
                        pass

        except Exception:
            pass

    page.on("response", on_response)

    # Visit sites with heavy Meta pixel usage
    sites = [
        ("https://m.mk.co.kr/", "mk_economy"),
        ("https://m.hankyung.com/", "hankyung"),
        ("https://biz.chosun.com/", "chosun_biz"),
        ("https://www.edaily.co.kr/", "edaily"),
        ("https://www.sedaily.com/", "sedaily"),
        ("https://m.mt.co.kr/", "moneytodya"),
        ("https://www.beautynury.com/", "beautynury"),
        ("https://www.musinsa.com/", "musinsa"),
    ]

    for url, name in sites:
        try:
            print(f"\n  [{name}] {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=12000)
            await page.wait_for_timeout(2500)

            # Scroll
            for i in range(6):
                await page.evaluate(f"window.scrollBy(0, {400 + i * 120})")
                await page.wait_for_timeout(700)

            # Visit an article for more pixel events
            try:
                link = await page.evaluate("""() => {
                    const links = document.querySelectorAll('a');
                    const valid = Array.from(links).filter(a => {
                        const t = (a.textContent || '').trim();
                        return t.length > 15 && t.length < 200 && a.href && a.href.startsWith('http');
                    });
                    return valid.length > 2 ? valid[2].href : null;
                }""")
                if link:
                    await page.goto(link, wait_until="domcontentloaded", timeout=10000)
                    await page.wait_for_timeout(2000)
                    for i in range(4):
                        await page.evaluate(f"window.scrollBy(0, {300 + i * 100})")
                        await page.wait_for_timeout(600)
            except Exception:
                pass

        except Exception as exc:
            print(f"    Error: {str(exc)[:80]}")

    print(f"\n{'=' * 40}")
    print(f"  META PIXEL RESULTS")
    print(f"{'=' * 40}")
    print(f"  Pixel tracking events: {len(ad_tracking_events)}")

    # Group by pixel ID
    pixel_ids = {}
    for evt in ad_tracking_events:
        pid = evt.get("pixel_id", "")
        if pid not in pixel_ids:
            pixel_ids[pid] = {
                "events": [],
                "pages": set(),
            }
        pixel_ids[pid]["events"].append(evt.get("event", ""))
        page_url = evt.get("page_url", "")
        if page_url:
            try:
                pixel_ids[pid]["pages"].add(urlparse(page_url).netloc)
            except Exception:
                pass

    print(f"  Unique pixel IDs: {len(pixel_ids)}")
    for pid, info in list(pixel_ids.items())[:10]:
        events = list(set(info["events"]))
        pages = list(info["pages"])
        print(f"    Pixel {pid[:15]}: events={events[:5]}, pages={pages[:3]}")

    await page.close()
    await ctx.close()

    return {
        "approach": "meta_pixel_deepdive",
        "tracking_events": len(ad_tracking_events),
        "unique_pixels": len(pixel_ids),
        "pixel_ids": list(pixel_ids.keys())[:20],
    }


def _check_threads_items(data, url):
    """Check Threads JSON data for ad markers."""
    if isinstance(data, dict):
        for key, val in data.items():
            if key in ("is_ad", "is_sponsored", "promoted", "boosted"):
                if val:
                    print(f"      Found {key}={val}")
            if isinstance(val, (dict, list)):
                _check_threads_items(val, url)
    elif isinstance(data, list):
        for item in data:
            _check_threads_items(item, url)


def _parse_js_for_ads(body, url, ads_list):
    """Parse JavaScript response for ad data."""
    patterns = [
        r'"advertiser_name"\s*:\s*"([^"]+)"',
        r'"sponsor_name"\s*:\s*"([^"]+)"',
        r'"page_name"\s*:\s*"([^"]+)"',
        r'"landing_url"\s*:\s*"([^"]+)"',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, body[:50000])
        for m in matches:
            ads_list.append({
                "source": "js_parse",
                "data": m[:100],
                "url": url[:200],
            })


def _parse_dfp_for_meta_ads(body, url, ads_list):
    """Parse DFP/GAM response for Meta advertiser data."""
    # Look for Facebook/Instagram advertiser identifiers in DFP responses
    meta_patterns = [
        r'"facebook\.com/([^"]+)"',
        r'"instagram\.com/([^"]+)"',
        r'"fb_page_id"\s*:\s*"(\d+)"',
    ]
    for pattern in meta_patterns:
        matches = re.findall(pattern, body[:100000])
        if matches:
            ads_list.append({
                "source": "dfp_meta",
                "data": matches[:5],
                "url": url[:200],
            })


async def main():
    print("=" * 60)
    print("  Instagram Alternative Deep Dive Tests")
    print("=" * 60)

    pw, browser = await create_browser()

    all_results = {}

    tests = [
        ("audience_network", deepdive_audience_network),
        ("threads", deepdive_threads),
        ("embeds", deepdive_embeds),
        ("meta_pixel", deepdive_meta_pixel),
    ]

    for name, fn in tests:
        try:
            t0 = time.time()
            result = await asyncio.wait_for(fn(browser), timeout=180)
            result["elapsed_sec"] = round(time.time() - t0, 1)
            all_results[name] = result
        except asyncio.TimeoutError:
            print(f"\n  [TIMEOUT] {name}")
            all_results[name] = {"error": "timeout"}
        except Exception as exc:
            print(f"\n  [ERROR] {name}: {str(exc)[:200]}")
            all_results[name] = {"error": str(exc)[:200]}

    await browser.close()
    await pw.stop()

    # Summary
    print("\n" + "=" * 60)
    print("  DEEP DIVE SUMMARY")
    print("=" * 60)
    for name, result in all_results.items():
        elapsed = result.get("elapsed_sec", "?")
        error = result.get("error", "")
        print(f"  {name:25s} | {elapsed}s | {json.dumps({k:v for k,v in result.items() if k not in ('elapsed_sec', 'error', 'pixel_ids', 'advertiser_domains')}, ensure_ascii=False)[:100]}")

    # Save results
    output_path = Path(_root) / "scripts" / "ig_deepdive_results.json"
    output_path.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\n  Results saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
