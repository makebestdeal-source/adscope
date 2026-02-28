"""playwright-stealth 패치 — base_crawler.py를 수정하지 않고 stealth 적용.

사용법 (fast_crawl.py 또는 scheduler 에서):
    from crawler.stealth_patch import enable_stealth
    enable_stealth()  # BaseCrawler._create_context에 stealth 주입

이후 모든 BaseCrawler 하위 크롤러가 자동으로 stealth 적용됨.
"""

from __future__ import annotations

from loguru import logger

_PATCHED = False


def enable_stealth():
    """BaseCrawler._create_context를 monkey-patch하여 playwright-stealth 적용."""
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    try:
        from playwright_stealth import Stealth
    except ImportError:
        logger.warning("[stealth_patch] playwright-stealth not installed, skipping")
        return

    from crawler.base_crawler import BaseCrawler

    _original_create_context = BaseCrawler._create_context

    async def _patched_create_context(self, persona, device):
        """Original _create_context + playwright-stealth 적용."""
        context = await _original_create_context(self, persona, device)

        # Stealth 적용: context의 모든 새 페이지에 자동 적용
        try:
            stealth = Stealth(
                navigator_languages_override=("ko-KR", "ko"),
                navigator_platform_override="Win32",
                # 핵심 evasion만 활성화 (UA는 device_config이 관리)
                navigator_user_agent=False,
                navigator_vendor=True,
                navigator_webdriver=True,
                navigator_plugins=True,
                navigator_permissions=True,
                chrome_app=True,
                chrome_csi=True,
                chrome_load_times=True,
                chrome_runtime=False,  # base_crawler에서 이미 처리
                iframe_content_window=True,
                media_codecs=True,
                navigator_hardware_concurrency=True,
                webgl_vendor=True,
                hairline=True,
                error_prototype=True,
                sec_ch_ua=True,
            )

            # Context-level init script로 stealth JS 주입
            scripts = list(stealth.enabled_scripts)
            for script in scripts:
                await context.add_init_script(script)

            logger.debug(f"[stealth_patch] Applied {len(scripts)} stealth scripts to {self.channel}")
        except Exception as e:
            # stealth 실패해도 기존 동작은 유지
            logger.debug(f"[stealth_patch] Failed for {self.channel}: {str(e)[:60]}")

        return context

    BaseCrawler._create_context = _patched_create_context
    logger.info("[stealth_patch] Enabled playwright-stealth for all crawlers")
