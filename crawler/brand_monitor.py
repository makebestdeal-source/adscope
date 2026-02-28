"""Brand channel monitor -- independent Playwright-based monitor.

Monitors brand official channels (YouTube, Instagram) via network intercept.
Does NOT inherit from BaseCrawler.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger
from playwright.async_api import async_playwright, Response

# Keywords that indicate ad/sponsored content
_AD_KEYWORDS_KO = ["협찬", "PPL", "광고", "제공"]
_AD_KEYWORDS_EN = ["#ad", "#sponsored", "paid partnership", "sponsored"]
_ALL_AD_KEYWORDS = _AD_KEYWORDS_KO + _AD_KEYWORDS_EN

_ROOT = Path(__file__).resolve().parent.parent
_IG_COOKIES_PATH = _ROOT / "ig_cookies.json"


class BrandChannelMonitor:
    """Monitors brand official channels via network intercept only."""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._ig_cookies: list[dict] = []

    async def start(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._ig_cookies = self._load_ig_cookies()
        self._ig_page = None
        self._ig_ctx = None

    @staticmethod
    def _load_ig_cookies() -> list[dict]:
        """Load Instagram cookies from ig_cookies.json."""
        if not _IG_COOKIES_PATH.exists():
            logger.warning(f"Instagram cookies not found: {_IG_COOKIES_PATH}")
            return []
        try:
            raw = json.loads(_IG_COOKIES_PATH.read_text(encoding="utf-8"))
            cookies = []
            for c in raw:
                cookie = {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c.get("domain", ".instagram.com"),
                    "path": c.get("path", "/"),
                }
                if c.get("expires") and c["expires"] > 0:
                    cookie["expires"] = c["expires"]
                if c.get("httpOnly") is not None:
                    cookie["httpOnly"] = c["httpOnly"]
                if c.get("secure") is not None:
                    cookie["secure"] = c["secure"]
                if c.get("sameSite"):
                    cookie["sameSite"] = c["sameSite"]
                cookies.append(cookie)
            logger.info(f"Loaded {len(cookies)} Instagram cookies for brand monitor")
            return cookies
        except Exception as e:
            logger.warning(f"Failed to load Instagram cookies: {e}")
            return []

    async def stop(self):
        if self._ig_page:
            try:
                await self._ig_page.close()
            except Exception:
                pass
        if self._ig_ctx:
            try:
                await self._ig_ctx.close()
            except Exception:
                pass
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *a):
        await self.stop()

    # ------------------------------------------------------------------
    # YouTube channel monitoring
    # ------------------------------------------------------------------
    async def monitor_youtube_channel(self, channel_url: str) -> list[dict]:
        """Monitor a YouTube channel's /videos tab.

        Strategy 1: HTTP fetch + ytInitialData parsing (fast, no browser)
        Strategy 2: Playwright network intercept (fallback)

        Returns list of video metadata dicts.
        """
        # Strategy 1: HTTP fetch (faster, avoids consent issues)
        videos = await self._fetch_youtube_videos_http(channel_url)
        if videos:
            logger.info(f"YouTube channel monitor: {len(videos)} videos found from {channel_url} (HTTP)")
            return videos

        # Strategy 2: Playwright fallback
        videos = await self._fetch_youtube_videos_playwright(channel_url)
        logger.info(f"YouTube channel monitor: {len(videos)} videos found from {channel_url} (Playwright)")
        return videos

    async def _fetch_youtube_videos_http(self, channel_url: str) -> list[dict]:
        """Fetch YouTube channel videos via HTTP + ytInitialData."""
        import httpx

        videos_url = channel_url.rstrip("/") + "/videos"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Cookie": "CONSENT=PENDING+987; SOCS=CAESEwgDEgk2MTY0NTkxNjQaAmVuIAEaBgiA_LyuBg",
        }

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
                r = await client.get(videos_url, headers=headers)
                if r.status_code != 200:
                    return []
        except Exception:
            return []

        html = r.text
        m = re.search(
            r"var\s+ytInitialData\s*=\s*(\{.*?\});\s*</script>", html, re.DOTALL
        )
        if not m:
            return []

        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return []

        videos = self._extract_youtube_videos(data)
        return videos

    async def _fetch_youtube_videos_playwright(self, channel_url: str) -> list[dict]:
        """Fetch YouTube channel videos via Playwright network intercept."""
        videos: list[dict] = []
        captured_json: list[dict] = []

        async def _on_response(response: Response):
            url = response.url
            if "/youtubei/v1/browse" in url or "/browse" in url:
                try:
                    ct = response.headers.get("content-type", "")
                    if "json" not in ct and "text" not in ct:
                        return
                    body = await response.text()
                    if not body:
                        return
                    data = json.loads(body)
                    captured_json.append(data)
                except Exception:
                    pass

        context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )

        # Set consent cookies to bypass YouTube consent page
        await context.add_cookies([
            {"name": "CONSENT", "value": "PENDING+987", "domain": ".youtube.com", "path": "/"},
            {"name": "SOCS", "value": "CAESEwgDEgk2MTY0NTkxNjQaAmVuIAEaBgiA_LyuBg", "domain": ".youtube.com", "path": "/"},
        ])

        page = await context.new_page()
        page.on("response", _on_response)

        try:
            videos_url = channel_url.rstrip("/") + "/videos"
            await page.goto(videos_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(1)

            # Also try to extract from page HTML (ytInitialData)
            html = await page.content()
            m = re.search(r"var\s+ytInitialData\s*=\s*(\{.*?\});\s*</script>", html, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                    captured_json.append(data)
                except json.JSONDecodeError:
                    pass
        except Exception as exc:
            logger.warning(f"YouTube channel navigation error: {exc}")
        finally:
            await page.close()
            await context.close()

        for data in captured_json:
            extracted = self._extract_youtube_videos(data)
            videos.extend(extracted)

        seen = set()
        unique = []
        for v in videos:
            vid = v.get("video_id")
            if vid and vid not in seen:
                seen.add(vid)
                unique.append(v)

        return unique

    def _extract_youtube_videos(self, data: dict) -> list[dict]:
        """Recursively extract video info from YouTube browse API JSON."""
        results = []
        self._walk_youtube_json(data, results)
        return results

    def _walk_youtube_json(self, obj: Any, results: list[dict]):
        """Walk JSON tree looking for gridVideoRenderer or richItemRenderer."""
        if isinstance(obj, dict):
            # gridVideoRenderer
            if "gridVideoRenderer" in obj:
                r = obj["gridVideoRenderer"]
                results.append(self._parse_video_renderer(r))
                return
            # richItemRenderer -> content -> videoRenderer
            if "richItemRenderer" in obj:
                content = obj["richItemRenderer"].get("content", {})
                if "videoRenderer" in content:
                    r = content["videoRenderer"]
                    results.append(self._parse_video_renderer(r))
                    return
            # videoRenderer at top level
            if "videoRenderer" in obj:
                r = obj["videoRenderer"]
                results.append(self._parse_video_renderer(r))
                return
            for v in obj.values():
                self._walk_youtube_json(v, results)
        elif isinstance(obj, list):
            for item in obj:
                self._walk_youtube_json(item, results)

    def _parse_video_renderer(self, renderer: dict) -> dict:
        """Parse a single video renderer dict into a clean metadata dict."""
        video_id = renderer.get("videoId", "")

        # Title
        title_runs = renderer.get("title", {}).get("runs", [])
        title = title_runs[0].get("text", "") if title_runs else ""
        if not title:
            title = renderer.get("title", {}).get("simpleText", "")

        # Thumbnail
        thumbs = renderer.get("thumbnail", {}).get("thumbnails", [])
        thumbnail = thumbs[-1].get("url", "") if thumbs else ""

        # View count
        view_text = renderer.get("viewCountText", {}).get("simpleText", "")
        view_count = self._parse_view_count(view_text)

        # Published time
        published = renderer.get("publishedTimeText", {}).get("simpleText", "")

        # Duration
        duration_text = (
            renderer.get("thumbnailOverlays", [{}])[0]
            .get("thumbnailOverlayTimeStatusRenderer", {})
            .get("text", {})
            .get("simpleText", "")
            if renderer.get("thumbnailOverlays")
            else ""
        )
        duration_seconds = self._parse_duration(duration_text)

        return {
            "video_id": video_id,
            "title": title,
            "thumbnail_url": thumbnail,
            "upload_date_text": published,
            "view_count": view_count,
            "duration_seconds": duration_seconds,
            "content_type": "short" if duration_seconds and duration_seconds < 61 else "video",
        }

    @staticmethod
    def _parse_view_count(text: str) -> int | None:
        """Parse '조회수 1,234회' or '1.2M views' to int."""
        if not text:
            return None
        cleaned = text.replace(",", "").replace(" ", "")
        m = re.search(r"([\d.]+)", cleaned)
        if not m:
            return None
        num = float(m.group(1))
        lower = cleaned.lower()
        if "만" in lower:
            return int(num * 10000)
        if "천" in lower:
            return int(num * 1000)
        if "억" in lower:
            return int(num * 100000000)
        if "m" in lower:
            return int(num * 1000000)
        if "k" in lower:
            return int(num * 1000)
        if "b" in lower:
            return int(num * 1000000000)
        return int(num)

    @staticmethod
    def _parse_duration(text: str) -> int | None:
        """Parse '12:34' or '1:02:30' to seconds."""
        if not text:
            return None
        parts = text.strip().split(":")
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            return int(parts[0])
        except (ValueError, IndexError):
            return None

    # ------------------------------------------------------------------
    # Instagram profile monitoring
    # ------------------------------------------------------------------
    async def _ensure_ig_session(self):
        """Ensure a reusable Instagram browser session is ready."""
        if self._ig_page and not self._ig_page.is_closed():
            return
        if self._ig_ctx:
            try:
                await self._ig_ctx.close()
            except Exception:
                pass
        self._ig_ctx = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        await self._ig_ctx.add_cookies(self._ig_cookies)
        self._ig_page = await self._ig_ctx.new_page()
        await self._ig_page.goto(
            "https://www.instagram.com/",
            wait_until="domcontentloaded",
            timeout=15000,
        )
        await asyncio.sleep(2)
        logger.info("Instagram API session initialized for brand monitor")

    async def monitor_instagram_profile(self, profile_url: str) -> list[dict]:
        """Monitor an Instagram profile via authenticated API calls.

        Uses web_profile_info API → get user_id → feed API.
        Reuses a persistent browser session for efficiency.

        Returns list of post metadata dicts.
        """
        if not self._ig_cookies:
            logger.warning("No Instagram cookies -- cannot monitor profiles")
            return []

        # Extract username from URL
        username = profile_url.strip().rstrip("/").split("/")[-1].lstrip("@")
        if not username:
            return []

        try:
            await self._ensure_ig_session()
        except Exception as exc:
            logger.warning(f"Instagram session init failed: {str(exc)[:80]}")
            return []

        csrf = next((c["value"] for c in self._ig_cookies if c["name"] == "csrftoken"), "")
        posts: list[dict] = []

        try:
            # Get user_id from web_profile_info
            user_id = await self._ig_page.evaluate(f"""
                async () => {{
                    try {{
                        const resp = await fetch('/api/v1/users/web_profile_info/?username={username}', {{
                            headers: {{
                                'X-CSRFToken': '{csrf}',
                                'X-Requested-With': 'XMLHttpRequest',
                                'X-IG-App-ID': '936619743392459',
                            }}
                        }});
                        const data = await resp.json();
                        return data?.data?.user?.id || null;
                    }} catch(e) {{ return null; }}
                }}
            """)

            if user_id:
                feed_data = await self._ig_page.evaluate(f"""
                    async () => {{
                        try {{
                            const resp = await fetch('/api/v1/feed/user/{user_id}/?count=24', {{
                                headers: {{
                                    'X-CSRFToken': '{csrf}',
                                    'X-Requested-With': 'XMLHttpRequest',
                                    'X-IG-App-ID': '936619743392459',
                                }}
                            }});
                            return await resp.json();
                        }} catch(e) {{ return {{}}; }}
                    }}
                """)

                items = feed_data.get("items", [])
                for item in items:
                    if isinstance(item, dict) and item.get("code"):
                        posts.append(self._parse_instagram_api_item(item))
        except Exception as exc:
            logger.warning(f"Instagram API error for {username}: {str(exc)[:100]}")
            self._ig_page = None  # Reset session on error

        # Deduplicate
        seen = set()
        unique = []
        for p in posts:
            sc = p.get("shortcode")
            if sc and sc not in seen:
                seen.add(sc)
                unique.append(p)

        logger.info(f"Instagram profile monitor: {len(unique)} posts from {profile_url}")
        return unique

    def _extract_instagram_posts(self, data: dict) -> list[dict]:
        """Extract posts from Instagram GraphQL JSON response."""
        results = []
        self._walk_instagram_json(data, results)
        return results

    def _walk_instagram_json(self, obj: Any, results: list[dict]):
        """Walk JSON tree looking for edge_owner_to_timeline_media."""
        if isinstance(obj, dict):
            if "edge_owner_to_timeline_media" in obj:
                edges = obj["edge_owner_to_timeline_media"].get("edges", [])
                for edge in edges:
                    node = edge.get("node", {})
                    results.append(self._parse_instagram_node(node))
                return
            # Also handle items from REST API
            if "items" in obj and isinstance(obj["items"], list):
                for item in obj["items"]:
                    if isinstance(item, dict) and "code" in item:
                        results.append(self._parse_instagram_api_item(item))
                return
            for v in obj.values():
                self._walk_instagram_json(v, results)
        elif isinstance(obj, list):
            for item in obj:
                self._walk_instagram_json(item, results)

    def _parse_instagram_node(self, node: dict) -> dict:
        """Parse a GraphQL node into a clean post dict."""
        shortcode = node.get("shortcode", "")
        caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
        caption = ""
        if caption_edges:
            caption = caption_edges[0].get("node", {}).get("text", "")

        timestamp = node.get("taken_at_timestamp")
        upload_date = None
        if timestamp:
            upload_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()

        like_count = node.get("edge_liked_by", {}).get("count")
        if like_count is None:
            like_count = node.get("edge_media_preview_like", {}).get("count")

        is_video = node.get("is_video", False)
        thumbnail_url = node.get("thumbnail_src", "") or node.get("display_url", "")

        return {
            "shortcode": shortcode,
            "caption": caption,
            "timestamp": timestamp,
            "upload_date": upload_date,
            "like_count": like_count,
            "thumbnail_url": thumbnail_url,
            "is_video": is_video,
            "content_type": "reel" if is_video else "post",
        }

    def _parse_instagram_api_item(self, item: dict) -> dict:
        """Parse a REST API item into a clean post dict."""
        shortcode = item.get("code", "")
        caption_obj = item.get("caption", {})
        caption = caption_obj.get("text", "") if isinstance(caption_obj, dict) else ""

        timestamp = item.get("taken_at")
        upload_date = None
        if timestamp:
            upload_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()

        like_count = item.get("like_count")
        is_video = item.get("media_type", 1) == 2

        thumbnail_url = ""
        image_versions = item.get("image_versions2", {})
        candidates = image_versions.get("candidates", [])
        if candidates:
            thumbnail_url = candidates[0].get("url", "")

        return {
            "shortcode": shortcode,
            "caption": caption,
            "timestamp": timestamp,
            "upload_date": upload_date,
            "like_count": like_count,
            "thumbnail_url": thumbnail_url,
            "is_video": is_video,
            "content_type": "reel" if is_video else "post",
        }

    def _extract_ig_posts_from_html(self, html: str) -> list[dict]:
        """Extract Instagram posts from embedded JSON in page HTML."""
        results = []
        # Try window._sharedData
        m = re.search(r"window\._sharedData\s*=\s*(\{.*?\});\s*</script>", html, re.DOTALL)
        if m:
            try:
                shared = json.loads(m.group(1))
                pages = shared.get("entry_data", {}).get("ProfilePage", [])
                if pages:
                    user = pages[0].get("graphql", {}).get("user", {})
                    edges = user.get("edge_owner_to_timeline_media", {}).get("edges", [])
                    for edge in edges:
                        node = edge.get("node", {})
                        results.append(self._parse_instagram_node(node))
            except (json.JSONDecodeError, KeyError, IndexError):
                pass

        # Try additional JSON data patterns
        for pattern in [
            r'"xdt_api__v1__feed__user_timeline_graphql_connection"\s*:\s*(\{[^<]+?\})\s*,\s*"',
            r'"edge_owner_to_timeline_media"\s*:\s*(\{"count".*?\})\s*[,}]',
        ]:
            m = re.search(pattern, html, re.DOTALL)
            if m and not results:
                try:
                    data = json.loads(m.group(1))
                    edges = data.get("edges", [])
                    for edge in edges:
                        node = edge.get("node", {})
                        if node.get("shortcode"):
                            results.append(self._parse_instagram_node(node))
                except (json.JSONDecodeError, KeyError):
                    pass
        return results

    # ------------------------------------------------------------------
    # Ad content detection
    # ------------------------------------------------------------------
    @staticmethod
    def detect_ad_content(content: dict) -> dict:
        """Check title/description/caption for ad keywords.

        Returns dict with:
            has_sponsored_tag: bool
            ad_keywords_found: list[str]
        """
        text_fields = []

        # Gather all text fields from the content dict
        for key in ("title", "caption", "description"):
            val = content.get(key, "")
            if val:
                text_fields.append(str(val))

        combined = " ".join(text_fields).lower()
        found = []

        for kw in _ALL_AD_KEYWORDS:
            if kw.lower() in combined:
                found.append(kw)

        return {
            "has_sponsored_tag": len(found) > 0,
            "ad_keywords_found": found,
        }
