"""뉴스 기사면 GDN 광고 + FB/IG 피드 광고 접촉 테스트.

네이버뉴스/다음뉴스 카테고리별 기사 클릭 -> 기사면 GDN 수집.
"""
import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

GDN_PATTERNS = [
    "doubleclick.net", "googlesyndication.com", "googleads",
    "adservice.google", "googleadservices", "pagead",
    "securepubads", "adsense", "tpc.googlesyndication",
]

ALL_AD_PATTERNS = GDN_PATTERNS + [
    "facebook.com/tr", "connect.facebook.net", "graph.facebook.com",
    "siape.veta.naver.com", "adcr.naver.com", "adsun.naver.com",
    "adfit.kakao.com", "display.ad.daum.net",
]

# ── 네이버뉴스 / 다음뉴스 카테고리 ──
NEWS_CATEGORIES = [
    # 네이버뉴스 카테고리
    ("naver-politics", "https://news.naver.com/section/100"),
    ("naver-economy", "https://news.naver.com/section/101"),
    ("naver-society", "https://news.naver.com/section/102"),
    ("naver-sports", "https://sports.news.naver.com/"),
    # 다음뉴스 카테고리
    ("daum-politics", "https://news.daum.net/politics"),
    ("daum-economy", "https://news.daum.net/economic"),
    ("daum-society", "https://news.daum.net/society"),
    ("daum-sports", "https://sports.daum.net/"),
]


async def surf_articles(ctx, cat_name, cat_url, max_articles=3):
    """카테고리 페이지에서 기사 클릭 -> 기사면 GDN 광고 캡처."""
    page = await ctx.new_page()
    all_ads = []
    article_count = 0

    async def on_resp(response):
        u = response.url
        if response.status == 200:
            for pat in ALL_AD_PATTERNS:
                if pat in u:
                    all_ads.append({"url": u[:120], "pattern": pat})
                    break

    page.on("response", on_resp)

    try:
        # 1. 카테고리 목록 로드
        await page.goto(cat_url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2)

        # 2. 기사 링크 추출
        article_links = await page.evaluate("""
            (() => {
                const as = document.querySelectorAll('a[href]');
                const arts = [];
                for (const a of as) {
                    const h = a.href;
                    if (!h || h.includes('#') || h.includes('javascript:')) continue;
                    if (h.includes('/article/') || h.includes('/news/read') ||
                        h.includes('n.news.naver.com') || h.includes('v.daum.net/v/') ||
                        h.includes('/newsView/') || h.match(/\\/\\d{10,}/)) {
                        arts.push(h);
                    }
                }
                return [...new Set(arts)].slice(0, 10);
            })()
        """)

        await page.close()

        if not article_links:
            return {"name": cat_name, "articles": 0, "gdn": 0, "total": 0}

        # 3. 기사 3개 방문
        for art_url in article_links[:max_articles]:
            art_page = await ctx.new_page()
            pre = len(all_ads)

            async def on_art_resp(response, _ads=all_ads):
                u = response.url
                if response.status == 200:
                    for pat in ALL_AD_PATTERNS:
                        if pat in u:
                            _ads.append({"url": u[:120], "pattern": pat})
                            break

            art_page.on("response", on_art_resp)

            try:
                await art_page.goto(art_url, wait_until="domcontentloaded", timeout=12000)
                for _ in range(8):
                    await art_page.evaluate("window.scrollBy(0, 350)")
                    await asyncio.sleep(0.5)
                await asyncio.sleep(1.5)
                article_count += 1
            except Exception:
                pass
            finally:
                await art_page.close()

        gdn = len([a for a in all_ads if any(p in a["url"] for p in GDN_PATTERNS)])
        naver_ad = len([a for a in all_ads if any(p in a["url"] for p in ["siape.veta", "adcr.naver", "adsun.naver"])])
        kakao_ad = len([a for a in all_ads if any(p in a["url"] for p in ["adfit.kakao", "display.ad.daum"])])

        return {
            "name": cat_name,
            "articles": article_count,
            "gdn": gdn,
            "naver": naver_ad,
            "kakao": kakao_ad,
            "total": len(all_ads),
        }

    except Exception as e:
        return {"name": cat_name, "articles": 0, "gdn": 0, "total": 0, "error": str(e)[:60]}
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def test_social(ctx):
    """IG/FB 로그인 피드 광고."""
    results = []

    # ── Instagram ──
    print("\n--- Instagram (cookie login) ---")
    page = await ctx.new_page()
    ig_ads = []

    async def on_ig(r):
        u = r.url
        if r.status == 200 and ("graphql" in u or "api/v1" in u):
            try:
                body = await r.text()
                if "is_ad" in body or '"sponsored"' in body.lower():
                    ig_ads.append(u[:80])
            except Exception:
                pass

    page.on("response", on_ig)

    try:
        cookie_path = Path(_root) / "ig_cookies.json"
        if cookie_path.exists():
            with open(cookie_path, encoding="utf-8") as f:
                cookies = json.load(f)
            await ctx.add_cookies(cookies)

        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(3)
        for _ in range(12):
            await page.evaluate("window.scrollBy(0, 500)")
            await asyncio.sleep(1.0)
        await asyncio.sleep(2)

        print(f"  Instagram: {len(ig_ads)} sponsored posts detected")
        results.append({"name": "Instagram", "ads": len(ig_ads)})
    except Exception as e:
        print(f"  Instagram: ERROR {str(e)[:60]}")
        results.append({"name": "Instagram", "ads": 0, "error": str(e)[:60]})
    finally:
        await page.close()

    # ── Facebook ──
    print("--- Facebook (login) ---")
    page2 = await ctx.new_page()
    fb_ads = []

    async def on_fb(r):
        u = r.url
        if r.status == 200 and any(p in u for p in ALL_AD_PATTERNS):
            fb_ads.append(u[:80])

    page2.on("response", on_fb)

    try:
        await page2.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2)
        await page2.fill('input[name="email"]', "01083706470")
        await page2.fill('input[name="pass"]', "pjm990101@")
        await page2.click('button[name="login"]')
        await asyncio.sleep(5)

        for _ in range(10):
            await page2.evaluate("window.scrollBy(0, 500)")
            await asyncio.sleep(1.0)
        await asyncio.sleep(2)

        print(f"  Facebook: {len(fb_ads)} ad responses")
        results.append({"name": "Facebook", "ads": len(fb_ads)})
    except Exception as e:
        print(f"  Facebook: ERROR {str(e)[:60]}")
        results.append({"name": "Facebook", "ads": 0, "error": str(e)[:60]})
    finally:
        await page2.close()

    return results


