"""Phone Chrome CDP 기반 모바일 광고 수집.

실제 스마트폰의 Chrome 브라우저에 CDP(Chrome DevTools Protocol)로 연결하여
모바일 웹사이트의 광고 네트워크 응답을 인터셉트합니다.

장점:
  - 실제 폰 하드웨어/네트워크/UA (완벽한 모바일 환경)
  - 루팅/CA 인증서 불필요 (mitmproxy 대비)
  - Playwright와 동일한 네트워크 인터셉트 방식
  - 기존 파서 로직 100% 재사용

사전 설정:
  1. 폰 USB 디버깅 활성화
  2. adb devices 로 연결 확인
  3. 폰에서 Chrome 앱 실행

Usage:
    python scripts/phone_chrome_capture.py                    # Naver + Kakao
    python scripts/phone_chrome_capture.py --sites naver      # Naver만
    python scripts/phone_chrome_capture.py --sites kakao      # Kakao만
    python scripts/phone_chrome_capture.py --sites instagram  # Instagram (로그인 필요)
    python scripts/phone_chrome_capture.py --scrolls 10       # 스크롤 횟수 지정
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "adscope.db"

# ── 광고 URL 패턴 ──

AD_PATTERNS = {
    "naver": {
        "gfp_json": ["nam.veta.naver.com/gfp"],
        "tracking": ["siape.veta.naver.com", "ade.naver.com"],
    },
    "kakao": {
        "sdk_json": ["display.ad.daum.net/sdk/"],
        "tracking": ["ad.daum.net", "kakaoad.com"],
    },
    "instagram": {
        "graphql": ["www.instagram.com/graphql", "www.instagram.com/api/graphql"],
        "feed_api": ["i.instagram.com/api/v1/feed"],
    },
}

# 하우스 광고 도메인 (네이버/카카오 자체 서비스)
_INFRA_DOMAINS = {
    "navercorp.com", "nstore.naver.com",
    "daum.net", "kakao.com", "kakaocorp.com",
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "criteo.com", "adroll.com", "taboola.com", "dable.io",
}

# 광고 리다이렉트 도메인은 하우스가 아님 (외부 광고주로의 리다이렉트)
_REDIRECT_DOMAINS = {
    "tivan.naver.com", "g.tivan.naver.com", "adcr.naver.com",
    "tr.ad.daum.net",  # 카카오 클릭 트래킹
}

CDP_PORT = 9222


def setup_adb_forward():
    """ADB 포트 포워딩 설정."""
    result = subprocess.run(
        ["adb", "forward", f"tcp:{CDP_PORT}", "localabstract:chrome_devtools_remote"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        logger.error(f"ADB forward failed: {result.stderr}")
        return False
    return True


def _extract_domain(url: str) -> str:
    """URL에서 도메인 추출."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        domain = domain.split(":")[0]
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def _is_inhouse(url: str) -> bool:
    """하우스 광고 여부. 리다이렉트 도메인은 통과."""
    domain = _extract_domain(url)
    if any(domain.endswith(d) for d in _REDIRECT_DOMAINS):
        return False
    return any(domain.endswith(d) for d in _INFRA_DOMAINS)


# ── Naver GFP 파서 ──

