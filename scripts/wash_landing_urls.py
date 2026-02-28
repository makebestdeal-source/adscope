"""기존 ad_details의 트래킹 URL을 리다이렉트 따라가서 최종 URL 파악.

1. ad_details에서 트래킹 URL을 가진 광고 추출
2. 브라우저로 리다이렉트 따라가서 최종 도메인 파악
3. 도메인 → 광고주 website 자동 매칭
4. landing_url_cache에 결과 캐싱
5. 광고주-캠페인 DB 정제

Usage: python scripts/wash_landing_urls.py [--batch-size=50] [--dry-run]
"""
import asyncio
import json
import re
import sys
from urllib.parse import urlparse

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from database import async_session
from sqlalchemy import text

# ── 트래킹 URL 패턴 (리다이렉트 따라갈 대상) ──
TRACKING_PATTERNS = [
    "g.tivan.naver.com", "tivan.naver.com",
    "ader.naver.com", "adcr.naver.com",
    "m.ad.search.naver.com", "siape.veta.naver.com",
    "ad.daum.net", "v.daum.net",
    "track.tiara.kakao.com",
    "adstransparency.google.com",
]

# ── 인프라 도메인 (최종 도메인이 이것이면 실패) ──
INFRA_DOMAINS = {
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "google.com", "google.co.kr", "gstatic.com", "googleapis.com",
    "googletagmanager.com", "google-analytics.com",
    "facebook.com", "facebook.net", "fbcdn.net",
    "youtube.com", "youtu.be", "t.co", "bit.ly",
    "naver.com", "daum.net", "kakao.com",
    "play.google.com", "apps.apple.com",
    "tivan.naver.com", "ader.naver.com", "adcr.naver.com",
}

# ── 도메인 → 광고주 매칭용 제외 도메인 ──
SKIP_DOMAINS = INFRA_DOMAINS | {
    "ssl.pstatic.net", "search.naver.com", "ad.search.naver.com",
    "shopping.naver.com", "smartstore.naver.com",
}


def is_tracking_url(url: str) -> bool:
    """트래킹/리다이렉트 URL인지 확인."""
    if not url:
        return False
    for pattern in TRACKING_PATTERNS:
        if pattern in url:
            return True
    return False


def extract_clean_domain(url: str) -> str | None:
    """URL에서 클린 도메인 추출."""
    if not url or not url.startswith("http"):
        return None
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if not domain or len(domain) < 4:
            return None
        # 인프라/스킵 도메인 체크
        for skip in SKIP_DOMAINS:
            if skip in domain:
                return None
        return domain
    except Exception:
        return None


async def resolve_url_with_browser(url: str, timeout_ms: int = 10000) -> dict | None:
    """브라우저로 URL을 열어 리다이렉트를 따라가고 최종 URL 및 메타데이터 추출.

    Returns:
        {"final_url", "final_domain", "page_title", "og_site_name", "advertiser_name"}
    """
    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                locale="ko-KR",
            )
            page = await context.new_page()

            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                await page.wait_for_timeout(2000)

                final_url = page.url
                final_domain = extract_clean_domain(final_url)

                if not final_domain:
                    return None

                # 메타데이터 추출
                info = await page.evaluate("""() => {
                    const getMeta = (attr, val) => {
                        const el = document.querySelector(`meta[${attr}="${val}"]`);
                        return el ? (el.content || '').trim() : null;
                    };
                    const siteName = getMeta('property', 'og:site_name') || getMeta('name', 'og:site_name');
                    const ogTitle = getMeta('property', 'og:title');
                    const title = document.title || '';
                    let copyright = null;
                    const bodyText = document.body ? document.body.innerText : '';
                    const cpMatch = bodyText.match(/(?:©|ⓒ|Copyright)\\s*\\d{0,4}\\s*([^.\\n]{2,50})/i);
                    if (cpMatch) copyright = cpMatch[1].trim();
                    return { site_name: siteName, og_title: ogTitle, title: title.slice(0, 200), copyright: copyright, url: location.href };
                }""")

                advertiser_name = None
                if info:
                    advertiser_name = info.get("site_name") or info.get("copyright")
                    if advertiser_name and (len(advertiser_name) < 2 or len(advertiser_name) > 60):
                        advertiser_name = None

                return {
                    "final_url": final_url,
                    "final_domain": final_domain,
                    "page_title": info.get("title") if info else None,
                    "og_site_name": info.get("site_name") if info else None,
                    "advertiser_name": advertiser_name,
                }

            except Exception as e:
                return None
            finally:
                await page.close()
                await context.close()
                await browser.close()

    except Exception as e:
        return None


