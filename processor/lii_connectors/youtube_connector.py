"""YouTube Data API v3 connector -- search for mentions + get reaction counts."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from processor.lii_connectors import BaseConnector

logger = logging.getLogger(__name__)

YT_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YT_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


class YouTubeConnector(BaseConnector):
    """Fetch mentions from YouTube via Data API v3."""

    def __init__(self):
        self.api_key = os.getenv("YOUTUBE_API_KEY", "")

    async def fetch_mentions(self, media_source: Any) -> list[dict]:
        if not self.api_key:
            logger.warning("[youtube] YOUTUBE_API_KEY not set, skipping %s", media_source.name)
            return []

        extra_config = media_source.extra_config or {}
        search_query = extra_config.get("search_query") or media_source.name
        max_results = min(extra_config.get("max_results", 25), 50)

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(YT_SEARCH_URL, params={
                    "part": "snippet",
                    "q": search_query,
                    "type": "video",
                    "order": "date",
                    "maxResults": max_results,
                    "regionCode": "KR",
                    "key": self.api_key,
                })
                if resp.status_code != 200:
                    logger.warning("[youtube] search API error %d for '%s'", resp.status_code, search_query)
                    return []
                data = resp.json()
        except Exception as e:
            logger.warning("[youtube] API exception for '%s': %s", search_query, e)
            return []

        items = data.get("items", [])
        if not items:
            return []

        # Get video stats for reach estimation
        video_ids = [it["id"]["videoId"] for it in items if it.get("id", {}).get("videoId")]
        stats_map = await self._get_video_stats(video_ids)

        results = []
        for item in items:
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue

            snippet = item.get("snippet", {})
            published_raw = snippet.get("publishedAt", "")
            published_at = None
            if published_raw:
                try:
                    published_at = datetime.fromisoformat(published_raw.replace("Z", "+00:00")).replace(tzinfo=None)
                except Exception:
                    pass

            stats = stats_map.get(video_id, {})
            view_count = int(stats.get("viewCount", 0))

            results.append({
                "title": snippet.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "content_snippet": snippet.get("description", "")[:2000],
                "published_at": published_at,
                "reach_estimate": view_count,
                "extra_data": {
                    "video_id": video_id,
                    "channel_title": snippet.get("channelTitle"),
                    "view_count": view_count,
                    "like_count": int(stats.get("likeCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0)),
                },
                "source_type": "youtube",
                "source_platform": "youtube",
            })

        logger.info("[youtube] fetched %d videos for '%s'", len(results), search_query)
        return results

    async def _get_video_stats(self, video_ids: list[str]) -> dict[str, dict]:
        """Fetch view/like/comment counts for a batch of video IDs."""
        if not video_ids:
            return {}

        stats_map = {}
        # API allows up to 50 IDs per request
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(YT_VIDEOS_URL, params={
                        "part": "statistics",
                        "id": ",".join(batch),
                        "key": self.api_key,
                    })
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    for item in data.get("items", []):
                        stats_map[item["id"]] = item.get("statistics", {})
            except Exception:
                continue

        return stats_map
