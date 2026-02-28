"""Social channel stats crawler -- collects subscribers/followers for ChannelStats.

YouTube: HTTP fetch + ytInitialData parsing (multiple URL formats).
Instagram: Playwright headless + cookie auth + HTML meta/JSON parsing.

Designed for maximum data capture with fallback strategies.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
from loguru import logger
from playwright.async_api import async_playwright

_ROOT = Path(__file__).resolve().parent.parent
_IG_COOKIES_PATH = _ROOT / "ig_cookies.json"


class SocialStatsCrawler:
    """Collects channel-level stats (subscribers, followers, post counts)."""

    def __init__(self):
        self._http = None
        self._playwright = None
        self._browser = None
        self._ig_cookies: list[dict] = []

    async def start(self):
        self._http = httpx.AsyncClient(follow_redirects=True, timeout=15)
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._ig_cookies = self._load_ig_cookies()
        self._ig_page = None  # Reusable IG API page
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
            logger.info(f"Loaded {len(cookies)} Instagram cookies")
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
        if self._http:
            await self._http.aclose()
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
    # YouTube channel stats (HTTP + ytInitialData, multi-URL fallback)
    # ------------------------------------------------------------------
    async def collect_youtube_stats(self, channel_url: str) -> dict | None:
        """Collect YouTube channel stats with fallback URL strategies.

        Tries: original URL -> /@handle search -> /c/name format.
        """
        clean_url = channel_url.rstrip("/")
        for suffix in ("/videos", "/shorts", "/streams", "/playlists"):
            if clean_url.endswith(suffix):
                clean_url = clean_url[: -len(suffix)]
                break

        # Try original URL first
        result = await self._fetch_youtube_stats(clean_url)
        if result:
            result["channel_url"] = channel_url
            return result

        # Try alternate URL formats
        handle = clean_url.split("/")[-1]
        if handle.startswith("@"):
            # Try without @
            alt = clean_url.rsplit("/", 1)[0] + "/c/" + handle[1:]
            result = await self._fetch_youtube_stats(alt)
        else:
            # Try with @
            alt = clean_url.rsplit("/", 1)[0] + "/@" + handle
            result = await self._fetch_youtube_stats(alt)

        if result:
            result["channel_url"] = channel_url
        return result

    async def _fetch_youtube_stats(self, url: str) -> dict | None:
        """Single attempt to fetch YouTube stats from a URL."""
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
            r = await self._http.get(url, headers=headers)
            if r.status_code != 200:
                return None
        except Exception:
            return None

        html = r.text

        # Try ytInitialData
        m = re.search(
            r"var\s+ytInitialData\s*=\s*(\{.*?\});\s*</script>", html, re.DOTALL
        )
        if m:
            try:
                data = json.loads(m.group(1))
                stats = self._parse_youtube_initial_data(data)
                if stats and stats.get("subscribers") is not None:
                    return stats
            except json.JSONDecodeError:
                pass

        # Fallback: parse meta tags
        stats = self._parse_youtube_meta_tags(html)
        if stats:
            return stats

        return None

    def _parse_youtube_meta_tags(self, html: str) -> dict | None:
        """Fallback: extract stats from meta/link tags in YouTube HTML."""
        result = {}

        # og:description often has subscriber info
        m = re.search(r'<meta\s+property="og:description"\s+content="([^"]*)"', html)
        if m:
            desc = m.group(1)
            # "Share your videos with friends, family, and the world"
            # Some channels: "구독자 XX만명" in description
            sub_match = re.search(r"(\d[\d,.]*)\s*(만|천|M|K|B)?\s*(subscribers|구독자)", desc, re.I)
            if sub_match:
                result["subscribers"] = self._parse_count_text(sub_match.group(0))

        # channelMetadataRenderer in ytInitialPlayerConfig or other embedded JSON
        m = re.search(r'"subscriberCountText":\s*\{"simpleText":\s*"([^"]+)"\}', html)
        if m:
            result["subscribers"] = self._parse_count_text(m.group(1))

        # Try to find subscriber count from any JSON in page
        for pattern in [
            r'"subscriberCountText":\s*\{[^}]*"content":\s*"([^"]+)"',
            r'"metadataParts":\s*\[\s*\{[^}]*"content":\s*"([^"]*(?:구독자|subscriber)[^"]*)"',
        ]:
            m = re.search(pattern, html, re.I)
            if m:
                result["subscribers"] = self._parse_count_text(m.group(1))
                break

        if result:
            return {
                "subscribers": result.get("subscribers"),
                "total_posts": result.get("total_posts"),
                "total_views": result.get("total_views"),
            }
        return None

    def _parse_youtube_initial_data(self, data: dict) -> dict | None:
        """Extract subscriber/video count from ytInitialData."""
        result: dict[str, Any] = {}
        self._walk_for_yt_stats(data, result)
        if not result:
            return None
        return {
            "subscribers": result.get("subscribers"),
            "total_posts": result.get("total_posts"),
            "total_views": result.get("total_views"),
        }

    def _walk_for_yt_stats(self, obj: Any, result: dict):
        """Walk JSON tree to find channel header stats."""
        if isinstance(obj, dict):
            if "pageHeaderRenderer" in obj:
                self._extract_page_header_stats(obj["pageHeaderRenderer"], result)
                return
            if "c4TabbedHeaderRenderer" in obj:
                header = obj["c4TabbedHeaderRenderer"]
                sub_text = header.get("subscriberCountText", {}).get("simpleText", "")
                if sub_text:
                    result["subscribers"] = self._parse_count_text(sub_text)
                return
            for v in obj.values():
                self._walk_for_yt_stats(v, result)
        elif isinstance(obj, list):
            for item in obj:
                self._walk_for_yt_stats(item, result)

    def _extract_page_header_stats(self, header: Any, result: dict):
        """Extract stats from pageHeaderRenderer."""
        if not isinstance(header, dict):
            return
        content = header.get("content", {})
        model = content.get("pageHeaderViewModel", {})
        metadata = model.get("metadata", {})
        content_metadata = metadata.get("contentMetadataViewModel", {})
        metadata_rows = content_metadata.get("metadataRows", [])

        for row in metadata_rows:
            parts = row.get("metadataParts", [])
            for part in parts:
                text_content = part.get("text", {}).get("content", "")
                if not text_content:
                    continue
                if any(k in text_content for k in ["subscriber", "구독자"]):
                    result["subscribers"] = self._parse_count_text(text_content)
                elif any(k in text_content for k in ["video", "동영상"]):
                    result["total_posts"] = self._parse_count_text(text_content)
                elif any(k in text_content for k in ["view", "조회"]):
                    result["total_views"] = self._parse_count_text(text_content)

    # ------------------------------------------------------------------
    # Instagram profile stats (Playwright + HTML parsing)
    # ------------------------------------------------------------------
    async def collect_instagram_stats(self, profile_url: str) -> dict | None:
        """Collect Instagram profile stats via authenticated API + Playwright.

        Strategy 1: web_profile_info API (fast, accurate - requires cookies)
        Strategy 2: Profile page meta description parsing (fallback)
        """
        username = self._extract_ig_username(profile_url)
        if not username:
            logger.warning(f"Cannot extract Instagram username from: {profile_url}")
            return None

        # Strategy 1: API-based (requires cookies)
        if self._ig_cookies:
            result = await self._collect_ig_stats_api(username)
            if result:
                result["channel_url"] = f"https://www.instagram.com/{username}/"
                return result

        # Strategy 2: Page-based fallback
        return await self._collect_ig_stats_page(username, profile_url)

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
        await self._ig_page.wait_for_timeout(2000)
        logger.info("Instagram API session initialized")

    async def _collect_ig_stats_api(self, username: str) -> dict | None:
        """Collect IG stats via authenticated web_profile_info API (reuses session)."""
        try:
            await self._ensure_ig_session()
        except Exception as exc:
            logger.warning(f"Instagram session init failed: {str(exc)[:80]}")
            return None

        csrf = next((c["value"] for c in self._ig_cookies if c["name"] == "csrftoken"), "")

        try:
            result = await self._ig_page.evaluate(f"""
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
                        const u = data?.data?.user;
                        if (!u) return null;
                        return {{
                            followers: u.edge_followed_by?.count || u.follower_count || null,
                            total_posts: u.edge_owner_to_timeline_media?.count || u.media_count || null,
                        }};
                    }} catch(e) {{ return null; }}
                }}
            """)

            if result and (result.get("followers") or result.get("total_posts")):
                return result
        except Exception as exc:
            logger.warning(f"Instagram API error for {username}: {str(exc)[:80]}")
            # Reset session on error
            self._ig_page = None

        return None

    async def _collect_ig_stats_page(self, username: str, profile_url: str) -> dict | None:
        """Fallback: collect IG stats from profile page meta tags."""
        url = f"https://www.instagram.com/{username}/"

        context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        if self._ig_cookies:
            await context.add_cookies(self._ig_cookies)

        page = await context.new_page()

        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            if resp and resp.status >= 400:
                return None

            await page.wait_for_timeout(3000)

            result = await self._extract_ig_from_meta(page, username)
            if result:
                return result

            html = await page.content()
            result = self._extract_ig_from_html(html, username)
            if result:
                return result
        except Exception as exc:
            logger.warning(f"Instagram page error for {username}: {str(exc)[:80]}")
        finally:
            try:
                await page.close()
                await context.close()
            except Exception:
                pass

        return None

    async def _extract_ig_from_meta(self, page, username: str) -> dict | None:
        """Extract follower/post counts from meta description tag.

        Format: "1.2M Followers, 500 Following, 1,234 Posts - ..."
        or Korean: "팔로워 12.5만명, 팔로잉 500명, 게시물 1,234개"
        """
        try:
            meta = await page.query_selector('meta[property="og:description"]')
            if not meta:
                meta = await page.query_selector('meta[name="description"]')
            if not meta:
                return None

            content = await meta.get_attribute("content")
            if not content:
                return None

            return self._parse_ig_description(content, username)
        except Exception:
            return None

    def _parse_ig_description(self, desc: str, username: str) -> dict | None:
        """Parse Instagram meta description for follower/post counts."""
        followers = None
        total_posts = None

        # English format: "1.2M Followers, 500 Following, 1,234 Posts"
        m = re.search(r"([\d,.]+[KkMm]?)\s*Followers", desc)
        if m:
            followers = self._parse_ig_count(m.group(1))

        m = re.search(r"([\d,.]+[KkMm]?)\s*Posts", desc)
        if m:
            total_posts = self._parse_ig_count(m.group(1))

        # Korean format: "팔로워 12.5만명"
        if followers is None:
            m = re.search(r"팔로워\s*([\d,.]+)\s*(만|천)?", desc)
            if m:
                followers = self._parse_count_text(f"{m.group(1)}{m.group(2) or ''}")

        if total_posts is None:
            m = re.search(r"게시물\s*([\d,.]+)", desc)
            if m:
                total_posts = self._parse_ig_count(m.group(1))

        if followers is None and total_posts is None:
            return None

        return {
            "followers": followers,
            "total_posts": total_posts,
            "channel_url": f"https://www.instagram.com/{username}/",
        }

    def _extract_ig_from_json(self, data: dict) -> dict | None:
        """Extract stats from captured Instagram API JSON response."""
        # web_profile_info format
        user = data.get("data", {}).get("user", {})
        if not user:
            user = data.get("user", {})
        if not user:
            # graphql format
            user = data.get("graphql", {}).get("user", {})
        if not user:
            return None

        followers = None
        edge_followed = user.get("edge_followed_by", {})
        if isinstance(edge_followed, dict):
            followers = edge_followed.get("count")
        if followers is None:
            followers = user.get("follower_count")

        total_posts = None
        edge_media = user.get("edge_owner_to_timeline_media", {})
        if isinstance(edge_media, dict):
            total_posts = edge_media.get("count")
        if total_posts is None:
            total_posts = user.get("media_count")

        if followers is None and total_posts is None:
            return None

        return {
            "followers": followers,
            "total_posts": total_posts,
        }

    def _extract_ig_from_html(self, html: str, username: str) -> dict | None:
        """Fallback: extract from embedded JSON or script tags in HTML."""
        # Try to find SharedData
        m = re.search(r"window\._sharedData\s*=\s*(\{.*?\});\s*</script>", html, re.DOTALL)
        if m:
            try:
                shared = json.loads(m.group(1))
                pages = shared.get("entry_data", {}).get("ProfilePage", [])
                if pages:
                    user = pages[0].get("graphql", {}).get("user", {})
                    result = self._extract_ig_from_json({"graphql": {"user": user}})
                    if result:
                        result["channel_url"] = f"https://www.instagram.com/{username}/"
                        return result
            except (json.JSONDecodeError, KeyError, IndexError):
                pass

        # Try meta description from raw HTML
        m = re.search(r'<meta\s+(?:property="og:description"|name="description")\s+content="([^"]*)"', html)
        if m:
            result = self._parse_ig_description(m.group(1), username)
            if result:
                return result

        return None

    @staticmethod
    def _extract_ig_username(url_or_handle: str) -> str | None:
        """Extract Instagram username from URL or handle."""
        url_or_handle = url_or_handle.strip().rstrip("/")
        if url_or_handle.startswith("@"):
            return url_or_handle[1:]
        if "instagram.com" in url_or_handle:
            m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", url_or_handle)
            if m:
                return m.group(1)
        if re.match(r"^[A-Za-z0-9_.]+$", url_or_handle):
            return url_or_handle
        return None

    @staticmethod
    def _parse_ig_count(text: str) -> int | None:
        """Parse Instagram count like '1.2M', '12.5K', '1,234'."""
        if not text:
            return None
        cleaned = text.replace(",", "").strip()
        m = re.match(r"([\d.]+)\s*([KkMm])?", cleaned)
        if not m:
            return None
        num = float(m.group(1))
        suffix = (m.group(2) or "").upper()
        if suffix == "M":
            return int(num * 1_000_000)
        if suffix == "K":
            return int(num * 1_000)
        return int(num)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_count_text(text: str) -> int | None:
        """Parse Korean/English count text to integer."""
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