def parse_naver_gfp(body: str) -> list[dict]:
    """네이버 GFP JSON 응답에서 광고 추출. naver_da._parse_gfp_json 로직 재사용."""
    ads = []
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return ads

    # Format 1: ads[] → adInfo.nativeData
    items = data.get("ads", [])
    if not isinstance(items, list):
        items = []

    for item in items:
        if not isinstance(item, dict):
            continue
        ad_info = item.get("adInfo", item.get("adinfo", item))
        if not isinstance(ad_info, dict):
            continue

        # adContext에서 광고주 도메인 먼저 추출 (nativeData/adContext 공통)
        ad_ctx_str = ad_info.get("adContext", "")
        adomain_domain = ""
        if ad_ctx_str and isinstance(ad_ctx_str, str):
            try:
                ctx = json.loads(ad_ctx_str)
                adomain = ctx.get("adomain", [])
                adomain_domain = adomain[0] if adomain else ""
            except json.JSONDecodeError:
                pass

        # nativeData 방식
        native = ad_info.get("nativeData", ad_info.get("native", {}))
        if isinstance(native, dict) and native:
            sponsor = native.get("sponsor", {})
            link = native.get("link", {})
            desc = native.get("desc", {})
            media = native.get("media", {})

            advertiser = sponsor.get("text") if isinstance(sponsor, dict) else None
            click_url = link.get("curl") if isinstance(link, dict) else None
            ad_text = desc.get("text") if isinstance(desc, dict) else None
            image_url = media.get("src") if isinstance(media, dict) else None

            if not click_url:
                continue

            # 실제 광고주 도메인 = adomain 우선, click_url은 tivan 리다이렉트일 수 있음
            display_domain = adomain_domain or _extract_domain(click_url)
            if _is_inhouse(f"https://{display_domain}") and not adomain_domain:
                continue

            ads.append({
                "advertiser_name": advertiser or display_domain,
                "ad_text": ad_text or advertiser or "",
                "url": click_url,
                "display_url": display_domain,
                "image_url": image_url,
                "ad_type": "phone_da",
                "ad_placement": "m_naver_home_feed",
                "detection_method": "phone_chrome_gfp",
            })
            continue

        # adContext-only 방식 (nativeData 없는 경우)
        if ad_ctx_str and isinstance(ad_ctx_str, str):
            adm = ad_info.get("adm", "")
            try:
                ctx = json.loads(ad_ctx_str)
                provider = ctx.get("adProviderName", "")

                landing_match = re.search(
                    r'(?:landingUrl|clickUrl|click_url|href)[=:]\s*["\']([^"\']+)',
                    adm,
                )
                click_url = landing_match.group(1) if landing_match else ""

                if not click_url and not adomain_domain:
                    continue

                advertiser = adomain_domain if adomain_domain else provider
                ads.append({
                    "advertiser_name": advertiser,
                    "ad_text": advertiser,
                    "url": click_url or f"https://{adomain_domain}",
                    "display_url": adomain_domain or _extract_domain(click_url),
                    "image_url": None,
                    "ad_type": "phone_da",
                    "ad_placement": "m_naver_home_feed",
                    "detection_method": "phone_chrome_gfp_ctx",
                })
            except json.JSONDecodeError:
                pass

    # Format 2: adUnits[]
    for unit in data.get("adUnits", []):
        if not isinstance(unit, dict):
            continue
        for ad in unit.get("ads", []):
            sub = parse_naver_gfp(json.dumps({"ads": [ad]}))
            ads.extend(sub)

    return ads


# ── Kakao SDK 파서 ──

