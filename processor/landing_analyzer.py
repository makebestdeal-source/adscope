"""Phase 3F: 랜딩페이지 분석 — 사업자 정보 추출 + 마켓플레이스 판매자 식별.

광고의 랜딩 URL을 방문하여 푸터의 사업자 정보(상호명, 사업자등록번호, 대표자)를
추출하고, 마켓플레이스인 경우 실제 판매자를 식별한다.

사용법:
    from processor.landing_analyzer import batch_analyze_landings
    stats = await batch_analyze_landings(days=1, limit=100)
"""

from __future__ import annotations

import asyncio
import random
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger
from playwright.async_api import async_playwright
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from crawler.config import crawler_settings
from database import async_session, init_db
from database.models import AdDetail, AdSnapshot

# ──────────────────────────────────────────────
# 상수/도메인 맵
# ──────────────────────────────────────────────

# 마켓플레이스 도메인 → 판매자 추출 전략
MARKETPLACE_DOMAINS: dict[str, dict] = {
    "smartstore.naver.com": {
        "type": "url_path",
        "platform": "네이버 스마트스토어",
        "seller_selectors": [".seller_info .name", "._1xwOPp", "._3bkMM0"],
    },
    "brand.naver.com": {
        "type": "url_path",
        "platform": "네이버 브랜드스토어",
        "seller_selectors": [],
    },
    "shopping.naver.com": {
        "type": "dom",
        "platform": "네이버 쇼핑",
        "seller_selectors": [".seller_info .name", "[class*='mall'] a"],
    },
    "coupang.com": {
        "type": "dom",
        "platform": "쿠팡",
        "seller_selectors": [
            ".prod-sale-vendor-name a",
            "[class*='vendor'] a",
            ".seller-name a",
        ],
    },
    "11st.co.kr": {
        "type": "dom",
        "platform": "11번가",
        "seller_selectors": [".seller_info .name", ".c_seller a", "#sellerInfoArea a"],
    },
    "gmarket.co.kr": {
        "type": "dom",
        "platform": "G마켓",
        "seller_selectors": [".seller-info .seller_name", "#seller_name"],
    },
    "auction.co.kr": {
        "type": "dom",
        "platform": "옥션",
        "seller_selectors": [".seller-info .seller_name", ".seller_info a"],
    },
    "ssg.com": {
        "type": "dom",
        "platform": "SSG닷컴",
        "seller_selectors": [".cdtl_store_nm", ".seller_name"],
    },
    "musinsa.com": {
        "type": "dom",
        "platform": "무신사",
        "seller_selectors": [".brand_name a", ".product_brand a"],
    },
    "oliveyoung.co.kr": {
        "type": "dom",
        "platform": "올리브영",
        "seller_selectors": [".prd_brand_name", ".brand_name"],
    },
    "kurly.com": {
        "type": "dom",
        "platform": "마켓컬리",
        "seller_selectors": [".seller_info", "[class*='seller']"],
    },
    "29cm.co.kr": {
        "type": "dom",
        "platform": "29CM",
        "seller_selectors": [".brand_name", "[class*='brand'] a"],
    },
    "lotteon.com": {
        "type": "dom",
        "platform": "롯데온",
        "seller_selectors": [".seller_name", ".store_name"],
    },
}

# 제3자 플랫폼 (광고주 ≠ 페이지 소유자)
THIRD_PARTY_DOMAINS: set[str] = {
    # 설문/리서치
    "docs.google.com", "forms.gle", "typeform.com", "surveymonkey.com",
    "naver.me", "walla.my", "form.office.naver.com", "forms.office.com",
    # 이벤트
    "eventus.io", "festa.io", "onoffmix.com", "event-us.kr",
    # 단축 URL
    "bit.ly", "url.kr", "han.gl", "vo.la", "me2.do", "goo.gl",
    "t.co", "lnkd.in", "tinyurl.com",
    # 기타 중개
    "linktr.ee", "linktree.com", "campsite.bio",
}

