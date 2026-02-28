"""RSS/Atom feed connector."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from processor.lii_connectors import BaseConnector

logger = logging.getLogger(__name__)


def _parse_feed_date(entry: dict) -> datetime | None:
    """Parse various date formats from RSS/Atom entries."""
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                from calendar import timegm
                return datetime.utcfromtimestamp(timegm(parsed))
            except Exception:
                continue

    for key in ("published", "updated", "pubDate"):
        raw = entry.get(key)
        if raw:
            try:
                return parsedate_to_datetime(raw).replace(tzinfo=None)
            except Exception:
                pass
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                pass
    return None


class RSSConnector(BaseConnector):
    """Fetch mentions from RSS/Atom feeds using feedparser."""

    async def fetch_mentions(self, media_source: Any) -> list[dict]:
        try:
            import feedparser
        except ImportError:
            logger.error("[rss] feedparser not installed: pip install feedparser")
            return []

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(media_source.url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; AdScope/1.0)"
                })
                resp.raise_for_status()
        except Exception as e:
            logger.warning("[rss] fetch failed for %s: %s", media_source.name, e)
            return []

        feed = feedparser.parse(resp.text)
        results = []

        for entry in feed.entries[:50]:
            url = entry.get("link", "").strip()
            if not url:
                continue

            title = entry.get("title", "")
            summary = entry.get("summary", entry.get("description", ""))
            if summary and len(summary) > 2000:
                summary = summary[:2000]

            published_at = _parse_feed_date(entry)

            extra = {}
            author = entry.get("author")
            if author:
                extra["author"] = author
            tags = [t.get("term", "") for t in entry.get("tags", []) if t.get("term")]
            if tags:
                extra["tags"] = tags

            results.append({
                "title": title,
                "url": url,
                "content_snippet": summary,
                "published_at": published_at,
                "extra_data": extra or None,
                "reach_estimate": None,
                "source_type": "news",
                "source_platform": "rss",
            })

        logger.info("[rss] fetched %d entries from %s", len(results), media_source.name)
        return results