async def resolve_batch_with_shared_browser(urls: list[tuple[int, str]], timeout_ms: int = 10000) -> dict[int, dict]:
    """여러 URL을 하나의 브라우저 인스턴스로 처리 (효율적).

    Args:
        urls: [(ad_detail_id, url), ...]

    Returns:
        {ad_detail_id: {"final_url", "final_domain", ...}}
    """
    from playwright.async_api import async_playwright

    results = {}

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="ko-KR",
                viewport={"width": 1280, "height": 720},
            )

            for ad_id, url in urls:
                page = None
                try:
                    page = await context.new_page()
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    await page.wait_for_timeout(1500)

                    final_url = page.url
                    final_domain = extract_clean_domain(final_url)

                    if not final_domain:
                        continue

                    info = await page.evaluate("""() => {
                        const getMeta = (attr, val) => {
                            const el = document.querySelector(`meta[${attr}="${val}"]`);
                            return el ? (el.content || '').trim() : null;
                        };
                        return {
                            site_name: getMeta('property', 'og:site_name') || getMeta('name', 'og:site_name'),
                            og_title: getMeta('property', 'og:title'),
                            title: (document.title || '').slice(0, 200),
                            url: location.href
                        };
                    }""")

                    advertiser_name = None
                    if info and info.get("site_name"):
                        s = info["site_name"].strip()
                        if 2 <= len(s) <= 60 and not s.startswith("http"):
                            advertiser_name = s

                    results[ad_id] = {
                        "final_url": final_url,
                        "final_domain": final_domain,
                        "page_title": info.get("title") if info else None,
                        "og_site_name": info.get("site_name") if info else None,
                        "advertiser_name": advertiser_name,
                    }

                except Exception:
                    pass
                finally:
                    if page:
                        try:
                            await page.close()
                        except Exception:
                            pass

            await context.close()
            await browser.close()

    except Exception as e:
        print(f"  Browser error: {e}")

    return results