# 연령제한 감지 키워드
AGE_GATE_INDICATORS: list[str] = [
    "19세 이상", "본인인증", "성인인증", "연령확인",
    "age verification", "are you over", "만 19세",
    "주류 구매", "담배 구매", "성인용품",
    "미성년자 구매 불가", "연령 인증이 필요",
]

# 코프로모션 구분자
CO_PROMO_SEPARATORS: list[str] = ["×", "x", "X", "콜라보", "collaboration", "제휴", "with"]

# 사업자등록번호 패턴
_BIZ_REG_PATTERN = re.compile(r"(\d{3})-?(\d{2})-?(\d{5})")


# ──────────────────────────────────────────────
# 결과 데이터 클래스
# ──────────────────────────────────────────────

@dataclass
class LandingAnalysis:
    """랜딩페이지 분석 결과."""

    url: str
    final_url: str | None = None
    page_type: str = "direct"  # direct / marketplace / third_party / age_restricted / error
    business_name: str | None = None
    business_registration: str | None = None
    representative: str | None = None
    seller_name: str | None = None
    platform_name: str | None = None
    co_promotion: list[str] | None = None
    page_title: str | None = None
    screenshot_path: str | None = None
    confidence: str = "low"  # high / medium / low
    analyzed_at: str | None = None
    error: str | None = None


# ──────────────────────────────────────────────
# 푸터 사업자 정보 추출 JS
# ──────────────────────────────────────────────

_FOOTER_EXTRACT_JS = """
() => {
    const result = {
        business_name: null,
        registration: null,
        representative: null,
        page_title: document.title || null
    };

    // 푸터 영역 찾기 (여러 후보)
    const footerEls = [
        document.querySelector('footer'),
        document.querySelector('[class*="footer"]'),
        document.querySelector('[id*="footer"]'),
        document.querySelector('.company_info'),
        document.querySelector('.corp_info'),
        document.querySelector('[class*="companyInfo"]'),
        document.querySelector('[class*="company-info"]'),
        document.querySelector('[class*="biz_info"]'),
        document.querySelector('[class*="business_info"]'),
    ].filter(Boolean);

    let searchText = footerEls.map(e => e.innerText || '').join('\\n');

    // 푸터를 못 찾으면 body 하단 20% 텍스트 사용
    if (!searchText.trim()) {
        const bodyText = document.body?.innerText || '';
        searchText = bodyText.slice(Math.floor(bodyText.length * 0.8));
    }

    if (!searchText.trim()) return result;

    // 사업자등록번호 (xxx-xx-xxxxx)
    const regMatch = searchText.match(/(\\d{3})-?(\\d{2})-?(\\d{5})/);
    if (regMatch) result.registration = regMatch[0];

    // 상호명/사업자명
    const namePatterns = [
        /(?:상호명?|사업자명?|회사명?|법인명?)\\s*[:：]?\\s*(.+)/,
        /(?:상호|사업자)\\s*[:：]\\s*(.+)/,
        /(?:Company|Company Name)\\s*[:：]?\\s*(.+)/i,
    ];
    for (const pat of namePatterns) {
        const m = searchText.match(pat);
        if (m) {
            const name = m[1].trim().split(/[\\n\\r|]/)[0].trim();
            if (name.length >= 2 && name.length <= 50) {
                result.business_name = name;
                break;
            }
        }
    }

    // 대표자
    const repPatterns = [
        /(?:대표자?|대표이사|CEO)\\s*[:：]?\\s*(.+)/i,
    ];
    for (const pat of repPatterns) {
        const m = searchText.match(pat);
        if (m) {
            const rep = m[1].trim().split(/[\\n\\r|]/)[0].trim();
            if (rep.length >= 2 && rep.length <= 30) {
                result.representative = rep;
                break;
            }
        }
    }

    return result;
}
"""


