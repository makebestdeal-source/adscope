"""Naver Shopping 상품 데이터 수집기 (API 방식).

네이버 검색 API(openapi.naver.com/v1/search/shop.json)를 사용하여
쇼핑 키워드별 상품 데이터를 수집.

수집 데이터: 상품명, 가격, 판매처, 상품URL, 이미지, 카테고리, 브랜드
→ SmartStoreSnapshot 테이블에 저장 → sales_estimator가 일별 델타로 판매량 추정.

방식:
  - 네이버 오픈API (검색 > 쇼핑) — 키워드당 최대 100건
  - Playwright 불필요, httpx로 직접 호출
  - 하루 25,000건 호출 가능

보완:
  - Phase 2: ad_details 테이블에서 스마트스토어 URL 발굴 → 추적 대상 확대
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import UTC, datetime

import httpx
from sqlalchemy import select, func

from database import async_session
from database.models import (
    AdDetail,
    AdSnapshot,
    Advertiser,
    ShoppingKeyword,
    SmartStoreSnapshot,
    SmartStoreTrackedProduct,
)

logger = logging.getLogger(__name__)

NAVER_SHOP_API = "https://openapi.naver.com/v1/search/shop.json"
PRODUCTS_PER_KEYWORD = 50  # API는 최대 100까지 지원
DEFAULT_BATCH_SIZE = 50


# ──────────────────────────────────────────────
# 네이버 쇼핑 검색 API 호출
# ──────────────────────────────────────────────

async def _search_keyword_api(
    client: httpx.AsyncClient,
    keyword: str,
    headers: dict,
    display: int = PRODUCTS_PER_KEYWORD,
) -> list[dict]:
    """네이버 검색 API로 쇼핑 상품 조회."""
    try:
        resp = await client.get(
            NAVER_SHOP_API,
            params={"query": keyword, "display": display, "sort": "sim"},
            headers=headers,
        )
        if resp.status_code != 200:
            logger.warning(
                "[shop_product] API error for '%s': %d %s",
                keyword, resp.status_code, resp.text[:100],
            )
            return []

        data = resp.json()
        items = data.get("items", [])

        products = []
        for i, item in enumerate(items):
            title = re.sub(r"<[^>]+>", "", item.get("title", "")).strip()
            if not title or len(title) < 2:
                continue

            price = None
            try:
                price = int(item.get("lprice", 0))
                if price <= 0:
                    price = None
            except (ValueError, TypeError):
                pass

            link = item.get("link", "")
            mall = item.get("mallName", "")
            image = item.get("image", "")
            brand = item.get("brand", "")

            # 카테고리 조합
            cats = [item.get(f"category{n}", "") for n in range(1, 5)]
            category = " > ".join(c for c in cats if c)

            products.append({
                "product_name": title[:500],
                "price": price,
                "store_name": mall[:200] if mall else None,
                "product_url": link,
                "review_count": 0,  # 검색 API에서는 미제공
                "purchase_cnt": 0,
                "category_name": category[:500] if category else None,
                "seller_grade": None,
                "ranking_position": i + 1,
                "ranking_category": keyword,
                "image_url": image,
                "brand": brand,
                "product_id": item.get("productId", ""),
                "product_type": item.get("productType", ""),
            })

        logger.info("[shop_product] '%s' -> %d products via API", keyword, len(products))
        return products

    except Exception as e:
        logger.warning("[shop_product] API exception for '%s': %s", keyword, e)
        return []


# ──────────────────────────────────────────────
# Phase 2: ad_details에서 스마트스토어 URL 발굴
# ──────────────────────────────────────────────

async def _discover_smartstore_from_ads(session) -> dict:
    """naver_shopping 채널 광고에서 smartstore URL 추출 → tracked_products 등록."""
    snap_q = select(AdSnapshot.id).where(AdSnapshot.channel == "naver_shopping")
    snap_ids = [r[0] for r in (await session.execute(snap_q)).all()]
    if not snap_ids:
        return {"discovered": 0}

    ad_q = (
        select(AdDetail.url, AdDetail.advertiser_name_raw, AdDetail.ad_text)
        .where(AdDetail.snapshot_id.in_(snap_ids))
        .where(
            AdDetail.url.like("%smartstore.naver.com%")
            | AdDetail.url.like("%brand.naver.com%")
        )
        .distinct()
    )
    rows = (await session.execute(ad_q)).all()

    existing_q = select(SmartStoreTrackedProduct.product_url)
    existing = {r[0] for r in (await session.execute(existing_q)).all()}

    discovered = 0
    for ad_url, adv_name_raw, ad_text in rows:
        if not ad_url:
            continue
        if "adcr.naver.com" in ad_url or "ader.naver.com" in ad_url:
            continue

        store_url = re.sub(r"/products/.*$", "", ad_url)
        if store_url in existing:
            continue

        store_match = re.search(
            r"(?:smartstore|brand)\.naver\.com/([^/?#]+)", store_url
        )
        store_name = store_match.group(1) if store_match else ""

        adv_q2 = (
            select(Advertiser.id)
            .where(func.lower(Advertiser.name) == (adv_name_raw or "").lower())
            .limit(1)
        )
        adv_row = (await session.execute(adv_q2)).scalar_one_or_none()

        tp = SmartStoreTrackedProduct(
            user_id=1,
            advertiser_id=adv_row,
            product_url=store_url,
            store_name=store_name[:200] if store_name else None,
            product_name=(ad_text or "")[:500] or None,
            label="auto:ad_discovery",
            is_active=True,
        )
        session.add(tp)
        existing.add(store_url)
        discovered += 1

    if discovered:
        await session.commit()
        logger.info("[shop_product] Phase 2: %d new stores from ad_details", discovered)

    return {"discovered": discovered}


# ──────────────────────────────────────────────
# 광고주 매칭
# ──────────────────────────────────────────────

async def _build_advertiser_lookup(session) -> dict[str, int]:
    """store_name/mall_name → advertiser_id 매핑."""
    lookup: dict[str, int] = {}

    snap_q = (
        select(SmartStoreSnapshot.store_name, SmartStoreSnapshot.advertiser_id)
        .where(SmartStoreSnapshot.advertiser_id > 0)
        .where(SmartStoreSnapshot.store_name.isnot(None))
        .distinct()
    )
    for store_name, adv_id in (await session.execute(snap_q)).all():
        if store_name:
            lookup[store_name.strip().lower()] = adv_id

    adv_q = select(Advertiser.id, Advertiser.name, Advertiser.smartstore_url).where(
        Advertiser.smartstore_url.isnot(None)
    )
    for adv_id, adv_name, surl in (await session.execute(adv_q)).all():
        match = re.search(r"(?:smartstore|brand)\.naver\.com/([^/?#]+)", surl or "")
        if match:
            lookup[match.group(1).strip().lower()] = adv_id
        if adv_name:
            lookup[adv_name.strip().lower()] = adv_id

    return lookup


def _match_advertiser(product: dict, lookup: dict[str, int]) -> int:
    store = product.get("store_name", "")
    if store and store.strip().lower() in lookup:
        return lookup[store.strip().lower()]
    url = product.get("product_url", "")
    match = re.search(r"(?:smartstore|brand)\.naver\.com/([^/?#]+)", url)
    if match and match.group(1).strip().lower() in lookup:
        return lookup[match.group(1).strip().lower()]
    return 0


# ──────────────────────────────────────────────
# 메인 수집 함수
# ──────────────────────────────────────────────

async def collect_shopping_products(
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict:
    """쇼핑 키워드 배치 수집 (API 방식) + 광고 기반 스토어 발굴.

    Phase 1: 네이버 검색 API → 상품 스냅샷 저장
    Phase 2: ad_details에서 스마트스토어 URL 발굴

    Returns: {"keywords_processed": N, "products_saved": N, "stores_discovered": N, "errors": N}
    """
    client_id = os.getenv("NAVER_SEARCH_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_SEARCH_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        logger.error("[shop_product] NAVER_SEARCH_CLIENT_ID/SECRET not set")
        return {"keywords_processed": 0, "products_saved": 0, "stores_discovered": 0, "errors": 0}

    api_headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }

    async with async_session() as session:
        now = datetime.now(UTC).replace(tzinfo=None)

        # Phase 2: 광고에서 스마트스토어 발굴
        discovery = await _discover_smartstore_from_ads(session)

        # Phase 1: 키워드 검색
        kw_query = (
            select(ShoppingKeyword)
            .where(ShoppingKeyword.is_active == True)  # noqa: E712
            .order_by(
                ShoppingKeyword.last_crawled_at.asc().nullsfirst(),
                ShoppingKeyword.priority.asc(),
            )
            .limit(batch_size)
        )
        kw_rows = (await session.execute(kw_query)).scalars().all()

        if not kw_rows:
            logger.warning("[shop_product] No active shopping keywords")
            return {
                "keywords_processed": 0,
                "products_saved": 0,
                "stores_discovered": discovery.get("discovered", 0),
                "errors": 0,
            }

        logger.info("[shop_product] Starting batch: %d keywords", len(kw_rows))

        adv_lookup = await _build_advertiser_lookup(session)
        total_saved = 0
        total_errors = 0

        async with httpx.AsyncClient(timeout=15.0) as http_client:
            for kw in kw_rows:
                try:
                    products = await _search_keyword_api(
                        http_client, kw.keyword, api_headers
                    )

                    for prod in products:
                        try:
                            advertiser_id = _match_advertiser(prod, adv_lookup)
                            purl = prod.get("product_url", "")

                            # 이전 스냅샷 델타
                            review_delta = 0
                            purchase_delta = 0
                            if purl:
                                prev_q = (
                                    select(SmartStoreSnapshot)
                                    .where(SmartStoreSnapshot.product_url == purl)
                                    .order_by(SmartStoreSnapshot.captured_at.desc())
                                    .limit(1)
                                )
                                prev = (await session.execute(prev_q)).scalar_one_or_none()
                                if prev:
                                    review_delta = max(0, (prod["review_count"] or 0) - (prev.review_count or 0))
                                    purchase_delta = max(0, (prod["purchase_cnt"] or 0) - (prev.purchase_cnt or 0))

                            snapshot = SmartStoreSnapshot(
                                advertiser_id=advertiser_id,
                                store_name=prod.get("store_name"),
                                product_url=purl,
                                product_name=prod.get("product_name"),
                                review_count=prod.get("review_count"),
                                review_delta=review_delta,
                                price=prod.get("price"),
                                purchase_cnt=prod.get("purchase_cnt"),
                                purchase_cnt_delta=purchase_delta,
                                category_name=prod.get("category_name"),
                                seller_grade=prod.get("seller_grade"),
                                ranking_position=prod.get("ranking_position"),
                                ranking_category=prod.get("ranking_category"),
                                captured_at=now,
                            )
                            session.add(snapshot)
                            total_saved += 1

                        except Exception as e:
                            logger.debug("[shop_product] save error: %s", e)
                            total_errors += 1

                    kw.last_crawled_at = now

                    if total_saved % 200 == 0 and total_saved > 0:
                        await session.commit()

                    # API 호출 간격 (rate limit 방지)
                    await asyncio.sleep(0.1)

                except Exception as e:
                    logger.warning("[shop_product] keyword '%s' error: %s", kw.keyword, e)
                    total_errors += 1

        await session.commit()

        logger.info(
            "[shop_product] Done: %d keywords, %d products, %d stores, %d errors",
            len(kw_rows), total_saved, discovery.get("discovered", 0), total_errors,
        )
        return {
            "keywords_processed": len(kw_rows),
            "products_saved": total_saved,
            "stores_discovered": discovery.get("discovered", 0),
            "errors": total_errors,
        }


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    batch = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    result = asyncio.run(collect_shopping_products(batch_size=batch))
    print(f"Result: {result}")