async def main():
    dry_run = "--dry-run" in sys.argv
    batch_size = 50
    for arg in sys.argv:
        if arg.startswith("--batch-size="):
            batch_size = int(arg.split("=")[1])

    print(f"=== Landing URL Wash {'(DRY RUN)' if dry_run else ''} ===")
    print(f"Batch size: {batch_size}")

    async with async_session() as session:
        # ── Step 1: 트래킹 URL을 가진 광고 중 광고주에 website 없는 것 우선 ──
        result = await session.execute(text("""
            SELECT d.id, d.url, d.advertiser_id, a.name, a.website
            FROM ad_details d
            LEFT JOIN advertisers a ON d.advertiser_id = a.id
            WHERE d.url IS NOT NULL AND d.url <> :empty
              AND (
                d.url LIKE :t1 OR d.url LIKE :t2 OR d.url LIKE :t3
                OR d.url LIKE :t4 OR d.url LIKE :t5
                OR d.url LIKE :t6 OR d.url LIKE :t7
              )
              AND (a.website IS NULL OR a.website = :empty)
            GROUP BY d.advertiser_id
            ORDER BY COUNT(*) DESC
            LIMIT :batch
        """), {
            'empty': '', 'batch': batch_size,
            't1': '%tivan.naver%', 't2': '%ader.naver%', 't3': '%adcr.naver%',
            't4': '%ad.daum%', 't5': '%track.tiara%',
            't6': '%adstransparency%', 't7': '%siape.veta%',
        })
        rows = result.fetchall()
        print(f"\nAdvertisers with tracking URLs and no website: {len(rows)}")

        if not rows:
            print("Nothing to resolve.")
            return

        # 각 광고주별 대표 URL 1개씩 수집
        urls_to_resolve = []
        for r in rows:
            ad_id, url, adv_id, adv_name, website = r
            urls_to_resolve.append((ad_id, url, adv_id, adv_name))

        print(f"Resolving {len(urls_to_resolve)} URLs via browser redirect...")

        # ── Step 2: 브라우저로 리다이렉트 따라가기 ──
        url_pairs = [(uid, url) for uid, url, _, _ in urls_to_resolve]
        resolved = await resolve_batch_with_shared_browser(url_pairs, timeout_ms=12000)

        print(f"Successfully resolved: {len(resolved)}/{len(urls_to_resolve)}")

        # ── Step 3: 결과를 landing_url_cache + advertiser.website에 반영 ──
        updated_advertisers = 0
        cached_domains = 0
        domain_to_advertiser = {}  # domain -> (advertiser_id, advertiser_name, og_site_name)

        for ad_id, url, adv_id, adv_name in urls_to_resolve:
            if ad_id not in resolved:
                continue

            r = resolved[ad_id]
            domain = r["final_domain"]

            if not domain:
                continue

            print(f"  [{adv_id}] {adv_name} -> {domain} (title: {(r.get('page_title') or '')[:40]})")

            domain_to_advertiser[domain] = (adv_id, adv_name, r.get("og_site_name"))

            if not dry_run:
                # landing_url_cache 업데이트
                from processor.landing_cache import cache_landing_result
                await cache_landing_result(
                    session,
                    url=r["final_url"],
                    brand_name=r.get("advertiser_name") or adv_name,
                    advertiser_id=adv_id,
                    page_title=r.get("page_title"),
                )
                cached_domains += 1

                # advertiser.website 업데이트
                await session.execute(text(
                    "UPDATE advertisers SET website = :website WHERE id = :id AND (website IS NULL OR website = :empty)"
                ), {"website": domain, "id": adv_id, "empty": ""})
                updated_advertisers += 1

        if not dry_run:
            await session.commit()

        # ── Step 4: 같은 도메인을 가진 다른 광고도 업데이트 ──
        if not dry_run and domain_to_advertiser:
            print(f"\n--- Propagating domains to other ads with same advertiser ---")
            propagated = 0
            for domain, (adv_id, adv_name, og_name) in domain_to_advertiser.items():
                # 같은 advertiser_id의 다른 ad_details에 extra_data.landing_domain 업데이트
                result2 = await session.execute(text("""
                    SELECT id, extra_data FROM ad_details
                    WHERE advertiser_id = :aid
                    AND (extra_data IS NULL OR extra_data NOT LIKE :pattern)
                    LIMIT 100
                """), {"aid": adv_id, "pattern": f'%"landing_domain"%'})

                for row2 in result2.fetchall():
                    try:
                        ed = json.loads(row2[1]) if row2[1] else {}
                    except Exception:
                        ed = {}
                    ed["landing_domain"] = domain
                    ed["landing_resolved"] = True
                    await session.execute(text(
                        "UPDATE ad_details SET extra_data = :ed WHERE id = :id"
                    ), {"ed": json.dumps(ed, ensure_ascii=False), "id": row2[0]})
                    propagated += 1

            await session.commit()
            print(f"  Propagated landing_domain to {propagated} ad_details")

        print(f"\n=== Summary ===")
        print(f"  Resolved URLs: {len(resolved)}")
        print(f"  Updated advertisers: {updated_advertisers}")
        print(f"  Cached domains: {cached_domains}")
        print(f"  Unique domains found: {len(domain_to_advertiser)}")


if __name__ == "__main__":
    asyncio.run(main())
