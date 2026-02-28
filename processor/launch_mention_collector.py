"""Launch mention collector -- collect media mentions for registered products.

MVP sources:
  1. Naver News Search API (news)
  2. Naver Blog Search API (blog)
  3. BrandChannelContent DB (youtube/sns keyword match)
  4. MediaSource connectors (RSS / YouTube API / HTML scraping)

Uses same NAVER_DATALAB_CLIENT_ID / SECRET as news_collector.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import UTC, datetime, timedelta
from html import unescape

import httpx
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import joinedload

from database import async_session
from database.models import BrandChannelContent, LaunchMention, LaunchProduct, MediaSource

logger = logging.getLogger(__name__)

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"
NAVER_BLOG_URL = "https://openapi.naver.com/v1/search/blog.json"

# Sentiment keywords (reuse from news_collector)
POSITIVE_KW = [
    "성장", "호실적", "인기", "1위", "히트", "호평", "수상", "흥행",
    "매출증가", "신제품", "출시", "혁신", "대상", "선정", "확대", "호조",
]
NEGATIVE_KW = [
    "적자", "논란", "사과", "불매", "리콜", "소송", "하락", "위기",
    "해킹", "피해", "고발", "벌금", "중단", "철수", "감소", "부진",
]

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return unescape(_TAG_RE.sub("", text))


def _detect_sentiment(title: str, desc: str) -> tuple[str, float]:
    text = f"{title} {desc}"
    pos = sum(1 for kw in POSITIVE_KW if kw in text)
    neg = sum(1 for kw in NEGATIVE_KW if kw in text)
    if pos > neg:
        return "positive", round(min(1.0, pos * 0.3), 2)
    elif neg > pos:
        return "negative", round(max(-1.0, -neg * 0.3), 2)
    return "neutral", 0.0


def _parse_naver_date(date_str: str) -> datetime | None:
    if not date_str:
        return None
    try:
        clean = date_str.rsplit("+", 1)[0].rsplit("-", 1)[0].strip()
        for fmt in ["%a, %d %b %Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
            try:
                return datetime.strptime(clean, fmt)
            except ValueError:
                continue
        return None
    except Exception:
        return None


async def _search_naver(
    endpoint: str,
    keyword: str,
    client_id: str,
    client_secret: str,
    display: int = 50,
) -> list[dict] | None:
    """Generic Naver Search API call (news or blog)."""
    params = {"query": keyword, "display": display, "start": 1, "sort": "date"}
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(endpoint, params=params, headers=headers)
            if resp.status_code != 200:
                logger.warning("[launch_mentions] Naver %s error %d for '%s'",
                               endpoint.split("/")[-1].replace(".json", ""),
                               resp.status_code, keyword)
                return None
            return resp.json().get("items", [])
    except Exception as e:
        logger.warning("[launch_mentions] Naver API exception for '%s': %s", keyword, e)
        return None


async def _check_url_exists(session, product_id: int, url: str) -> bool:
    """Check if mention URL already exists for this product."""
    result = await session.execute(
        select(func.count(LaunchMention.id)).where(
            and_(
                LaunchMention.launch_product_id == product_id,
                LaunchMention.url == url,
            )
        )
    )
    return result.scalar_one() > 0


async def _collect_naver_mentions(
    session,
    product: LaunchProduct,
    endpoint: str,
    source_type: str,
    source_platform: str,
    client_id: str,
    client_secret: str,
    cutoff: datetime,
) -> tuple[int, int]:
    """Collect mentions from a Naver search endpoint for a product's keywords."""
    created = 0
    duplicates = 0
    now = datetime.now(UTC).replace(tzinfo=None)

    for keyword in (product.keywords or []):
        items = await _search_naver(endpoint, keyword, client_id, client_secret)
        if items is None:
            continue

        for item in items:
            url = item.get("link", "").strip()
            if not url:
                continue

            if await _check_url_exists(session, product.id, url):
                duplicates += 1
                continue

            title = _strip_html(item.get("title", ""))
            description = _strip_html(item.get("description", ""))
            published_at = _parse_naver_date(item.get("pubDate", ""))

            if published_at and published_at < cutoff:
                continue

            sentiment, sentiment_score = _detect_sentiment(title, description)

            session.add(LaunchMention(
                launch_product_id=product.id,
                source_type=source_type,
                source_platform=source_platform,
                url=url,
                title=title[:500] if title else None,
                description=description[:1000] if description else None,
                author=item.get("bloggername", "")[:200] or None,
                published_at=published_at,
                sentiment=sentiment,
                sentiment_score=sentiment_score,
                matched_keyword=keyword[:200],
                collected_at=now,
            ))
            created += 1

    return created, duplicates


