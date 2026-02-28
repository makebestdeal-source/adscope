"""YouTube/Google 수동 로그인 -> 쿠키 내보내기 스크립트.

사용법:
    python scripts/yt_cookie_export.py

동작:
    1. headful 브라우저로 Google 로그인 페이지를 연다.
    2. 사용자가 수동으로 Google 계정에 로그인한다 (2FA 포함).
    3. 로그인 후 YouTube로 이동하여 세션 확인.
    4. 터미널에서 Enter를 누른다.
    5. 브라우저의 쿠키를 yt_cookies/yt_session.json에 저장한다.
    6. 이후 youtube_surf.py 크롤러가 자동으로 이 쿠키를 사용한다.

주의:
    - 반드시 headful 모드로 실행해야 한다 (GUI 필요).
    - 쿠키 만료 시 이 스크립트를 다시 실행하면 된다.
    - 쿠키 파일은 yt_cookies/ 디렉토리에 저장된다.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# dotenv 로드 (선택)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_COOKIE_DIR = _PROJECT_ROOT / "yt_cookies"
_COOKIE_FILE = _COOKIE_DIR / "yt_session.json"

# Google/YouTube 세션에 필수적인 쿠키 목록
_REQUIRED_COOKIES = {"SID", "HSID", "SSID", "APISID", "SAPISID"}
_IMPORTANT_COOKIES = {
    "SID", "HSID", "SSID", "APISID", "SAPISID",
    "LOGIN_INFO", "PREF", "YSC", "VISITOR_INFO1_LIVE",
    "__Secure-1PSID", "__Secure-3PSID",
    "__Secure-1PAPISID", "__Secure-3PAPISID",
}


async def main():
    from playwright.async_api import async_playwright

    print("=" * 60)
    print("  YouTube / Google Cookie Export Tool")
    print("=" * 60)
    print()
    print("  1) A browser window will open to Google login page.")
    print("  2) Log in to your Google account manually.")
    print("     (Complete 2FA if needed.)")
    print("  3) After login, YouTube will load automatically.")
    print("  4) Confirm you are logged in on YouTube.")
    print("  5) Come back here and press Enter to save cookies.")
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
                "--lang=ko-KR",
                "--window-size=1280,900",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )

        # Stealth: webdriver property 숨기기
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = await context.new_page()

        # Step 1: Google 로그인 페이지 열기
        print("[*] Opening Google login page...")
        await page.goto(
            "https://accounts.google.com/signin",
            wait_until="domcontentloaded",
        )

        loop = asyncio.get_event_loop()

        print()
        print(">>> Please log in to your Google account in the browser. <<<")
        print(">>> After login, press Enter here to continue to YouTube. <<<")
        print()
        await loop.run_in_executor(None, input, "Press Enter after Google login: ")

        # Step 2: YouTube로 이동하여 로그인 세션 확인
        print("[*] Navigating to YouTube to confirm session...")
        await page.goto(
            "https://www.youtube.com/",
            wait_until="domcontentloaded",
        )
        await page.wait_for_timeout(3000)

        current_url = page.url
        print(f"[*] Current URL: {current_url}")

        # 로그인 상태 확인 (아바타 버튼 존재 여부)
        logged_in = await page.evaluate("""() => {
            // 로그인 시 존재하는 요소들 확인
            const avatar = document.querySelector(
                'button#avatar-btn, img.yt-img-shadow[alt],'
                + ' yt-img-shadow#img'
            );
            const signIn = document.querySelector(
                'a[href*="accounts.google.com/ServiceLogin"],'
                + ' ytd-button-renderer a[href*="signin"]'
            );
            if (avatar && !signIn) return true;
            if (signIn) return false;
            return null;
        }""")

        if logged_in is True:
            print("[+] YouTube login confirmed!")
        elif logged_in is False:
            print("[!] WARNING: YouTube login NOT detected.")
            print("[!] You may not be logged in.")
            confirm = await loop.run_in_executor(
                None, input, "Save cookies anyway? (y/n): ",
            )
            if confirm.strip().lower() != "y":
                print("[*] Cancelled.")
                await browser.close()
                return
        else:
            print("[?] Could not determine login status.")
            print("[?] Please verify you see your avatar on YouTube.")
            print()
            await loop.run_in_executor(
                None, input,
                "Press Enter to save cookies (or Ctrl+C to cancel): ",
            )

        # Step 3: 쿠키 수집
        all_cookies = await context.cookies()
        yt_cookies = [
            c for c in all_cookies
            if isinstance(c.get("domain"), str)
            and (
                "google.com" in c["domain"]
                or "youtube.com" in c["domain"]
                or "googleapis.com" in c["domain"]
                or "gstatic.com" in c["domain"]
                or "doubleclick.net" in c["domain"]
            )
        ]

        if not yt_cookies:
            print("[!] No Google/YouTube cookies found!")
            print("[!] Make sure you completed the login successfully.")
            await browser.close()
            return

        # Step 4: 필수 쿠키 검증
        cookie_names = {c.get("name", "") for c in yt_cookies}
        found_required = _REQUIRED_COOKIES & cookie_names
        missing_required = _REQUIRED_COOKIES - cookie_names
        found_important = _IMPORTANT_COOKIES & cookie_names

        if missing_required:
            print(f"[!] WARNING: Missing required cookies: {', '.join(sorted(missing_required))}")
            print("[!] Login may not have completed successfully.")
            confirm = await loop.run_in_executor(
                None, input, "Save anyway? (y/n): ",
            )
            if confirm.strip().lower() != "y":
                print("[*] Cancelled.")
                await browser.close()
                return

        # Step 5: 저장
        _COOKIE_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "manual_export",
            "browser_url": current_url,
            "cookie_count": len(yt_cookies),
            "required_cookies_found": sorted(found_required),
            "important_cookies_found": sorted(found_important),
            "cookies": yt_cookies,
        }
        _COOKIE_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print()
        print(f"[+] Success! Saved {len(yt_cookies)} cookies to:")
        print(f"    {_COOKIE_FILE}")
        print()
        print(f"  Required cookies ({len(found_required)}/{len(_REQUIRED_COOKIES)}):")
        print(f"    {', '.join(sorted(found_required))}")
        if missing_required:
            print(f"  Missing: {', '.join(sorted(missing_required))}")
        print()
        print(f"  Important cookies found: {len(found_important)}")
        print(f"    {', '.join(sorted(found_important))}")
        print()
        print("  The youtube_surf crawler will automatically use these cookies.")
        print("  Re-run this script when cookies expire (>30 days).")
        print()

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
