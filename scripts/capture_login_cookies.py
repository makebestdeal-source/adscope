"""로그인 쿠키 반자동 캡처 도구.

Headful 브라우저에서 사용자가 수동 로그인 → 쿠키를 cookie_data/SHARED/에 저장.
저장된 쿠키는 모든 페르소나에서 fallback으로 사용 가능.

Usage:
    python scripts/capture_login_cookies.py --platform meta
    python scripts/capture_login_cookies.py --platform kakao
    python scripts/capture_login_cookies.py --platform meta --mobile
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
COOKIE_DIR = ROOT / "cookie_data" / "SHARED"

# ── 플랫폼별 설정 ──

PLATFORM_CONFIG = {
    "meta": {
        "login_url": "https://www.instagram.com/accounts/login/",
        "success_indicators": [
            "instagram.com/direct",
            "instagram.com/explore",
            "instagram.com/accounts/onetap",
            "instagram.com/?",
        ],
        "success_cookies": ["sessionid", "ds_user_id"],
        "cookie_domains": ["instagram.com", "facebook.com", "fbcdn.net", "meta.com"],
        "output_file": "meta_login.json",
        "timeout_sec": 300,
    },
    "kakao": {
        "login_url": "https://accounts.kakao.com/login/?continue=https://m.daum.net/",
        "success_indicators": [
            "m.daum.net",
            "daum.net/",
            "story.kakao.com",
        ],
        "success_cookies": ["_kawlt", "_karmt", "_kahai"],
        "cookie_domains": ["kakao.com", "daum.net", "kakao.co.kr", "daumcdn.net"],
        "output_file": "kakao_login.json",
        "timeout_sec": 300,
    },
}

# 모바일 디바이스 설정
MOBILE_DEVICE = {
    "viewport": {"width": 360, "height": 780},
    "user_agent": (
        "Mozilla/5.0 (Linux; Android 14; SM-S926B) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Mobile Safari/537.36"
    ),
    "is_mobile": True,
    "has_touch": True,
    "device_scale_factor": 3.0,
}


async def capture_cookies(platform: str, mobile: bool = False):
    config = PLATFORM_CONFIG[platform]
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  {platform.upper()} 로그인 쿠키 캡처")
    print(f"  브라우저가 열리면 직접 로그인해주세요.")
    print(f"  로그인 완료 후 자동으로 쿠키가 저장됩니다.")
    print(f"  제한시간: {config['timeout_sec']}초")
    print(f"{'='*60}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        ctx_opts = {"locale": "ko-KR", "timezone_id": "Asia/Seoul"}
        if mobile:
            ctx_opts.update(MOBILE_DEVICE)

        context = await browser.new_context(**ctx_opts)
        page = await context.new_page()

        await page.goto(config["login_url"], wait_until="domcontentloaded")
        print(f"  로그인 페이지 열림: {config['login_url']}")
        print("  로그인을 진행해주세요...\n")

        # 로그인 완료 감지 루프
        logged_in = False
        elapsed = 0
        check_interval = 2

        while elapsed < config["timeout_sec"]:
            await asyncio.sleep(check_interval)
            elapsed += check_interval

            # 방법 1: URL 변화 감지
            current_url = page.url
            if any(ind in current_url for ind in config["success_indicators"]):
                print(f"  로그인 감지 (URL): {current_url}")
                logged_in = True
                break

            # 방법 2: 세션 쿠키 존재 확인
            cookies = await context.cookies()
            cookie_names = {c["name"] for c in cookies}
            if any(sc in cookie_names for sc in config["success_cookies"]):
                print(f"  로그인 감지 (쿠키): {config['success_cookies']}")
                logged_in = True
                break

            if elapsed % 30 == 0:
                print(f"  대기 중... ({elapsed}초/{config['timeout_sec']}초)")

        if not logged_in:
            print("\n  [TIMEOUT] 로그인 시간 초과. 쿠키가 저장되지 않았습니다.")
            await browser.close()
            return False

        # 로그인 후 잠시 대기 (추가 쿠키 세팅)
        await asyncio.sleep(3)

        # 쿠키 추출
        all_cookies = await context.cookies()

        # 플랫폼 관련 쿠키만 필터
        domain_filter = config["cookie_domains"]
        filtered = [
            c for c in all_cookies
            if isinstance(c.get("domain"), str)
            and any(d in c["domain"] for d in domain_filter)
        ]

        if not filtered:
            # 필터 없이 전체 저장 (도메인 매칭 실패 시)
            filtered = all_cookies
            print(f"  [WARN] 도메인 필터 매칭 안 됨, 전체 쿠키 저장 ({len(all_cookies)}개)")

        # 저장
        output_path = COOKIE_DIR / config["output_file"]
        data = {
            "platform": platform,
            "captured_at": datetime.now(UTC).isoformat(),
            "cookie_count": len(filtered),
            "mobile": mobile,
            "cookies": filtered,
        }
        output_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        print(f"\n  쿠키 저장 완료!")
        print(f"  경로: {output_path}")
        print(f"  쿠키 수: {len(filtered)}개")
        print(f"  도메인: {', '.join(sorted({c['domain'] for c in filtered}))}")

        # 유효성 간단 확인
        session_cookies = [c for c in filtered if c["name"] in config["success_cookies"]]
        if session_cookies:
            print(f"  세션 쿠키: {[c['name'] for c in session_cookies]}")
        else:
            print("  [WARN] 핵심 세션 쿠키가 없습니다. 로그인이 완전하지 않을 수 있습니다.")

        await browser.close()
        return True


def main():
    parser = argparse.ArgumentParser(description="로그인 쿠키 캡처")
    parser.add_argument("--platform", required=True, choices=["meta", "kakao"])
    parser.add_argument("--mobile", action="store_true", help="모바일 뷰포트 사용")
    args = parser.parse_args()

    ok = asyncio.run(capture_cookies(args.platform, mobile=args.mobile))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
