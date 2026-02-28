"""Instagram 모바일 웹 크롤러 -- GraphQL 네트워크 캡처로 광고 수집.

explore/reels 페이지에서 콘텐츠를 직접 클릭하여 탐색하며
GraphQL API 응답의 is_ad/is_sponsored 플래그를 캡처한다.
DOM 기반 광고 탐지 사용 안 함. 네트워크 캡처만 사용.

접촉 측정(contact measurement) 우선순위:
1. 수동 쿠키 세션 복원 (scripts/ig_cookie_export.py 로 내보낸 쿠키)
2. ID/PW 자동 로그인 (INSTAGRAM_USERNAME/PASSWORD 환경변수)
3. 비로그인 공개 브라우징 + 광고 네트워크 캡처 (공개 프로필/릴스)
3a. Threads.net GraphQL 캡처 (로그인 불필요, is_paid_partnership 감지)
3b. Instagram 프로필 API coauthor 추출 (브랜드 콜라보 = 광고 관계)
4. Meta Ad Library fallback (카탈로그 수집, is_contact=False)

수동 쿠키 세션 사용법:
  python scripts/ig_cookie_export.py
  -> 브라우저가 열림 -> 수동 로그인 -> Enter 입력 -> 쿠키 저장
  -> 이후 크롤러 실행 시 자동으로 저장된 쿠키 세션 사용
"""

from __future__ import annotations

import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger
from playwright.async_api import BrowserContext, Page, Response

from crawler.base_crawler import BaseCrawler
from crawler.personas.device_config import DeviceConfig
from crawler.personas.profiles import PersonaProfile

# Meta 광고 라이브러리 URL (Instagram 플랫폼 필터)
_META_AD_LIBRARY_IG_URL = (
    "https://www.facebook.com/ads/library/"
    "?active_status=active&ad_type=all&country=KR&is_targeted_country=false"
    "&media_type=all&publisher_platforms[0]=instagram"
    "&search_type=keyword_unordered&q={query}"
)

# 수동 쿠키 파일 기본 경로
_MANUAL_COOKIE_DIR = os.path.join(os.path.dirname(__file__), "..", "ig_cookies")

# 2FA / CAPTCHA 감지 키워드
_2FA_KEYWORDS = (
    "security code", "verification", "two-factor", "two factor",
    "인증", "보안 코드", "확인 코드",
)
_CAPTCHA_KEYWORDS = (
    "captcha", "보안 확인", "verify it's you", "본인 확인",
    "automated", "suspicious",
)

# 비로그인 공개 페이지에서 방문할 인기 한국 브랜드/인플루언서 공개 프로필
_PUBLIC_PROFILES = [
    "samsung", "hyundai", "kaborin_official", "innisfreeofficial",
    "oliveyoung", "elorea", "coupang.official", "maboroshi_korea",
    "29cm.official", "nike", "adidas", "cocacola", "starbucks",
    "netflixkr", "yogerpresso", "samsungmobile", "lgelectronics",
]

# 광고 네트워크 도메인 패턴 (비로그인 공개 페이지에서도 감지 가능)
_AD_NETWORK_PATTERNS = (
    "i.instagram.com/api/v1/ads/",
    "i.instagram.com/api/v1/feed/injected_",
    "graph.instagram.com",
    "an.facebook.com",
    "www.facebook.com/tr",
    "connect.facebook.net",
    "/logging_client_events",
    "i.instagram.com/api/v1/feed/timeline/",
)

# Threads.net 검색 키워드 (한국 브랜드/카테고리)
_THREADS_SEARCH_QUERIES = [
    "samsung korea", "hyundai", "nike korea", "adidas korea",
    "lotte", "coupang", "musinsa", "oliveyoung",
    "innisfree", "starbucks korea", "netflix korea",
]

# Threads.net 브랜드 프로필 (직접 방문용 - 광고성 콘텐츠 확률 높음)
_THREADS_BRAND_PROFILES = [
    "samsung", "nike", "adidas", "starbucks", "netflix",
    "cocacola", "mcdonalds", "apple", "amazon", "spotify",
]

# Instagram 프로필 API에서 coauthor (브랜드 콜라보) 추출할 프로필 목록
# _COAUTHOR_PRIORITY: 테스트에서 coauthor 포스트가 확인된 프로필 (항상 포함)
_COAUTHOR_PRIORITY_PROFILES = [
    "innisfreeofficial",  # confirmed: Laneige collab
    "samsung",            # confirmed: coauthor posts
    "hyundai",            # confirmed: coauthor posts
]
_BRAND_PROFILES_FOR_COAUTHOR = [
    "samsung", "samsungmobile", "hyundai", "nike", "adidas",
    "innisfreeofficial", "oliveyoung", "starbucks", "netflixkr",
    "cocacola", "lgelectronics", "coupang.official", "29cm.official",
    "laborislane", "amorepacific", "skinfood_official",
]