async def _collect_brand_content_mentions(
    session,
    product: LaunchProduct,
    cutoff: datetime,
) -> tuple[int, int]:
    """Match product keywords against existing BrandChannelContent."""
    created = 0
    duplicates = 0
    now = datetime.now(UTC).replace(tzinfo=None)

    for keyword in (product.keywords or []):
        like_pattern = f"%{keyword}%"
        result = await session.execute(
            select(BrandChannelContent).where(
                and_(
                    BrandChannelContent.advertiser_id == product.advertiser_id,
                    or_(
                        BrandChannelContent.title.ilike(like_pattern),
                        BrandChannelContent.description.ilike(like_pattern),
                    ),
                    BrandChannelContent.discovered_at >= cutoff,
                )
            ).limit(50)
        )
        rows = result.scalars().all()

        for row in rows:
            # Build URL from content
            if row.platform == "youtube":
                url = f"https://youtube.com/watch?v={row.content_id}"
                source_type = "youtube"
            elif row.platform == "instagram":
                url = f"https://instagram.com/p/{row.content_id}"
                source_type = "sns"
            else:
                continue

            if await _check_url_exists(session, product.id, url):
                duplicates += 1
                continue

            session.add(LaunchMention(
                launch_product_id=product.id,
                source_type=source_type,
                source_platform=row.platform,
                url=url,
                title=row.title[:500] if row.title else None,
                description=(row.description or "")[:1000] or None,
                published_at=row.upload_date,
                view_count=row.view_count,
                like_count=row.like_count,
                matched_keyword=keyword[:200],
                collected_at=now,
            ))
            created += 1

    return created, duplicates


async def collect_launch_mentions(
    session=None,
    product_ids: list[int] | None = None,
    days: int = 30,
) -> dict:
    """Collect media mentions for all active launch products.

    Returns: {"products_processed": N, "mentions_added": N, "duplicates": N}
    """
    client_id = os.getenv("NAVER_DATALAB_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_DATALAB_CLIENT_SECRET", "")

    own_session = session is None
    if own_session:
        session = async_session()

    try:
        now = datetime.now(UTC).replace(tzinfo=None)
        cutoff = now - timedelta(days=days)

        # Get active products
        query = select(LaunchProduct).where(LaunchProduct.is_active == True)  # noqa: E712
        if product_ids:
            query = query.where(LaunchProduct.id.in_(product_ids))
        result = await session.execute(query)
        products = result.scalars().all()

        if not products:
            logger.info("[launch_mentions] No active products found")
            return {"products_processed": 0, "mentions_added": 0, "duplicates": 0}

        total_created = 0
        total_duplicates = 0

        for product in products:
            # 1. Naver News
            if client_id and client_secret:
                c, d = await _collect_naver_mentions(
                    session, product, NAVER_NEWS_URL,
                    "news", "naver_news", client_id, client_secret, cutoff,
                )
                total_created += c
                total_duplicates += d

                # 2. Naver Blog
                c, d = await _collect_naver_mentions(
                    session, product, NAVER_BLOG_URL,
                    "blog", "naver_blog", client_id, client_secret, cutoff,
                )
                total_created += c
                total_duplicates += d

            # 3. Brand channel content (YouTube/Instagram)
            c, d = await _collect_brand_content_mentions(session, product, cutoff)
            total_created += c
            total_duplicates += d

        await session.commit()
        logger.info(
            "[launch_mentions] products=%d created=%d duplicates=%d",
            len(products), total_created, total_duplicates,
        )
        return {
            "products_processed": len(products),
            "mentions_added": total_created,
            "duplicates": total_duplicates,
        }

    except Exception:
        logger.exception("[launch_mentions] collect_launch_mentions failed")
        await session.rollback()
        raise
    finally:
        if own_session:
            await session.close()