async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=False,
        channel="chrome",
        args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
    )
    ctx = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        locale="ko-KR",
        timezone_id="Asia/Seoul",
    )
    stealth = Stealth(navigator_languages_override=("ko-KR", "ko"))
    for s in list(stealth.enabled_scripts):
        await ctx.add_init_script(s)

    print("=" * 70)
    print("News Article + Social Ad Capture Test")
    print("=" * 70)

    # ── Part 1: News articles ──
    print("\n--- Naver/Daum News Articles (3 articles per category) ---")
    print(f"{'Category':<22} {'Arts':>4} {'GDN':>4} {'Naver':>5} {'Kakao':>5} {'Total':>5}")
    print("-" * 55)

    news_results = []
    for name, url in NEWS_CATEGORIES:
        r = await surf_articles(ctx, name, url, max_articles=3)
        news_results.append(r)
        err = r.get("error", "")
        if err:
            print(f"{name:<22} ERROR: {err[:30]}")
        else:
            print(f"{r['name']:<22} {r['articles']:>4} {r['gdn']:>4} {r.get('naver',0):>5} {r.get('kakao',0):>5} {r['total']:>5}")

    t_gdn = sum(r.get("gdn", 0) for r in news_results)
    t_nav = sum(r.get("naver", 0) for r in news_results)
    t_kak = sum(r.get("kakao", 0) for r in news_results)
    t_all = sum(r.get("total", 0) for r in news_results)
    t_arts = sum(r.get("articles", 0) for r in news_results)
    print(f"{'TOTAL':<22} {t_arts:>4} {t_gdn:>4} {t_nav:>5} {t_kak:>5} {t_all:>5}")

    # ── Part 2: Social ──
    social = await test_social(ctx)

    # ── Summary ──
    print("\n" + "=" * 70)
    print(f"News: {t_arts} articles -> GDN {t_gdn}, Naver {t_nav}, Kakao {t_kak}")
    print(f"Social: IG {social[0].get('ads',0) if social else 0}, FB {social[1].get('ads',0) if len(social)>1 else 0}")
    print(f"Grand total ad responses: {t_all + sum(s.get('ads',0) for s in social)}")

    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
