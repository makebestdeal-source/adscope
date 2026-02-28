"""News mention collector -- Naver News Search API.

Sources:
  Naver News Search API (https://openapi.naver.com/v1/search/news.json)
  Same client ID/secret as DataLab (NAVER_DATALAB_CLIENT_ID / SECRET).

Output: NewsMention rows per advertiser.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import UTC, datetime, timedelta
from html import unescape

import httpx
from sqlalchemy import and_, func, select

from database import async_session
from database.models import Advertiser, Campaign, NewsMention

logger = logging.getLogger(__name__)

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"

# ── Sentiment keywords ──
POSITIVE_KW = [
    "성장", "호실적", "인기", "1위", "히트", "호평", "수상", "흥행",
    "매출증가", "신제품", "출시", "혁신", "대상", "선정", "확대", "호조",
]
NEGATIVE_KW = [
    "적자", "논란", "사과", "불매", "리콜", "소송", "하락", "위기",
    "해킹", "피해", "고발", "벌금", "중단", "철수", "감소", "부진",
]
PR_SIGNALS = [
    "보도자료", "사전예약", "출시", "오픈", "론칭", "런칭",
    "할인", "이벤트", "프로모션", "제공", "캠페인",
]

# HTML tag stripper
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities."""
    if not text:
        return ""
    return unescape(_TAG_RE.sub("", text))


def _detect_sentiment(title: str, description: str) -> tuple[str, float]:
    """Simple keyword-based Korean sentiment detection."""
    text = f"{title} {description}"
    pos_count = sum(1 for kw in POSITIVE_KW if kw in text)
    neg_count = sum(1 for kw in NEGATIVE_KW if kw in text)

    if pos_count > neg_count:
        score = min(1.0, pos_count * 0.3)
        return "positive", round(score, 2)
    elif neg_count > pos_count:
        score = max(-1.0, -neg_count * 0.3)
        return "negative", round(score, 2)
    return "neutral", 0.0


def _detect_pr(title: str, description: str) -> bool:
    """Detect if article is likely a press release."""
    text = f"{title} {description}"
    return sum(1 for s in PR_SIGNALS if s in text) >= 2


def _parse_naver_date(date_str: str) -> datetime | None:
    """Parse Naver news date format: 'Mon, 19 Feb 2026 09:00:00 +0900'."""
    if not date_str:
        return None
    try:
        # Remove timezone offset and parse
        clean = date_str.rsplit("+", 1)[0].rsplit("-", 1)[0].strip()
        for fmt in [
            "%a, %d %b %Y %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
        ]:
            try:
                return datetime.strptime(clean, fmt)
            except ValueError:
                continue
        return None
    except Exception:
        return None


async def _fetch_naver_news(
    keyword: str,
    client_id: str,
    client_secret: str,
    display: int = 100,
    sort: str = "date",
) -> list[dict] | None:
    """Fetch news articles from Naver News Search API."""
    params = {
        "query": keyword,
        "display": display,
        "start": 1,
        "sort": sort,
    }
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(NAVER_NEWS_URL, params=params, headers=headers)
            if resp.status_code != 200:
                logger.warning(
                    "[news] Naver News API error %d for '%s'",
                    resp.status_code, keyword,
                )
                return None
            data = resp.json()
            return data.get("items", [])
    except Exception as e:
        logger.warning("[news] Naver News API exception for '%s': %s", keyword, e)
        return None


async def collect_news_mentions(
    session=None,
    advertiser_ids: list[int] | None = None,
    days: int = 7,
) -> dict:
    """Collect news mentions for advertisers using Naver News API.

    Returns: {"processed": N, "created": N, "skipped": N, "duplicates": N}
    """
    client_id = os.getenv("NAVER_DATALAB_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_DATALAB_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        logger.warning("[news] NAVER_DATALAB_CLIENT_ID/SECRET not set, skipping")
        return {"processed": 0, "created": 0, "skipped": 0, "duplicates": 0, "error": "no_credentials"}

    own_session = session is None
    if own_session:
        session = async_session()

    try:
        now = datetime.now(UTC).replace(tzinfo=None)
        cutoff = now - timedelta(days=days)

        # Get advertisers with active campaigns or recent activity
        adv_query = select(Advertiser.id, Advertiser.name).where(
            Advertiser.id.in_(
                select(Campaign.advertiser_id)
                .where(Campaign.last_seen >= cutoff)
                .group_by(Campaign.advertiser_id)
            )
        )
        if advertiser_ids:
            adv_query = adv_query.where(Advertiser.id.in_(advertiser_ids))

        result = await session.execute(adv_query)
        advertisers = result.fetchall()

        if not advertisers:
            logger.info("[news] No active advertisers found")
            return {"processed": 0, "created": 0, "skipped": 0, "duplicates": 0}

        created = 0
        duplicates = 0
        skipped = 0

        for adv_id, adv_name in advertisers:
            if not adv_name:
                skipped += 1
                continue

            # Search by advertiser name
            items = await _fetch_naver_news(adv_name, client_id, client_secret)
            if items is None:
                skipped += 1
                continue

            for item in items:
                article_url = item.get("link", "").strip()
                if not article_url:
                    continue

                # Check duplicate by URL
                exists = (
                    await session.execute(
                        select(func.count(NewsMention.id)).where(
                            NewsMention.article_url == article_url
                        )
                    )
                ).scalar_one()
                if exists:
                    duplicates += 1
                    continue

                title = _strip_html(item.get("title", ""))
                description = _strip_html(item.get("description", ""))
                published_at = _parse_naver_date(item.get("pubDate", ""))

                # Filter: only recent articles
                if published_at and published_at < cutoff:
                    continue

                sentiment, sentiment_score = _detect_sentiment(title, description)
                is_pr = _detect_pr(title, description)

                mention = NewsMention(
                    advertiser_id=adv_id,
                    source="naver_news",
                    article_url=article_url,
                    article_title=title[:500] if title else None,
                    article_description=description[:2000] if description else None,
                    publisher=item.get("originallink", "")[:200] or None,
                    published_at=published_at,
                    search_keyword=adv_name,
                    sentiment=sentiment,
                    sentiment_score=sentiment_score,
                    is_pr=is_pr,
                    collected_at=now,
                )
                session.add(mention)
                created += 1

        await session.commit()
        total = len(advertisers)
        logger.info(
            "[news] processed=%d created=%d duplicates=%d skipped=%d",
            total, created, duplicates, skipped,
        )
        return {
            "processed": total,
            "created": created,
            "skipped": skipped,
            "duplicates": duplicates,
        }

    except Exception:
        logger.exception("[news] collect_news_mentions failed")
        await session.rollback()
        raise
    finally:
        if own_session:
            await session.close()