# ─────────────────────────────────────────────
# MediaSource connector-based collection
# ─────────────────────────────────────────────

async def crawl_media_sources() -> dict:
    """Iterate active MediaSources, fetch mentions via connectors, match to products."""
    from processor.lii_connectors.factory import get_connector

    stats = {"sources_processed": 0, "mentions_created": 0, "errors": 0}

    async with async_session() as session:
        now = datetime.now(UTC).replace(tzinfo=None)

        # Get active media sources
        result = await session.execute(
            select(MediaSource)
            .where(MediaSource.is_active == True)  # noqa: E712
            .options(joinedload(MediaSource.parse_profile))
        )
        sources = result.scalars().all()

        # Get active products for keyword matching
        product_result = await session.execute(
            select(LaunchProduct).where(LaunchProduct.is_active == True)  # noqa: E712
        )
        products = product_result.scalars().all()

        for source in sources:
            # Check schedule_interval
            if source.last_crawl_at:
                elapsed = (now - source.last_crawl_at).total_seconds() / 60
                if elapsed < source.schedule_interval:
                    continue

            try:
                connector = get_connector(source.connector_type)
                raw_mentions = await connector.fetch_mentions(source)

                for item in raw_mentions:
                    url = (item.get("url") or "").strip()
                    if not url:
                        continue

                    # Global URL dedup
                    exists = (await session.execute(
                        select(func.count(LaunchMention.id)).where(LaunchMention.url == url)
                    )).scalar_one()
                    if exists:
                        continue

                    # Match to product by keyword
                    matched_product, matched_kw = _match_to_product(
                        item.get("title", ""),
                        item.get("content_snippet", ""),
                        products,
                    )
                    if not matched_product:
                        continue

                    title = item.get("title", "")
                    description = item.get("content_snippet", "")
                    sentiment, score = _detect_sentiment(title, description)

                    session.add(LaunchMention(
                        launch_product_id=matched_product.id,
                        source_type=item.get("source_type", "news"),
                        source_platform=item.get("source_platform", source.connector_type),
                        url=url[:1000],
                        title=title[:500] if title else None,
                        description=description[:1000] if description else None,
                        published_at=item.get("published_at"),
                        view_count=item.get("extra_data", {}).get("view_count") if item.get("extra_data") else None,
                        like_count=item.get("extra_data", {}).get("like_count") if item.get("extra_data") else None,
                        comment_count=item.get("extra_data", {}).get("comment_count") if item.get("extra_data") else None,
                        sentiment=sentiment,
                        sentiment_score=score,
                        matched_keyword=matched_kw,
                        media_source_id=source.id,
                        extra_data=item.get("extra_data"),
                        collected_at=now,
                    ))
                    stats["mentions_created"] += 1

                source.last_crawl_at = now
                source.error_count = max(0, source.error_count - 1)
                stats["sources_processed"] += 1

            except Exception as e:
                source.error_count = (source.error_count or 0) + 1
                total_attempts = stats["sources_processed"] + stats["errors"] + 1
                source.error_rate = round(source.error_count / max(total_attempts, 1), 3)
                stats["errors"] += 1
                logger.exception("[media_sources] crawl failed for %s: %s", source.name, e)

        await session.commit()

    logger.info("[media_sources] done: %s", stats)
    return stats


def _match_to_product(
    title: str, content: str, products: list[LaunchProduct],
) -> tuple[LaunchProduct | None, str | None]:
    """Match mention text to a product by its keywords."""
    text = f"{title} {content}".lower()
    for product in products:
        for kw in (product.keywords or []):
            if kw.lower() in text:
                return product, kw[:200]
    return None, None
