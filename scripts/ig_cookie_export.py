"""Instagram 수동 로그인 -> 쿠키 내보내기 스크립트.

사용법:
    python scripts/ig_cookie_export.py

동작:
    1. headful 브라우저로 Instagram 로그인 페이지를 연다.
    2. 사용자가 수동으로 로그인한다 (2FA/CAPTCHA 포함).
    3. 로그인 완료 후 터미널에서 Enter를 누른다.
    4. 브라우저의 쿠키를 ig_cookies/ig_session.json에 저장한다.
    5. 이후 Instagram 크롤러가 자동으로 이 쿠키를 사용한다.

주의:
    - 반드시 headful 모드로 실행해야 한다 (GUI 필요).
    - 쿠키 만료 시 이 스크립트를 다시 실행하면 된다.
    - 쿠키 파일은 ig_cookies/ 디렉토리에 저장된다.
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
_COOKIE_DIR = _PROJECT_ROOT / "ig_cookies"
_COOKIE_FILE = _COOKIE_DIR / "ig_session.json"


async def main():
    from playwright.async_api import async_playwright

    print("=" * 60)
    print("  Instagram Cookie Export Tool")
    print("=" * 60)
    print()
    print("  1) A browser window will open to Instagram login page.")
    print("  2) Log in manually (complete 2FA/CAPTCHA if needed).")
    print("  3) After login succeeds, come back here and press Enter.")
    print("  4) Cookies will be saved for the crawler to use.")
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 430, "height": 932},
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.4 Mobile/15E148 Safari/604.1"
            ),
            is_mobile=True,
            has_touch=True,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )

        # Stealth
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = await context.new_page()

        print("[*] Opening Instagram login page...")
        await page.goto(
            "https://www.instagram.com/accounts/login/",
            wait_until="domcontentloaded",
        )

        # 자동 로그인 시도
        _ID = "makebestdeal@gmail.com"
        _PW = "pjm990101@"
        try:
            await page.wait_for_selector('input[name="username"]', timeout=10000)
            await page.fill('input[name="username"]', _ID)
            await page.fill('input[name="password"]', _PW)
            await asyncio.sleep(0.5)
            await page.click('button[type="submit"]')
            print("[*] Auto-filled credentials and clicked login.")
        except Exception as e:
            print(f"[!] Auto-fill failed: {e}")
            print("    Please log in manually.")

        print()
        print(">>> 2FA/CAPTCHA가 있으면 브라우저에서 직접 처리하세요. <<<")
        print(">>> 로그인 완료 후 여기서 Enter를 누르세요. <<<")
        print()

        # 동기 input을 비동기 루프에서 실행
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, input, "Press Enter after login: ")

        # 현재 URL 확인
        current_url = page.url
        print(f"[*] Current URL: {current_url}")

        if "accounts/login" in current_url.lower():
            print("[!] WARNING: Still on login page. Cookies may not be valid.")
            confirm = await loop.run_in_executor(
                None, input, "Save anyway? (y/n): ",
            )
            if confirm.strip().lower() != "y":
                print("[*] Cancelled.")
                await browser.close()
                return

        # 쿠키 수집
        all_cookies = await context.cookies()
        ig_cookies = [
            c for c in all_cookies
            if isinstance(c.get("domain"), str)
            and ("instagram.com" in c["domain"]
                 or "facebook.com" in c["domain"])
        ]

        if not ig_cookies:
            print("[!] No Instagram/Facebook cookies found!")
            print("[!] Make sure you completed the login successfully.")
            await browser.close()
            return

        # 저장
        _COOKIE_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "manual_export",
            "browser_url": current_url,
            "cookie_count": len(ig_cookies),
            "cookies": ig_cookies,
        }
        _COOKIE_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print()
        print(f"[+] Success! Saved {len(ig_cookies)} cookies to:")
        print(f"    {_COOKIE_FILE}")
        print()
        print("  The crawler will automatically use these cookies.")
        print("  Re-run this script when cookies expire.")
        print()

        # 세션 쿠키 중 중요한 것들 확인
        important_names = {"sessionid", "ds_user_id", "csrftoken", "mid", "ig_did"}
        found_important = [
            c["name"] for c in ig_cookies
            if c.get("name", "").lower() in important_names
        ]
        if found_important:
            print(f"  Key cookies found: {', '.join(found_important)}")
        else:
            print("  [!] Warning: sessionid/ds_user_id not found.")
            print("  [!] Login may not have completed successfully.")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
