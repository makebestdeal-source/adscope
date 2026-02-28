"""YouTube organic surfing crawler -- network capture for ad collection.

Loads trending/popular videos directly and captures pre-roll/mid-roll ads
via doubleclick/googlevideo network responses.
No search page visits. No DOM selector ad detection.

Enhanced with:
- playwright-stealth v2 for browser-level anti-detection patching
- Persistent browser profile (--user-data-dir) for realistic fingerprint
- CDP (Chrome DevTools Protocol) network interception for pagead/adview capture
"""

from __future__ import annotations

import json
import os
import re
import random
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote, quote

from loguru import logger
from playwright.async_api import BrowserContext, Page, Response, async_playwright

from crawler.base_crawler import BaseCrawler
from crawler.landing_resolver import resolve_landings_batch
from crawler.personas.device_config import DeviceConfig
from crawler.personas.profiles import PersonaProfile

# playwright-stealth v2: browser-level anti-detection (much more effective
# than manual JS injection). Falls back gracefully if not installed.
try:
    from playwright_stealth import Stealth as _PlaywrightStealth
    _HAS_STEALTH = True
except ImportError:
    _HAS_STEALTH = False
    logger.warning("[youtube_surf] playwright-stealth not installed; falling back to manual stealth scripts")


# 페르소나별 시드 키워드 (비상업, 콘텐츠 중심 — 알고리즘 시딩용)
_PERSONA_SEED_KEYWORDS: dict[str, list[str]] = {
    "M10": ["배그 하이라이트", "축구 골 모음", "마인크래프트 건축"],
    "F10": ["뉴진스 무대", "데일리 브이로그", "학교 일상"],
    "M20": ["코딩 브이로그", "운동 루틴", "유럽 여행"],
    "F20": ["카페 브이로그", "데일리룩 코디", "서울 맛집"],
    "M30": ["시승기 리뷰", "재테크 기초", "아빠 육아"],
    "F30": ["육아 일상", "인테리어 투어", "간단 요리"],
    "M40": ["골프 레슨", "시사 토론", "캠핑 브이로그"],
    "F40": ["건강 스트레칭", "학습법 추천", "집밥 레시피"],
    "M50": ["건강 걷기", "뉴스 브리핑", "등산 코스"],
    "F50": ["건강 식단", "생활 꿀팁", "꽃꽂이"],
    "M60": ["아침 체조", "다큐멘터리", "텃밭 가꾸기"],
    "F60": ["건강 체조", "요리 프로그램", "국내 여행지"],
    "CTRL_CLEAN": ["오늘의 뉴스", "날씨"],
    "CTRL_RETARGET": ["쇼핑 하울", "신상품 리뷰"],
}