# ──────────────────────────────────────────────
# 도메인 유틸
# ──────────────────────────────────────────────

def _extract_domain(url: str) -> str | None:
    """URL에서 도메인 추출 (www. 제거)."""
    try:
        host = urlparse(url).hostname or ""
        return host.removeprefix("www.") or None
    except Exception:
        return None


def _match_marketplace(domain: str) -> str | None:
    """도메인이 마켓플레이스인지 확인. 매칭되면 키 반환."""
    if not domain:
        return None
    for mp_domain in MARKETPLACE_DOMAINS:
        if domain == mp_domain or domain.endswith("." + mp_domain):
            return mp_domain
    return None


def _is_third_party(domain: str) -> bool:
    """제3자 플랫폼(설문/이벤트/단축URL) 여부."""
    if not domain:
        return False
    for tp in THIRD_PARTY_DOMAINS:
        if domain == tp or domain.endswith("." + tp):
            return True
    return False


# ──────────────────────────────────────────────
# 코프로모션 감지
# ──────────────────────────────────────────────

def detect_co_promotion(ad_text: str | None) -> list[str] | None:
    """광고 텍스트에서 'A x B' 코프로모션 패턴 감지.

    Returns:
        [브랜드A, 브랜드B] 또는 None
    """
    if not ad_text:
        return None

    for sep in CO_PROMO_SEPARATORS:
        # "삼성 x 지마켓", "나이키 × 애플" 등 패턴
        # 구분자 앞뒤에 공백이 있어야 단어 구분자로 인정 (x는 단어의 일부일 수 있으므로)
        if sep in ("x", "X"):
            pattern = re.compile(rf"\s{re.escape(sep)}\s")
            if not pattern.search(ad_text):
                continue
            parts = pattern.split(ad_text, maxsplit=1)
        else:
            if sep not in ad_text:
                continue
            parts = ad_text.split(sep, 1)

        if len(parts) == 2:
            # 앞 브랜드: 마지막 단어(들)
            a = parts[0].strip()
            b = parts[1].strip()
            # 너무 길면 끝/앞 20자만
            a = a[-20:].strip() if len(a) > 20 else a
            b = b[:20].strip() if len(b) > 20 else b
            if len(a) >= 2 and len(b) >= 2:
                return [a, b]

    return None


# ──────────────────────────────────────────────
# 랜딩페이지 분석 (단건)
# ──────────────────────────────────────────────

