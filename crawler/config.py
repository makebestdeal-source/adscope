"""크롤러 전역 설정."""

from pydantic_settings import BaseSettings


class CrawlerSettings(BaseSettings):
    # 타임아웃
    page_timeout_ms: int = 30_000
    navigation_timeout_ms: int = 15_000

    # 재시도
    max_retries: int = 3
    retry_delay_sec: float = 2.0

    # 동시성
    max_concurrent_browsers: int = 3

    # 스크린샷
    screenshot_dir: str = "screenshots"
    screenshot_quality: int = 80

    # 브라우저
    headless: bool = True
    headful_channels: str = ""
    slow_mo_ms: int = 0

    # Redis (중복 필터링)
    redis_url: str = "redis://localhost:6379/0"
    dedup_ttl_hours: int = 24

    # 랜딩페이지 분석
    landing_concurrent: int = 3
    landing_timeout_ms: int = 10_000
    landing_capture_screenshot: bool = False
    landing_screenshot_dir: str = "screenshots/landing"

    # ── 휴먼라이크 행동 설정 ──

    # 쿠키 워밍업 (2사이트 x 3~8초 = ~20초, 타임아웃 방지)
    warmup_site_count: int = 2
    warmup_dwell_min_ms: int = 3_000
    warmup_dwell_max_ms: int = 8_000
    warmup_scroll_count: int = 2

    # 페이지 체류 (파싱 전)
    dwell_min_ms: int = 12_000
    dwell_max_ms: int = 25_000
    dwell_scroll_count_min: int = 3
    dwell_scroll_count_max: int = 7

    # 스크롤 행동
    scroll_step_min: int = 4
    scroll_step_max: int = 8
    scroll_step_pause_min_ms: int = 150
    scroll_step_pause_max_ms: int = 600
    scroll_reverse_chance: float = 0.15
    scroll_reverse_ratio: float = 0.3
    scroll_read_pause_min_ms: int = 2_000
    scroll_read_pause_max_ms: int = 6_000

    # 마우스 움직임
    mouse_enabled: bool = True
    mouse_jiggle_min_moves: int = 2
    mouse_jiggle_max_moves: int = 5
    mouse_hover_chance: float = 0.3

    # 페이지 간 쿨다운
    inter_page_min_ms: int = 4_000
    inter_page_max_ms: int = 12_000

    # 스케줄러 오프셋
    schedule_offset_min_minutes: int = 3
    schedule_offset_max_minutes: int = 8

    model_config = {"env_prefix": "CRAWLER_"}


crawler_settings = CrawlerSettings()
