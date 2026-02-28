"""크롤러 베이스 클래스 — 모든 채널 크롤러의 부모."""

import asyncio
import os
import random
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from loguru import logger
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from crawler.config import crawler_settings
from crawler.cookie_store import CookieStore, get_cookie_store
from crawler.personas.cookie_profiles import RETARGET_WARMUP_URLS, get_warmup_urls
from crawler.personas.device_config import DEFAULT_MOBILE, PC_DEVICE, DeviceConfig
from crawler.personas.profiles import PERSONAS, PersonaProfile
from processor.image_store import ImageStore, get_image_store


class BaseCrawler(ABC):
    """모든 채널 크롤러가 상속하는 베이스 클래스."""

    channel: str = ""  # 하위 클래스에서 override

    def __init__(self):
        self.settings = crawler_settings
        self._playwright = None
        self._browser: Browser | None = None
        self._image_store: ImageStore = get_image_store()
        self._cookie_store: CookieStore = get_cookie_store()

    # ── Lifecycle ──

    async def start(self):
        """Playwright 브라우저 시작."""
        self._playwright = await async_playwright().start()

        # 채널별 headful 오버라이드
        headful_list = [c.strip() for c in self.settings.headful_channels.split(",") if c.strip()]
        use_headless = self.settings.headless and self.channel not in headful_list

        # headful 채널은 실제 Chrome 사용 (Chromium 핑거프린트 회피)
        use_chrome = self.channel in headful_list
        launch_opts = dict(
            headless=use_headless,
            slow_mo=self.settings.slow_mo_ms or None,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
            ],
        )
        if use_chrome:
            launch_opts["channel"] = "chrome"

        self._browser = await self._playwright.chromium.launch(**launch_opts)
        logger.info(f"[{self.channel}] 브라우저 시작 (headless={use_headless}, chrome={use_chrome})")

    async def stop(self):
        """브라우저 종료."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info(f"[{self.channel}] 브라우저 종료")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.stop()

    # ── Context 생성 ──

    def _is_headful_chrome(self) -> bool:
        """현재 채널이 headful Chrome 모드인지 확인."""
        headful_list = [c.strip() for c in self.settings.headful_channels.split(",") if c.strip()]
        return self.channel in headful_list

    async def _create_context(
        self,
        persona: PersonaProfile,
        device: DeviceConfig,
    ) -> BrowserContext:
        """페르소나 + 디바이스 설정으로 브라우저 컨텍스트 생성."""
        # headful Chrome: UA 오버라이드 없이 Chrome 네이티브 사용
        if self._is_headful_chrome():
            ctx_opts: dict = {"locale": "ko-KR", "timezone_id": "Asia/Seoul"}
            if device.is_mobile:
                ctx_opts["viewport"] = {"width": device.viewport_width, "height": device.viewport_height}
                ctx_opts["is_mobile"] = True
                ctx_opts["has_touch"] = True
                ctx_opts["device_scale_factor"] = device.device_scale_factor
            context = await self._browser.new_context(**ctx_opts)
        else:
            context = await self._browser.new_context(
                viewport={"width": device.viewport_width, "height": device.viewport_height},
                user_agent=device.user_agent,
                is_mobile=device.is_mobile,
                has_touch=device.has_touch,
                device_scale_factor=device.device_scale_factor,
                locale="ko-KR",
                timezone_id="Asia/Seoul",
            )
        context.set_default_timeout(self.settings.page_timeout_ms)
        context.set_default_navigation_timeout(self.settings.navigation_timeout_ms)

        # Stealth: 봇 감지 회피
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const p = [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                        { name: 'Native Client', filename: 'internal-nacl-plugin' },
                    ];
                    p.length = 3;
                    return p;
                }
            });
            Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR', 'ko', 'en-US', 'en'] });
            if (!window.chrome) window.chrome = {};
            if (!window.chrome.runtime) window.chrome.runtime = { connect: () => {}, sendMessage: () => {} };
            const origQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (params) =>
                params.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : origQuery(params);
            const gp = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(p) {
                if (p === 37445) return 'Intel Inc.';
                if (p === 37446) return 'Intel Iris OpenGL Engine';
                return gp.call(this, p);
            };
        """)

        # headful Chrome: 스텔스/워밍업 스킵 (실제 Chrome이 자체 처리)
        if self._is_headful_chrome():
            # headful도 영속 쿠키는 로드
            await self._load_persisted_cookies(context, persona)
            return context

        # 영속 쿠키 로드 (이전 세션에서 축적된 쿠키)
        await self._load_persisted_cookies(context, persona)

        # 로그인 페르소나면 쿠키 주입
        if persona.cookie_env_key:
            await self._inject_cookies(context, persona)

        # Phase 3B: 타겟팅 쿠키 워밍업
        await self._warmup_cookies(context, persona)

        return context

    async def _inject_cookies(self, context: BrowserContext, persona: PersonaProfile):
        """환경변수에서 네이버 쿠키를 로드하여 주입."""
        cookie_value = os.getenv(persona.cookie_env_key, "")
        if not cookie_value:
            logger.warning(f"[{self.channel}] {persona.code} 쿠키 미설정: {persona.cookie_env_key}")
            return

        cookies = []
        for pair in cookie_value.split(";"):
            pair = pair.strip()
            if "=" in pair:
                name, value = pair.split("=", 1)
                cookies.append({
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": ".naver.com",
                    "path": "/",
                })
        if cookies:
            await context.add_cookies(cookies)
            logger.debug(f"[{self.channel}] {persona.code} 쿠키 {len(cookies)}개 주입")

    # ── 쿠키 영속화 (Phase 4) ──

    async def _load_persisted_cookies(self, context: BrowserContext, persona: PersonaProfile):
        """이전 세션에서 저장된 쿠키를 컨텍스트에 로드."""
        cookies = self._cookie_store.load(persona.code, self.channel)
        if cookies:
            try:
                await context.add_cookies(cookies)
                logger.debug(f"[{self.channel}] {persona.code} 영속 쿠키 {len(cookies)}개 로드")
            except Exception as e:
                logger.debug(f"[{self.channel}] 영속 쿠키 로드 실패: {e}")

    async def _save_context_cookies(self, context: BrowserContext, persona: PersonaProfile):
        """현재 컨텍스트의 쿠키를 영속 저장."""
        try:
            cookies = await context.cookies()
            if cookies:
                self._cookie_store.save(persona.code, self.channel, cookies)
        except Exception as e:
            logger.debug(f"[{self.channel}] 쿠키 저장 실패: {e}")

    # ── 쿠키 워밍업 (Phase 3B) ──

    async def _warmup_cookies(self, context: BrowserContext, persona: PersonaProfile):
        """페르소나의 연령/성별에 맞는 사이트를 방문하여 타겟팅 쿠키 축적.

        Phase 5: 사이트당 10-25초 체류, 스크롤+마우스로 자연스러운 브라우징.
        클린 프로필(is_clean=True)이면 스킵.
        CTRL_RETARGET 페르소나는 쇼핑 사이트 방문으로 리타겟팅 유도.
        """
        if getattr(persona, "is_clean", False):
            return

        is_retarget = persona.code == "CTRL_RETARGET"
        urls = get_warmup_urls(persona.age_group, persona.gender, is_retarget=is_retarget)

        if not urls:
            return

        s = self.settings
        max_sites = s.warmup_site_count
        page = await context.new_page()
        visited = 0

        for url in urls[:max_sites]:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=12000)

                # 사이트당 10-25초 자연스러운 체류
                dwell_ms = random.randint(s.warmup_dwell_min_ms, s.warmup_dwell_max_ms)
                scroll_rounds = random.randint(2, s.warmup_scroll_count)

                for _ in range(scroll_rounds):
                    dist = random.randint(300, 600)
                    await self._human_scroll(page, dist)
                    await self._human_mouse_jiggle(page)

                # 남은 체류 시간 대기
                remaining = max(1000, dwell_ms - (scroll_rounds * 5000))
                await page.wait_for_timeout(remaining)
                visited += 1

                # 사이트 간 쿨다운
                if visited < max_sites:
                    await page.wait_for_timeout(random.randint(2000, 5000))

            except Exception as e:
                logger.debug(f"[{self.channel}] warmup skip: {url} — {e}")
        await page.close()

        if visited:
            logger.debug(f"[{self.channel}] 워밍업 완료: {persona.code} ({visited}/{max_sites} sites)")

    # ── 스크린샷 ──

    async def _take_screenshot(self, page: Page, keyword: str, persona_code: str) -> str | None:
        """광고 영역 스크린샷 캡처 후 경로 반환."""
        screenshot_dir = Path(self.settings.screenshot_dir) / self.channel / datetime.now().strftime("%Y%m%d")
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"{persona_code}_{keyword}_{timestamp}.png"
        filepath = screenshot_dir / filename

        await page.screenshot(path=str(filepath), full_page=True)
        logger.debug(f"[{self.channel}] 스크린샷 저장: {filepath}")

        # WebP 변환 저장 (비동기이지만 I/O가 가벼우므로 직접 호출)
        try:
            stored = await self._image_store.save(str(filepath), self.channel, "screenshot")
            return stored
        except Exception as e:
            logger.warning(f"[{self.channel}] 이미지 스토리지 저장 실패: {e}")
            return str(filepath)

    # ── 광고 영역 element 스냅샷 ──

    async def _capture_ad_element(
        self,
        page: Page,
        selector_or_locator,
        keyword: str,
        persona_code: str,
        placement_name: str = "ad",
    ) -> str | None:
        """개별 광고 영역 element 스크린샷 캡처.

        Args:
            page: Playwright Page
            selector_or_locator: CSS 셀렉터(str) 또는 Locator 객체
            keyword: 키워드(파일명용)
            persona_code: 페르소나 코드(파일명용)
            placement_name: 광고 지면명 (e.g. "timeboard", "feed_ad")

        Returns:
            저장된 이미지 경로 또는 None
        """
        try:
            if isinstance(selector_or_locator, str):
                locator = page.locator(selector_or_locator).first
            else:
                locator = selector_or_locator

            if await locator.count() == 0:
                return None

            screenshot_dir = (
                Path(self.settings.screenshot_dir)
                / self.channel
                / datetime.now().strftime("%Y%m%d")
            )
            screenshot_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%H%M%S")
            safe_keyword = keyword[:20].replace(" ", "_").replace("/", "_")
            filename = f"{placement_name}_{persona_code}_{safe_keyword}_{timestamp}.png"
            filepath = screenshot_dir / filename

            await locator.screenshot(path=str(filepath))
            logger.debug(f"[{self.channel}] element 스냅샷 저장: {filepath}")

            try:
                stored = await self._image_store.save(str(filepath), self.channel, "element")
                return stored
            except Exception:
                return str(filepath)
        except Exception as e:
            logger.warning(f"[{self.channel}] element 스냅샷 실패 ({placement_name}): {e}")
            return None

    # ── 인간적 인터랙션 헬퍼 (Phase 5 강화) ──

    async def _human_scroll(self, page: Page, distance: int = 500):
        """인간적 스크롤 — 가변 속도, 간헐적 역스크롤, 읽기 대기."""
        s = self.settings
        steps = random.randint(s.scroll_step_min, s.scroll_step_max)
        per_step = distance // max(steps, 1)

        for _ in range(steps):
            jitter = random.randint(-30, 30)
            await page.evaluate(f"window.scrollBy(0, {per_step + jitter})")
            await page.wait_for_timeout(
                random.randint(s.scroll_step_pause_min_ms, s.scroll_step_pause_max_ms)
            )

        # 15% 확률 위로 스크롤 (재독 시뮬레이션)
        if random.random() < s.scroll_reverse_chance:
            reverse_dist = int(distance * s.scroll_reverse_ratio)
            await page.wait_for_timeout(random.randint(300, 800))
            await page.evaluate(f"window.scrollBy(0, -{reverse_dist})")
            await page.wait_for_timeout(random.randint(500, 1500))

        # 스크롤 후 읽기 대기
        await page.wait_for_timeout(
            random.randint(s.scroll_read_pause_min_ms, s.scroll_read_pause_max_ms)
        )

    async def _human_delay(self, page: Page, base_ms: int = 1000):
        """랜덤 지연 (base +/- 30%)."""
        jitter = int(base_ms * 0.3)
        await page.wait_for_timeout(base_ms + random.randint(-jitter, jitter))

    async def _human_mouse_jiggle(self, page: Page):
        """뷰포트 내 랜덤 마우스 이동 + 선택적 hover."""
        s = self.settings
        if not s.mouse_enabled:
            return

        try:
            viewport = page.viewport_size
            if not viewport:
                return
            vw, vh = viewport["width"], viewport["height"]

            moves = random.randint(s.mouse_jiggle_min_moves, s.mouse_jiggle_max_moves)
            for _ in range(moves):
                x = random.randint(int(vw * 0.1), int(vw * 0.9))
                y = random.randint(int(vh * 0.1), int(vh * 0.8))
                await page.mouse.move(x, y, steps=random.randint(5, 15))
                await page.wait_for_timeout(random.randint(100, 400))

            # 30% 확률 콘텐츠 요소 hover
            if random.random() < s.mouse_hover_chance:
                await self._hover_random_element(page)

        except Exception as e:
            logger.debug(f"[{self.channel}] mouse jiggle skip: {e}")

    async def _hover_random_element(self, page: Page):
        """화면 내 보이는 콘텐츠 요소에 마우스 hover."""
        try:
            pos = await page.evaluate("""() => {
                const els = document.querySelectorAll('a, img, h2, h3, p, article');
                const visible = Array.from(els).filter(el => {
                    const r = el.getBoundingClientRect();
                    return r.top > 0 && r.top < window.innerHeight
                        && r.width > 50 && r.height > 20;
                });
                if (!visible.length) return null;
                const el = visible[Math.floor(Math.random() * visible.length)];
                const r = el.getBoundingClientRect();
                return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
            }""")
            if pos:
                await page.mouse.move(pos["x"], pos["y"], steps=random.randint(8, 20))
                await page.wait_for_timeout(random.randint(500, 2000))
        except Exception:
            pass

    async def _dwell_on_page(self, page: Page):
        """페이지 파싱 전 자연스러운 읽기 행동 시뮬레이션 (12-25초).

        스크롤 + 마우스 이동 + 읽기 대기를 조합하여 실제 사용자처럼 체류.
        """
        s = self.settings
        dwell_target_ms = random.randint(s.dwell_min_ms, s.dwell_max_ms)
        scroll_count = random.randint(s.dwell_scroll_count_min, s.dwell_scroll_count_max)

        elapsed = 0
        for i in range(scroll_count):
            if elapsed >= dwell_target_ms:
                break

            dist = random.randint(300, 700)
            await self._human_scroll(page, dist)
            elapsed += 4000  # _human_scroll 소요시간 근사

            # 50% 확률 마우스 이동
            if random.random() < 0.5:
                await self._human_mouse_jiggle(page)
                elapsed += 2000

        # 목표 체류시간까지 남은 시간 대기
        remaining = max(0, dwell_target_ms - elapsed)
        if remaining > 0:
            await page.wait_for_timeout(remaining)

    async def _inter_page_cooldown(self, page: Page):
        """페이지 간 자연스러운 쿨다운 (4-12초)."""
        s = self.settings
        wait_ms = random.randint(s.inter_page_min_ms, s.inter_page_max_ms)
        await page.wait_for_timeout(wait_ms)

    # ── 재시도 래퍼 ──

    async def _with_retry(self, coro_func, *args, **kwargs):
        """재시도 로직 래퍼."""
        for attempt in range(1, self.settings.max_retries + 1):
            try:
                return await coro_func(*args, **kwargs)
            except Exception as e:
                logger.warning(
                    f"[{self.channel}] 시도 {attempt}/{self.settings.max_retries} 실패: {e}"
                )
                if attempt == self.settings.max_retries:
                    logger.error(f"[{self.channel}] 최대 재시도 초과: {e}")
                    raise
                await asyncio.sleep(self.settings.retry_delay_sec * attempt)

    # ── 추상 메서드 (하위 클래스에서 구현) ──

    @abstractmethod
    async def crawl_keyword(
        self,
        keyword: str,
        persona: PersonaProfile,
        device: DeviceConfig,
    ) -> dict:
        """키워드 하나에 대해 광고 데이터를 수집.

        Returns:
            {
                "keyword": str,
                "persona_code": str,
                "device": str,
                "channel": str,
                "captured_at": datetime,
                "screenshot_path": str | None,
                "ads": [
                    {
                        "advertiser_name": str,
                        "ad_text": str,
                        "url": str,
                        "position": int,
                        "ad_type": str,
                        "extra_data": dict,
                    },
                    ...
                ],
            }
        """
        ...

    async def crawl_keywords(
        self,
        keywords: list[str],
        persona_code: str = "M30",
        device_type: str = "pc",
    ) -> list[dict]:
        """여러 키워드를 순차적으로 수집."""
        persona = PERSONAS[persona_code]
        device = PC_DEVICE if device_type == "pc" else DEFAULT_MOBILE

        results = []
        for kw in keywords:
            try:
                result = await self._with_retry(self.crawl_keyword, kw, persona, device)
                results.append(result)
                logger.info(
                    f"[{self.channel}] '{kw}' 수집 완료 — "
                    f"광고 {len(result.get('ads', []))}건 ({persona_code}/{device_type})"
                )
            except Exception as e:
                logger.error(f"[{self.channel}] '{kw}' 수집 실패: {e}")
                results.append({
                    "keyword": kw,
                    "persona_code": persona_code,
                    "device": device_type,
                    "channel": self.channel,
                    "captured_at": datetime.utcnow(),
                    "error": str(e),
                    "ads": [],
                })
        return results