async def analyze_landing_page(
    browser,
    url: str,
    ad_text: str | None = None,
    capture_screenshot: bool = False,
) -> LandingAnalysis:
    """단일 랜딩 URL 분석.

    1. 제3자 도메인 → page_type="third_party"
    2. 페이지 방문 → 연령제한 감지
    3. 마켓플레이스 → 판매자 추출
    4. 푸터 사업자 정보 추출
    5. 코프로모션 감지
    """
    result = LandingAnalysis(
        url=url,
        analyzed_at=datetime.utcnow().isoformat() + "Z",
    )

    domain = _extract_domain(url)
    if not domain:
        result.page_type = "error"
        result.error = "invalid_url"
        return result

    # 1) 제3자 도메인 체크 (페이지 방문 불필요)
    if _is_third_party(domain):
        result.page_type = "third_party"
        result.confidence = "high"
        # 광고 텍스트에서 코프로모션 체크만 수행
        result.co_promotion = detect_co_promotion(ad_text)
        return result

    # 2) 마켓플레이스 도메인 체크
    mp_key = _match_marketplace(domain)
    if mp_key:
        result.page_type = "marketplace"
        result.platform_name = MARKETPLACE_DOMAINS[mp_key]["platform"]

    # 3) 페이지 방문
    context = await browser.new_context(
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        ignore_https_errors=True,
    )
    try:
        page = await context.new_page()
        timeout = crawler_settings.landing_timeout_ms

        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            await page.wait_for_timeout(1500)  # JS 안정화 대기
        except Exception as e:
            result.page_type = "error"
            result.error = f"navigation_failed: {type(e).__name__}"
            result.confidence = "low"
            return result

        # 최종 URL (리다이렉트 추적)
        result.final_url = page.url

        # 4) 연령제한 감지
        try:
            body_text = await page.inner_text("body")
            body_lower = body_text.lower()
            for indicator in AGE_GATE_INDICATORS:
                if indicator in body_lower:
                    result.page_type = "age_restricted"
                    result.confidence = "medium"
                    # 도메인 fallback
                    result.business_name = domain
                    result.co_promotion = detect_co_promotion(ad_text)
                    return result
        except Exception:
            pass

        # 5) 마켓플레이스 판매자 추출
        if mp_key:
            seller = await _extract_marketplace_seller(page, mp_key)
            result.seller_name = seller

        # 6) 푸터 사업자 정보 추출
        try:
            footer_data = await page.evaluate(_FOOTER_EXTRACT_JS)
            result.business_name = footer_data.get("business_name")
            result.business_registration = footer_data.get("registration")
            result.representative = footer_data.get("representative")
            result.page_title = footer_data.get("page_title")
        except Exception as e:
            logger.debug(f"[landing] 푸터 추출 실패 ({url}): {e}")

        # 7) 신뢰도 결정
        if result.business_name and result.business_registration:
            result.confidence = "high"
        elif result.business_name or result.seller_name:
            result.confidence = "medium"
        else:
            result.confidence = "low"
            # 도메인 fallback
            if not result.business_name:
                result.business_name = domain

        # 8) 코프로모션 감지
        result.co_promotion = detect_co_promotion(ad_text)

        # 9) 스크린샷 (선택적)
        if capture_screenshot:
            try:
                ss_dir = Path(crawler_settings.landing_screenshot_dir)
                ss_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = ss_dir / f"landing_{timestamp}_{random.randint(100,999)}.png"
                await page.screenshot(path=str(filepath), full_page=False)
                result.screenshot_path = str(filepath)
            except Exception as e:
                logger.debug(f"[landing] 스크린샷 실패: {e}")

    finally:
        await context.close()

    return result


# ──────────────────────────────────────────────
# 마켓플레이스 판매자 추출
# ──────────────────────────────────────────────

async def _extract_marketplace_seller(page, mp_key: str) -> str | None:
    """마켓플레이스 페이지에서 실제 판매자/스토어명 추출."""
    config = MARKETPLACE_DOMAINS[mp_key]

    # URL path 기반 (smartstore.naver.com/스토어명/...)
    if config["type"] == "url_path":
        try:
            path = urlparse(page.url).path.strip("/")
            parts = path.split("/")
            if parts and parts[0]:
                store_name = parts[0]
                # 숫자만 있으면 무시 (상품ID)
                if not store_name.isdigit():
                    return store_name
        except Exception:
            pass

    # DOM 셀렉터 기반
    for selector in config.get("seller_selectors", []):
        try:
            el = await page.query_selector(selector)
            if el:
                text = (await el.inner_text()).strip()
                if text and 2 <= len(text) <= 50:
                    return text
        except Exception:
            continue

    return None


# ──────────────────────────────────────────────
# 배치 분석
# ──────────────────────────────────────────────

