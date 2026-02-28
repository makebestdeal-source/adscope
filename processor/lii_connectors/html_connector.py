"""HTML list-detail connector -- uses Playwright headless + ParseProfile selectors."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from processor.lii_connectors import BaseConnector

logger = logging.getLogger(__name__)


class HTMLConnector(BaseConnector):
    """Scrape article mentions from HTML pages using CSS selectors from ParseProfile."""

    async def fetch_mentions(self, media_source: Any) -> list[dict]:
        profile = media_source.parse_profile
        if not profile:
            logger.warning("[html] No parse_profile for %s, skipping", media_source.name)
            return []

        if not profile.list_selector:
            logger.warning("[html] No list_selector in profile for %s", media_source.name)
            return []

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("[html] playwright not installed")
            return []

        results = []

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    viewport={"width": 1280, "height": 800},
                )
                page = await context.new_page()

                await page.goto(media_source.url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(2000)

                # Extract article links from list page
                elements = await page.query_selector_all(profile.list_selector)
                links = []
                for el in elements[:20]:
                    href = await el.get_attribute("href")
                    if href:
                        full_url = urljoin(media_source.url, href)
                        text = (await el.inner_text()).strip()
                        links.append({"url": full_url, "list_title": text})

                # Visit detail pages if selectors are configured
                for link_info in links:
                    article = {"url": link_info["url"], "title": link_info.get("list_title", "")}

                    if profile.title_selector or profile.content_selector or profile.date_selector:
                        try:
                            await page.goto(link_info["url"], wait_until="domcontentloaded", timeout=15000)
                            await page.wait_for_timeout(1000)

                            if profile.title_selector:
                                title_el = await page.query_selector(profile.title_selector)
                                if title_el:
                                    article["title"] = (await title_el.inner_text()).strip()

                            if profile.content_selector:
                                content_el = await page.query_selector(profile.content_selector)
                                if content_el:
                                    text = (await content_el.inner_text()).strip()
                                    article["content_snippet"] = text[:2000]

                            if profile.date_selector:
                                date_el = await page.query_selector(profile.date_selector)
                                if date_el:
                                    date_text = (await date_el.inner_text()).strip()
                                    article["published_at"] = _parse_date_text(date_text)
                        except Exception as e:
                            logger.debug("[html] detail page error for %s: %s", link_info["url"], e)

                    results.append({
                        "title": article.get("title", ""),
                        "url": article["url"],
                        "content_snippet": article.get("content_snippet", ""),
                        "published_at": article.get("published_at"),
                        "extra_data": None,
                        "reach_estimate": None,
                        "source_type": "news",
                        "source_platform": "html",
                    })

                await browser.close()
        except Exception as e:
            logger.exception("[html] crawl failed for %s: %s", media_source.name, e)

        logger.info("[html] fetched %d articles from %s", len(results), media_source.name)
        return results


def _parse_date_text(text: str) -> datetime | None:
    """Try to parse common Korean/ISO date formats."""
    import re

    if not text:
        return None

    # ISO format: 2026-02-20
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            pass

    # Korean: 2026.02.20 or 2026년 02월 20일
    m = re.search(r"(\d{4})[.\s년]+(\d{1,2})[.\s월]+(\d{1,2})", text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            pass

    return None
