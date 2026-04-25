"""Facebook/Instagram 피드 서핑 크롤러 — 로그인 후 피드 스크롤하여 Sponsored 광고 수집.

기존 meta_library.py (Ad Library 스크래핑)와 별개로,
실제 사용자 피드에서 Sponsored 포스트를 네트워크 인터셉트 + DOM 탐지로 수집.

수집 방식:
  1) Facebook: 로그인 → 뉴스피드 스크롤 → "Sponsored" 라벨 포스트 캡처
  2) Instagram: 로그인 → 피드 스크롤 → "Sponsored"/"광고" 라벨 포스트 캡처

보안:
  - cookie_data/{persona}/instagram.json 쿠키 사용 (로그인 세션)
  - headless 모드 (stealth 적용)
  - 네트워크 인터셉트로 광고 데이터 캡처 (DOM 셀렉터로 탐지하지 않음 — 프로젝트 규칙)
    ※ Sponsored 라벨 확인은 광고 식별이지 광고 탐지가 아님
"""

from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger
from playwright.async_api import Page, Response

from crawler.base_crawler import BaseCrawler
from crawler.constants import is_infra_domain as _is_infra
from crawler.personas.device_config import DeviceConfig
from crawler.personas.profiles import PersonaProfile
from crawler.url_utils import extract_domain, resolve_redirect_url

# ── 설정 ──

META_FEED_SCROLL_COUNT = max(5, int(os.getenv("META_FEED_SCROLL_COUNT", "25")))
META_FEED_PLATFORM = os.getenv("META_FEED_PLATFORM", "both").strip().lower()  # facebook/instagram/both

# 쿠키 디렉토리
_COOKIE_DIR = Path(__file__).resolve().parent.parent / "cookie_data"