async def batch_analyze_landings(
    days: int = 1,
    limit: int = 100,
    capture_screenshot: bool | None = None,
) -> dict:
    """미분석 ad_details의 랜딩페이지 일괄 분석.

    Args:
        days: 최근 N일 이내 광고만 대상
        limit: 최대 분석할 광고 수
        capture_screenshot: 스크린샷 캡처 여부 (None이면 config 따름)

    Returns:
        {"total": int, "analyzed": int, "backfilled": int, "errors": int}
    """
    await init_db()

    if capture_screenshot is None:
        capture_screenshot = crawler_settings.landing_capture_screenshot

    cutoff = datetime.utcnow() - timedelta(days=days)

    # 1) 미분석 ad_details 조회 (landing_analysis가 없는 것)
    async with async_session() as session:
        q = (
            select(
                AdDetail.id,
                AdDetail.url,
                AdDetail.ad_text,
                AdDetail.advertiser_name_raw,
            )
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .where(AdSnapshot.captured_at >= cutoff)
            .where(AdDetail.url.isnot(None))
            .where(AdDetail.url != "")
            # extra_data에 landing_analysis 키가 없는 것만
            .where(
                ~AdDetail.extra_data.op("?")("landing_analysis")
                if hasattr(AdDetail.extra_data, "op")
                else True  # SQLite fallback
            )
            .order_by(AdDetail.id.desc())
            .limit(limit)
        )
        result = await session.execute(q)
        rows = result.all()

    if not rows:
        logger.info("[landing] 분석 대상 없음")
        return {"total": 0, "analyzed": 0, "backfilled": 0, "errors": 0}

    # URL 중복 제거 (같은 URL은 1회만 방문, 결과 공유)
    url_to_ids: dict[str, list[int]] = {}
    url_to_ad_text: dict[str, str | None] = {}
    url_to_current_name: dict[str, str | None] = {}

    for row in rows:
        ad_id, url, ad_text_val, name_raw = row
        if url not in url_to_ids:
            url_to_ids[url] = []
            url_to_ad_text[url] = ad_text_val
            url_to_current_name[url] = name_raw
        url_to_ids[url].append(ad_id)

    unique_urls = list(url_to_ids.keys())
    logger.info(
        f"[landing] {len(rows)}건 대상, {len(unique_urls)}개 고유 URL 분석 시작"
    )

    # 2) Playwright로 일괄 분석
    stats = {"total": len(rows), "analyzed": 0, "backfilled": 0, "errors": 0}
    sem = asyncio.Semaphore(crawler_settings.landing_concurrent)
    analyses: dict[str, LandingAnalysis] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        async def limited_analyze(url: str) -> tuple[str, LandingAnalysis]:
            async with sem:
                # 랜덤 딜레이 (rate limiting)
                await asyncio.sleep(random.uniform(0.5, 1.5))
                analysis = await analyze_landing_page(
                    browser, url, url_to_ad_text.get(url), capture_screenshot
                )
                return url, analysis

        results = await asyncio.gather(
            *[limited_analyze(u) for u in unique_urls],
            return_exceptions=True,
        )

        await browser.close()

    # 결과 수집
    for r in results:
        if isinstance(r, Exception):
            stats["errors"] += 1
            logger.warning(f"[landing] 분석 예외: {r}")
            continue
        url, analysis = r
        analyses[url] = analysis
        stats["analyzed"] += len(url_to_ids.get(url, []))

    # 3) DB 업데이트
    async with async_session() as session:
        for url, analysis in analyses.items():
            ad_ids = url_to_ids.get(url, [])
            analysis_dict = asdict(analysis)

            for ad_id in ad_ids:
                # extra_data에 landing_analysis 추가
                ad = await session.get(AdDetail, ad_id)
                if not ad:
                    continue

                extra = ad.extra_data or {}
                extra["landing_analysis"] = analysis_dict
                ad.extra_data = extra

                # advertiser_name_raw가 NULL이면 backfill
                if not ad.advertiser_name_raw:
                    backfill_name = (
                        analysis.seller_name
                        or analysis.business_name
                    )
                    if backfill_name and analysis.page_type != "error":
                        ad.advertiser_name_raw = backfill_name
                        stats["backfilled"] += 1
                        logger.debug(
                            f"[landing] backfill ad#{ad_id}: {backfill_name}"
                        )

        await session.commit()

    logger.info(
        f"[landing] 완료: {stats['analyzed']}건 분석, "
        f"{stats['backfilled']}건 광고주명 보충, {stats['errors']}건 오류"
    )
    return stats
