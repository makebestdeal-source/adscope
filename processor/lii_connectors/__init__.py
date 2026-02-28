"""LII Connectors -- pluggable media source fetchers."""

from __future__ import annotations

from typing import Any


class BaseConnector:
    """Base class for LII media source connectors."""

    async def fetch_mentions(self, media_source: Any) -> list[dict]:
        """Return list of dicts with keys:
        title, url, content_snippet, published_at, extra_data, reach_estimate
        """
        raise NotImplementedError

    async def close(self):
        pass