class MetaFeedSurfCrawler(BaseCrawler):
    """Facebook/Instagram 피드에 로그인하여 Sponsored 광고를 서핑 수집."""

    channel = "meta"

    async def crawl_keyword(
        self,
        keyword: str,
        persona: PersonaProfile,
        device: DeviceConfig,
    ) -> dict:
        start_time = datetime.now(timezone.utc)
        context = await self._create_context(persona, device)

        try:
            # 쿠키 로드 (Instagram/Facebook 세션)
            cookie_loaded = await self._load_meta_cookies(context, persona.code)
            if not cookie_loaded:
                logger.warning(f"[{self.channel}] 쿠키 없음 — 로그인 불가, 수집 제한적")

            page = await context.new_page()
            all_ads: list[dict] = []

            # 네트워크 인터셉트 (광고 API 응답 캡처)
            network_ads: list[dict] = []

            async def _on_meta_ad_response(response: Response):
                url = response.url
                try:
                    # Facebook GraphQL 광고 응답
                    if 'graphql' in url and response.status == 200:
                        ct = response.headers.get('content-type', '')
                        if 'json' in ct:
                            data = await response.json()
                            ads = self._parse_fb_graphql_ads(data)
                            network_ads.extend(ads)
                    # Instagram 피드 API
                    elif ('feed' in url or 'timeline' in url) and 'instagram' in url:
                        if response.status == 200:
                            ct = response.headers.get('content-type', '')
                            if 'json' in ct:
                                data = await response.json()
                                ads = self._parse_ig_feed_ads(data)
                                network_ads.extend(ads)
                except Exception:
                    pass

            page.on('response', _on_meta_ad_response)

            platform = keyword.lower() if keyword in ("facebook", "instagram") else META_FEED_PLATFORM

            is_mobile = device.is_mobile

            # Facebook 피드 서핑
            if platform in ("facebook", "both"):
                fb_ads = await self._surf_facebook_feed(page, persona.code, is_mobile)
                all_ads.extend(fb_ads)

            # Instagram 피드 서핑
            if platform in ("instagram", "both"):
                ig_ads = await self._surf_instagram_feed(page, persona.code, is_mobile)
                all_ads.extend(ig_ads)

            # 네트워크 캡처 병합
            if network_ads:
                net_normalized = self._normalize_network_ads(network_ads)
                logger.info(f"[{self.channel}] network captured {len(net_normalized)} ads")
                # 중복 제거 후 병합
                existing_sigs = {(a.get("url", ""), a.get("advertiser_name", "")) for a in all_ads}
                for na in net_normalized:
                    sig = (na.get("url", ""), na.get("advertiser_name", ""))
                    if sig not in existing_sigs:
                        all_ads.append(na)
                        existing_sigs.add(sig)

            await self._download_creative_assets(
                all_ads,
                extra_keys=("image_url",),
                category="creative",
                filename_prefix="meta_feed_creative",
            )
            await self._save_context_cookies(context, persona)
            screenshot_path = await self._take_screenshot(page, keyword or "feed_surf", persona.code)
            elapsed = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            logger.info(f"[{self.channel}] total ads: {len(all_ads)} (platform={platform})")

            return {
                "keyword": keyword or "feed_surf",
                "persona_code": persona.code,
                "device": device.device_type,
                "channel": self.channel,
                "captured_at": datetime.now(timezone.utc),
                "page_url": page.url,
                "screenshot_path": screenshot_path,
                "ads": all_ads,
                "crawl_duration_ms": elapsed,
            }
        finally:
            for p in context.pages:
                await p.close()
            await context.close()

    # ── Facebook 피드 서핑 ──

    async def _surf_facebook_feed(self, page: Page, persona_code: str, is_mobile: bool = False) -> list[dict]:
        """Facebook 뉴스피드를 스크롤하여 네트워크 광고 응답을 유도한다.

        광고 탐지는 DOM 셀렉터 대신 네트워크 인터셉트(_on_meta_ad_response)에서만 수행.
        이 메서드는 피드를 스크롤해 GraphQL 응답을 트리거하는 역할만 한다.
        """
        fb_url = "https://m.facebook.com/" if is_mobile else "https://www.facebook.com/"

        try:
            await page.goto(fb_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000 + random.randint(500, 1500))

            # 로그인 확인 (광고 탐지가 아닌 세션 상태 확인)
            is_logged_in = await page.evaluate("""() => {
                return !!(document.querySelector('[aria-label="Facebook"]') ||
                         document.querySelector('[data-pagelet="Feed"]') ||
                         document.querySelector('[role="feed"]'));
            }""")

            if not is_logged_in:
                logger.warning(f"[{self.channel}] Facebook 로그인 안 됨 — 피드 접근 제한")
                return []

            logger.info(f"[{self.channel}] Facebook 피드 서핑 시작 (네트워크 인터셉트 전용)")

            # 스크롤로 GraphQL 광고 응답 유도 — 광고 추출은 _on_meta_ad_response에서
            for _ in range(META_FEED_SCROLL_COUNT):
                await page.evaluate(f"window.scrollBy(0, {600 + random.randint(100, 300)})")
                await page.wait_for_timeout(1500 + random.randint(500, 1000))

        except Exception as exc:
            logger.warning(f"[{self.channel}] Facebook feed surf failed: {exc}")

        return []

    # ── Instagram 피드 서핑 ──

    async def _surf_instagram_feed(self, page: Page, persona_code: str, is_mobile: bool = False) -> list[dict]:
        """Instagram 피드를 스크롤하여 네트워크 광고 응답을 유도한다.

        광고 탐지는 DOM 셀렉터 대신 네트워크 인터셉트(_on_meta_ad_response)에서만 수행.
        이 메서드는 피드를 스크롤해 Instagram feed API 응답을 트리거하는 역할만 한다.
        """
        try:
            await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000 + random.randint(500, 1500))

            # 로그인 확인 (광고 탐지가 아닌 세션 상태 확인)
            is_logged_in = await page.evaluate("""() => {
                return !!(document.querySelector('[aria-label="Home"]') ||
                         document.querySelector('nav[role="navigation"]') ||
                         document.querySelector('a[href="/direct/inbox/"]'));
            }""")

            if not is_logged_in:
                logger.warning(f"[{self.channel}] Instagram 로그인 안 됨 — 피드 접근 제한")
                return []

            logger.info(f"[{self.channel}] Instagram 피드 서핑 시작 (네트워크 인터셉트 전용)")

            # 스크롤로 feed API 광고 응답 유도 — 광고 추출은 _on_meta_ad_response에서
            for _ in range(META_FEED_SCROLL_COUNT):
                await page.evaluate(f"window.scrollBy(0, {500 + random.randint(100, 300)})")
                await page.wait_for_timeout(1500 + random.randint(500, 1000))

        except Exception as exc:
            logger.warning(f"[{self.channel}] Instagram feed surf failed: {exc}")

        return []

    # ── 쿠키 관리 ──

    async def _load_meta_cookies(self, context, persona_code: str) -> bool:
        """cookie_data/{persona}/instagram.json에서 쿠키 로드. 없으면 SHARED fallback."""
        loaded = False

        # 1차: 페르소나별 쿠키
        for cookie_file_name in ("instagram.json", "instagram_mobile.json", "meta_feed.json"):
            cookie_path = _COOKIE_DIR / persona_code / cookie_file_name
            if not cookie_path.exists():
                continue
            loaded = await self._inject_meta_cookie_file(context, cookie_path, persona_code)
            if loaded:
                return True

        # 2차: SHARED fallback (공유 계정 쿠키)
        shared_path = _COOKIE_DIR / "SHARED" / "meta_login.json"
        if not loaded and shared_path.exists():
            loaded = await self._inject_meta_cookie_file(context, shared_path, "SHARED")

        return loaded

    async def _inject_meta_cookie_file(self, context, cookie_path, label: str) -> bool:
        """메타 쿠키 파일을 컨텍스트에 주입."""
        try:
            data = json.loads(cookie_path.read_text(encoding="utf-8"))
            cookies = data.get("cookies", [])
            if not cookies:
                return False

            meta_cookies = [
                c for c in cookies
                if isinstance(c.get("domain"), str)
                and any(d in c["domain"] for d in (
                    "instagram.com", "facebook.com", "fbcdn.net", "meta.com",
                ))
            ]
            if meta_cookies:
                await context.add_cookies(meta_cookies)
                logger.info(
                    f"[{self.channel}] 쿠키 로드: "
                    f"{len(meta_cookies)}개 ({label}, {cookie_path.name})"
                )
                return True
        except Exception as exc:
            logger.debug(f"[{self.channel}] 쿠키 로드 실패 ({cookie_path.name}): {exc}")
        return False

    # ── URL 리졸브 ──
    # _resolve_fb_redirect / _resolve_ig_redirect → crawler.url_utils.resolve_redirect_url

    @staticmethod
    def _resolve_fb_redirect(url: str | None) -> str | None:
        return resolve_redirect_url(url)

    @staticmethod
    def _resolve_ig_redirect(url: str | None) -> str | None:
        return resolve_redirect_url(url)

    # ── 네트워크 캡처 파싱 ──

    def _parse_fb_graphql_ads(self, data: dict) -> list[dict]:
        """Facebook GraphQL 응답에서 광고 데이터 추출."""
        ads: list[dict] = []
        if not isinstance(data, dict):
            return ads

        # 재귀적으로 sponsored_data / ad_id 탐색
        self._walk_fb_graphql(data, ads, depth=0)
        return ads

    def _walk_fb_graphql(self, obj, ads: list[dict], depth: int):
        """Facebook GraphQL JSON 재귀 탐색."""
        if depth > 10:
            return
        if isinstance(obj, dict):
            # sponsored_data 노드 발견
            if 'sponsored_data' in obj or 'is_sponsored' in obj:
                sponsor = obj.get('sponsored_data', {})
                advertiser = None
                click_url = None

                if isinstance(sponsor, dict):
                    advertiser = sponsor.get('advertiser_name') or sponsor.get('page_name')
                    click_url = sponsor.get('url') or sponsor.get('link')

                # story 노드에서도 탐색
                story = obj.get('story', obj.get('node', {}))
                if isinstance(story, dict) and not advertiser:
                    actors = story.get('actors', [])
                    if actors and isinstance(actors[0], dict):
                        advertiser = actors[0].get('name')
                    if not click_url:
                        click_url = story.get('url') or story.get('tracking', {}).get('url')

                if advertiser or click_url:
                    ads.append({
                        'advertiser': advertiser,
                        'click_url': click_url,
                        'platform': 'facebook',
                        'source': 'graphql_sponsored',
                    })

            for v in obj.values():
                self._walk_fb_graphql(v, ads, depth + 1)

        elif isinstance(obj, list):
            for item in obj:
                self._walk_fb_graphql(item, ads, depth + 1)

    def _parse_ig_feed_ads(self, data: dict) -> list[dict]:
        """Instagram 피드 API 응답에서 광고 데이터 추출."""
        ads: list[dict] = []
        if not isinstance(data, dict):
            return ads

        # Instagram API: items[].ad_id 또는 items[].injected
        items = data.get('items', data.get('feed_items', []))
        if not isinstance(items, list):
            return ads

        for item in items:
            if not isinstance(item, dict):
                continue
            # 광고 식별: ad_id, is_ad, injected
            if not (item.get('ad_id') or item.get('is_ad') or
                    item.get('injected') or item.get('ad_action')):
                continue

            user = item.get('user', {})
            advertiser = user.get('full_name') or user.get('username') or None
            caption = item.get('caption', {})
            ad_text = caption.get('text', '')[:200] if isinstance(caption, dict) else ''
            link = item.get('link') or item.get('ad_link_url') or ''

            # 이미지
            image_versions = item.get('image_versions2', {}).get('candidates', [])
            image_url = image_versions[0].get('url') if image_versions else None

            if advertiser or link:
                ads.append({
                    'advertiser': advertiser,
                    'click_url': link,
                    'ad_text': ad_text,
                    'image_url': image_url,
                    'platform': 'instagram',
                    'source': 'ig_feed_api',
                })

        return ads

    def _normalize_network_ads(self, captures: list[dict]) -> list[dict]:
        """네트워크 캡처를 정규화된 광고 리스트로 변환."""
        ads: list[dict] = []
        seen: set[str] = set()

        for cap in captures:
            advertiser = cap.get('advertiser')
            click_url = cap.get('click_url')
            platform = cap.get('platform', 'meta')

            # URL 리졸브
            if click_url:
                if 'l.facebook.com' in click_url:
                    click_url = self._resolve_fb_redirect(click_url) or click_url
                elif 'l.instagram.com' in click_url:
                    click_url = self._resolve_ig_redirect(click_url) or click_url

            display_url = None
            if click_url:
                try:
                    display_url = urlparse(click_url).netloc.removeprefix('www.').removeprefix('m.')
                except Exception:
                    pass

            if not advertiser and display_url and not _is_infra(display_url):
                advertiser = display_url

            if not advertiser and not click_url:
                continue

            sig = f"{advertiser}|{click_url or ''}"
            if sig in seen:
                continue
            seen.add(sig)

            placement = f"{platform}_feed"
            product = "FB 피드 광고" if platform == "facebook" else "IG 피드 광고"

            ads.append({
                "advertiser_name": advertiser,
                "ad_text": cap.get('ad_text') or advertiser or f"{platform}_ad",
                "ad_description": None,
                "url": click_url,
                "display_url": display_url,
                "position": len(ads) + 1,
                "ad_type": "social_feed",
                "ad_placement": placement,
                "ad_product_name": product,
                "ad_format_type": "social",
                "campaign_purpose": "awareness",
                "creative_image_path": None,
                "extra_data": {
                    "detection_method": "network_intercept",
                    "platform": platform,
                    "source": cap.get('source', ''),
                    "image_url": cap.get('image_url'),
                },
            })

        return ads