def parse_kakao_sdk(body: str) -> list[dict]:
    """카카오 SDK 배너 JSON 응답에서 광고 추출. kakao_da._parse_sdk_captures 로직 재사용."""
    ads = []
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return ads

    ad_items = data.get("ads", [])
    if not isinstance(ad_items, list):
        return ads

    for item in ad_items:
        if not isinstance(item, dict):
            continue

        # Native format
        if item.get("landingUrl"):
            advertiser = item.get("profileName", "")
            landing = item.get("landingUrl", "")
            title = item.get("title", "")
            main_img = item.get("mainImage", {})
            image_url = main_img.get("url") if isinstance(main_img, dict) else None

            if not landing:
                continue
            if _is_inhouse(landing):
                continue

            ads.append({
                "advertiser_name": advertiser or _extract_domain(landing),
                "ad_text": title or advertiser or "",
                "url": landing,
                "display_url": _extract_domain(landing),
                "image_url": image_url,
                "ad_type": "phone_da",
                "ad_placement": "m_daum_feed",
                "detection_method": "phone_chrome_sdk_native",
            })
            continue

        # Banner format (HTML content)
        content = item.get("content", "")
        if not content or not isinstance(content, str):
            continue

        # Landing URL 추출
        url_patterns = [
            r'"(?:clickUrl|landingUrl|landing|click_url|redirect_url|lp)"\s*:\s*"([^"]+)"',
            r'(?:clickUrl|landingUrl|click_url)\s*=\s*["\']([^"\']+)',
            # href pointing to click tracking URL
            r'href\s*=\s*["\']([^"\']*tr\.ad\.daum\.net/clk[^"\']*)["\']',
            r'"(?:url|link)"\s*:\s*"(https?://[^"]+)"',
        ]
        click_url = ""
        for pat in url_patterns:
            m = re.search(pat, content)
            if m:
                click_url = m.group(1)
                break

        if not click_url:
            # tr.ad.daum.net/clk URL 찾기 (클릭 리다이렉트)
            clk_match = re.search(r'(https?://tr\.ad\.daum\.net/clk[^\s"\'<>]+)', content)
            if clk_match:
                click_url = clk_match.group(1)

        if not click_url:
            # 외부 URL 찾기 (CDN/인프라 제외)
            _CDN_PATTERNS = {"daumcdn.net", "kakaocdn.net", "kakaocdn.com",
                             "daumimg.net", "pstatic.net", "googleusercontent.com",
                             "w3.org", "onkakao.net", "ds.kakao.com"}
            for m in re.finditer(r'https?://[^\s"\'<>]+', content):
                u = m.group(0)
                domain = _extract_domain(u)
                if not domain:
                    continue
                if any(domain.endswith(d) for d in _CDN_PATTERNS):
                    continue
                if any(domain.endswith(d) for d in _INFRA_DOMAINS):
                    continue
                click_url = u
                break

        if not click_url:
            continue

        # 광고주명 추출
        adv_patterns = [
            r'"(?:profileName|advertiserName|brandName)"\s*:\s*"([^"]+)"',
            r'"title"\s*:\s*"([^"]{2,40})"',
        ]
        advertiser = ""
        for pat in adv_patterns:
            m = re.search(pat, content)
            if m:
                advertiser = m.group(1)
                break
        if not advertiser:
            advertiser = _extract_domain(click_url)

        # 이미지 URL 추출
        img_patterns = [
            r'"(?:bgImageUrl|imageUrl|imgUrl)"\s*:\s*"([^"]+)"',
            r'<img[^>]+src=["\']([^"\']+)["\']',
        ]
        image_url = None
        for pat in img_patterns:
            m = re.search(pat, content)
            if m:
                candidate = m.group(1)
                if not any(x in candidate.lower() for x in ("admark", "optout", "1x1", "pixel")):
                    image_url = candidate
                    break

        ads.append({
            "advertiser_name": advertiser,
            "ad_text": advertiser,
            "url": click_url,
            "display_url": _extract_domain(click_url),
            "image_url": image_url,
            "ad_type": "phone_da",
            "ad_placement": "m_daum_feed",
            "detection_method": "phone_chrome_sdk_banner",
        })

    return ads


# ── Instagram 파서 ──

def parse_instagram_graphql(body: str) -> list[dict]:
    """인스타그램 GraphQL 응답에서 Sponsored 포스트 추출."""
    ads = []
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return ads

    # GraphQL feed에서 sponsored 항목 탐색 (재귀)
    _find_sponsored(data, ads, depth=0)
    return ads


def _find_sponsored(obj, ads: list, depth: int):
    """재귀적으로 sponsored 광고 탐색."""
    if depth > 10 or not isinstance(obj, (dict, list)):
        return

    if isinstance(obj, list):
        for item in obj:
            _find_sponsored(item, ads, depth + 1)
        return

    # Sponsored 포스트 감지
    is_ad = (
        obj.get("is_ad")
        or obj.get("ad_id")
        or obj.get("injected")
        or obj.get("ad_action")
        or obj.get("sponsor_tags")
    )

    if is_ad:
        user = obj.get("user", obj.get("owner", {}))
        if isinstance(user, dict):
            advertiser = user.get("full_name") or user.get("username")
        else:
            advertiser = None

        caption = obj.get("caption", {})
        ad_text = ""
        if isinstance(caption, dict):
            ad_text = (caption.get("text") or "")[:200]
        elif isinstance(caption, str):
            ad_text = caption[:200]

        link = obj.get("link") or obj.get("ad_link_url") or ""

        if advertiser or link:
            ads.append({
                "advertiser_name": advertiser or "Instagram Ad",
                "ad_text": ad_text or advertiser or "",
                "url": link,
                "display_url": _extract_domain(link) if link else "",
                "image_url": None,
                "ad_type": "phone_feed",
                "ad_placement": "instagram_feed",
                "detection_method": "phone_chrome_graphql",
            })
        return  # 이미 처리됨

    # 재귀 탐색
    for v in obj.values():
        if isinstance(v, (dict, list)):
            _find_sponsored(v, ads, depth + 1)


