"""채널 수집 진단 — 각 크롤러의 설정/접속/셀렉터 상태 점검.

Usage:
    python scripts/diagnose_channels.py
    python scripts/diagnose_channels.py --channels naver_da,google_gdn
"""

import argparse
import asyncio
import io
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from loguru import logger


@dataclass
class SelectorProbe:
    selector: str
    found: bool = False
    count: int = 0
    error: str | None = None


@dataclass
class ChannelDiagnosis:
    channel: str
    status: str = "unknown"
    target_url: str = ""
    config_ok: bool = False
    missing_env_vars: list[str] = field(default_factory=list)
    page_loaded: bool = False
    load_error: str | None = None
    final_url: str | None = None
    selector_probes: list[SelectorProbe] = field(default_factory=list)
    iframe_count: int = 0
    accessible_iframes: int = 0
    blocked_iframes: int = 0
    notes: list[str] = field(default_factory=list)


CHANNEL_PROBES = {
    "naver_search": {
        "url": "https://search.naver.com/search.naver?query=%EB%8C%80%EC%B6%9C",
        "env_vars": [],
        "selectors": [
            "#power_link_body",
            "#power_link_body li.lst",
            "#power_link_body a.lnk_head",
            ".title_url_area",
        ],
    },
    "naver_da": {
        "url": "https://www.naver.com/",
        "env_vars": [],
        "selectors": [
            "a[href*='siape.veta.naver.com']",
            "a[href*='adcr.naver.com']",
            "[class*='ad_area']",
            "[id*='timeboard']",
        ],
    },
    "google_gdn": {
        "url": "https://www.daum.net/",
        "env_vars": [],
        "selectors": [
            'iframe[src*="doubleclick.net"]',
            'iframe[src*="googlesyndication.com"]',
            'a[href*="doubleclick.net"]',
            'ins.adsbygoogle',
        ],
    },
    "youtube_ads": {
        "url": "https://www.youtube.com/results?search_query=%EB%8C%80%EC%B6%9C",
        "env_vars": [],
        "selectors": [
            "ytd-promoted-sparkles-web-renderer",
            "ytd-display-ad-renderer",
            "ytd-promoted-video-renderer",
            "ytd-in-feed-ad-layout-renderer",
            '[class*="sparkles"]',
        ],
    },
    "kakao_da": {
        "url": "https://www.daum.net/",
        "env_vars": [],
        "selectors": [
            'iframe[src*="ad.daum.net"]',
            'iframe[src*="kakaoad"]',
            '[data-tiara-layer="ad"]',
            '[class*="ad_wrap"]',
        ],
    },
    "facebook": {
        "url": "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=KR&q=%EB%8C%80%EC%B6%9C",
        "env_vars": [],
        "selectors": [
            '[data-testid="ad_library_card"]',
            'div[role="article"]',
            '[class*="_7jvw"]',
        ],
    },
}


async def diagnose_channel(channel: str, probe: dict) -> ChannelDiagnosis:
    """채널 1개 진단."""
    from playwright.async_api import async_playwright

    diag = ChannelDiagnosis(channel=channel, target_url=probe["url"])

    # Phase 1: 설정 체크
    missing = [v for v in probe.get("env_vars", []) if not os.getenv(v)]
    diag.missing_env_vars = missing
    diag.config_ok = len(missing) == 0

    # Phase 2: 접속 체크
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        page = await context.new_page()

        try:
            await page.goto(probe["url"], wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(5000)
            diag.page_loaded = True
            diag.final_url = page.url
        except Exception as e:
            diag.page_loaded = False
            diag.load_error = str(e)[:200]
            diag.status = "broken"
            await browser.close()
            return diag

        # Phase 3: 셀렉터 체크
        for selector in probe.get("selectors", []):
            sp = SelectorProbe(selector=selector)
            try:
                count = await page.locator(selector).count()
                sp.found = count > 0
                sp.count = count
            except Exception as e:
                sp.error = str(e)[:100]
            diag.selector_probes.append(sp)

        # Phase 4: iframe 체크
        all_iframes = page.frames[1:]  # skip main frame
        diag.iframe_count = len(all_iframes)
        for frame in all_iframes:
            try:
                await frame.evaluate("document.body ? document.body.innerHTML.length : 0")
                diag.accessible_iframes += 1
            except Exception:
                diag.blocked_iframes += 1

        if diag.iframe_count > 0 and diag.blocked_iframes > 0:
            diag.notes.append(
                f"iframe {diag.accessible_iframes}/{diag.iframe_count} accessible, "
                f"{diag.blocked_iframes} cross-origin blocked"
            )

        # 상태 결정
        found_count = sum(1 for sp in diag.selector_probes if sp.found)
        if found_count == 0:
            diag.status = "broken"
            diag.notes.append("No ad selectors found - DOM structure may have changed")
        elif found_count < len(diag.selector_probes) // 2:
            diag.status = "degraded"
            diag.notes.append("Some selectors working, others stale")
        else:
            diag.status = "ok"

        await browser.close()

    return diag


async def main():
    parser = argparse.ArgumentParser(description="채널 수집 진단")
    parser.add_argument("--channels", default="all", help="진단할 채널 (쉼표 구분)")
    args = parser.parse_args()

    if args.channels == "all":
        channels = list(CHANNEL_PROBES.keys())
    else:
        channels = [c.strip() for c in args.channels.split(",")]

    results = []
    for ch in channels:
        if ch not in CHANNEL_PROBES:
            logger.warning(f"Unknown channel: {ch}")
            continue
        logger.info(f"Diagnosing {ch}...")
        diag = await diagnose_channel(ch, CHANNEL_PROBES[ch])
        results.append(diag)

    # 리포트 출력
    icon_map = {"ok": "[OK]  ", "degraded": "[WARN]", "broken": "[FAIL]"}
    print("\n" + "=" * 70)
    print("  ADSCOPE CHANNEL DIAGNOSTIC REPORT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    for diag in results:
        icon = icon_map.get(diag.status, "[?]   ")
        print(f"\n{icon} {diag.channel}")
        print(f"    URL: {diag.target_url}")
        print(f"    Page loaded: {diag.page_loaded}")
        if diag.load_error:
            print(f"    Load error: {diag.load_error}")
        if diag.missing_env_vars:
            print(f"    Missing env vars: {', '.join(diag.missing_env_vars)}")
        for sp in diag.selector_probes:
            mark = "+" if sp.found else "-"
            print(f"    [{mark}] {sp.selector} (count={sp.count})")
        if diag.iframe_count:
            print(f"    iframes: total={diag.iframe_count}, accessible={diag.accessible_iframes}, blocked={diag.blocked_iframes}")
        for note in diag.notes:
            print(f"    NOTE: {note}")

    print("\n" + "=" * 70)

    # 요약
    ok_count = sum(1 for d in results if d.status == "ok")
    warn_count = sum(1 for d in results if d.status == "degraded")
    fail_count = sum(1 for d in results if d.status == "broken")
    print(f"  Summary: {ok_count} OK / {warn_count} WARN / {fail_count} FAIL")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
