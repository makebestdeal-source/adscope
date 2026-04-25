"""Shopping product detail crawler -- enrich snapshots with review/purchase data.

smartstore_snapshots 테이블에서 review_count=0 인 오늘 스냅샷의 상품 URL을 방문하여
리뷰수, 구매건수, 평균평점, 판매자등급을 수집하고, 일일 판매량을 추정한다.

수집 방식:
  - Playwright headless + stealth (네이버 차단 방지)
  - 상품 페이지 로드 후 window.__NEXT_DATA__ 추출 (가장 안정적)
  - 네트워크 인터셉트로 product JSON API 응답 캡처 (보조)
  - 두 소스를 병합하여 최종 데이터 구성

판매량 추정:
  - 이전일 같은 product_url 의 review_count 와 비교
  - review_delta * 카테고리별 배수 = estimated_daily_sales
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from datetime import UTC, datetime, timedelta

from playwright.async_api import async_playwright
from sqlalchemy import and_, select, func

from database import async_session
from database.models import SmartStoreSnapshot

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 카테고리별 리뷰-판매 배수 (리뷰 1건 = 실제 구매 N건 추정)
# ──────────────────────────────────────────────
CATEGORY_MULTIPLIER: dict[str, int] = {
    "식품": 10,
    "생활/건강": 8,
    "생활": 8,
    "건강": 8,
    "패션의류": 15,
    "패션잡화": 15,
    "패션": 15,
    "의류": 15,
    "디지털/가전": 12,
    "디지털": 12,
    "가전": 12,
    "전자": 12,
    "가구/인테리어": 8,
    "가구": 8,
    "인테리어": 8,
    "출산/육아": 10,
    "출산": 10,
    "육아": 10,
    "스포츠/레저": 12,
    "스포츠": 12,
    "레저": 12,
    "화장품/미용": 10,
    "화장품": 10,
    "미용": 10,
    "뷰티": 10,
    "default": 10,
}

# 랜덤 User-Agent 풀
_USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) "
        "Gecko/20100101 Firefox/132.0"
    ),
]


def _get_multiplier(category_name: str | None) -> int:
    """카테고리명에서 배수 결정. 부분 매칭 지원."""
    if not category_name:
        return CATEGORY_MULTIPLIER["default"]
    cat_lower = category_name.lower()
    for key, val in CATEGORY_MULTIPLIER.items():
        if key == "default":
            continue
        if key in cat_lower:
            return val
    return CATEGORY_MULTIPLIER["default"]


# ──────────────────────────────────────────────
# 상품 페이지에서 데이터 추출
# ──────────────────────────────────────────────

async def _extract_from_page(page) -> dict:
    """window.__NEXT_DATA__ 및 네트워크 캡처 데이터를 병합하여 상품 정보 추출."""
    data: dict = {}

    # 1) window.__NEXT_DATA__ 에서 추출 (가장 안정적)
    try:
        next_data = await page.evaluate("""() => {
            try {
                if (window.__NEXT_DATA__) {
                    return JSON.stringify(window.__NEXT_DATA__);
                }
            } catch(e) {}
            return null;
        }""")
        if next_data:
            parsed = json.loads(next_data)
            _extract_from_next_data(parsed, data)
    except Exception as e:
        logger.debug("[shop_detail] __NEXT_DATA__ extract error: %s", str(e)[:100])

    # 2) 페이지 HTML 에서 JSON-LD / 메타 데이터 추출 (보조)
    if not data.get("review_count"):
        try:
            meta_data = await page.evaluate("""() => {
                const result = {};

                // JSON-LD (schema.org Product)
                const ldScripts = document.querySelectorAll('script[type="application/ld+json"]');
                ldScripts.forEach(s => {
                    try {
                        const d = JSON.parse(s.textContent);
                        if (d['@type'] === 'Product' || d.aggregateRating) {
                            if (d.aggregateRating) {
                                result.ratingValue = d.aggregateRating.ratingValue;
                                result.reviewCount = d.aggregateRating.reviewCount;
                            }
                        }
                    } catch(e) {}
                });

                // og:title 등 메타 태그
                const ogTitle = document.querySelector('meta[property="og:title"]');
                if (ogTitle) result.ogTitle = ogTitle.content;

                return result;
            }""")
            if meta_data:
                if meta_data.get("reviewCount") and not data.get("review_count"):
                    try:
                        data["review_count"] = int(meta_data["reviewCount"])
                    except (ValueError, TypeError):
                        pass
                if meta_data.get("ratingValue") and not data.get("avg_rating"):
                    try:
                        data["avg_rating"] = float(meta_data["ratingValue"])
                    except (ValueError, TypeError):
                        pass
        except Exception as e:
            logger.debug("[shop_detail] meta extract error: %s", str(e)[:100])

    return data


def _extract_from_next_data(next_data: dict, out: dict) -> None:
    """__NEXT_DATA__ 구조에서 상품 상세 정보 추출."""
    # props.pageProps.initialState.product.A 등의 구조
    try:
        props = next_data.get("props", {})
        page_props = props.get("pageProps", {})

        # 방법 A: initialState 구조 (일반적인 스마트스토어)
        initial_state = page_props.get("initialState", {})

        # product 정보
        product = initial_state.get("product", {})
        if isinstance(product, dict):
            # product.A 또는 product 자체
            product_a = product.get("A", product)
            if isinstance(product_a, dict):
                _extract_product_fields(product_a, out)

        # 리뷰 정보
        review_section = initial_state.get("review", {})
        if isinstance(review_section, dict):
            total = review_section.get("totalCount") or review_section.get("total")
            if total is not None and not out.get("review_count"):
                try:
                    out["review_count"] = int(total)
                except (ValueError, TypeError):
                    pass
            avg = review_section.get("averageScore") or review_section.get("averageStarScore")
            if avg is not None and not out.get("avg_rating"):
                try:
                    out["avg_rating"] = float(avg)
                except (ValueError, TypeError):
                    pass

        # 방법 B: initialData 구조 (일부 브랜드스토어)
        initial_data = page_props.get("initialData", {})
        if isinstance(initial_data, dict) and not out.get("review_count"):
            _extract_product_fields(initial_data, out)

        # 방법 C: 직접 pageProps 에 데이터가 있는 경우
        if not out.get("review_count"):
            _extract_product_fields(page_props, out)

    except Exception as e:
        logger.debug("[shop_detail] __NEXT_DATA__ parse error: %s", str(e)[:100])


def _extract_product_fields(product: dict, out: dict) -> None:
    """상품 dict 에서 필요한 필드들을 추출."""
    # Review count
    if not out.get("review_count"):
        for key in (
            "totalReviewCount", "reviewCount", "totalReviewCnt",
            "cumulativeReviewCount", "reviewAmount",
        ):
            val = product.get(key)
            if isinstance(val, dict):
                # reviewAmount: {totalReviewCount: N, averageReviewScore: X}
                val = val.get("totalReviewCount") or val.get("totalCount")
            if val is not None:
                try:
                    out["review_count"] = int(val)
                    break
                except (ValueError, TypeError):
                    continue

    # Average rating
    if not out.get("avg_rating"):
        for key in (
            "averageReviewScore", "avgRating", "averageStarScore",
            "ratingAverage", "averageScore",
        ):
            val = product.get(key)
            if isinstance(val, dict):
                val = val.get("averageReviewScore") or val.get("averageStarScore")
            if val is not None:
                try:
                    out["avg_rating"] = round(float(val), 2)
                    break
                except (ValueError, TypeError):
                    continue

    # Purchase count
    if not out.get("purchase_cnt"):
        for key in (
            "totalPurchaseCnt", "purchaseCnt", "cumulationSaleCount",
            "cumulativePurchaseCount", "purchaseCount",
        ):
            val = product.get(key)
            if val is not None:
                try:
                    out["purchase_cnt"] = int(val)
                    break
                except (ValueError, TypeError):
                    continue

    # Seller grade
    if not out.get("seller_grade"):
        channel = product.get("channel") or {}
        if isinstance(channel, dict):
            grade = channel.get("sellerGrade") or channel.get("grade")
            if grade:
                out["seller_grade"] = str(grade)
        # 직접 필드
        if not out.get("seller_grade"):
            for key in ("sellerGrade", "seller_grade", "grade"):
                val = product.get(key)
                if val:
                    out["seller_grade"] = str(val)
                    break

    # Category name
    if not out.get("category_name"):
        cat = product.get("category") or {}
        if isinstance(cat, dict):
            cat_name = cat.get("wholeCategoryName") or cat.get("categoryName")
            if cat_name:
                out["category_name"] = str(cat_name)
        if not out.get("category_name"):
            for key in ("wholeCategoryName", "categoryName", "category_name"):
                val = product.get(key)
                if val and isinstance(val, str):
                    out["category_name"] = val
                    break

    # 재귀적으로 중첩 구조 탐색 (1 depth 만)
    for key, val in product.items():
        if isinstance(val, dict) and not out.get("review_count"):
            _extract_product_fields(val, out)
            if out.get("review_count"):
                break


# ──────────────────────────────────────────────
# 네트워크 인터셉트 핸들러
# ──────────────────────────────────────────────

def _make_response_handler(captured: dict):
    """네트워크 응답 인터셉트 핸들러 팩토리."""

    async def _on_response(response):
        try:
            if response.status != 200:
                return
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            url = response.url

            # 스마트스토어 API 엔드포인트 매칭
            endpoints_of_interest = (
                "/products/", "/product-detail", "/product-info",
                "/review/", "/reviews", "/channel/",
                "simple-products", "best-products",
            )
            if not any(ep in url for ep in endpoints_of_interest):
                return

            body = await response.json()
            if not isinstance(body, dict):
                return

            # 리뷰 관련 API
            if "/review" in url:
                captured["review_api"] = body
            # 상품 상세 API
            elif "/product" in url:
                captured["product_api"] = body
            # 채널(판매자) 정보
            elif "/channel" in url:
                captured["channel_api"] = body

        except Exception:
            pass

    return _on_response


def _merge_network_data(captured: dict, out: dict) -> None:
    """네트워크 캡처된 JSON 데이터를 out 에 병합."""
    # 리뷰 API
    review_api = captured.get("review_api", {})
    if isinstance(review_api, dict):
        if not out.get("review_count"):
            for key in ("totalCount", "totalElements", "totalReviewCount"):
                val = review_api.get(key)
                if val is not None:
                    try:
                        out["review_count"] = int(val)
                        break
                    except (ValueError, TypeError):
                        continue
        if not out.get("avg_rating"):
            for key in ("averageScore", "averageStarScore", "ratingAverage"):
                val = review_api.get(key)
                if val is not None:
                    try:
                        out["avg_rating"] = round(float(val), 2)
                        break
                    except (ValueError, TypeError):
                        continue

    # 상품 API
    product_api = captured.get("product_api", {})
    if isinstance(product_api, dict):
        _extract_product_fields(product_api, out)

    # 채널 API
    channel_api = captured.get("channel_api", {})
    if isinstance(channel_api, dict) and not out.get("seller_grade"):
        grade = channel_api.get("sellerGrade") or channel_api.get("grade")
        if grade:
            out["seller_grade"] = str(grade)


# ──────────────────────────────────────────────
# DB: 대상 URL 조회 & 업데이트
# ──────────────────────────────────────────────

async def _get_target_urls(max_products: int) -> list[dict]:
    """오늘 수집된 스냅샷 중 review_count=0 인 고유 product_url 목록 반환."""
    today_start = datetime.now(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None,
    )

    async with async_session() as session:
        # 오늘 수집된 스냅샷 중 review_count 가 없는(=0) 것
        query = (
            select(
                SmartStoreSnapshot.product_url,
                func.min(SmartStoreSnapshot.id).label("min_id"),
                func.max(SmartStoreSnapshot.advertiser_id).label("advertiser_id"),
                func.max(SmartStoreSnapshot.category_name).label("category_name"),
            )
            .where(
                and_(
                    SmartStoreSnapshot.captured_at >= today_start,
                    SmartStoreSnapshot.product_url.isnot(None),
                    SmartStoreSnapshot.product_url != "",
                )
            )
            .where(
                (SmartStoreSnapshot.review_count == 0)
                | (SmartStoreSnapshot.review_count.is_(None))
            )
            .group_by(SmartStoreSnapshot.product_url)
            .order_by(func.min(SmartStoreSnapshot.id).asc())
            .limit(max_products)
        )
        rows = (await session.execute(query)).all()

        targets = []
        for row in rows:
            url = row.product_url
            if not url:
                continue
            # smartstore / brand store URL 만 대상
            if "smartstore.naver.com" not in url and "brand.naver.com" not in url:
                continue
            targets.append({
                "product_url": url,
                "advertiser_id": row.advertiser_id,
                "category_name": row.category_name,
            })

        logger.info("[shop_detail] Found %d target URLs to enrich", len(targets))
        return targets


async def _update_snapshots(
    product_url: str,
    enriched: dict,
    yesterday_review: int | None,
) -> int:
    """해당 product_url 의 오늘 스냅샷 레코드들을 UPDATE."""
    today_start = datetime.now(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None,
    )

    updated = 0
    async with async_session() as session:
        query = (
            select(SmartStoreSnapshot)
            .where(
                and_(
                    SmartStoreSnapshot.product_url == product_url,
                    SmartStoreSnapshot.captured_at >= today_start,
                )
            )
        )
        result = await session.execute(query)
        snapshots = result.scalars().all()

        for snap in snapshots:
            if enriched.get("review_count") is not None:
                snap.review_count = enriched["review_count"]
            if enriched.get("avg_rating") is not None:
                snap.avg_rating = enriched["avg_rating"]
            if enriched.get("purchase_cnt") is not None:
                snap.purchase_cnt = enriched["purchase_cnt"]
            if enriched.get("seller_grade"):
                snap.seller_grade = enriched["seller_grade"]
            if enriched.get("category_name") and not snap.category_name:
                snap.category_name = enriched["category_name"]

            # Delta & 판매량 추정
            review_count = enriched.get("review_count") or 0
            if yesterday_review is not None and review_count > 0:
                review_delta = max(0, review_count - yesterday_review)
                snap.review_delta = review_delta

                multiplier = _get_multiplier(
                    enriched.get("category_name") or snap.category_name
                )
                snap.estimated_daily_sales = review_delta * multiplier
                snap.estimation_method = "review_delta"

            # purchase_cnt delta
            purchase_cnt = enriched.get("purchase_cnt")
            if purchase_cnt is not None and snap.purchase_cnt_delta in (None, 0):
                # 이전일 데이터 비교가 가능할 때만
                pass  # _get_yesterday_purchase_cnt 는 아래 로직에서 처리

            updated += 1

        if updated:
            await session.commit()

    return updated


async def _get_yesterday_data(product_url: str) -> dict:
    """이전일 같은 product_url 의 스냅샷에서 review_count, purchase_cnt 조회."""
    today_start = datetime.now(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None,
    )
    yesterday_start = today_start - timedelta(days=1)

    async with async_session() as session:
        query = (
            select(SmartStoreSnapshot)
            .where(
                and_(
                    SmartStoreSnapshot.product_url == product_url,
                    SmartStoreSnapshot.captured_at >= yesterday_start,
                    SmartStoreSnapshot.captured_at < today_start,
                )
            )
            .order_by(SmartStoreSnapshot.captured_at.desc())
            .limit(1)
        )
        prev = (await session.execute(query)).scalar_one_or_none()

        if prev:
            return {
                "review_count": prev.review_count,
                "purchase_cnt": prev.purchase_cnt,
            }
    return {}


# ──────────────────────────────────────────────
# 메인 수집 함수
# ──────────────────────────────────────────────

async def enrich_snapshots(
    batch_size: int = 100,
    max_products: int = 500,
) -> dict:
    """상품 페이지를 방문하여 review/purchase 데이터를 수집하고 판매량 추정.

    Args:
        batch_size: 한 브라우저 세션에서 처리할 최대 상품 수
        max_products: 전체 처리 대상 최대 수

    Returns:
        {"total_targets": N, "enriched": N, "skipped": N, "errors": N}
    """
    targets = await _get_target_urls(max_products)
    if not targets:
        logger.info("[shop_detail] No targets to enrich")
        return {"total_targets": 0, "enriched": 0, "skipped": 0, "errors": 0}

    enriched_count = 0
    skipped_count = 0
    error_count = 0
    total = len(targets)

    # 배치 단위로 브라우저 세션 관리
    for batch_start in range(0, total, batch_size):
        batch = targets[batch_start : batch_start + batch_size]
        logger.info(
            "[shop_detail] Processing batch %d-%d / %d",
            batch_start + 1,
            min(batch_start + batch_size, total),
            total,
        )

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = await browser.new_context(
                    locale="ko-KR",
                    timezone_id="Asia/Seoul",
                    user_agent=random.choice(_USER_AGENTS),
                )

                # stealth: webdriver 속성 숨기기
                await context.add_init_script(
                    'Object.defineProperty(navigator, "webdriver", '
                    '{get: () => undefined});'
                )

                # playwright-stealth 패키지 사용 (설치되어 있으면)
                try:
                    from playwright_stealth import Stealth

                    stealth = Stealth(
                        navigator_languages_override=("ko-KR", "ko"),
                        navigator_platform_override="Win32",
                        navigator_user_agent=False,
                        navigator_webdriver=True,
                        navigator_plugins=True,
                        navigator_permissions=True,
                        chrome_app=True,
                        chrome_csi=True,
                        chrome_load_times=True,
                        chrome_runtime=False,
                        iframe_content_window=True,
                        media_codecs=True,
                        navigator_hardware_concurrency=True,
                        webgl_vendor=True,
                    )
                    scripts = list(stealth.enabled_scripts)
                    for script in scripts:
                        await context.add_init_script(script)
                    logger.debug(
                        "[shop_detail] playwright-stealth applied (%d scripts)",
                        len(scripts),
                    )
                except ImportError:
                    logger.debug("[shop_detail] playwright-stealth not installed, using basic stealth")
                except Exception as e:
                    logger.debug("[shop_detail] stealth init error: %s", str(e)[:80])

                try:
                    for i, target in enumerate(batch):
                        product_url = target["product_url"]
                        try:
                            # 네트워크 캡처 저장소
                            captured_json: dict = {}

                            page = await context.new_page()
                            page.on("response", _make_response_handler(captured_json))

                            try:
                                logger.debug(
                                    "[shop_detail] [%d/%d] Visiting: %s",
                                    batch_start + i + 1,
                                    total,
                                    product_url[:100],
                                )

                                await page.goto(
                                    product_url,
                                    wait_until="domcontentloaded",
                                    timeout=30000,
                                )
                                # 데이터 로딩 대기
                                await page.wait_for_timeout(2000)

                                # 데이터 추출
                                enriched = await _extract_from_page(page)

                                # 네트워크 캡처 데이터 병합
                                _merge_network_data(captured_json, enriched)

                                # 카테고리 정보 보존
                                if not enriched.get("category_name") and target.get("category_name"):
                                    enriched["category_name"] = target["category_name"]

                                # 유효 데이터가 있는지 확인
                                has_data = (
                                    enriched.get("review_count")
                                    or enriched.get("purchase_cnt")
                                    or enriched.get("avg_rating")
                                    or enriched.get("seller_grade")
                                )

                                if not has_data:
                                    skipped_count += 1
                                    logger.debug(
                                        "[shop_detail] No data extracted from %s",
                                        product_url[:80],
                                    )
                                    continue

                                # 이전일 데이터 조회
                                yesterday = await _get_yesterday_data(product_url)
                                yesterday_review = yesterday.get("review_count")

                                # DB 업데이트
                                updated = await _update_snapshots(
                                    product_url, enriched, yesterday_review,
                                )
                                if updated:
                                    enriched_count += 1
                                    logger.info(
                                        "[shop_detail] [%d/%d] Enriched: reviews=%s, "
                                        "purchases=%s, rating=%s, grade=%s | %s",
                                        batch_start + i + 1,
                                        total,
                                        enriched.get("review_count"),
                                        enriched.get("purchase_cnt"),
                                        enriched.get("avg_rating"),
                                        enriched.get("seller_grade"),
                                        product_url[:60],
                                    )
                                else:
                                    skipped_count += 1

                            finally:
                                await page.close()

                            # Rate limiting: 1~3초 랜덤 딜레이
                            delay = random.uniform(1.0, 3.0)
                            await asyncio.sleep(delay)

                        except Exception as e:
                            error_count += 1
                            logger.warning(
                                "[shop_detail] Error processing %s: %s",
                                product_url[:80],
                                str(e)[:120],
                            )
                            continue

                finally:
                    await context.close()
                    await browser.close()

        except Exception as e:
            error_count += len(batch)
            logger.warning(
                "[shop_detail] Browser session error: %s",
                str(e)[:120],
            )

    result = {
        "total_targets": total,
        "enriched": enriched_count,
        "skipped": skipped_count,
        "errors": error_count,
    }
    logger.info(
        "[shop_detail] Done: targets=%d enriched=%d skipped=%d errors=%d",
        total, enriched_count, skipped_count, error_count,
    )
    return result


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    batch = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    maxp = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    result = asyncio.run(enrich_snapshots(batch_size=batch, max_products=maxp))
    print(result)
