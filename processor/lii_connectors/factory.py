"""Connector factory -- maps connector_type to connector class."""

from __future__ import annotations

from processor.lii_connectors import BaseConnector


def get_connector(connector_type: str) -> BaseConnector:
    """Return connector instance for the given type."""
    if connector_type == "rss":
        from processor.lii_connectors.rss_connector import RSSConnector
        return RSSConnector()
    elif connector_type == "api_youtube":
        from processor.lii_connectors.youtube_connector import YouTubeConnector
        return YouTubeConnector()
    elif connector_type == "html_list_detail":
        from processor.lii_connectors.html_connector import HTMLConnector
        return HTMLConnector()
    else:
        raise ValueError(f"Unknown connector type: {connector_type}")