# ── DB 저장 ──

async def save_ads_to_db(channel: str, page_url: str, ads: list[dict]):
    """ad_snapshots + ad_details에 저장."""
    import aiosqlite

    if not ads:
        return 0

    now = datetime.now(UTC)

    async with aiosqlite.connect(str(DB_PATH)) as db:
        # 폰 수집용 기본 keyword 조회 (없으면 생성)
        row = await db.execute_fetchall(
            "SELECT id FROM keywords WHERE keyword = 'phone_chrome' LIMIT 1"
        )
        if row:
            keyword_id = row[0][0]
        else:
            cur = await db.execute(
                "INSERT INTO keywords (keyword, industry_id, is_active) VALUES ('phone_chrome', 1, 1)"
            )
            keyword_id = cur.lastrowid

        # 폰 수집 페르소나 (M40 = 40대 남성, 폰 소유자 프로필)
        persona_row = await db.execute_fetchall(
            "SELECT id FROM personas WHERE code = 'M40' LIMIT 1"
        )
        persona_id = persona_row[0][0] if persona_row else 7

        # ad_snapshots 생성
        cursor = await db.execute(
            """INSERT INTO ad_snapshots
               (keyword_id, persona_id, device, channel, captured_at, page_url, ad_count)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (keyword_id, persona_id, "mobile_phone", channel, now.isoformat(), page_url, len(ads)),
        )
        snapshot_id = cursor.lastrowid

        # ad_details 생성
        rows = []
        for i, ad in enumerate(ads):
            extra = json.dumps({
                "detection_method": ad.get("detection_method", ""),
                "image_url": ad.get("image_url", ""),
                "source": "phone_chrome_cdp",
            }, ensure_ascii=False)

            rows.append((
                snapshot_id,
                (ad.get("advertiser_name") or "")[:200],
                (ad.get("ad_text") or "")[:500],
                i + 1,  # position
                ad.get("url") or "",
                (ad.get("display_url") or "")[:500],
                ad.get("ad_type", "phone_da"),
                ad.get("ad_placement", ""),
                extra,
            ))

        await db.executemany(
            """INSERT INTO ad_details
               (snapshot_id, advertiser_name_raw, ad_text, position,
                url, display_url, ad_type, ad_placement, extra_data)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        await db.commit()

    return len(ads)


# ── 사이트별 크롤 ──

async def crawl_naver(page, scrolls: int = 8) -> list[dict]:
    """m.naver.com 광고 수집."""
    captured = []

    async def on_response(resp):
        url = resp.url
        if "nam.veta.naver.com/gfp" in url and "/v1" in url:
            try:
                body = await resp.text()
                if body and len(body) > 100:
                    captured.append(body)
            except Exception:
                pass

    page.on("response", on_response)

    try:
        logger.info("[naver] m.naver.com...")
        await page.goto("https://m.naver.com", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)

        for i in range(scrolls):
            await page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(1.5 + (i % 3) * 0.5)

        await asyncio.sleep(2)
    finally:
        page.remove_listener("response", on_response)

    # 파싱
    ads = []
    for body in captured:
        ads.extend(parse_naver_gfp(body))

    # 중복 제거 (URL 기준)
    seen = set()
    unique = []
    for ad in ads:
        key = ad.get("url", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(ad)

    logger.info(f"[naver] GFP responses: {len(captured)}, ads: {len(unique)}")
    return unique


async def crawl_kakao(page, scrolls: int = 8) -> list[dict]:
    """m.daum.net 광고 수집."""
    captured = []

    async def on_response(resp):
        url = resp.url
        if "display.ad.daum.net/sdk/" in url:
            try:
                body = await resp.text()
                if body and len(body) > 100:
                    captured.append(body)
            except Exception:
                pass

    page.on("response", on_response)

    try:
        logger.info("[kakao] m.daum.net...")
        await page.goto("https://m.daum.net", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)

        for i in range(scrolls):
            await page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(1.5 + (i % 3) * 0.5)

        await asyncio.sleep(2)
    finally:
        page.remove_listener("response", on_response)

    # 파싱
    ads = []
    for body in captured:
        ads.extend(parse_kakao_sdk(body))

    # 중복 제거
    seen = set()
    unique = []
    for ad in ads:
        key = ad.get("url", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(ad)

    logger.info(f"[kakao] SDK responses: {len(captured)}, ads: {len(unique)}")
    return unique


async def crawl_instagram(page, scrolls: int = 10) -> list[dict]:
    """instagram.com 광고 수집 (로그인 상태 필요)."""
    captured = []

    async def on_response(resp):
        url = resp.url
        if any(p in url for p in ["graphql", "api/v1/feed"]):
            try:
                body = await resp.text()
                if body and len(body) > 500:
                    # sponsor 관련 키워드 포함 여부 빠른 체크
                    lower = body.lower()
                    if any(k in lower for k in ["sponsor", "ad_id", "injected", "is_ad"]):
                        captured.append(body)
            except Exception:
                pass

    page.on("response", on_response)

    try:
        logger.info("[instagram] instagram.com...")
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # 로그인 상태 확인
        url = page.url
        if "login" in url.lower():
            logger.warning("[instagram] Not logged in! Please login manually on phone Chrome.")
            page.remove_listener("response", on_response)
            return []

        for i in range(scrolls):
            await page.evaluate("window.scrollBy(0, 500)")
            await asyncio.sleep(2.0 + (i % 4) * 0.5)

        await asyncio.sleep(2)
    finally:
        page.remove_listener("response", on_response)

    # 파싱
    ads = []
    for body in captured:
        ads.extend(parse_instagram_graphql(body))

    logger.info(f"[instagram] GraphQL captures: {len(captured)}, ads: {len(ads)}")
    return ads


# ── 메인 ──

SITE_CRAWLERS = {
    "naver": ("naver_da", "https://m.naver.com", crawl_naver),
    "kakao": ("kakao_da", "https://m.daum.net", crawl_kakao),
    "instagram": ("meta", "https://www.instagram.com", crawl_instagram),
}


async def run(sites: list[str], scrolls: int):
    from playwright.async_api import async_playwright

    # ADB 포트 포워딩
    if not setup_adb_forward():
        logger.error("ADB forward failed. Is phone connected?")
        return

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
        except Exception as e:
            logger.error(f"CDP connect failed: {e}")
            logger.info("Make sure Chrome is open on the phone.")
            return

        contexts = browser.contexts
        if not contexts:
            logger.error("No browser context found.")
            await browser.close()
            return

        ctx = contexts[0]
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        total_ads = 0

        for site in sites:
            if site not in SITE_CRAWLERS:
                logger.warning(f"Unknown site: {site}")
                continue

            channel, page_url, crawler_fn = SITE_CRAWLERS[site]

            try:
                ads = await crawler_fn(page, scrolls=scrolls)
            except Exception as e:
                logger.error(f"[{site}] crawl error: {e}")
                continue

            if not ads:
                logger.info(f"[{site}] No ads captured.")
                continue

            # 로그 출력
            for i, ad in enumerate(ads[:10]):
                name = (ad.get("advertiser_name") or "?")[:25]
                url = (ad.get("url") or "")[:50]
                logger.info(f"  [{i+1}] {name} | {url}")

            # DB 저장
            try:
                saved = await save_ads_to_db(channel, page_url, ads)
                logger.info(f"[{site}] Saved {saved} ads to DB.")
                total_ads += saved
            except Exception as e:
                logger.error(f"[{site}] DB save error: {e}")

        logger.info(f"=== Total: {total_ads} ads from {len(sites)} sites ===")

        # 폰 홈으로 돌아가기 (선택적)
        try:
            await page.goto("about:blank")
        except Exception:
            pass

        await browser.close()


def main():
    parser = argparse.ArgumentParser(description="Phone Chrome CDP ad capture")
    parser.add_argument(
        "--sites", nargs="+", default=["naver", "kakao"],
        choices=["naver", "kakao", "instagram"],
        help="Sites to crawl (default: naver kakao)",
    )
    parser.add_argument("--scrolls", type=int, default=8, help="Scroll count per site")
    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")

    asyncio.run(run(args.sites, args.scrolls))


if __name__ == "__main__":
    main()
