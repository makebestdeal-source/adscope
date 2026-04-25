"""Naver News Search API 기반 뉴스 멘션 수집기.

advertisers 테이블의 브랜드명으로 네이버 뉴스를 검색하여
news_mentions 테이블에 저장합니다.

- API: https://openapi.naver.com/v1/search/news.json
- Headers: X-Naver-Client-Id, X-Naver-Client-Secret
- Rate limit: 25,000 calls/day
- 간단한 키워드 기반 감성 분석 포함
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import UTC, datetime
from html import unescape

import httpx
from sqlalchemy import select

from database import async_session
from database.models import Advertiser, NewsMention

logger = logging.getLogger(__name__)

NAVER_NEWS_API = "https://openapi.naver.com/v1/search/news.json"

# ──────────────────────────────────────────────
# 감성 분석용 키워드
# ──────────────────────────────────────────────
POSITIVE_KEYWORDS = [
    "성장", "인기", "출시", "흥행", "매출", "호평", "성공", "1위",
    "수상", "혁신", "돌파", "호조", "확대", "신기록", "투자유치",
    "상승", "급증", "대박", "베스트셀러", "호실적", "최초",
    "선정", "획득", "증가", "달성", "기대", "주목",
]

NEGATIVE_KEYWORDS = [
    "논란", "리콜", "소송", "피해", "문제", "하락", "적자", "불만",
    "실패", "위기", "사고", "결함", "비판", "의혹", "탈세",
    "해킹", "유출", "벌금", "제재", "파산", "폐업", "철수",
    "감소", "급락", "불량", "환불", "지적", "고발",
]

# HTML tag stripper
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """HTML 태그 제거 및 HTML 엔티티 디코딩."""
    if not text:
        return ""
    return unescape(_TAG_RE.sub("", text)).strip()


def _analyze_sentiment(title: str, description: str) -> tuple[str, float]:
    """제목 + 설명에서 긍정/부정 키워드를 카운트하여 감성 판단.

    Returns:
        (sentiment_label, sentiment_score)
        sentiment_label: "positive" / "neutral" / "negative"
        sentiment_score: -1.0 ~ 1.0
    """
    text = f"{title} {description}"

    pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
    neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)

    total = pos_count + neg_count
    if total == 0:
        return "neutral", 0.0

    score = (pos_count - neg_count) / total  # -1.0 ~ 1.0

    if score > 0.15:
        label = "positive"
    elif score < -0.15:
        label = "negative"
    else:
        label = "neutral"

    return label, round(score, 3)


def _detect_pr(title: str, description: str) -> bool:
    """보도자료(PR) 여부 간이 탐지."""
    text = f"{title} {description}".lower()
    pr_signals = ["보도자료", "press release", "제공=", "뉴스와이어", "배포"]
    return any(sig in text for sig in pr_signals)


def _parse_pub_date(date_str: str) -> datetime | None:
    """네이버 뉴스 API pubDate 파싱. (RFC 2822 형식)

    Example: 'Mon, 23 Mar 2026 09:00:00 +0900'
    """
    if not date_str:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str).replace(tzinfo=None)
    except Exception:
        return None


# ──────────────────────────────────────────────
# API 호출
# ──────────────────────────────────────────────

async def _search_news(
    client: httpx.AsyncClient,
    keyword: str,
    headers: dict,
    display: int = 10,
) -> list[dict]:
    """네이버 뉴스 검색 API 호출 후 정제된 결과 반환."""
    try:
        resp = await client.get(
            NAVER_NEWS_API,
            params={
                "query": keyword,
                "display": min(display, 100),
                "start": 1,
                "sort": "date",
            },
            headers=headers,
        )
        if resp.status_code != 200:
            logger.warning(
                "[news_collector] API error for '%s': %d %s",
                keyword, resp.status_code, resp.text[:200],
            )
            return []

        data = resp.json()
        items = data.get("items", [])
        results = []

        for item in items:
            title = _strip_html(item.get("title", ""))
            description = _strip_html(item.get("description", ""))
            article_url = item.get("originallink") or item.get("link", "")

            if not title or not article_url:
                continue

            # 도메인에서 언론사 추출
            publisher = ""
            domain_match = re.search(
                r"https?://(?:www\.)?([^/]+)", item.get("originallink", "") or article_url,
            )
            if domain_match:
                publisher = domain_match.group(1)

            published_at = _parse_pub_date(item.get("pubDate", ""))
            sentiment, sentiment_score = _analyze_sentiment(title, description)
            is_pr = _detect_pr(title, description)

            results.append({
                "article_url": article_url[:1000],
                "article_title": title[:500],
                "article_description": description[:2000] if description else None,
                "publisher": publisher[:200] if publisher else None,
                "published_at": published_at,
                "sentiment": sentiment,
                "sentiment_score": sentiment_score,
                "is_pr": is_pr,
            })

        logger.info("[news_collector] '%s' -> %d articles", keyword, len(results))
        return results

    except Exception as e:
        logger.warning("[news_collector] API exception for '%s': %s", keyword, e)
        return []


# ──────────────────────────────────────────────
# 메인 수집 함수
# ──────────────────────────────────────────────

async def collect_news_mentions(
    max_advertisers: int = 200,
    articles_per_brand: int = 10,
) -> dict:
    """Collect news articles for advertisers via Naver News Search API.

    Args:
        max_advertisers: 처리할 최대 광고주 수
        articles_per_brand: 광고주당 수집할 기사 수 (max 100)

    Returns:
        {"processed": N, "saved": N, "errors": N}
    """
    client_id = os.getenv("NAVER_SEARCH_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_SEARCH_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        logger.error("[news_collector] NAVER_SEARCH_CLIENT_ID/SECRET not set")
        return {"processed": 0, "saved": 0, "errors": 0}

    api_headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }

    total_processed = 0
    total_saved = 0
    total_errors = 0

    async with async_session() as session:
        now = datetime.now(UTC).replace(tzinfo=None)

        # 광고주 목록 가져오기 (brand_name 또는 name이 있는 광고주)
        adv_query = (
            select(Advertiser)
            .where(Advertiser.name.isnot(None))
            .order_by(Advertiser.id.asc())
            .limit(max_advertisers)
        )
        advertisers = (await session.execute(adv_query)).scalars().all()

        if not advertisers:
            logger.warning("[news_collector] No advertisers found")
            return {"processed": 0, "saved": 0, "errors": 0}

        logger.info(
            "[news_collector] Starting: %d advertisers, %d articles/brand",
            len(advertisers), articles_per_brand,
        )

        # 기존 article_url 캐시 (중복 방지 -- advertiser_id + article_url)
        existing_q = select(NewsMention.advertiser_id, NewsMention.article_url)
        existing_rows = (await session.execute(existing_q)).all()
        existing_set: set[tuple[int, str]] = {
            (row[0], row[1]) for row in existing_rows
        }

        async with httpx.AsyncClient(timeout=15.0) as http_client:
            for adv in advertisers:
                try:
                    # brand_name 우선, 없으면 name
                    keyword = (adv.brand_name or adv.name or "").strip()
                    if not keyword or len(keyword) < 2:
                        continue

                    articles = await _search_news(
                        http_client, keyword, api_headers, display=articles_per_brand,
                    )

                    for article in articles:
                        url = article["article_url"]

                        # 중복 체크: advertiser_id + article_url
                        if (adv.id, url) in existing_set:
                            continue

                        mention = NewsMention(
                            advertiser_id=adv.id,
                            source="naver_news",
                            article_url=url,
                            article_title=article["article_title"],
                            article_description=article["article_description"],
                            publisher=article["publisher"],
                            published_at=article["published_at"],
                            search_keyword=keyword,
                            sentiment=article["sentiment"],
                            sentiment_score=article["sentiment_score"],
                            is_pr=article["is_pr"],
                            collected_at=now,
                        )
                        session.add(mention)
                        existing_set.add((adv.id, url))
                        total_saved += 1

                    total_processed += 1

                    # 주기적 커밋
                    if total_processed % 50 == 0:
                        await session.commit()
                        logger.info(
                            "[news_collector] Progress: %d/%d advertisers, %d saved",
                            total_processed, len(advertisers), total_saved,
                        )

                    # API rate limit 방지
                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.warning(
                        "[news_collector] Error for advertiser %d (%s): %s",
                        adv.id, adv.name, e,
                    )
                    total_errors += 1

        await session.commit()

    logger.info(
        "[news_collector] Done: %d processed, %d saved, %d errors",
        total_processed, total_saved, total_errors,
    )
    return {
        "processed": total_processed,
        "saved": total_saved,
        "errors": total_errors,
    }


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    max_adv = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    arts = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    result = asyncio.run(
        collect_news_mentions(max_advertisers=max_adv, articles_per_brand=arts)
    )
    logger.info("Result: %s", result)