class InstagramMobileCrawler(BaseCrawler):
    """Instagram GraphQL 네트워크 캡처로 스폰서드 광고 수집."""

    channel = "instagram"
    keyword_dependent = False

    def __init__(self):
        super().__init__()
        self.explore_clicks = max(1, int(os.getenv("INSTAGRAM_EXPLORE_CLICKS", "6")))
        self.reels_swipes = max(1, int(os.getenv("INSTAGRAM_REELS_SWIPES", "10")))
        self.public_profile_visits = max(
            1, int(os.getenv("INSTAGRAM_PUBLIC_PROFILE_VISITS", "8"))
        )
        self._has_login = bool(
            os.getenv("INSTAGRAM_USERNAME", "") and os.getenv("INSTAGRAM_PASSWORD", "")
        )
        self._manual_cookie_dir = Path(
            os.getenv("INSTAGRAM_COOKIE_DIR", _MANUAL_COOKIE_DIR)
        )

    # ================================================================
    # crawl_keyword  (반환 형식 변경 없음)
    # ================================================================

    async def crawl_keyword(
        self,
        keyword: str,
        persona: PersonaProfile,
        device: DeviceConfig,
    ) -> dict:
        start_time = datetime.now(timezone.utc)
        context = await self._create_context(persona, device)
        page = await context.new_page()

        try:
            # -- GraphQL 네트워크 캡처 설정 --
            graphql_ads: list[dict] = []
            graphql_hit_count = [0]
            # 비로그인 공개 브라우징 시 광고 네트워크 응답 캡처용
            ad_network_captures: list[dict] = []

            async def _on_ig_response(response: Response):
                url = response.url
                # GraphQL / API v1 캡처 (로그인 상태 브라우징)
                # /api/graphql (trailing slash 없음) + /graphql/ 둘 다 매칭
                if '/graphql' in url or '/api/v1/' in url:
                    graphql_hit_count[0] += 1
                    try:
                        if response.status == 200:
                            ct = response.headers.get('content-type', '')
                            if 'json' in ct or 'javascript' in ct:
                                body = await response.text()
                                if body and len(body) > 50:
                                    import json as _json
                                    data = _json.loads(body)
                                    found = self._extract_graphql_ads(data)
                                    if found:
                                        logger.debug(
                                            "[{}] GraphQL ad found: {} from {}",
                                            self.channel, len(found), url[:80],
                                        )
                                    graphql_ads.extend(found)
                    except Exception as exc:
                        logger.debug(
                            "[{}] GraphQL parse error: {}",
                            self.channel, exc,
                        )
                # 광고 네트워크 도메인 캡처 (비로그인 공개 페이지)
                for pat in _AD_NETWORK_PATTERNS:
                    if pat in url:
                        try:
                            if response.status == 200:
                                ct = response.headers.get('content-type', '')
                                if 'json' in ct or 'javascript' in ct:
                                    data = await response.json()
                                    found = self._extract_ad_network_data(
                                        data, url,
                                    )
                                    ad_network_captures.extend(found)
                        except Exception:
                            pass
                        break

            page.on('response', _on_ig_response)

            all_ads: list[dict] = []
            logged_in = False
            contact_method = "none"

            # ============================================================
            # Priority 1: 수동 쿠키 세션 복원 (ig_cookie_export.py)
            # ============================================================
            manual_cookies_loaded = await self._load_manual_cookies(context)
            if manual_cookies_loaded:
                cookie_valid = await self._try_restore_session(page, persona)
                if cookie_valid:
                    logged_in = True
                    contact_method = "manual_cookie"
                    logger.info(
                        "[{}] manual cookie session restored",
                        self.channel,
                    )
                else:
                    logger.info(
                        "[{}] manual cookies expired/invalid",
                        self.channel,
                    )

            # ============================================================
            # Priority 2: ID/PW 자동 로그인
            # ============================================================
            if not logged_in and self._has_login:
                cookie_valid = await self._try_restore_session(page, persona)
                if cookie_valid:
                    logged_in = True
                    contact_method = "auto_cookie"
                    logger.info(
                        "[{}] auto cookie session restored",
                        self.channel,
                    )
                else:
                    logged_in = await self._try_login(page)
                    if logged_in:
                        challenge = await self._detect_challenge(page)
                        if challenge:
                            logger.warning(
                                "[{}] challenge detected ({}), skip login",
                                self.channel, challenge,
                            )
                            logged_in = False
                        else:
                            contact_method = "id_pw_login"

            # ============================================================
            # 로그인 성공: GraphQL 캡처 브라우징 (is_contact=True)
            # ============================================================
            if logged_in:
                await self._browse_feed(page)
                await self._browse_explore(page)
                await self._browse_reels(page)

                all_ads = self._build_ig_ads(graphql_ads, is_contact=True)
                logger.info(
                    "[{}] GraphQL contact ads: {} (raw: {}, API hits: {}, method={})",
                    self.channel, len(all_ads), len(graphql_ads),
                    graphql_hit_count[0], contact_method,
                )

                # 수동 쿠키 세션이면 쿠키를 다시 저장 (갱신)
                if contact_method == "manual_cookie":
                    await self._save_manual_cookies(context)

            # ============================================================
            # Priority 3: 비로그인 공개 브라우징 + 광고 네트워크 캡처
            # ============================================================
            if len(all_ads) == 0:
                logger.info(
                    "[{}] trying public browsing (no login)",
                    self.channel,
                )
                public_ads = await self._browse_public_pages(page)
                # 공개 네트워크 캡처에서 얻은 광고도 합산
                if ad_network_captures:
                    public_ads.extend(
                        self._build_network_ads(ad_network_captures)
                    )
                if public_ads:
                    all_ads.extend(public_ads)
                    contact_method = "public_browsing"
                    logger.info(
                        "[{}] public browsing ads: {} (network captures: {})",
                        self.channel, len(public_ads),
                        len(ad_network_captures),
                    )

            # ============================================================
            # Priority 3a: Threads.net GraphQL 캡처 (로그인 불필요)
            # ============================================================
            if len(all_ads) == 0:
                logger.info(
                    "[{}] trying Threads.net GraphQL capture",
                    self.channel,
                )
                threads_ads = await self._browse_threads(context)
                if threads_ads:
                    all_ads.extend(threads_ads)
                    contact_method = "threads_graphql"
                    logger.info(
                        "[{}] Threads.net ads: {}",
                        self.channel, len(threads_ads),
                    )

            # ============================================================
            # Priority 3b: Instagram 프로필 API coauthor 추출
            # ============================================================
            if len(all_ads) == 0:
                logger.info(
                    "[{}] trying profile API coauthor extraction",
                    self.channel,
                )
                coauthor_ads = await self._extract_profile_coauthors(
                    context,
                )
                if coauthor_ads:
                    all_ads.extend(coauthor_ads)
                    contact_method = "profile_coauthor"
                    logger.info(
                        "[{}] profile coauthor ads: {}",
                        self.channel, len(coauthor_ads),
                    )

            # ============================================================
            # Priority 4: Meta Ad Library fallback (is_contact=False)
            # ============================================================
            if len(all_ads) == 0:
                logger.info(
                    "[{}] Meta Ad Library fallback (login={})",
                    self.channel, "O" if logged_in else "X",
                )
                library_ads = await self._fallback_meta_library(
                    context, keyword or "한국", persona.code,
                )
                all_ads.extend(library_ads)
                contact_method = "meta_library_fallback"
                logger.info(
                    "[{}] Meta Ad Library fallback: {} ads",
                    self.channel, len(library_ads),
                )

            await self._save_context_cookies(context, persona)
            screenshot_path = None
            elapsed = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )

            return {
                "keyword": keyword or "instagram_explore",
                "persona_code": persona.code,
                "device": device.device_type,
                "channel": self.channel,
                "captured_at": datetime.now(timezone.utc),
                "page_url": page.url,
                "screenshot_path": screenshot_path,
                "ads": all_ads,
                "crawl_duration_ms": elapsed,
                "contact_method": contact_method,
            }
        finally:
            await page.close()
            await context.close()

    # ================================================================
    # 로그인 / 세션
    # ================================================================

    async def _try_restore_session(
        self, page: Page, persona: PersonaProfile,
    ) -> bool:
        """쿠키 기반 세션 복원 시도. 유효하면 True 반환.

        instagram.com에 접속 후 로그인 페이지로 리다이렉트되는지 확인.
        """
        try:
            await page.goto(
                "https://www.instagram.com/",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await page.wait_for_timeout(3000)

            current_url = page.url.lower()
            if "accounts/login" in current_url or "accounts/signup" in current_url:
                logger.debug(
                    "[{}] cookie session invalid (redirected to login)",
                    self.channel,
                )
                return False

            # 로그인 페이지가 아니면 세션 유효
            logger.debug(
                "[{}] cookie session valid (url: {})",
                self.channel, page.url[:80],
            )
            return True
        except Exception as exc:
            logger.debug("[{}] cookie session check failed: {}", self.channel, exc)
            return False

    async def _try_login(self, page: Page) -> bool:
        """ID/PW 로그인 수행. 성공 시 True, 실패 시 False 반환."""
        username = os.getenv("INSTAGRAM_USERNAME", "")
        password = os.getenv("INSTAGRAM_PASSWORD", "")
        if not username or not password:
            logger.debug(
                "[{}] login credentials missing (INSTAGRAM_USERNAME/PASSWORD)",
                self.channel,
            )
            return False

        try:
            await page.goto(
                "https://www.instagram.com/accounts/login/",
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(3000)

            # 쿠키 동의 / 팝업 처리
            await self._handle_login_wall(page)

            # 사용자명 입력
            username_input = page.locator('input[name="username"]')
            await username_input.fill(username)
            await page.wait_for_timeout(random.randint(500, 1000))

            # 비밀번호 입력
            password_input = page.locator('input[name="password"]')
            await password_input.fill(password)
            await page.wait_for_timeout(random.randint(500, 1000))

            # 로그인 버튼 클릭
            await page.locator('button[type="submit"]').click()
            await page.wait_for_timeout(5000)

            # "나중에 하기" 등 후속 팝업 처리
            await self._handle_login_wall(page)
            await page.wait_for_timeout(2000)
            await self._handle_login_wall(page)

            # -- 로그인 성공 검증: URL 확인 --
            current_url = page.url.lower()
            if "accounts/login" in current_url:
                logger.error(
                    "[{}] login failed: still on login page (url={})",
                    self.channel, page.url,
                )
                return False

            logger.info("[{}] login success: {}", self.channel, username)
            return True

        except Exception as exc:
            logger.error("[{}] login error: {}", self.channel, exc)
            return False

    async def _detect_challenge(self, page: Page) -> str | None:
        """2FA / CAPTCHA 챌린지 감지. 감지 시 유형 문자열 반환, 없으면 None."""
        try:
            body_text = await page.evaluate(
                "() => (document.body ? document.body.innerText : '').toLowerCase()"
            )
            current_url = page.url.lower()

            # 2FA 감지
            for kw in _2FA_KEYWORDS:
                if kw in body_text or kw in current_url:
                    return "2fa"

            # CAPTCHA 감지
            for kw in _CAPTCHA_KEYWORDS:
                if kw in body_text or kw in current_url:
                    return "captcha"

            # challenge URL 패턴
            if "challenge" in current_url or "checkpoint" in current_url:
                return "challenge_page"

            return None
        except Exception as exc:
            logger.debug("[{}] challenge detection error: {}", self.channel, exc)
            return None

    # ================================================================
    # 수동 쿠키 로드/저장
    # ================================================================

    async def _load_manual_cookies(self, context: BrowserContext) -> bool:
        """수동으로 내보낸 Instagram 쿠키 파일을 컨텍스트에 주입.

        ig_cookies/ 디렉토리에서 가장 최근 쿠키 파일을 찾아 로드한다.
        Returns: 쿠키 로드 성공 여부
        """
        cookie_dir = self._manual_cookie_dir
        if not cookie_dir.exists():
            return False

        # 가장 최근에 수정된 JSON 파일 찾기
        cookie_files = sorted(
            cookie_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not cookie_files:
            return False

        cookie_file = cookie_files[0]
        try:
            data = json.loads(cookie_file.read_text(encoding="utf-8"))
            cookies = data.get("cookies", [])
            if not cookies:
                logger.debug(
                    "[{}] manual cookie file empty: {}",
                    self.channel, cookie_file.name,
                )
                return False

            # 만료 체크: updated_at이 30일 이전이면 무시
            updated_at = data.get("updated_at", "")
            if updated_at:
                try:
                    ts = datetime.fromisoformat(updated_at)
                    age_days = (datetime.now(timezone.utc) - ts).days
                    if age_days > 30:
                        logger.info(
                            "[{}] manual cookies expired ({} days old): {}",
                            self.channel, age_days, cookie_file.name,
                        )
                        return False
                except Exception:
                    pass

            # Instagram 도메인 쿠키만 필터
            ig_cookies = [
                c for c in cookies
                if isinstance(c.get("domain"), str)
                and ("instagram.com" in c["domain"]
                     or "facebook.com" in c["domain"])
            ]
            if not ig_cookies:
                logger.debug(
                    "[{}] no Instagram/Facebook cookies in file: {}",
                    self.channel, cookie_file.name,
                )
                return False

            await context.add_cookies(ig_cookies)
            logger.info(
                "[{}] manual cookies loaded: {} cookies from {}",
                self.channel, len(ig_cookies), cookie_file.name,
            )
            return True

        except Exception as exc:
            logger.warning(
                "[{}] manual cookie load failed: {}",
                self.channel, exc,
            )
            return False

    async def _save_manual_cookies(self, context: BrowserContext):
        """현재 세션 쿠키를 수동 쿠키 파일에 갱신 저장."""
        try:
            cookie_dir = self._manual_cookie_dir
            cookie_dir.mkdir(parents=True, exist_ok=True)

            cookies = await context.cookies()
            ig_cookies = [
                c for c in cookies
                if isinstance(c.get("domain"), str)
                and ("instagram.com" in c["domain"]
                     or "facebook.com" in c["domain"])
            ]
            if not ig_cookies:
                return

            out_path = cookie_dir / "ig_session.json"
            data = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "source": "auto_refresh",
                "cookie_count": len(ig_cookies),
                "cookies": ig_cookies,
            }
            out_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.debug(
                "[{}] manual cookies refreshed: {} cookies",
                self.channel, len(ig_cookies),
            )
        except Exception as exc:
            logger.debug(
                "[{}] manual cookie save failed: {}", self.channel, exc,
            )

    # ================================================================
    # 비로그인 공개 브라우징 + 광고 네트워크 캡처
    # ================================================================

    async def _browse_public_pages(self, page: Page) -> list[dict]:
        """비로그인 상태에서 공개 Instagram 페이지를 탐색하며 광고 수집.

        공개 프로필, 공개 포스트/릴스를 방문하고 네트워크 응답에서
        광고 관련 데이터를 캡처한다. Instagram은 비로그인 상태에서도
        i.instagram.com API를 통해 일부 광고 데이터를 전송한다.
        """
        network_ads: list[dict] = []

        # 1) 공개 프로필 방문하면서 네트워크 캡처
        profiles_to_visit = random.sample(
            _PUBLIC_PROFILES,
            min(self.public_profile_visits, len(_PUBLIC_PROFILES)),
        )

        for profile in profiles_to_visit:
            try:
                url = f"https://www.instagram.com/{profile}/"
                await page.goto(
                    url, wait_until="domcontentloaded", timeout=15000,
                )
                await self._handle_login_wall(page)
                await page.wait_for_timeout(random.randint(1500, 2500))

                # 스크롤하여 추가 API 호출 유도
                await self._lightweight_scroll(page, rounds=3)
                await page.wait_for_timeout(random.randint(1000, 2000))

                # 공개 포스트/릴스 링크 수집 후 일부 클릭
                post_links = await page.evaluate("""() => {
                    const links = document.querySelectorAll(
                        'a[href*="/p/"], a[href*="/reel/"]'
                    );
                    return Array.from(links).slice(0, 5).map(a => a.href);
                }""")

                if post_links:
                    target = random.choice(post_links)
                    try:
                        await page.goto(
                            target, wait_until="domcontentloaded",
                            timeout=12000,
                        )
                        await self._handle_login_wall(page)
                        await page.wait_for_timeout(
                            random.randint(2000, 3500),
                        )
                        await self._lightweight_scroll(page, rounds=2)
                    except Exception:
                        pass

            except Exception as exc:
                logger.debug(
                    "[{}] public profile {} failed: {}",
                    self.channel, profile, exc,
                )

        # 2) 공개 Reels 페이지 시도
        try:
            await page.goto(
                "https://www.instagram.com/reels/",
                wait_until="domcontentloaded", timeout=15000,
            )
            await self._handle_login_wall(page)
            await page.wait_for_timeout(2000)

            current_url = page.url.lower()
            if "accounts/login" not in current_url:
                # Reels 접근 성공 -> 스와이프
                await self._swipe_reels(page)
                logger.debug(
                    "[{}] public reels browsing completed",
                    self.channel,
                )
            else:
                logger.debug(
                    "[{}] public reels redirected to login",
                    self.channel,
                )
        except Exception as exc:
            logger.debug(
                "[{}] public reels failed: {}", self.channel, exc,
            )

        # 3) 공개 Explore 페이지 시도
        try:
            await page.goto(
                "https://www.instagram.com/explore/",
                wait_until="domcontentloaded", timeout=15000,
            )
            await self._handle_login_wall(page)
            await page.wait_for_timeout(2000)

            current_url = page.url.lower()
            if "accounts/login" not in current_url:
                await self._lightweight_scroll(page, rounds=4)
                logger.debug(
                    "[{}] public explore browsing completed",
                    self.channel,
                )
        except Exception as exc:
            logger.debug(
                "[{}] public explore failed: {}", self.channel, exc,
            )

        logger.info(
            "[{}] public browsing done: visited {} profiles",
            self.channel, len(profiles_to_visit),
        )
        return network_ads

    # ================================================================
    # Priority 3a: Threads.net GraphQL 캡처
    # ================================================================

    async def _browse_threads(self, context: BrowserContext) -> list[dict]:
        """Threads.net 피드/검색 브라우징으로 paid_partnership 광고 캡처.

        Threads.net은 로그인 없이 접근 가능하며, GraphQL 응답에
        is_paid_partnership / is_ad 플래그가 포함된다.
        네트워크 캡처만 사용 (DOM 탐지 없음).
        """
        page = await context.new_page()
        threads_ads: list[dict] = []

        async def _on_threads_response(response: Response):
            url = response.url
            try:
                if response.status != 200:
                    return
                ct = response.headers.get("content-type", "")
                if "json" not in ct:
                    return
                if ("threads.net" not in url and "threads.com" not in url):
                    return
                if "/graphql" not in url:
                    return

                body = await response.text()
                if not body or len(body) < 100:
                    return

                import json as _json
                data = _json.loads(body)
                found = self._extract_threads_ads(data)
                if found:
                    logger.debug(
                        "[{}] Threads ad found: {} from {}",
                        self.channel, len(found), url[:80],
                    )
                    threads_ads.extend(found)
            except Exception as exc:
                logger.debug(
                    "[{}] Threads parse error: {}",
                    self.channel, exc,
                )

        page.on("response", _on_threads_response)

        try:
            # 1) Threads 홈페이지 피드 브라우징
            logger.debug("[{}] Threads home feed browsing", self.channel)
            await page.goto(
                "https://www.threads.net/",
                wait_until="domcontentloaded", timeout=15000,
            )
            current = page.url.lower()
            if "login" not in current:
                await page.wait_for_timeout(3000)
                for i in range(15):
                    dist = 500 + i * 50 + random.randint(-30, 30)
                    await page.evaluate(f"window.scrollBy(0, {dist})")
                    await page.wait_for_timeout(random.randint(800, 1200))

            # 2) 브랜드 프로필 직접 방문 (paid_partnership 확률 높음)
            brand_profiles = random.sample(
                _THREADS_BRAND_PROFILES,
                min(4, len(_THREADS_BRAND_PROFILES)),
            )
            for brand in brand_profiles:
                try:
                    profile_url = f"https://www.threads.net/@{brand}"
                    await page.goto(
                        profile_url,
                        wait_until="domcontentloaded", timeout=12000,
                    )
                    current = page.url.lower()
                    if "login" in current:
                        continue

                    await page.wait_for_timeout(2000)
                    for i in range(10):
                        dist = 400 + i * 50 + random.randint(-20, 20)
                        await page.evaluate(f"window.scrollBy(0, {dist})")
                        await page.wait_for_timeout(random.randint(700, 1100))

                except Exception as exc:
                    logger.debug(
                        "[{}] Threads profile '@{}' failed: {}",
                        self.channel, brand, exc,
                    )

            # 3) 한국 브랜드 검색으로 추가 콘텐츠 로드
            queries = random.sample(
                _THREADS_SEARCH_QUERIES,
                min(3, len(_THREADS_SEARCH_QUERIES)),
            )
            for query in queries:
                try:
                    search_url = (
                        f"https://www.threads.net/search"
                        f"?q={query}&serp_type=default"
                    )
                    await page.goto(
                        search_url,
                        wait_until="domcontentloaded", timeout=12000,
                    )
                    current = page.url.lower()
                    if "login" in current:
                        continue

                    await page.wait_for_timeout(2000)
                    for i in range(8):
                        dist = 400 + i * 60 + random.randint(-20, 20)
                        await page.evaluate(f"window.scrollBy(0, {dist})")
                        await page.wait_for_timeout(random.randint(600, 1000))

                except Exception as exc:
                    logger.debug(
                        "[{}] Threads search '{}' failed: {}",
                        self.channel, query, exc,
                    )

        except Exception as exc:
            logger.debug(
                "[{}] Threads browsing failed: {}", self.channel, exc,
            )
        finally:
            await page.close()

        return self._build_threads_ads(threads_ads)

    def _extract_threads_ads(self, data, depth: int = 0) -> list[dict]:
        """Threads GraphQL 응답에서 paid_partnership/is_ad 포스트 추출."""
        if depth > 20:
            return []
        ads: list[dict] = []

        if isinstance(data, dict):
            # is_paid_partnership == True 인 포스트 감지
            if data.get("is_paid_partnership") is True:
                user = data.get("user") or data.get("owner") or {}
                username = (
                    user.get("username", "")
                    if isinstance(user, dict) else ""
                )
                caption = data.get("caption") or {}
                text = (
                    caption.get("text", "")[:300]
                    if isinstance(caption, dict) else ""
                )
                # 스폰서 정보 추출
                tpa_info = data.get("text_post_app_info") or {}
                sponsor_user = (
                    tpa_info.get("sponsor_user")
                    or tpa_info.get("branded_content_sponsor")
                    or {}
                )
                sponsor = (
                    sponsor_user.get("username", "")
                    if isinstance(sponsor_user, dict) else ""
                )
                ads.append({
                    "username": username,
                    "text": text,
                    "sponsor": sponsor,
                    "type": "paid_partnership",
                    "code": data.get("code", ""),
                })

            # is_ad == True 인 포스트 감지
            if data.get("is_ad") is True or data.get("is_sponsored") is True:
                user = data.get("user") or data.get("owner") or {}
                username = (
                    user.get("username", "")
                    if isinstance(user, dict) else ""
                )
                caption = data.get("caption") or {}
                text = (
                    caption.get("text", "")[:300]
                    if isinstance(caption, dict) else ""
                )
                link = (
                    data.get("link") or data.get("cta_url") or None
                )
                ads.append({
                    "username": username,
                    "text": text,
                    "sponsor": "",
                    "type": "is_ad",
                    "url": link,
                    "code": data.get("code", ""),
                })

            for v in data.values():
                ads.extend(self._extract_threads_ads(v, depth + 1))

        elif isinstance(data, list):
            for item in data:
                ads.extend(self._extract_threads_ads(item, depth + 1))

        return ads

    def _build_threads_ads(self, captures: list[dict]) -> list[dict]:
        """Threads 캡처를 정규화된 광고 리스트로 변환."""
        ads: list[dict] = []
        seen: set[str] = set()

        for cap in captures:
            username = cap.get("username", "")
            sponsor = cap.get("sponsor", "")
            code = cap.get("code", "")
            ad_url = cap.get("url")

            # 광고주 이름: sponsor > username
            advertiser = sponsor or username
            if not advertiser:
                continue

            sig = f"{advertiser}|{code}"
            if sig in seen:
                continue
            seen.add(sig)

            # Threads 포스트 URL
            post_url = ad_url
            if not post_url and code:
                post_url = f"https://www.threads.net/post/{code}"

            display_url = None
            if post_url:
                try:
                    display_url = urlparse(post_url).netloc
                except Exception:
                    pass

            ads.append({
                "advertiser_name": advertiser,
                "ad_text": cap.get("text") or "threads_sponsored",
                "ad_description": None,
                "url": post_url,
                "display_url": display_url or "threads.net",
                "position": len(ads) + 1,
                "ad_type": "social_sponsored",
                "ad_placement": "threads_feed",
                "extra_data": {
                    "source_url": "threads_graphql",
                    "detection_method": "threads_graphql_intercept",
                    "partnership_type": cap.get("type", ""),
                    "sponsor_username": sponsor,
                    "poster_username": cap.get("username", ""),
                    "is_contact": True,
                    "mobile_web": True,
                },
            })

        return ads

    # ================================================================
    # Priority 3b: Instagram 프로필 API coauthor 추출
    # ================================================================

    async def _extract_profile_coauthors(
        self, context: BrowserContext,
    ) -> list[dict]:
        """Instagram 프로필 embed 페이지에서 coauthor_producers 추출.

        브랜드 프로필의 /embed/ 페이지 HTML에 포함된
        coauthor_producers (브랜드 콜라보/인플루언서 협업) 데이터를
        추출한다. 이는 실제 광고 관계(브랜드 파트너십)를 나타낸다.

        주의: Instagram 프로필 페이지는 2026년 2월 기준 로그인 필수로 변경되었으나,
        /embed/ 페이지는 로그인 없이 접근 가능하며, HTML 내부 JavaScript에
        coauthor_producers 데이터가 포함된다.
        """
        import re as _re

        # embed 페이지용 데스크톱 컨텍스트 생성
        desktop_ctx = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        await desktop_ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        profile_ads: list[dict] = []

        try:
            # 우선 프로필 (coauthor 확인됨) + 랜덤 추가 프로필
            remaining = [
                p for p in _BRAND_PROFILES_FOR_COAUTHOR
                if p not in _COAUTHOR_PRIORITY_PROFILES
            ]
            extra_count = min(5, len(remaining))
            extra = random.sample(remaining, extra_count)
            profiles = list(_COAUTHOR_PRIORITY_PROFILES) + extra

            logger.debug(
                "[{}] coauthor embed profiles to visit ({}): {}",
                self.channel, len(profiles), profiles,
            )

            for profile_name in profiles:
                page = await desktop_ctx.new_page()
                try:
                    embed_url = (
                        f"https://www.instagram.com/{profile_name}/embed/"
                    )
                    logger.debug(
                        "[{}] visiting embed: {}",
                        self.channel, profile_name,
                    )
                    await page.goto(
                        embed_url,
                        wait_until="domcontentloaded",
                        timeout=15000,
                    )
                    await page.wait_for_timeout(random.randint(1500, 2500))

                    # embed HTML에서 coauthor 데이터 추출
                    html = await page.evaluate(
                        "() => document.documentElement.outerHTML"
                    )
                    found = self._extract_coauthor_from_embed_html(
                        html, profile_name,
                    )
                    if found:
                        logger.info(
                            "[{}] coauthor ads from embed {}: {}",
                            self.channel, profile_name, len(found),
                        )
                        profile_ads.extend(found)

                except Exception as exc:
                    logger.debug(
                        "[{}] embed {} coauthor failed: {}",
                        self.channel, profile_name, exc,
                    )
                finally:
                    await page.close()

            logger.info(
                "[{}] coauthor embed extraction done: {} raw ads from {} profiles",
                self.channel, len(profile_ads), len(profiles),
            )

        except Exception as exc:
            logger.debug(
                "[{}] coauthor extraction failed: {}",
                self.channel, exc,
            )
        finally:
            await desktop_ctx.close()

        return self._build_coauthor_ads(profile_ads)

    def _extract_coauthor_from_embed_html(
        self, html: str, profile_name: str,
    ) -> list[dict]:
        """embed 페이지 HTML에서 coauthor_producers 데이터 추출.

        Instagram embed 페이지의 JavaScript에는 포스트 데이터가
        escaped JSON 형식으로 포함되어 있다.
        coauthor_producers 배열에서 콜라보 파트너 정보를 추출한다.
        """
        import re as _re
        ads: list[dict] = []

        try:
            # non-empty coauthor_producers 배열 찾기
            # 형식: coauthor_producers\":[{\"id\":\"...
            marker = 'coauthor_producers\\":[{\\"id\\"'
            idx = 0
            while True:
                idx = html.find(marker, idx)
                if idx == -1:
                    break

                # 배열 시작점 찾기
                arr_prefix = 'coauthor_producers\\":'
                arr_start_search = html.index(arr_prefix, idx) + len(arr_prefix)
                arr_start = html.index('[', arr_start_search)

                # 대응하는 ] 찾기
                depth = 0
                arr_end = arr_start
                for i in range(arr_start, min(len(html), arr_start + 5000)):
                    if html[i] == '[':
                        depth += 1
                    elif html[i] == ']':
                        depth -= 1
                    if depth == 0:
                        arr_end = i + 1
                        break

                arr_str = html[arr_start:arr_end]

                # JSON unescape: \\" -> ", \\/ -> /
                unescaped = arr_str.replace('\\"', '"').replace('\\/', '/')

                try:
                    arr = json.loads(unescaped)
                except json.JSONDecodeError:
                    idx = idx + 1
                    continue

                if not arr:
                    idx = idx + 1
                    continue

                # coauthor 정보 추출
                coauthor_names = []
                external_coauthors = []
                for c in arr:
                    if isinstance(c, dict):
                        ca_name = c.get("username", "")
                        if ca_name:
                            coauthor_names.append(ca_name)
                            if ca_name != profile_name:
                                external_coauthors.append(ca_name)

                # shortcode 찾기 (coauthor 위치 앞에서)
                before = html[max(0, idx - 5000):idx]
                sc_matches = _re.findall(
                    r'shortcode\\":\\"([A-Za-z0-9_-]+)', before,
                )
                shortcode = sc_matches[-1] if sc_matches else ""

                # caption 텍스트 찾기
                cap_matches = _re.findall(
                    r'"text\\":\\"([^"\\]{0,200})', before,
                )
                caption_text = cap_matches[-1] if cap_matches else ""

                ads.append({
                    "brand": profile_name,
                    "brand_username": profile_name,
                    "coauthors": coauthor_names,
                    "external_coauthors": external_coauthors,
                    "caption": caption_text[:300],
                    "shortcode": shortcode,
                    "image_url": None,
                })

                idx = idx + 1

        except Exception as exc:
            logger.debug(
                "[{}] embed coauthor parse error for {}: {}",
                self.channel, profile_name, exc,
            )

        return ads

    def _build_coauthor_ads(self, captures: list[dict]) -> list[dict]:
        """coauthor 캡처를 정규화된 광고 리스트로 변환."""
        ads: list[dict] = []
        seen: set[str] = set()

        for cap in captures:
            brand = cap.get("brand", "")
            coauthors = cap.get("coauthors", [])
            shortcode = cap.get("shortcode", "")

            if not brand:
                continue

            sig = f"{brand}|{shortcode}"
            if sig in seen:
                continue
            seen.add(sig)

            post_url = None
            if shortcode:
                post_url = f"https://www.instagram.com/p/{shortcode}/"

            coauthor_str = ", ".join(coauthors) if coauthors else ""
            ad_text = cap.get("caption") or f"{brand} x {coauthor_str}"

            ads.append({
                "advertiser_name": brand,
                "ad_text": ad_text[:300],
                "ad_description": (
                    f"Brand collab: {coauthor_str}"
                    if coauthor_str else None
                ),
                "url": post_url,
                "display_url": "instagram.com",
                "position": len(ads) + 1,
                "ad_type": "branded_content",
                "ad_placement": "instagram_profile_collab",
                "extra_data": {
                    "source_url": "web_profile_info_api",
                    "image_url": cap.get("image_url"),
                    "detection_method": "profile_coauthor_intercept",
                    "brand_username": cap.get("brand_username", ""),
                    "coauthor_usernames": coauthors,
                    "is_contact": True,
                    "mobile_web": True,
                },
            })

        return ads

    # ================================================================
    # 광고 네트워크 데이터 추출
    # ================================================================

    def _extract_ad_network_data(
        self, data, source_url: str,
    ) -> list[dict]:
        """광고 네트워크 응답에서 광고 데이터 추출.

        비로그인 상태에서도 Instagram API 응답에 포함될 수 있는
        sponsored/promoted 콘텐츠를 탐지한다.
        """
        ads: list[dict] = []

        # GraphQL 스타일 광고 추출 재사용
        found = self._extract_graphql_ads(data)
        if found:
            ads.extend(found)

        # feed timeline 응답에서 injected items 추출
        if isinstance(data, dict):
            items = data.get("feed_items") or data.get("items") or []
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    # injected ad 패턴
                    media = item.get("media_or_ad") or item
                    if (media.get("ad_id")
                            or media.get("ad_action")
                            or media.get("dr_ad_type")):
                        user = media.get("user") or {}
                        advertiser = (
                            user.get("username")
                            if isinstance(user, dict) else None
                        )
                        caption_obj = media.get("caption") or {}
                        caption = (
                            caption_obj.get("text", "")
                            if isinstance(caption_obj, dict)
                            else str(caption_obj)
                        )
                        link = (
                            media.get("link")
                            or media.get("cta_url")
                            or media.get("story_cta_url")
                        )
                        ads.append({
                            "advertiser": advertiser,
                            "body": (caption or "ig_network_ad")[:300],
                            "url": link,
                            "image_url": None,
                        })

        return ads

    def _build_network_ads(self, captures: list[dict]) -> list[dict]:
        """비로그인 네트워크 캡처를 정규화된 광고 리스트로 변환."""
        ads: list[dict] = []
        seen: set[str] = set()

        for cap in captures:
            url = cap.get("url")
            advertiser = cap.get("advertiser")
            if not url and not advertiser:
                continue

            sig = f"{url or ''}|{advertiser or ''}"
            if sig in seen:
                continue
            seen.add(sig)

            display_url = None
            if url:
                try:
                    display_url = urlparse(url).netloc
                except Exception:
                    pass

            if not advertiser and display_url:
                advertiser = (
                    display_url.removeprefix("www.")
                    .removeprefix("l.instagram.com")
                )

            ads.append({
                "advertiser_name": advertiser,
                "ad_text": cap.get("body") or "ig_network_ad",
                "ad_description": None,
                "url": url,
                "display_url": display_url,
                "position": len(ads) + 1,
                "ad_type": "feed_sponsored",
                "ad_placement": "instagram_public_network",
                "extra_data": {
                    "source_url": "network_intercept",
                    "image_url": cap.get("image_url"),
                    "mobile_web": True,
                    "detection_method": "public_network_capture",
                    "is_contact": True,
                },
            })

        return ads

    # ================================================================
    # 경량 브라우징 (naver_da.py 패턴 참고)
    # ================================================================

    async def _lightweight_scroll(self, page: Page, rounds: int = 4):
        """경량 JS 스크롤 -- _human_scroll 대신 빠른 scrollBy."""
        for s in range(rounds):
            dist = 400 + s * 120 + random.randint(-50, 50)
            await page.evaluate(f"window.scrollBy(0, {dist})")
            await page.wait_for_timeout(random.randint(600, 1200))

    async def _browse_feed(self, page: Page):
        """홈 피드 스크롤 (로그인 상태)."""
        await page.goto(
            "https://www.instagram.com/",
            wait_until="domcontentloaded",
        )
        await self._handle_login_wall(page)
        await page.wait_for_timeout(2000)

        for _ in range(self.explore_clicks):
            await self._lightweight_scroll(page, rounds=2)
            await page.wait_for_timeout(random.randint(1500, 2500))

        # 고정 2초 대기 (inter_page_cooldown 대체)
        await page.wait_for_timeout(2000)

    async def _browse_explore(self, page: Page):
        """Explore 페이지 탐색."""
        await page.goto(
            "https://www.instagram.com/explore/",
            wait_until="domcontentloaded",
        )
        await self._handle_login_wall(page)
        await page.wait_for_timeout(2000)
        await self._click_explore_content(page)

        # 고정 2초 대기
        await page.wait_for_timeout(2000)

    async def _browse_reels(self, page: Page):
        """Reels 피드 탐색."""
        await page.goto(
            "https://www.instagram.com/reels/",
            wait_until="domcontentloaded",
        )
        await self._handle_login_wall(page)
        await page.wait_for_timeout(2000)
        await self._swipe_reels(page)

    # ================================================================
    # Explore 콘텐츠 클릭
    # ================================================================

    async def _click_explore_content(self, page: Page):
        """Explore 그리드에서 썸네일을 클릭하여 콘텐츠 탐색."""
        for i in range(self.explore_clicks):
            try:
                await self._lightweight_scroll(page, rounds=2)

                clicked = await page.evaluate("""() => {
                    const items = document.querySelectorAll(
                        'a[href*="/p/"], a[href*="/reel/"]'
                    );
                    if (items.length === 0) return false;
                    const target = items[Math.floor(Math.random() * items.length)];
                    target.click();
                    return true;
                }""")

                if clicked:
                    await page.wait_for_timeout(random.randint(2000, 3500))
                    await self._handle_login_wall(page)
                    await page.go_back()
                    await page.wait_for_timeout(random.randint(500, 1200))
                else:
                    await self._lightweight_scroll(page, rounds=3)

            except Exception as exc:
                logger.debug("[{}] explore click {} failed: {}", self.channel, i, exc)
                try:
                    await page.goto(
                        "https://www.instagram.com/explore/",
                        wait_until="domcontentloaded",
                    )
                    await page.wait_for_timeout(2000)
                except Exception:
                    pass

        logger.debug(
            "[{}] explore clicks {} done", self.channel, self.explore_clicks,
        )

    # ================================================================
    # Reels 스와이프
    # ================================================================

    async def _swipe_reels(self, page: Page):
        """Reels 피드에서 스와이프하여 콘텐츠 탐색."""
        for i in range(self.reels_swipes):
            try:
                dist = 600 + random.randint(0, 400)
                await page.evaluate(f"window.scrollBy(0, {dist})")
                await page.wait_for_timeout(random.randint(1500, 3000))
            except Exception as exc:
                logger.debug("[{}] reels swipe {} failed: {}", self.channel, i, exc)

        logger.debug(
            "[{}] reels swipes {} done", self.channel, self.reels_swipes,
        )

    # ================================================================
    # 로그인 월 처리
    # ================================================================

    async def _handle_login_wall(self, page: Page):
        """인스타그램 로그인 팝업/월 자동 닫기."""
        for _ in range(5):
            try:
                dismissed = await page.evaluate("""() => {
                    const btns = document.querySelectorAll(
                        'button, a, div[role="button"]'
                    );
                    for (const btn of btns) {
                        const t = (btn.textContent || '').trim();
                        if (/^(Not Now|나중에 하기|Not now|닫기|Close|Later|Cancel)$/i.test(t)) {
                            btn.click(); return 'dismiss:' + t;
                        }
                    }
                    const overlay = document.querySelector(
                        '[role="dialog"] button[aria-label="Close"]'
                    );
                    if (overlay) { overlay.click(); return 'overlay'; }
                    const loginOverlay = document.querySelector(
                        'div[class*="RnEpo"], div[class*="LoginAndSignupPage"]'
                    );
                    if (loginOverlay) {
                        loginOverlay.remove(); return 'removed_overlay';
                    }
                    return null;
                }""")
                if dismissed:
                    await page.wait_for_timeout(1500)
                    return
            except Exception:
                pass
            await page.wait_for_timeout(1000)

    # ================================================================
    # GraphQL 광고 추출
    # ================================================================

    def _extract_graphql_ads(self, data) -> list[dict]:
        """GraphQL 응답 JSON에서 스폰서드 포스트 재귀 추출."""
        ads: list[dict] = []
        self._walk_json_for_ads(data, ads)
        return ads

    def _walk_json_for_ads(self, obj, ads: list[dict]):
        """재귀적으로 JSON을 순회하며 is_ad/is_sponsored 플래그 탐색."""
        if isinstance(obj, dict):
            if obj.get('is_ad') or obj.get('is_sponsored') or obj.get('ad_id'):
                user = (
                    obj.get('user') or obj.get('owner')
                    or obj.get('sponsor') or {}
                )
                advertiser = (
                    user.get('username') if isinstance(user, dict) else None
                )

                caption = ''
                cap = obj.get('caption')
                if isinstance(cap, dict):
                    caption = cap.get('text', '')
                elif isinstance(cap, str):
                    caption = cap

                link = (
                    obj.get('link') or obj.get('cta_url')
                    or obj.get('story_cta_url') or None
                )

                image_url = None
                iv2 = obj.get('image_versions2')
                if isinstance(iv2, dict):
                    candidates = iv2.get('candidates', [])
                    if candidates and isinstance(candidates[0], dict):
                        image_url = candidates[0].get('url')

                ads.append({
                    'advertiser': advertiser,
                    'body': (caption or 'instagram_sponsored')[:300],
                    'url': link,
                    'image_url': image_url,
                })

            for v in obj.values():
                self._walk_json_for_ads(v, ads)
        elif isinstance(obj, list):
            for item in obj:
                self._walk_json_for_ads(item, ads)

    # ================================================================
    # 결과 빌드
    # ================================================================

    def _build_ig_ads(
        self, captures: list[dict], *, is_contact: bool = False,
    ) -> list[dict]:
        """GraphQL 캡처를 정규화된 광고 리스트로."""
        ads: list[dict] = []
        seen: set[str] = set()

        for cap in captures:
            url = cap.get('url')
            advertiser = cap.get('advertiser')
            if not url and not advertiser:
                continue

            sig = f"{url or ''}|{advertiser or ''}"
            if sig in seen:
                continue
            seen.add(sig)

            display_url = None
            if url:
                try:
                    display_url = urlparse(url).netloc
                except Exception:
                    pass

            if not advertiser and display_url:
                advertiser = (
                    display_url.removeprefix('www.')
                    .removeprefix('l.instagram.com')
                )

            ads.append({
                'advertiser_name': advertiser,
                'ad_text': cap.get('body') or 'instagram_sponsored',
                'ad_description': None,
                'url': url,
                'display_url': display_url,
                'position': len(ads) + 1,
                'ad_type': 'feed_sponsored',
                'ad_placement': 'instagram_explore',
                'extra_data': {
                    'source_url': 'graphql_api',
                    'image_url': cap.get('image_url'),
                    'mobile_web': True,
                    'detection_method': 'graphql_intercept',
                    'is_contact': is_contact,
                },
            })

        return ads

    # ================================================================
    # Meta Ad Library fallback (비로그인 시)
    # ================================================================

    # 다양한 업종 키워드로 광고 수집 범위 확대
    _LIBRARY_KEYWORDS = [
        "쇼핑", "뷰티", "패션", "게임", "금융",
        "여행", "교육", "건강", "음식", "테크",
    ]

    async def _fallback_meta_library(
        self, context, keyword: str, persona_code: str,
    ) -> list[dict]:
        """Meta 광고 라이브러리에서 Instagram 플랫폼 광고 수집 (fallback).

        입력 키워드 + 업종 키워드 2개를 추가 검색하여 수집량 확대.
        """
        all_ads: list[dict] = []
        seen_sigs: set[str] = set()

        # 메인 키워드 + 랜덤 업종 키워드 2개
        keywords = [keyword]
        extra = random.sample(self._LIBRARY_KEYWORDS, min(2, len(self._LIBRARY_KEYWORDS)))
        keywords.extend(extra)

        for kw in keywords:
            try:
                ads = await self._search_ad_library(
                    context, kw, persona_code, seen_sigs,
                )
                all_ads.extend(ads)
            except Exception as e:
                logger.debug(
                    "[{}] Ad Library keyword '{}' failed: {}",
                    self.channel, kw, e,
                )

        logger.info(
            "[{}] Ad Library fallback total: {} ads ({} keywords)",
            self.channel, len(all_ads), len(keywords),
        )
        return all_ads

    async def _search_ad_library(
        self, context, keyword: str, persona_code: str,
        seen_sigs: set[str],
    ) -> list[dict]:
        """단일 키워드로 Meta Ad Library 검색."""
        page = await context.new_page()
        search_url = _META_AD_LIBRARY_IG_URL.format(query=keyword)

        try:
            await page.goto(search_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # 스크롤 10회로 증가 (5 -> 10)
            for s in range(10):
                dist = 800 + s * 100 + random.randint(-50, 50)
                await page.evaluate(f"window.scrollBy(0, {dist})")
                await page.wait_for_timeout(random.randint(600, 1000))

            # -- 광고 크리에이티브(이미지/영상)만 정밀 캡처 --
            card_screenshot_map: dict[int, str] = {}
            try:
                creative_info = await page.evaluate("""() => {
                    const results = [];
                    // 카드 컨테이너 탐색
                    const cardSels = [
                        '[data-testid*="ad-content-body"]',
                        'div[role="article"]',
                    ];
                    let cards = [];
                    let useParent = false;
                    for (const sel of cardSels) {
                        cards = Array.from(document.querySelectorAll(sel));
                        if (cards.length > 0) {
                            useParent = sel.includes('ad-content-body');
                            break;
                        }
                    }
                    for (let i = 0; i < Math.min(cards.length, 30); i++) {
                        let card = cards[i];
                        if (useParent) {
                            for (let j = 0; j < 3; j++) {
                                if (card.parentElement) card = card.parentElement;
                            }
                        }
                        // 크리에이티브 요소 탐색: 영상 > 이미지 순
                        const video = card.querySelector('video');
                        if (video) {
                            const rect = video.getBoundingClientRect();
                            if (rect.width > 50 && rect.height > 50) {
                                results.push({idx: i, type: 'video'});
                                continue;
                            }
                        }
                        // 광고 이미지 (scontent/fbcdn = 실제 크리에이티브)
                        const img = card.querySelector(
                            'img[src*="scontent"], img[src*="fbcdn"]'
                        );
                        if (img) {
                            const rect = img.getBoundingClientRect();
                            if (rect.width > 80 && rect.height > 50) {
                                results.push({idx: i, type: 'image'});
                                continue;
                            }
                        }
                        results.push({idx: i, type: null});
                    }
                    return results;
                }""")

                if creative_info:
                    for info in creative_info:
                        idx = info["idx"]
                        ctype = info.get("type")
                        if not ctype:
                            continue
                        try:
                            # 카드 내부에서 크리에이티브 요소만 선택
                            card_sels = [
                                '[data-testid*="ad-content-body"]',
                                'div[role="article"]',
                            ]
                            card_el = None
                            for cs in card_sels:
                                loc = page.locator(cs)
                                if await loc.count() > idx:
                                    card_el = loc.nth(idx)
                                    if "ad-content-body" in cs:
                                        card_el = card_el.locator("xpath=ancestor::*[3]")
                                    break
                            if not card_el:
                                continue

                            if ctype == "video":
                                target = card_el.locator("video").first
                            else:
                                target = card_el.locator(
                                    'img[src*="scontent"], img[src*="fbcdn"]'
                                ).first

                            if await target.count() > 0 and await target.is_visible():
                                path = await self._capture_ad_element(
                                    page, target, keyword, persona_code,
                                    placement_name=f"ig_creative_{idx}",
                                )
                                if path:
                                    card_screenshot_map[idx] = path
                        except Exception:
                            pass
                    logger.debug(
                        "[{}] creative screenshots: {} captured",
                        self.channel, len(card_screenshot_map),
                    )
            except Exception as exc:
                logger.debug(
                    "[{}] creative screenshot capture failed: {}",
                    self.channel, exc,
                )

            # 광고 카드 파싱 (3단계 폴백)
            raw_ads = await page.evaluate("""() => {
                const clean = (v) => (v || '').replace(/\\s+/g, ' ').trim();
                const results = [];

                // 전략 1: data-testid 기반
                const adBodies = document.querySelectorAll(
                    '[data-testid*="ad-content-body"]'
                );
                for (const body of Array.from(adBodies).slice(0, 30)) {
                    let card = body;
                    for (let i = 0; i < 3; i++) {
                        if (card.parentElement) card = card.parentElement;
                    }

                    let advertiserName = null;
                    const spans = card.querySelectorAll('span');
                    for (const span of spans) {
                        const t = span.textContent.trim();
                        if (t.length < 2 || /^\\d+:\\d+/.test(t)) continue;
                        if (/started|running|active|inactive/i.test(t))
                            continue;
                        advertiserName = t.slice(0, 150);
                        break;
                    }

                    const img = card.querySelector(
                        'img[src*="scontent"], img[src*="fbcdn"]'
                    );
                    const imageUrl = img
                        ? (img.currentSrc || img.src) : null;
                    const pageLink = card.querySelector(
                        'a[href*="view_all_page_id"], a[href*="/ads/?"]'
                    );

                    results.push({
                        advertiser_name: advertiserName,
                        ad_text: clean(card.innerText || '').slice(0, 500),
                        url: pageLink ? pageLink.href : null,
                        image_url: imageUrl,
                        position: results.length + 1,
                    });
                }

                if (results.length > 0) return results;

                // 전략 2: role=article 기반
                const articles = document.querySelectorAll(
                    'div[role="article"]'
                );
                for (const art of Array.from(articles).slice(0, 30)) {
                    const spans = art.querySelectorAll('span');
                    let advertiserName = null;
                    for (const span of spans) {
                        const t = span.textContent.trim();
                        if (t.length < 2 || t.length > 100) continue;
                        if (/started|running|active|inactive/i.test(t))
                            continue;
                        if (/^\\d+$/.test(t)) continue;
                        advertiserName = t;
                        break;
                    }

                    const img = art.querySelector('img[src*="scontent"]');
                    const imageUrl = img
                        ? (img.currentSrc || img.src) : null;
                    const link = art.querySelector('a[href]');

                    results.push({
                        advertiser_name: advertiserName,
                        ad_text: clean(art.innerText || '').slice(0, 500),
                        url: link ? link.href : null,
                        image_url: imageUrl,
                        position: results.length + 1,
                    });
                }

                if (results.length > 0) return results;

                // 전략 3: 링크 기반 폴백
                const links = document.querySelectorAll(
                    'a[href*="ads/library"]'
                );
                return Array.from(links).slice(0, 20).map((a, idx) => ({
                    advertiser_name: clean(a.innerText).slice(0, 100),
                    ad_text: clean(a.title || a.innerText || ''),
                    url: a.href || null,
                    image_url: null,
                    position: idx + 1,
                }));
            }""")

            ads: list[dict] = []

            for item in raw_ads:
                advertiser = item.get("advertiser_name")
                ad_text = (
                    item.get("ad_text") or advertiser or "instagram_ad"
                )

                sig = f"{advertiser or ''}|{ad_text[:60]}"
                if sig in seen_sigs:
                    continue
                seen_sigs.add(sig)

                url = item.get("url")
                display_url = None
                if url:
                    try:
                        display_url = urlparse(url).netloc or None
                    except Exception:
                        pass

                pos = item.get("position", len(ads) + 1)
                card_idx = pos - 1
                creative_path = card_screenshot_map.get(card_idx)

                ads.append({
                    "advertiser_name": advertiser,
                    "ad_text": ad_text,
                    "ad_description": None,
                    "url": url,
                    "display_url": display_url,
                    "position": len(ads) + 1,
                    "ad_type": "social_library",
                    "ad_placement": "instagram_ad_library",
                    "creative_image_path": creative_path,
                    "extra_data": {
                        "image_url": item.get("image_url"),
                        "ad_delivery_start_time": item.get("started"),
                        "detection_method": "meta_ad_library_fallback",
                        "platform_filter": "instagram",
                        "search_keyword": keyword,
                    },
                })

            logger.info(
                "[{}] Ad Library '{}' -> {} ads",
                self.channel, keyword, len(ads),
            )
            return ads

        except Exception as e:
            logger.error(
                "[{}] Ad Library search '{}' failed: {}",
                self.channel, keyword, e,
            )
            return []
        finally:
            await page.close()