class YouTubeSurfCrawler(BaseCrawler):
    """영상 직접 로드 + doubleclick/googlevideo 네트워크 캡처."""

    channel = "youtube_surf"
    keyword_dependent = False

    # 광고가 붙는 긴 영상 시드 (8분 이상 — 프리롤+미드롤 광고 확보)
    _SEED_VIDEOS: list[str] = [
        "https://www.youtube.com/watch?v=9bZkp7q19f0",  # Gangnam Style 4:13
        "https://www.youtube.com/watch?v=kJQP7kiw5Fk",  # Despacito 4:42
        "https://www.youtube.com/watch?v=RgKAFK5djSk",  # See You Again 3:58
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Rick Astley 3:33
        "https://www.youtube.com/watch?v=hY7m5jjJ9mM",  # 야생의숲 1hr+
        "https://www.youtube.com/watch?v=5qap5aO4i9A",  # lofi hip hop 실시간(긴)
        "https://www.youtube.com/watch?v=KkaGV_uo6oA",  # 나혼자산다 17min
        "https://www.youtube.com/watch?v=FyASdjVAKFI",  # 전지적참견 15min
        "https://www.youtube.com/watch?v=36YnV9STBqc",  # TED 15min
        "https://www.youtube.com/watch?v=aircAruvnKk",  # 3Blue1Brown 19min
        "https://www.youtube.com/watch?v=fJ9rUzIMcZQ",  # Queen Bohemian 6min
        "https://www.youtube.com/watch?v=YR5ApYxkU-U",  # Lady Gaga 13min
    ]

    # YouTube-specific stealth script injected into every context.
    # Covers detection vectors beyond what base_crawler handles:
    #   - chrome.app / chrome.csi / chrome.loadTimes  (missing in old headless)
    #   - navigator.connection  (Network Information API, absent in headless)
    #   - Notification.permission default
    #   - window.outerWidth / outerHeight  (0 in old headless)
    #   - MediaSession API stub
    #   - navigator.getBattery stub
    #   - iframe contentWindow consistency
    _YT_STEALTH_SCRIPT: str = """
    (() => {
        // -- chrome.app --
        if (!window.chrome) window.chrome = {};
        if (!window.chrome.app) {
            window.chrome.app = {
                isInstalled: false,
                InstallState: {DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed'},
                RunningState: {CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running'},
                getDetails: function() { return null; },
                getIsInstalled: function() { return false; },
                installState: function(cb) { if (cb) cb('not_installed'); },
            };
        }
        // -- chrome.csi --
        if (!window.chrome.csi) {
            window.chrome.csi = function() {
                return {
                    startE: Date.now(),
                    onloadT: Date.now(),
                    pageT: Math.random() * 500 + 100,
                    tran: 15,
                };
            };
        }
        // -- chrome.loadTimes --
        if (!window.chrome.loadTimes) {
            window.chrome.loadTimes = function() {
                return {
                    commitLoadTime: Date.now() / 1000,
                    connectionInfo: 'h2',
                    finishDocumentLoadTime: Date.now() / 1000,
                    finishLoadTime: Date.now() / 1000,
                    firstPaintAfterLoadTime: 0,
                    firstPaintTime: Date.now() / 1000,
                    navigationType: 'Other',
                    npnNegotiatedProtocol: 'h2',
                    requestTime: Date.now() / 1000 - 0.3,
                    startLoadTime: Date.now() / 1000 - 0.5,
                    wasAlternateProtocolAvailable: false,
                    wasFetchedViaSpdy: true,
                    wasNpnNegotiated: true,
                };
            };
        }
        // -- chrome.runtime (extend) --
        if (!window.chrome.runtime) {
            window.chrome.runtime = {};
        }
        if (!window.chrome.runtime.connect) {
            window.chrome.runtime.connect = function() { return {}; };
        }
        if (!window.chrome.runtime.sendMessage) {
            window.chrome.runtime.sendMessage = function() {};
        }

        // -- navigator.connection (Network Information API) --
        if (!navigator.connection) {
            Object.defineProperty(navigator, 'connection', {
                get: () => ({
                    effectiveType: '4g',
                    rtt: 50,
                    downlink: 10,
                    saveData: false,
                    type: 'wifi',
                    addEventListener: function() {},
                    removeEventListener: function() {},
                }),
            });
        }

        // -- Notification.permission --
        if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
            try {
                Object.defineProperty(Notification, 'permission', {
                    get: () => 'default',
                });
            } catch(e) {}
        }

        // -- window.outerWidth / outerHeight (0 in old headless) --
        if (window.outerWidth === 0 || window.outerHeight === 0) {
            Object.defineProperty(window, 'outerWidth', {
                get: () => window.innerWidth,
            });
            Object.defineProperty(window, 'outerHeight', {
                get: () => window.innerHeight + 85,
            });
        }

        // -- navigator.getBattery --
        if (!navigator.getBattery) {
            navigator.getBattery = () => Promise.resolve({
                charging: true,
                chargingTime: 0,
                dischargingTime: Infinity,
                level: 1.0,
                addEventListener: function() {},
                removeEventListener: function() {},
            });
        }

        // -- MediaSession stub --
        if (!navigator.mediaSession) {
            try {
                Object.defineProperty(navigator, 'mediaSession', {
                    get: () => ({
                        metadata: null,
                        playbackState: 'none',
                        setActionHandler: function() {},
                        setPositionState: function() {},
                    }),
                });
            } catch(e) {}
        }

        // -- Prevent iframe contentWindow detection --
        const originalAttachShadow = Element.prototype.attachShadow;
        if (originalAttachShadow) {
            Element.prototype.attachShadow = function() {
                return originalAttachShadow.apply(this, arguments);
            };
        }

        // -- Screen properties consistency --
        if (screen.availWidth === 0 || screen.width === 0) {
            Object.defineProperty(screen, 'width', { get: () => window.innerWidth });
            Object.defineProperty(screen, 'height', { get: () => window.innerHeight });
            Object.defineProperty(screen, 'availWidth', { get: () => window.innerWidth });
            Object.defineProperty(screen, 'availHeight', { get: () => window.innerHeight });
            Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
            Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
        }
    })();
    """

    # Persistent profile directory for YouTube (shared across runs).
    # A lived-in profile with cookies/history makes YouTube treat us as real.
    _PROFILE_DIR: str = os.getenv(
        "YT_SURF_PROFILE_DIR",
        str(Path(tempfile.gettempdir()) / "adscopre_yt_surf_profile"),
    )

    # Manual cookie file path (exported via scripts/yt_cookie_export.py)
    _YT_COOKIE_DIR: Path = Path(
        os.getenv(
            "YOUTUBE_COOKIE_DIR",
            str(Path(__file__).resolve().parent.parent / "yt_cookies"),
        )
    )
    _YT_COOKIE_FILE: Path = _YT_COOKIE_DIR / "yt_session.json"
    _YT_COOKIE_MAX_AGE_DAYS: int = int(os.getenv("YOUTUBE_COOKIE_MAX_AGE_DAYS", "30"))

    # Common launch args for YouTube headless
    _LAUNCH_ARGS: list[str] = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-infobars",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
        # GPU / WebGL -- make headless look like a real browser
        "--enable-gpu",
        "--enable-webgl",
        "--enable-webgl2",
        "--use-gl=angle",
        "--use-angle=default",
        # Media / codecs -- needed for YouTube ad playback
        "--autoplay-policy=no-user-gesture-required",
        "--enable-features=AudioServiceOutOfProcess",
        "--disable-features=MediaCapabilitiesForAutoplay",
        # Additional stealth flags
        "--disable-dev-shm-usage",
        "--disable-ipc-flooding-protection",
        "--lang=ko-KR",
        "--window-size=1920,1080",
    ]

    def __init__(self):
        super().__init__()
        self.video_samples = max(1, int(os.getenv("YOUTUBE_SURF_SAMPLES", "10")))
        self.ad_wait_ms = max(5000, int(os.getenv("YOUTUBE_AD_WAIT_MS", "15000")))
        # Persistent context (created in start, used instead of _browser)
        self._persistent_ctx: BrowserContext | None = None
        # playwright-stealth instance (reusable)
        self._stealth = _PlaywrightStealth() if _HAS_STEALTH else None

    # ── YouTube-specific browser launch (overrides BaseCrawler.start) ──

    async def start(self):
        """Launch browser with persistent profile + stealth for YouTube.

        Uses launch_persistent_context with --user-data-dir so YouTube sees
        a browser with real cookies/history. Combined with playwright-stealth
        v2 for comprehensive anti-detection at the browser level.
        This override does NOT touch base_crawler.py.
        """
        self._playwright = await async_playwright().start()

        # Ensure profile directory exists
        Path(self._PROFILE_DIR).mkdir(parents=True, exist_ok=True)

        # Launch persistent context (replaces browser.new_context)
        self._persistent_ctx = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=self._PROFILE_DIR,
            headless=True,
            args=self._LAUNCH_ARGS,
            viewport={"width": 1920, "height": 1080},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            slow_mo=self.settings.slow_mo_ms or None,
        )

        # Apply playwright-stealth v2 at browser level (far superior to JS injection)
        if self._stealth:
            try:
                await self._stealth.apply_stealth_async(self._persistent_ctx)
                logger.info(f"[{self.channel}] persistent context + playwright-stealth v2 applied")
            except Exception as exc:
                logger.warning(f"[{self.channel}] playwright-stealth failed ({exc}), falling back to manual scripts")
                await self._persistent_ctx.add_init_script(self._YT_STEALTH_SCRIPT)
        else:
            # Fallback: manual stealth scripts
            await self._persistent_ctx.add_init_script(self._YT_STEALTH_SCRIPT)

        # Also set _browser to None so stop() does not try to close it
        self._browser = None
        stealth_mode = "v2" if self._stealth else "manual"

        # Load manual cookies from yt_cookies/yt_session.json (if available)
        cookie_loaded = await self._load_yt_manual_cookies(self._persistent_ctx)
        login_status = "logged-in session" if cookie_loaded else "anonymous"
        logger.info(
            f"[{self.channel}] browser started: persistent profile + headless=True"
            f" (stealth={stealth_mode}, session={login_status})"
        )

    async def stop(self):
        """Close persistent context and Playwright."""
        if self._persistent_ctx:
            try:
                await self._persistent_ctx.close()
            except Exception:
                pass
            self._persistent_ctx = None
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._playwright:
            await self._playwright.stop()
        logger.info(f"[{self.channel}] browser stopped")

    # ── YouTube-specific context with enhanced stealth ──

    async def _create_context(
        self,
        persona: PersonaProfile,
        device: DeviceConfig,
    ) -> BrowserContext:
        """Return the persistent context with stealth already applied.

        Unlike the base class which creates a new context per crawl, we
        reuse the persistent context so YouTube sees a lived-in profile.
        Cookies/history accumulate across crawl runs.
        """
        ctx = self._persistent_ctx
        if ctx is None:
            # Fallback: if persistent context not available, use base
            ctx = await super()._create_context(persona, device)
            if self._stealth:
                await self._stealth.apply_stealth_async(ctx)
            else:
                await ctx.add_init_script(self._YT_STEALTH_SCRIPT)
        return ctx

    # ── YouTube manual cookie load/save ──

    async def _load_yt_manual_cookies(self, context: BrowserContext) -> bool:
        """Load manually exported YouTube/Google cookies into the context.

        Reads yt_cookies/yt_session.json (created by scripts/yt_cookie_export.py).
        Returns True if cookies were loaded successfully (logged-in session).
        Returns False if no cookies, expired, or load failed (anonymous mode).
        """
        cookie_file = self._YT_COOKIE_FILE
        if not cookie_file.exists():
            logger.debug(f"[{self.channel}] no manual cookie file: {cookie_file}")
            return False

        try:
            data = json.loads(cookie_file.read_text(encoding="utf-8"))
            cookies = data.get("cookies", [])
            if not cookies:
                logger.debug(f"[{self.channel}] manual cookie file empty")
                return False

            # Freshness check: skip cookies older than max age
            updated_at = data.get("updated_at", "")
            if updated_at:
                try:
                    ts = datetime.fromisoformat(updated_at)
                    # Ensure timezone-aware comparison
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    age_days = (datetime.now(timezone.utc) - ts).days
                    if age_days > self._YT_COOKIE_MAX_AGE_DAYS:
                        logger.info(
                            f"[{self.channel}] manual cookies expired"
                            f" ({age_days} days old, max={self._YT_COOKIE_MAX_AGE_DAYS})"
                        )
                        return False
                    logger.debug(
                        f"[{self.channel}] cookie age: {age_days} days"
                    )
                except Exception:
                    pass

            # Filter to Google/YouTube domain cookies only
            yt_cookies = [
                c for c in cookies
                if isinstance(c.get("domain"), str)
                and (
                    "google.com" in c["domain"]
                    or "youtube.com" in c["domain"]
                    or "googleapis.com" in c["domain"]
                )
            ]
            if not yt_cookies:
                logger.debug(f"[{self.channel}] no Google/YouTube cookies in file")
                return False

            await context.add_cookies(yt_cookies)
            required_found = data.get("required_cookies_found", [])
            logger.info(
                f"[{self.channel}] manual cookies loaded:"
                f" {len(yt_cookies)} cookies"
                f" (required: {', '.join(required_found) if required_found else 'unknown'})"
            )
            return True

        except Exception as exc:
            logger.warning(f"[{self.channel}] manual cookie load failed: {exc}")
            return False

    async def _save_yt_manual_cookies(self, context: BrowserContext):
        """Re-save current session cookies to extend the manual cookie session.

        Called after a successful crawl to refresh the updated_at timestamp,
        keeping the cookies fresh for future runs.
        """
        cookie_file = self._YT_COOKIE_FILE
        # Only refresh if the original file exists (user ran export at least once)
        if not cookie_file.exists():
            return

        try:
            all_cookies = await context.cookies()
            yt_cookies = [
                c for c in all_cookies
                if isinstance(c.get("domain"), str)
                and (
                    "google.com" in c["domain"]
                    or "youtube.com" in c["domain"]
                    or "googleapis.com" in c["domain"]
                )
            ]
            if not yt_cookies:
                return

            # Preserve original metadata, update cookies and timestamp
            try:
                orig_data = json.loads(cookie_file.read_text(encoding="utf-8"))
            except Exception:
                orig_data = {}

            # Check which required cookies are present
            required_names = {"SID", "HSID", "SSID", "APISID", "SAPISID"}
            cookie_name_set = {c.get("name", "") for c in yt_cookies}
            found_required = sorted(required_names & cookie_name_set)

            data = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "source": orig_data.get("source", "auto_refresh"),
                "browser_url": orig_data.get("browser_url", ""),
                "cookie_count": len(yt_cookies),
                "required_cookies_found": found_required,
                "cookies": yt_cookies,
            }

            self._YT_COOKIE_DIR.mkdir(parents=True, exist_ok=True)
            cookie_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.debug(
                f"[{self.channel}] manual cookies refreshed: {len(yt_cookies)} cookies"
            )
        except Exception as exc:
            logger.debug(f"[{self.channel}] manual cookie save failed: {exc}")

    async def crawl_keyword(
        self,
        keyword: str,
        persona: PersonaProfile,
        device: DeviceConfig,
    ) -> dict:
        start_time = datetime.utcnow()
        context = await self._create_context(persona, device)
        page = await context.new_page()

        # CDP session for lower-level network interception.
        # Captures pagead/adview requests that Playwright may miss.
        cdp_session = None
        cdp_ad_captures: list[dict] = []

        try:
            # ── CDP network interception ──
            try:
                cdp_session = await context.new_cdp_session(page)
                await cdp_session.send("Network.enable")

                def _on_cdp_request(params):
                    url = params.get("request", {}).get("url", "")
                    # Capture pagead adview/interaction (actual ad impressions)
                    if "/pagead/adview" in url or "/pagead/interaction" in url:
                        cdp_ad_captures.append({
                            "advertiser": None,
                            "click_url": url,
                            "ad_type": "pagead_impression",
                            "source": "cdp_pagead",
                        })
                    elif "youtube.com/api/stats/ads" in url:
                        cdp_ad_captures.append({
                            "advertiser": None,
                            "click_url": url,
                            "ad_type": "stats_impression",
                            "source": "cdp_stats",
                        })

                cdp_session.on("Network.requestWillBeSent", _on_cdp_request)
            except Exception as exc:
                logger.debug(f"[{self.channel}] CDP session setup failed: {exc}")

            # ── Playwright-level network ad capture ──
            ad_captures: list[dict] = []

            async def _on_network_response(response: Response):
                url = response.url
                try:
                    # 1) Player API (adPlacements / playerAds)
                    if 'youtubei/v1/player' in url:
                        if response.status == 200:
                            ct = response.headers.get('content-type', '')
                            if 'json' in ct:
                                data = await response.json()
                                ads = _parse_player_ads(data)
                                if ads:
                                    logger.debug(f"[youtube] player API ads: {len(ads)}")
                                ad_captures.extend(ads)
                        return

                    # 2) get_midroll_info (actual ad renderer data)
                    if 'get_midroll_info' in url or 'get_ad_break' in url:
                        if response.status == 200:
                            ct = response.headers.get('content-type', '')
                            if 'json' in ct:
                                data = await response.json()
                                ads = _parse_midroll_ads(data)
                                if ads:
                                    logger.debug(f"[youtube] midroll ads: {len(ads)}")
                                ad_captures.extend(ads)
                        return

                    # 3) Ad network (doubleclick, pagead, stats)
                    if not any(d in url for d in (
                        'doubleclick.net', 'youtube.com/api/stats/ads',
                        'youtube.com/pagead/', 'googlesyndication.com',
                    )):
                        return

                    if response.status != 200:
                        return
                    ct = response.headers.get('content-type', '')
                    if 'json' in ct:
                        data = await response.json()
                        ads = _parse_ad_json(data, url)
                        ad_captures.extend(ads)
                    else:
                        body = await response.text()
                        if len(body) > 20:
                            ads = _parse_ad_text(body, url)
                            ad_captures.extend(ads)
                except Exception:
                    pass

            page.on('response', _on_network_response)

            # ── 1) YouTube consent/cookie setup ──
            await context.add_cookies([
                {'name': 'CONSENT', 'value': 'YES+cb.20260215-00-p0.kr+FX+999',
                 'domain': '.youtube.com', 'path': '/'},
                {'name': 'PREF', 'value': 'tz=Asia.Seoul&hl=ko&gl=KR',
                 'domain': '.youtube.com', 'path': '/'},
            ])

            # ── 2) 홈페이지에서 추천 영상 빠르게 수집 (시딩 스킵) ──
            video_urls: list[str] = []
            try:
                await page.goto("https://www.youtube.com/", wait_until="domcontentloaded")
                await _handle_consent(page)
                await page.wait_for_timeout(3000)
                # 빠른 스크롤 2회
                for _ in range(2):
                    await page.evaluate("window.scrollBy(0, 800)")
                    await page.wait_for_timeout(1000)
                video_urls = await _extract_video_links(page, 20)
                logger.debug(f"[{self.channel}] 홈페이지 추천 영상 {len(video_urls)}개")
            except Exception as exc:
                logger.debug(f"[{self.channel}] 홈페이지 수집 실패: {exc}")

            # 시드 영상으로 보충 (항상 광고가 붙는 인기 영상)
            seed_pool = list(self._SEED_VIDEOS)
            random.shuffle(seed_pool)
            for sv in seed_pool:
                if sv not in video_urls:
                    video_urls.append(sv)
            video_urls = list(dict.fromkeys(video_urls))
            logger.debug(f"[{self.channel}] 총 영상 {len(video_urls)}개 (시드 포함)")

            # ── 3) 영상 직접 로드 → 네트워크에서 광고 자동 캡처 ──
            sampled = random.sample(video_urls, min(self.video_samples, len(video_urls)))

            for i, video_url in enumerate(sampled, 1):
                try:
                    await page.goto(video_url, wait_until="domcontentloaded")
                    await self._human_delay(page, 2000)

                    # 재생 강제: mute + play (autoplay 보장)
                    try:
                        await page.evaluate("""() => {
                            const v = document.querySelector('video');
                            if (v) { v.muted = true; v.play().catch(() => {}); }
                            // 플레이 버튼 클릭 시도
                            const btn = document.querySelector('.ytp-large-play-button, .ytp-play-button, [aria-label*="재생"], [aria-label*="Play"]');
                            if (btn) btn.click();
                        }""")
                    except Exception:
                        pass

                    # 광고 슬롯 감지 (ytInitialPlayerResponse)
                    ad_info = await _detect_ad_slot(page)
                    if ad_info:
                        ad_captures.append(ad_info)

                    # 광고 대기 — 5회 체크 (총 ad_wait_ms)
                    check_interval = self.ad_wait_ms // 5
                    for check_round in range(5):
                        await page.wait_for_timeout(check_interval)
                        dom_ad = await _check_ad_playing(page)
                        if dom_ad:
                            ad_captures.append(dom_ad)
                            logger.info(f"[{self.channel}] [{i}] 인스트림 광고 감지! round={check_round} adv={dom_ad.get('advertiser')}")
                            # 광고 스크린샷 캡처
                            try:
                                ad_ss = await self._capture_ad_element(
                                    page, page.locator("video").first,
                                    keyword or "surf", persona.code,
                                    placement_name=f"yt_instream_{i}_{check_round}",
                                )
                                if ad_ss:
                                    dom_ad["creative_image_path"] = ad_ss
                            except Exception:
                                pass
                            break

                    before_count = len(ad_captures)
                    logger.debug(
                        f"[{self.channel}] [{i}/{len(sampled)}] 영상 완료: {video_url[:60]} "
                        f"(누적 캡처: {len(ad_captures)}건)"
                    )

                    await page.wait_for_timeout(random.randint(500, 1500))

                except Exception as exc:
                    logger.debug(f"[{self.channel}] 영상 로드 실패: {exc}")

            # ── 4) Merge CDP captures + build results ──
            # Merge CDP-level ad captures (pagead impressions, stats pings)
            if cdp_ad_captures:
                logger.debug(f"[{self.channel}] CDP captured {len(cdp_ad_captures)} additional ad signals")
                ad_captures.extend(cdp_ad_captures)

            all_ads = _build_ads(ad_captures)
            logger.info(f"[{self.channel}] network captured ads: {len(all_ads)} (raw: {len(ad_captures)}, cdp: {len(cdp_ad_captures)})")

            # Resolve advertiser names from landing pages
            unresolved = [a for a in all_ads if not a.get("advertiser_name")]
            if unresolved:
                resolved_count = await resolve_landings_batch(
                    context, unresolved, max_resolve=5, timeout_ms=8000,
                )
                logger.info(f"[{self.channel}] landing resolution {resolved_count}/{len(unresolved)}")

            await self._save_context_cookies(context, persona)
            # Re-save manual cookies to extend session freshness
            await self._save_yt_manual_cookies(context)
            screenshot_path = await self._take_screenshot(page, keyword or "surf", persona.code)
            elapsed = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            return {
                "keyword": keyword or "organic_surf",
                "persona_code": persona.code,
                "device": device.device_type,
                "channel": self.channel,
                "captured_at": datetime.utcnow(),
                "page_url": page.url,
                "screenshot_path": screenshot_path,
                "ads": all_ads,
                "crawl_duration_ms": elapsed,
            }
        finally:
            # Detach CDP session
            if cdp_session:
                try:
                    await cdp_session.detach()
                except Exception:
                    pass
            # Close the page but NOT the persistent context
            # (context persists across crawl_keyword calls)
            await page.close()

    # ── 영상 URL 수집 ──

    async def _collect_trending_videos(self, page: Page) -> list[str]:
        """트렌딩 페이지에서 영상 URL 수집."""
        try:
            await page.goto("https://www.youtube.com/feed/trending", wait_until="domcontentloaded")
            await _handle_consent(page)
            await self._dwell_on_page(page)

            for _ in range(3):
                await self._human_scroll(page, random.randint(600, 1200))

            return await _extract_video_links(page, 30)
        except Exception as exc:
            logger.debug(f"[{self.channel}] 트렌딩 수집 실패: {exc}")
            return []

    async def _collect_channel_videos(self, page: Page) -> list[str]:
        """인기 채널에서 영상 URL 수집 (fallback)."""
        channels = [
            "https://www.youtube.com/@MBCentertainment/videos",
            "https://www.youtube.com/@SBSenter/videos",
            "https://www.youtube.com/@KBSEntertain/videos",
        ]
        all_urls: list[str] = []
        for ch_url in random.sample(channels, min(2, len(channels))):
            try:
                await page.goto(ch_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
                urls = await _extract_video_links(page, 10)
                all_urls.extend(urls)
            except Exception:
                continue
        return list(set(all_urls))


# ── 모듈 레벨 유틸 (youtube_ads.py에서도 재사용) ──

async def _handle_consent(page: Page):
    """YouTube 쿠키 동의 팝업 수락."""
    for _ in range(3):
        try:
            clicked = await page.evaluate("""() => {
                const btns = document.querySelectorAll('button, tp-yt-paper-button');
                for (const btn of btns) {
                    const t = (btn.textContent || '').trim();
                    if (/^(Accept all|모두 동의|동의|수락|모두 수락|모두 동의합니다)$/i.test(t)) {
                        btn.click(); return true;
                    }
                }
                const form = document.querySelector('form[action*="consent"]');
                if (form) { const s = form.querySelector('button'); if (s) { s.click(); return true; } }
                return false;
            }""")
            if clicked:
                await page.wait_for_timeout(2000)
                return
        except Exception:
            pass
        await page.wait_for_timeout(1000)


async def _extract_video_links(page: Page, limit: int = 30) -> list[str]:
    """페이지에서 /watch?v= 링크 수집."""
    return await page.evaluate("""(limit) => {
        const links = document.querySelectorAll('a[href*="/watch?v="]');
        const seen = new Set();
        const urls = [];
        for (const a of links) {
            const href = a.href || '';
            if (!href.includes('/watch?v=')) continue;
            const clean = href.split('&')[0];
            if (seen.has(clean)) continue;
            seen.add(clean);
            urls.push(clean);
            if (urls.length >= limit) break;
        }
        return urls;
    }""", limit)


async def _seed_persona_algorithm(page: Page, persona_code: str):
    """페르소나에 맞는 키워드로 YouTube 알고리즘 시딩."""
    seeds = _PERSONA_SEED_KEYWORDS.get(persona_code, ["오늘의 뉴스"])
    seed_keyword = random.choice(seeds)
    logger.debug(f"[youtube] 알고리즘 시딩: '{seed_keyword}' (persona={persona_code})")

    try:
        search_url = f"https://www.youtube.com/results?search_query={quote(seed_keyword)}"
        await page.goto(search_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(random.randint(2000, 3000))

        video_links = await _extract_video_links(page, 3)
        if video_links:
            await page.goto(video_links[0], wait_until="domcontentloaded")
            try:
                await page.evaluate("""() => {
                    const v = document.querySelector('video');
                    if (v && v.paused) v.play().catch(() => {});
                }""")
            except Exception:
                pass
            await page.wait_for_timeout(random.randint(5000, 10000))
            logger.debug(f"[youtube] 시딩 영상 시청 완료: {video_links[0][:60]}")
    except Exception as exc:
        logger.debug(f"[youtube] 시딩 실패: {exc}")


async def _collect_homepage_videos(page: Page, limit: int = 20) -> list[str]:
    """YouTube 홈페이지에서 추천 영상 URL 수집."""
    try:
        await page.goto("https://www.youtube.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 800)")
            await page.wait_for_timeout(random.randint(1500, 2500))

        urls = await _extract_video_links(page, limit)
        if not urls:
            # SPA 렌더링 추가 대기
            await page.wait_for_timeout(3000)
            urls = await _extract_video_links(page, limit)
        return urls
    except Exception as exc:
        logger.debug(f"[youtube] 홈페이지 수집 실패: {exc}")
        return []


def _parse_player_ads(data: dict) -> list[dict]:
    """youtubei/v1/player 응답에서 adPlacements 추출."""
    ads: list[dict] = []
    if not isinstance(data, dict):
        return ads

    for placement in data.get('adPlacements', []):
        renderer = placement.get('adPlacementRenderer', {})
        items = renderer.get('renderer', {})
        for key, val in items.items():
            if not isinstance(val, dict):
                continue
            click_url = _dig_click_url(val)
            advertiser = _dig_advertiser(val)
            if click_url or advertiser:
                ads.append({
                    'advertiser': advertiser,
                    'click_url': click_url,
                    'ad_type': key,
                    'source': 'player_api',
                })

    for player_ad in data.get('playerAds', []):
        if not isinstance(player_ad, dict):
            continue
        for key, val in player_ad.items():
            if not isinstance(val, dict):
                continue
            click_url = _dig_click_url(val)
            advertiser = _dig_advertiser(val)
            if click_url or advertiser:
                ads.append({
                    'advertiser': advertiser,
                    'click_url': click_url,
                    'ad_type': key,
                    'source': 'player_ads',
                })

    return ads


def _dig_click_url(val: dict) -> str | None:
    """중첩된 YouTube 광고 JSON에서 클릭 URL 추출."""
    # clickthroughEndpoint → urlEndpoint → url
    for ep_key in ('clickthroughEndpoint', 'navigationEndpoint', 'urlEndpoint'):
        ep = val.get(ep_key, {})
        if isinstance(ep, dict):
            url_ep = ep.get('urlEndpoint', ep)
            if isinstance(url_ep, dict) and url_ep.get('url'):
                return url_ep['url']
    # pings → clickthroughPings
    pings = val.get('pings', {})
    ct_pings = pings.get('clickthroughPings', [])
    if ct_pings:
        first = ct_pings[0]
        if isinstance(first, dict):
            return first.get('baseUrl')
        elif isinstance(first, str):
            return first
    return None


def _dig_advertiser(val: dict) -> str | None:
    """중첩된 YouTube 광고 JSON에서 광고주명 추출."""
    # advertiserName 직접
    if val.get('advertiserName'):
        return val['advertiserName']
    # adTitle.runs[0].text
    ad_title = val.get('adTitle', {})
    if isinstance(ad_title, dict):
        runs = ad_title.get('runs', [])
        if runs and isinstance(runs[0], dict):
            return runs[0].get('text')
    elif isinstance(ad_title, str) and ad_title:
        return ad_title
    # headline.simpleText (companion ad)
    headline = val.get('headline', {})
    if isinstance(headline, dict) and headline.get('simpleText'):
        return headline['simpleText']
    elif isinstance(headline, str) and headline:
        return headline
    # description.runs[0].text
    desc = val.get('description', {})
    if isinstance(desc, dict):
        runs = desc.get('runs', [])
        if runs and isinstance(runs[0], dict):
            return runs[0].get('text', '')[:100] or None
    # title.simpleText
    title = val.get('title', {})
    if isinstance(title, dict):
        return title.get('simpleText')
    return None


async def _detect_ad_slot(page: Page) -> dict | None:
    """ytInitialPlayerResponse에서 광고 슬롯 존재 감지."""
    try:
        result = await page.evaluate("""() => {
            const pr = window.ytInitialPlayerResponse;
            if (!pr) return null;
            const placements = pr.adPlacements || [];
            if (placements.length === 0) return null;
            const info = {slotCount: placements.length, renderers: []};
            for (const p of placements) {
                const config = (p.adPlacementRenderer || {}).config || {};
                const kind = (config.adPlacementConfig || {}).kind || '';
                const r = (p.adPlacementRenderer || {}).renderer || {};
                info.renderers.push({kind, type: Object.keys(r)[0] || 'unknown'});
            }
            return info;
        }""")
        if result and result.get('slotCount', 0) > 0:
            renderers = result.get('renderers', [])
            kind = renderers[0].get('kind', '') if renderers else ''
            ad_type = 'preroll' if 'START' in kind else 'midroll'
            logger.debug(f"[youtube] 광고 슬롯 감지: {result['slotCount']}개 ({ad_type})")
            return {
                'advertiser': None,
                'click_url': None,
                'ad_type': f'slot_{ad_type}',
                'source': 'ad_slot_detected',
                'ad_text': f"youtube_{ad_type}_slot",
                'slot_count': result['slotCount'],
            }
    except Exception:
        pass
    return None


async def _check_ad_playing(page: Page) -> dict | None:
    """DOM에서 광고 재생 상태 및 광고주 정보 확인."""
    try:
        dom_ad = await page.evaluate("""() => {
            const player = document.querySelector('.html5-video-player, #movie_player');
            if (!player) return null;
            const adShowing = player.classList.contains('ad-showing') ||
                              player.classList.contains('ad-interrupting');
            if (!adShowing) return null;

            const getText = (sel) => {
                const el = document.querySelector(sel);
                return el ? el.textContent.trim() : null;
            };
            const getHref = (sel) => {
                const el = document.querySelector(sel);
                return el ? (el.href || el.getAttribute('href') || null) : null;
            };

            return {
                ad_text: getText('.ytp-ad-text, .ytp-ad-preview-text, .ad-simple-text'),
                cta_text: getText('.ytp-ad-button-text, .ytp-ad-visit-advertiser-button-text'),
                advertiser: getText('.ytp-ad-info-dialog-advertiser-name'),
                skip_text: getText('.ytp-skip-ad-button, .ytp-ad-skip-button-modern'),
                ad_url: getHref('a.ytp-ad-button, .ytp-ad-visit-advertiser-link, button.ytp-ad-button'),
            };
        }""")
        if dom_ad:
            advertiser = dom_ad.get('advertiser') or dom_ad.get('cta_text')
            logger.debug(f"[youtube] DOM 광고 재생 감지: adv={advertiser}, text={dom_ad.get('ad_text')}")
            return {
                'advertiser': advertiser,
                'click_url': dom_ad.get('ad_url'),
                'ad_type': 'video_instream',
                'source': 'dom_ad_playing',
                'ad_text': dom_ad.get('ad_text'),
            }
    except Exception:
        pass
    return None


async def _fetch_ad_break(page: Page, ad_break_url: str) -> list[dict]:
    """getAdBreakUrl을 직접 fetch하여 프리롤 광고 데이터 추출."""
    ads: list[dict] = []
    try:
        resp = await page.request.get(ad_break_url, timeout=8000)
        if resp.status == 200:
            ct = resp.headers.get('content-type', '')
            if 'json' in ct:
                data = await resp.json()
                ads = _parse_midroll_ads(data)
                if not ads:
                    # 직접 player_ads 파싱도 시도
                    ads = _parse_player_ads(data)
    except Exception as exc:
        logger.debug(f"[youtube] adBreak fetch 실패: {exc}")
    return ads


def _parse_midroll_ads(data) -> list[dict]:
    """get_midroll_info / get_ad_break 응답에서 광고 렌더러 추출."""
    ads: list[dict] = []
    if not isinstance(data, dict):
        return ads

    # 재귀적으로 광고 렌더러 탐색
    _walk_for_ad_renderers(data, ads)
    return ads


def _walk_for_ad_renderers(obj, ads: list[dict]):
    """JSON을 재귀 순회하며 광고 렌더러(instreamVideoAdRenderer 등) 탐색."""
    if isinstance(obj, dict):
        # 알려진 광고 렌더러 키 확인
        for ad_key in (
            'instreamVideoAdRenderer', 'adSlotRenderer',
            'linearAdSequenceRenderer', 'actionCompanionAdRenderer',
        ):
            if ad_key in obj:
                val = obj[ad_key]
                if isinstance(val, dict):
                    click_url = _dig_click_url(val)
                    advertiser = _dig_advertiser(val)
                    if click_url or advertiser:
                        ads.append({
                            'advertiser': advertiser,
                            'click_url': click_url,
                            'ad_type': ad_key,
                            'source': 'midroll_api',
                        })
                    # 중첩 렌더러도 탐색
                    _walk_for_ad_renderers(val, ads)
                    return  # 이 branch 처리 완료

        for v in obj.values():
            _walk_for_ad_renderers(v, ads)
    elif isinstance(obj, list):
        for item in obj:
            _walk_for_ad_renderers(item, ads)


def _parse_ad_json(data: dict, source_url: str) -> list[dict]:
    """doubleclick/pagead JSON 응답에서 광고 추출."""
    ads: list[dict] = []
    if 'youtube.com/api/stats/ads' in source_url:
        ads.append({
            'advertiser': None,
            'click_url': source_url,
            'ad_type': 'stats_impression',
            'source': 'stats_ads',
        })
    return ads


def _parse_ad_text(body: str, source_url: str) -> list[dict]:
    """doubleclick/pagead 텍스트 응답에서 adurl= 추출."""
    ads: list[dict] = []
    ad_urls = re.findall(r'adurl=([^&"\'<>\s]+)', body)
    for ad_url in ad_urls:
        decoded = unquote(ad_url)
        if not decoded.startswith('http'):
            continue
        try:
            domain = urlparse(decoded).netloc or ''
            domain = domain.removeprefix('www.').removeprefix('m.')
        except Exception:
            domain = ''
        if domain:
            ads.append({
                'advertiser': domain,
                'click_url': decoded,
                'ad_type': 'doubleclick',
                'source': 'network_text',
            })
    return ads


def _build_ads(captures: list[dict]) -> list[dict]:
    """네트워크 캡처를 정규화된 광고 리스트로."""
    ads: list[dict] = []
    seen: set[str] = set()

    # 실제 광고 소스 (트래킹 URL 필터 스킵 대상)
    REAL_AD_SOURCES = (
        'player_api', 'player_ads', 'midroll_api',
        'dom_ad_playing', 'ad_slot_detected',
    )

    for cap in captures:
        click_url = cap.get('click_url')
        advertiser = cap.get('advertiser')
        source = cap.get('source', '')
        ad_text = cap.get('ad_text')

        # ad_slot_detected/dom_ad_playing은 advertiser/click_url 없어도 유지
        if source not in REAL_AD_SOURCES:
            if not click_url and not advertiser:
                continue

        # stats_ads는 트래킹 전용 → 스킵
        if source == 'stats_ads':
            continue

        display_url = None
        if click_url:
            try:
                display_url = urlparse(click_url).netloc
            except Exception:
                pass

        if not advertiser and display_url:
            advertiser = display_url.removeprefix('www.').removeprefix('m.')

        # 트래킹 URL만 있는 건 스킵 (실제 광고 소스는 유지)
        if source not in REAL_AD_SOURCES:
            if display_url and any(d in display_url for d in (
                'doubleclick.net', 'googlesyndication.com',
                'youtube.com', 'google.com',
            )):
                continue

        sig = f"{advertiser or ad_text or source}|{(display_url or '')[:50]}"
        if sig in seen:
            continue
        seen.add(sig)

        ads.append({
            "advertiser_name": advertiser,
            "ad_text": ad_text or advertiser or "youtube_ad",
            "ad_description": None,
            "url": click_url,
            "display_url": display_url,
            "position": len(ads) + 1,
            "ad_type": cap.get('ad_type', 'video_preroll'),
            "extra_data": {
                "source": source,
                "surf_mode": True,
            },
        })

    return ads


# ── Google Ads Transparency Center fallback ──

_TRANSPARENCY_URL = (
    "https://adstransparency.google.com/"
    "?region=KR&format=VIDEO"
)


async def _fallback_transparency_center(
    context, keyword: str, persona_code: str, crawler,
) -> list[dict]:
    """Google Ads Transparency Center에서 YouTube 비디오 광고 수집.

    headless에서도 동작하며 실제 광고주 데이터를 반환한다.
    """
    page = await context.new_page()
    ads: list[dict] = []

    try:
        await page.goto(_TRANSPARENCY_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # 검색 입력
        search_input = page.locator(
            'input[type="text"], input[aria-label*="Search"], '
            'input[aria-label*="search"], input[placeholder*="Search"]'
        ).first
        if await search_input.count() > 0:
            await search_input.fill(keyword)
            await search_input.press("Enter")
            await page.wait_for_timeout(5000)

        # 스크롤하여 결과 로드
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 800)")
            await page.wait_for_timeout(1500)

        # 광고 카드 파싱
        card_screenshot_map: dict[int, str] = {}
        raw_data = await page.evaluate("""() => {
            const results = [];
            const selectors = [
                'creative-preview', 'advertiser-row',
                '[class*="ad-card"]', '[class*="creative"]',
                'a[href*="advertiser"]',
            ];
            let cards = [];
            for (const sel of selectors) {
                cards = Array.from(document.querySelectorAll(sel));
                if (cards.length > 0) break;
            }
            if (cards.length === 0) {
                const links = document.querySelectorAll('a[href*="advertiser"]');
                cards = Array.from(links);
            }
            for (const [idx, card] of cards.slice(0, 30).entries()) {
                const text = (card.textContent || '').replace(/\\s+/g, ' ').trim();
                const href = card.href || card.querySelector('a')?.href || '';
                const img = card.querySelector('img');
                results.push({
                    advertiser_name: text.slice(0, 150) || null,
                    url: href || null,
                    image_url: img ? (img.src || img.currentSrc) : null,
                    position: idx + 1,
                });
            }
            if (results.length === 0) {
                const bodyText = document.body.innerText || '';
                const lines = bodyText.split('\\n').filter(l => l.trim().length > 5);
                for (const [idx, line] of lines.slice(0, 20).entries()) {
                    if (line.match(/[가-힣]{2,}/) && line.length < 100) {
                        results.push({
                            advertiser_name: line.trim().slice(0, 150),
                            url: null, image_url: null,
                            position: idx + 1,
                        });
                    }
                }
            }
            return results;
        }""")

        # TC 결과 뷰포트 스크린샷 (스크롤 위치별)
        try:
            for scroll_idx in range(min(3, max(1, len(raw_data) // 6))):
                await page.evaluate(f"window.scrollTo(0, {scroll_idx * 800})")
                await page.wait_for_timeout(500)
                path = await crawler._capture_ad_element(
                    page, page.locator("body"), keyword, persona_code,
                    placement_name=f"yt_tc_view_{scroll_idx}",
                )
                if path:
                    # 각 뷰포트에 대응하는 광고 인덱스들에 매핑
                    for i in range(scroll_idx * 6, min((scroll_idx + 1) * 6, len(raw_data))):
                        card_screenshot_map[i] = path
        except Exception:
            pass

        seen: set[str] = set()
        for item in raw_data:
            name = item.get("advertiser_name")
            if not name or len(name) < 2:
                continue

            sig = name[:60]
            if sig in seen:
                continue
            seen.add(sig)

            pos = item.get("position", len(ads) + 1)
            creative_path = card_screenshot_map.get(pos - 1)

            ads.append({
                "advertiser_name": name,
                "ad_text": name,
                "ad_description": None,
                "url": item.get("url"),
                "display_url": None,
                "position": len(ads) + 1,
                "ad_type": "video_transparency",
                "ad_placement": "youtube_transparency_center",
                "creative_image_path": creative_path,
                "extra_data": {
                    "image_url": item.get("image_url"),
                    "detection_method": "google_ads_transparency_center",
                    "platform_filter": "video",
                },
            })

        logger.info(f"[youtube] Transparency Center '{keyword}' → {len(ads)}건")

    except Exception as exc:
        logger.error(f"[youtube] Transparency Center 실패: {exc}")
    finally:
        await page.close()

    return ads
