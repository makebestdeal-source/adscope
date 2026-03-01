"""Main APScheduler runner for persona/day based crawl jobs."""

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from crawler.google_gdn import GoogleGDNCrawler
from crawler.google_search_ads import GoogleSearchAdsCrawler
from crawler.kakao_da import KakaoDACrawler
from crawler.meta_library import MetaLibraryCrawler
from crawler.naver_search import NaverSearchCrawler
from crawler.youtube_ads import YouTubeAdsCrawler
from crawler.youtube_surf import YouTubeSurfCrawler
from crawler.instagram_catalog import InstagramCatalogCrawler
from crawler.naver_da import NaverDACrawler
from crawler.tiktok_ads import TikTokAdsCrawler
from crawler.naver_shopping import NaverShoppingCrawler
from database import async_session
from processor.ai_enricher import enrich_ads
from processor.campaign_builder import rebuild_campaigns_and_spend
from processor.pipeline import save_crawl_results
from scripts.sync_db_to_railway import sync as sync_db_to_railway
from scheduler.schedules import WEEKDAY_SCHEDULE, WEEKEND_SCHEDULE, ScheduleSlot
from scheduler.weekend_rules import get_weekend_boost_keywords


def _env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        parsed = int(raw.strip())
    except Exception:
        return default
    return max(minimum, parsed)


def should_skip_keyword_independent_channel(
    last_run_at: datetime | None,
    now_utc: datetime,
    min_interval_minutes: int,
) -> bool:
    if last_run_at is None:
        return False
    if min_interval_minutes <= 0:
        return False
    elapsed_minutes = (now_utc - last_run_at).total_seconds() / 60
    return elapsed_minutes < min_interval_minutes


SUPPORTED_CRAWLER_MAP = {
    # 접촉 채널 (is_contact=True)
    "naver_search": NaverSearchCrawler,
    "naver_da": NaverDACrawler,
    "google_gdn": GoogleGDNCrawler,
    "kakao_da": KakaoDACrawler,
    "youtube_surf": YouTubeSurfCrawler,
    # 카탈로그 채널 (is_contact=False)
    "youtube_ads": YouTubeAdsCrawler,
    "google_search_ads": GoogleSearchAdsCrawler,
    "facebook": MetaLibraryCrawler,
    "instagram": InstagramCatalogCrawler,
    "tiktok_ads": TikTokAdsCrawler,
    "naver_shopping": NaverShoppingCrawler,
}


def _parse_channels(raw: str | None) -> list[str]:
    if raw is None or not raw.strip():
        return ["naver_search"]
    channels: list[str] = []
    for chunk in raw.split(","):
        name = chunk.strip()
        if not name:
            continue
        if name not in SUPPORTED_CRAWLER_MAP:
            logger.warning("Unsupported crawl channel ignored: {}", name)
            continue
        if name not in channels:
            channels.append(name)
    return channels or ["naver_search"]


def _parse_channel_int_map(raw: str | None, minimum: int = 0) -> dict[str, int]:
    mapping: dict[str, int] = {}
    if raw is None or not raw.strip():
        return mapping

    for chunk in raw.split(","):
        entry = chunk.strip()
        if not entry:
            continue
        if ":" not in entry:
            logger.warning("Invalid channel map entry ignored (expected channel:value): {}", entry)
            continue

        channel, value_raw = entry.split(":", 1)
        channel = channel.strip()
        if channel not in SUPPORTED_CRAWLER_MAP:
            logger.warning("Unsupported channel in map ignored: {}", channel)
            continue
        try:
            value = int(value_raw.strip())
        except Exception:
            logger.warning("Invalid integer in channel map ignored: {}", entry)
            continue
        mapping[channel] = max(minimum, value)
    return mapping


def _limit_keywords_for_channel(
    job_keywords: list[str],
    channel: str,
    crawler_cls,
    channel_keyword_limits: dict[str, int],
) -> list[str]:
    limit = channel_keyword_limits.get(channel)
    if limit is not None:
        if limit <= 0:
            return list(job_keywords)
        return job_keywords[:limit]
    if not getattr(crawler_cls, "keyword_dependent", True):
        return job_keywords[:1]
    return list(job_keywords)


def _resolve_min_interval_for_channel(
    channel: str,
    is_keyword_dependent: bool,
    default_non_keyword_interval: int,
    channel_min_intervals: dict[str, int],
) -> int:
    if channel in channel_min_intervals:
        return channel_min_intervals[channel]
    if not is_keyword_dependent:
        return default_non_keyword_interval
    return 0


class AdScopeScheduler:
    """Crawler scheduler."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
        self._keywords: list[str] = []
        self.enable_campaign_rebuild = _env_bool("ENABLE_CAMPAIGN_REBUILD", default=True)
        self.crawl_channels = _parse_channels(os.getenv("CRAWL_CHANNELS", "naver_search"))
        self.non_keyword_channel_min_interval_minutes = _env_int(
            "NON_KEYWORD_CHANNEL_MIN_INTERVAL_MINUTES",
            default=240,
            minimum=0,
        )
        self.channel_min_intervals = _parse_channel_int_map(
            os.getenv("CRAWL_CHANNEL_MIN_INTERVALS"),
            minimum=0,
        )
        # 검색/카탈로그 광고는 연령 타겟팅 없음 → 페르소나별 반복 불필요 (120분 간격)
        _no_persona_channels = [
            "naver_search",       # 키워드 입찰, 연령 무관
            "google_search_ads",  # 투명성센터 카탈로그
            "naver_shopping",     # 키워드 기반 파워링크
            "youtube_ads",        # 투명성센터 카탈로그
            "facebook",           # Ad Library 카탈로그
            "instagram",          # Ad Library 카탈로그
            "tiktok_ads",         # Creative Center 카탈로그
        ]
        for ch in _no_persona_channels:
            if ch not in self.channel_min_intervals:
                self.channel_min_intervals[ch] = 120
        self.channel_keyword_limits = _parse_channel_int_map(
            os.getenv("CRAWL_CHANNEL_KEYWORD_LIMITS"),
            minimum=0,
        )
        self._channel_last_run_at: dict[str, datetime] = {}
        # 서킷브레이커: 연속 실패 추적 (채널 -> 연속실패횟수)
        self._channel_fail_count: dict[str, int] = {}
        self._circuit_breaker_threshold = _env_int("CIRCUIT_BREAKER_THRESHOLD", default=5, minimum=2)
        self._retry_max = _env_int("CRAWL_RETRY_MAX", default=2, minimum=0)
        logger.info("[schedule] crawl channels: {}", ", ".join(self.crawl_channels))

    def load_keywords(self, keywords_path: str = "database/seed_data/keywords.json"):
        """Load crawl keywords from seed data."""
        path = Path(keywords_path)
        if not path.exists():
            logger.warning(f"Keyword file not found: {path}")
            return
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self._keywords = list(
            dict.fromkeys(
                item["keyword"].strip()
                for item in data
                if item.get("keyword") and item["keyword"].strip()
            )
        )
        logger.info(f"Loaded {len(self._keywords)} keywords")

    def _resolve_keywords(self) -> list[str]:
        """Compose final keyword set for current run."""
        keywords = list(self._keywords)
        boost_keywords = get_weekend_boost_keywords()
        if boost_keywords:
            keywords.extend(boost_keywords)
            logger.info(f"Added weekend boost keywords: {len(boost_keywords)}")
        return list(dict.fromkeys(k for k in keywords if k))

    def setup_schedules(self):
        """Register weekday and weekend schedules into APScheduler."""
        for slot in WEEKDAY_SCHEDULE:
            self._add_job(slot, day_of_week="mon-fri")

        for slot in WEEKEND_SCHEDULE:
            self._add_job(slot, day_of_week="sat-sun")

        # AI enrichment: 매일 03:00 (새벽 배치)
        if _env_bool("ENABLE_AI_ENRICH", default=True) and os.getenv("DEEPSEEK_API_KEY"):
            self.scheduler.add_job(
                self._run_ai_enrich,
                CronTrigger(hour=3, minute=0, timezone="Asia/Seoul"),
                id="ai_enrich_daily",
                replace_existing=True,
            )
            logger.info("[schedule] AI enrichment scheduled daily at 03:00")

        # Visual mark detection: 매일 03:15 (AI enricher 이후)
        if _env_bool("ENABLE_VISUAL_MARK_DETECT", default=True) and os.getenv("OPENROUTER_API_KEY"):
            self.scheduler.add_job(
                self._run_visual_mark_detect,
                CronTrigger(hour=3, minute=15, timezone="Asia/Seoul"),
                id="visual_mark_detect_daily",
                replace_existing=True,
            )
            logger.info("[schedule] Visual mark detection scheduled daily at 03:15")

        # Brand channel monitor: 매일 02:00 (콘텐츠 수집)
        if _env_bool("ENABLE_BRAND_MONITOR", default=True):
            self.scheduler.add_job(
                self._run_brand_monitor,
                CronTrigger(hour=2, minute=0, timezone="Asia/Seoul"),
                id="brand_monitor_daily",
                replace_existing=True,
            )
            logger.info("[schedule] Brand monitor scheduled daily at 02:00")

        # Social channel stats: 매일 02:30 (구독자/팔로워 스냅샷)
        if _env_bool("ENABLE_SOCIAL_STATS", default=True):
            self.scheduler.add_job(
                self._run_social_stats,
                CronTrigger(hour=2, minute=30, timezone="Asia/Seoul"),
                id="social_stats_daily",
                replace_existing=True,
            )
            logger.info("[schedule] Social stats scheduled daily at 02:30")

        # ── Meta-signal jobs (04:00 ~ 05:30) ──

        # SmartStore meta-signal: 매일 04:00 + 16:00 (재고 델타용 2회)
        if _env_bool("ENABLE_SMARTSTORE_SIGNAL", default=True):
            self.scheduler.add_job(
                self._run_smartstore_signal,
                CronTrigger(hour=4, minute=0, timezone="Asia/Seoul"),
                id="smartstore_signal_daily",
                replace_existing=True,
            )
            self.scheduler.add_job(
                self._run_smartstore_signal,
                CronTrigger(hour=16, minute=0, timezone="Asia/Seoul"),
                id="smartstore_signal_afternoon",
                replace_existing=True,
            )
            logger.info("[schedule] SmartStore signal scheduled daily at 04:00 + 16:00")

        # Traffic signal: 매일 04:30
        if _env_bool("ENABLE_TRAFFIC_SIGNAL", default=True):
            self.scheduler.add_job(
                self._run_traffic_signal,
                CronTrigger(hour=4, minute=30, timezone="Asia/Seoul"),
                id="traffic_signal_daily",
                replace_existing=True,
            )
            logger.info("[schedule] Traffic signal scheduled daily at 04:30")

        # Activity score: 매일 05:00
        if _env_bool("ENABLE_ACTIVITY_SCORE", default=True):
            self.scheduler.add_job(
                self._run_activity_score,
                CronTrigger(hour=5, minute=0, timezone="Asia/Seoul"),
                id="activity_score_daily",
                replace_existing=True,
            )
            logger.info("[schedule] Activity score scheduled daily at 05:00")

        # Meta-signal aggregator: 매일 05:30 (모든 개별 신호 수집 이후)
        self.scheduler.add_job(
            self._run_meta_signal_aggregate,
            CronTrigger(hour=5, minute=30, timezone="Asia/Seoul"),
            id="meta_signal_aggregate_daily",
            replace_existing=True,
        )
        logger.info("[schedule] Meta-signal aggregator scheduled daily at 05:30")

        # News collection: 매일 05:45 (메타시그널 이후, 소셜 임팩트 이전)
        if _env_bool("ENABLE_NEWS_COLLECTION", default=True):
            self.scheduler.add_job(
                self._run_news_collection,
                CronTrigger(hour=5, minute=45, timezone="Asia/Seoul"),
                id="news_collection_daily",
                replace_existing=True,
            )
            logger.info("[schedule] News collection scheduled daily at 05:45")

        # Social impact score: 매일 06:00 (뉴스 수집 + 메타시그널 완료 후)
        if _env_bool("ENABLE_SOCIAL_IMPACT", default=True):
            self.scheduler.add_job(
                self._run_social_impact_score,
                CronTrigger(hour=6, minute=0, timezone="Asia/Seoul"),
                id="social_impact_score_daily",
                replace_existing=True,
            )
            logger.info("[schedule] Social impact score scheduled daily at 06:00")

        # Journey ingest: 매일 06:15 (소셜 임팩트 이후)
        self.scheduler.add_job(
            self._run_journey_ingest,
            CronTrigger(hour=6, minute=15, timezone="Asia/Seoul"),
            id="journey_ingest_daily",
            replace_existing=True,
        )
        logger.info("[schedule] Journey ingest scheduled daily at 06:15")

        # Campaign enrich: 매일 06:30
        self.scheduler.add_job(
            self._run_campaign_enrich,
            CronTrigger(hour=6, minute=45, timezone="Asia/Seoul"),
            id="campaign_enrich_daily",
            replace_existing=True,
        )
        logger.info("[schedule] Campaign enrich scheduled daily at 06:45")

        # Lift calculator: 매일 07:00 (저니 인제스트 이후)
        self.scheduler.add_job(
            self._run_lift_calculate,
            CronTrigger(hour=7, minute=0, timezone="Asia/Seoul"),
            id="lift_calculate_daily",
            replace_existing=True,
        )
        logger.info("[schedule] Lift calculator scheduled daily at 07:00")

        # Marketing schedule update: 매일 07:15 (모든 일일 처리 완료 후)
        self.scheduler.add_job(
            self._run_marketing_schedule_update,
            CronTrigger(hour=7, minute=15, timezone="Asia/Seoul"),
            id="marketing_schedule_daily",
            replace_existing=True,
        )
        logger.info("[schedule] Marketing schedule update scheduled daily at 07:15")

        # Advertiser link collector: 매일 07:30 (광고주 website/소셜 자동 수집)
        self.scheduler.add_job(
            self._run_advertiser_link_collector,
            CronTrigger(hour=7, minute=30, timezone="Asia/Seoul"),
            id="advertiser_link_collector_daily",
            replace_existing=True,
        )
        logger.info("[schedule] Advertiser link collector scheduled daily at 07:30")

        # LII: Media source mention crawl: 매 30분
        if _env_bool("ENABLE_LII_CRAWL", default=True):
            self.scheduler.add_job(
                self._run_lii_media_crawl,
                CronTrigger(minute="*/30", timezone="Asia/Seoul"),
                id="lii_media_crawl_30min",
                replace_existing=True,
            )
            logger.info("[schedule] LII media source crawl scheduled every 30 minutes")

        # LII: Launch mention collection + score calc: 매일 06:30
        if _env_bool("ENABLE_LII_SCORE", default=True):
            self.scheduler.add_job(
                self._run_lii_collect_and_score,
                CronTrigger(hour=6, minute=30, timezone="Asia/Seoul"),
                id="lii_collect_score_daily",
                replace_existing=True,
            )
            logger.info("[schedule] LII collect + score scheduled daily at 06:30")

        # DB backup: 매일 01:00
        self.scheduler.add_job(
            self._run_db_backup,
            CronTrigger(hour=1, minute=0, timezone="Asia/Seoul"),
            id="db_backup_daily",
            replace_existing=True,
        )
        logger.info("[schedule] DB backup scheduled daily at 01:00")

        # 이미지 정리: 매주 일요일 02:00 (90일 초과 삭제)
        self.scheduler.add_job(
            self._run_image_cleanup,
            CronTrigger(day_of_week="sun", hour=2, minute=0, timezone="Asia/Seoul"),
            id="image_cleanup_weekly",
            replace_existing=True,
        )
        logger.info("[schedule] Image cleanup scheduled weekly on Sun at 02:00")

        # Staging 정리: 매일 01:30 (48시간 초과 처리완료 레코드 삭제)
        self.scheduler.add_job(
            self._run_staging_cleanup,
            CronTrigger(hour=1, minute=30, timezone="Asia/Seoul"),
            id="staging_cleanup_daily",
            replace_existing=True,
        )
        logger.info("[schedule] Staging cleanup scheduled daily at 01:30")

        # Plan expiry check: 매일 00:30
        self.scheduler.add_job(
            self._check_plan_expiry,
            CronTrigger(hour=0, minute=30, timezone="Asia/Seoul"),
            id="plan_expiry_check",
            replace_existing=True,
        )
        logger.info("[schedule] Plan expiry check scheduled daily at 00:30")

        # DART ad expense collection: 매월 1일 07:30 (사업보고서 광고비 수집)
        if _env_bool("ENABLE_DART_COLLECTOR", default=True):
            self.scheduler.add_job(
                self._run_dart_collector,
                CronTrigger(day=1, hour=7, minute=30, timezone="Asia/Seoul"),
                id="dart_collector_monthly",
                replace_existing=True,
            )
            logger.info("[schedule] DART ad expense collector scheduled monthly on 1st at 07:30")

        # ADIC 100대 광고주 광고비: 매월 1일 08:00
        if _env_bool("ENABLE_ADIC_COLLECTOR", default=True):
            self.scheduler.add_job(
                self._run_adic_collector,
                CronTrigger(day=1, hour=8, minute=0, timezone="Asia/Seoul"),
                id="adic_collector_monthly",
                replace_existing=True,
            )
            logger.info("[schedule] ADIC ad expense collector scheduled monthly on 1st at 08:00")

        # 네이버 키워드 CPC/검색량 업데이트: 매주 월요일 07:30
        if _env_bool("ENABLE_NAVER_KEYWORD", default=True) and os.getenv("NAVER_AD_API_KEY"):
            self.scheduler.add_job(
                self._run_naver_keyword_update,
                CronTrigger(day_of_week="mon", hour=7, minute=30, timezone="Asia/Seoul"),
                id="naver_keyword_weekly",
                replace_existing=True,
            )
            logger.info("[schedule] Naver keyword stats scheduled weekly on Mon at 07:30")

        # 오픈애즈 시장 데이터: 매주 월요일 08:00
        if _env_bool("ENABLE_OPENADS", default=True):
            self.scheduler.add_job(
                self._run_openads_collector,
                CronTrigger(day_of_week="mon", hour=8, minute=0, timezone="Asia/Seoul"),
                id="openads_weekly",
                replace_existing=True,
            )
            logger.info("[schedule] OpenAds market data scheduled weekly on Mon at 08:00")

        # SerpApi Google Ads Transparency (weekly, 50 queries/run)
        if os.getenv("SERPAPI_KEY") and _env_bool("ENABLE_SERPAPI", default=True):
            self.scheduler.add_job(
                self._run_serpapi_collector,
                CronTrigger(day_of_week="wed", hour=7, minute=0, timezone="Asia/Seoul"),
                id="serpapi_weekly",
                replace_existing=True,
            )
            logger.info("[schedule] SerpApi Google Ads scheduled weekly on Wed at 07:00")

        job_count = len(self.scheduler.get_jobs())
        logger.info(f"Registered {job_count} schedules")

    def _add_job(self, slot: ScheduleSlot, day_of_week: str):
        """Register a schedule slot as a cron job."""
        hour, minute = slot.time.split(":")
        trigger = CronTrigger(
            day_of_week=day_of_week,
            hour=int(hour),
            minute=int(minute),
            timezone="Asia/Seoul",
        )
        job_id = f"{slot.persona_code}_{slot.time}_{day_of_week}_{slot.device}"

        self.scheduler.add_job(
            self._run_crawl_job,
            trigger=trigger,
            id=job_id,
            kwargs={
                "persona_code": slot.persona_code,
                "device_type": slot.device,
                "label": slot.label,
            },
            replace_existing=True,
        )

    async def _run_crawl_job(self, persona_code: str, device_type: str, label: str):
        """Run one crawl job and optionally rebuild campaign/spend tables."""
        if not self._keywords:
            logger.warning("[schedule] keyword list is empty; reloading from seed file")
            self.load_keywords()

        job_keywords = self._resolve_keywords()
        if not job_keywords:
            logger.error("[schedule] no keywords to crawl; aborting job")
            return {
                "persona_code": persona_code,
                "device_type": device_type,
                "label": label,
                "keyword_count": 0,
                "saved_snapshots": 0,
                "total_ads": 0,
                "errors": 0,
                "campaign_rebuild_enabled": self.enable_campaign_rebuild,
                "campaign_rebuild": None,
            }

        logger.info(
            f"[schedule] crawl started: {persona_code} / {device_type} / {label} "
            f"({datetime.now().strftime('%H:%M')})"
        )

        results: list[dict] = []
        for channel in self.crawl_channels:
            # 서킷브레이커: 연속 N회 실패한 채널은 스킵
            fail_count = self._channel_fail_count.get(channel, 0)
            if fail_count >= self._circuit_breaker_threshold:
                logger.warning(
                    "[schedule] circuit breaker OPEN for {} ({} consecutive failures, threshold {}). "
                    "Skipping. Reset with CIRCUIT_BREAKER_THRESHOLD env or restart.",
                    channel, fail_count, self._circuit_breaker_threshold,
                )
                continue

            crawler_cls = SUPPORTED_CRAWLER_MAP[channel]
            logger.info("[schedule] channel start: {}", channel)
            is_keyword_dependent = getattr(crawler_cls, "keyword_dependent", True)
            channel_keywords = _limit_keywords_for_channel(
                job_keywords=job_keywords,
                channel=channel,
                crawler_cls=crawler_cls,
                channel_keyword_limits=self.channel_keyword_limits,
            )
            channel_min_interval = _resolve_min_interval_for_channel(
                channel=channel,
                is_keyword_dependent=is_keyword_dependent,
                default_non_keyword_interval=self.non_keyword_channel_min_interval_minutes,
                channel_min_intervals=self.channel_min_intervals,
            )
            if channel_min_interval > 0:
                now_utc = datetime.now(UTC)
                last_run_at = self._channel_last_run_at.get(channel)
                if should_skip_keyword_independent_channel(
                    last_run_at=last_run_at,
                    now_utc=now_utc,
                    min_interval_minutes=channel_min_interval,
                ):
                    logger.info(
                        "[schedule] skip channel {} (min interval {}m)",
                        channel,
                        channel_min_interval,
                    )
                    continue

            # 재시도 로직 (최대 _retry_max 회)
            last_exc = None
            for attempt in range(1 + self._retry_max):
                try:
                    async with crawler_cls() as crawler:
                        channel_results = await crawler.crawl_keywords(
                            keywords=channel_keywords,
                            persona_code=persona_code,
                            device_type=device_type,
                        )
                        results.extend(channel_results)
                    if channel_min_interval > 0:
                        self._channel_last_run_at[channel] = datetime.now(UTC)
                    # 성공 → 서킷브레이커 카운트 리셋
                    self._channel_fail_count[channel] = 0
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
                    if attempt < self._retry_max:
                        wait_sec = 10 * (attempt + 1)
                        logger.warning(
                            "[schedule] channel {} attempt {}/{} failed: {}. Retrying in {}s...",
                            channel, attempt + 1, 1 + self._retry_max,
                            str(exc)[:100], wait_sec,
                        )
                        await asyncio.sleep(wait_sec)

            if last_exc is not None:
                # 모든 재시도 실패 → 서킷브레이커 카운트 증가
                self._channel_fail_count[channel] = fail_count + 1
                logger.exception("[schedule] channel failed after %d attempts: %s", 1 + self._retry_max, channel)
                now = datetime.now(UTC)
                results.extend(
                    [
                        {
                            "keyword": kw,
                            "persona_code": persona_code,
                            "device": device_type,
                            "channel": channel,
                            "captured_at": now,
                            "error": str(last_exc),
                            "ads": [],
                        }
                        for kw in channel_keywords
                    ]
                )
                if channel_min_interval > 0:
                    self._channel_last_run_at[channel] = datetime.now(UTC)

        total_ads = sum(len(r.get("ads", [])) for r in results)
        errors = sum(1 for r in results if r.get("error"))
        async with async_session() as session:
            saved = await save_crawl_results(session, results)

        rebuild_stats: dict | None = None
        if saved > 0 and self.enable_campaign_rebuild:
            try:
                rebuild_stats = await rebuild_campaigns_and_spend(active_days=7)
                logger.info(
                    "[schedule] campaign/spend rebuild complete - campaigns {} / spend_estimates {}",
                    rebuild_stats["campaigns_total"],
                    rebuild_stats["spend_estimates_total"],
                )
            except Exception:
                logger.exception("[schedule] campaign/spend rebuild failed")
        elif saved > 0:
            logger.info("[schedule] campaign rebuild disabled by ENABLE_CAMPAIGN_REBUILD=false")

        # ── AI Panel: record panel observations from crawl results ──
        if saved > 0:
            try:
                from database.models import PanelObservation, AdDetail, AdSnapshot
                async with async_session() as panel_session:
                    # Get recently saved snapshots for this persona
                    from sqlalchemy import select, and_
                    from datetime import timedelta
                    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=30)
                    snap_q = (
                        select(AdDetail.advertiser_id, AdSnapshot.channel)
                        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
                        .where(
                            and_(
                                AdSnapshot.captured_at >= cutoff,
                                AdDetail.advertiser_id.isnot(None),
                            )
                        )
                        .distinct()
                    )
                    obs_rows = (await panel_session.execute(snap_q)).fetchall()
                    panel_count = 0
                    for adv_id, channel in obs_rows:
                        panel_session.add(PanelObservation(
                            panel_type="ai",
                            panel_id=persona_code,
                            advertiser_id=adv_id,
                            channel=channel,
                            device=device_type,
                            is_verified=False,
                        ))
                        panel_count += 1
                    await panel_session.commit()
                    if panel_count:
                        logger.info("[schedule] AI panel: recorded %d observations", panel_count)
            except Exception:
                logger.exception("[schedule] AI panel recording failed")

        # ── Sync DB to Railway after successful crawl ──
        if saved > 0:
            try:
                sync_db_to_railway()
                logger.info("[schedule] Railway DB sync complete")
            except Exception:
                logger.exception("[schedule] Railway DB sync failed (non-fatal)")

        logger.info(
            f"[schedule] crawl finished: {persona_code} / {device_type} / {label} - "
            f"keywords {len(results)}, ads {total_ads}, errors {errors}, saved {saved}"
        )

        return {
            "persona_code": persona_code,
            "device_type": device_type,
            "label": label,
            "keyword_count": len(job_keywords),
            "saved_snapshots": saved,
            "total_ads": total_ads,
            "errors": errors,
            "campaign_rebuild_enabled": self.enable_campaign_rebuild,
            "campaign_rebuild": rebuild_stats,
        }

    async def _run_brand_monitor(self):
        """Daily brand channel content monitoring."""
        try:
            from crawler.brand_monitor import BrandChannelMonitor
            from processor.brand_pipeline import save_brand_content
            from database.models import Advertiser
            from sqlalchemy import select
            import json as _json

            async with async_session() as session:
                stmt = select(Advertiser).where(Advertiser.official_channels.isnot(None))
                result = await session.execute(stmt)
                advertisers = result.scalars().all()

            if not advertisers:
                logger.info("[schedule] brand monitor: no advertisers with official_channels")
                return

            total_new = 0
            async with BrandChannelMonitor() as monitor:
                for adv in advertisers:
                    channels = adv.official_channels
                    if isinstance(channels, str):
                        try:
                            channels = _json.loads(channels)
                        except (ValueError, TypeError):
                            continue
                    if not channels or not isinstance(channels, dict):
                        continue

                    yt_url = channels.get("youtube")
                    if yt_url:
                        try:
                            import asyncio
                            contents = await asyncio.wait_for(
                                monitor.monitor_youtube_channel(yt_url), timeout=60,
                            )
                            async with async_session() as session:
                                n = await save_brand_content(session, adv.id, "youtube", yt_url, contents)
                                await session.commit()
                                total_new += n
                        except Exception:
                            pass

                    ig_url = channels.get("instagram")
                    if ig_url:
                        if not ig_url.startswith("http"):
                            ig_url = f"https://www.instagram.com/{ig_url.lstrip('@')}/"
                        try:
                            import asyncio
                            contents = await asyncio.wait_for(
                                monitor.monitor_instagram_profile(ig_url), timeout=60,
                            )
                            async with async_session() as session:
                                n = await save_brand_content(session, adv.id, "instagram", ig_url, contents)
                                await session.commit()
                                total_new += n
                        except Exception:
                            pass

            logger.info("[schedule] brand monitor done: {} new items from {} advertisers",
                        total_new, len(advertisers))
        except Exception:
            logger.exception("[schedule] brand monitor failed")

    async def _run_social_stats(self):
        """Daily social channel stats snapshot (subscribers/followers)."""
        try:
            from crawler.social_stats_crawler import SocialStatsCrawler
            from database.models import Advertiser, BrandChannelContent, ChannelStats
            from sqlalchemy import select, func
            from datetime import timedelta, timezone as tz
            import json as _json

            KST = tz(timedelta(hours=9))

            async with async_session() as session:
                stmt = select(Advertiser).where(Advertiser.official_channels.isnot(None))
                result = await session.execute(stmt)
                advertisers = result.scalars().all()

            if not advertisers:
                logger.info("[schedule] social stats: no advertisers with official_channels")
                return

            collected = 0
            async with SocialStatsCrawler() as crawler:
                for adv in advertisers:
                    channels = adv.official_channels
                    if isinstance(channels, str):
                        try:
                            channels = _json.loads(channels)
                        except (ValueError, TypeError):
                            continue
                    if not channels or not isinstance(channels, dict):
                        continue

                    yt_url = channels.get("youtube")
                    if yt_url:
                        try:
                            stats = await crawler.collect_youtube_stats(yt_url)
                            if stats:
                                subs = stats.get("subscribers")
                                # Compute engagement from BrandChannelContent
                                cutoff = datetime.now() - timedelta(days=30)
                                async with async_session() as session:
                                    row_result = await session.execute(
                                        select(
                                            func.avg(BrandChannelContent.like_count),
                                            func.avg(BrandChannelContent.view_count),
                                        ).where(
                                            BrandChannelContent.advertiser_id == adv.id,
                                            BrandChannelContent.platform == "youtube",
                                            BrandChannelContent.discovered_at >= cutoff,
                                        )
                                    )
                                    avg_row = row_result.one()
                                    avg_likes = round(avg_row[0], 1) if avg_row[0] else None
                                    avg_views = round(avg_row[1], 1) if avg_row[1] else None
                                    eng_rate = round((avg_likes / subs) * 100, 4) if subs and avg_likes else None

                                    cs = ChannelStats(
                                        advertiser_id=adv.id, platform="youtube",
                                        channel_url=yt_url, subscribers=subs,
                                        total_posts=stats.get("total_posts"),
                                        total_views=stats.get("total_views"),
                                        avg_likes=avg_likes, avg_views=avg_views,
                                        engagement_rate=eng_rate,
                                        collected_at=datetime.now(),
                                    )
                                    session.add(cs)
                                    await session.commit()
                                    collected += 1
                        except Exception:
                            pass

                    ig_url = channels.get("instagram")
                    if ig_url:
                        if not ig_url.startswith("http"):
                            ig_url = f"https://www.instagram.com/{ig_url.lstrip('@')}/"
                        try:
                            stats = await crawler.collect_instagram_stats(ig_url)
                            if stats:
                                fol = stats.get("followers")
                                cutoff = datetime.now() - timedelta(days=30)
                                async with async_session() as session:
                                    row_result = await session.execute(
                                        select(
                                            func.avg(BrandChannelContent.like_count),
                                            func.avg(BrandChannelContent.view_count),
                                        ).where(
                                            BrandChannelContent.advertiser_id == adv.id,
                                            BrandChannelContent.platform == "instagram",
                                            BrandChannelContent.discovered_at >= cutoff,
                                        )
                                    )
                                    avg_row = row_result.one()
                                    avg_likes = round(avg_row[0], 1) if avg_row[0] else None
                                    avg_views = round(avg_row[1], 1) if avg_row[1] else None
                                    eng_rate = round((avg_likes / fol) * 100, 4) if fol and avg_likes else None

                                    cs = ChannelStats(
                                        advertiser_id=adv.id, platform="instagram",
                                        channel_url=ig_url, followers=fol,
                                        total_posts=stats.get("total_posts"),
                                        avg_likes=avg_likes, avg_views=avg_views,
                                        engagement_rate=eng_rate,
                                        collected_at=datetime.now(),
                                    )
                                    session.add(cs)
                                    await session.commit()
                                    collected += 1
                        except Exception:
                            pass

            logger.info("[schedule] social stats done: {} channel stats collected", collected)
        except Exception:
            logger.exception("[schedule] social stats failed")

    async def _run_ai_enrich(self):
        """Daily AI enrichment batch."""
        try:
            stats = await enrich_ads(limit=200)
            logger.info(
                "[schedule] AI enrich done: updated={}, analyzed={}",
                stats.get("updated", 0), stats.get("analyzed", 0),
            )
        except Exception:
            logger.exception("[schedule] AI enrich failed")

    async def _run_visual_mark_detect(self):
        """Daily visual ad mark detection batch."""
        try:
            from processor.visual_mark_detector import detect_visual_marks
            stats = await detect_visual_marks(limit=200)
            logger.info(
                "[schedule] Visual mark detect done: analyzed={}, marks={}, unknown={}",
                stats.get("analyzed", 0), stats.get("marks_found", 0),
                stats.get("unknown_marks", 0),
            )
        except Exception:
            logger.exception("[schedule] Visual mark detect failed")

    # ── Meta-signal tasks ──

    async def _run_smartstore_signal(self):
        """Daily SmartStore meta-signal collection + sales estimation."""
        try:
            from processor.smartstore_collector import collect_smartstore_signals
            stats = await collect_smartstore_signals()
            logger.info("[schedule] SmartStore signal done: %s", stats)

            from processor.smartstore_sales_estimator import update_sales_estimates
            est_stats = await update_sales_estimates()
            logger.info("[schedule] SmartStore sales estimation done: %s", est_stats)
        except Exception:
            logger.exception("[schedule] SmartStore signal failed")

    async def _run_traffic_signal(self):
        """Daily traffic signal estimation."""
        try:
            from processor.traffic_estimator import estimate_traffic_signals
            stats = await estimate_traffic_signals()
            logger.info("[schedule] Traffic signal done: %s", stats)
        except Exception:
            logger.exception("[schedule] Traffic signal failed")

    async def _run_activity_score(self):
        """Daily activity score calculation."""
        try:
            from processor.activity_scorer import calculate_activity_scores
            stats = await calculate_activity_scores()
            logger.info("[schedule] Activity score done: %s", stats)
        except Exception:
            logger.exception("[schedule] Activity score failed")

    async def _run_meta_signal_aggregate(self):
        """Daily meta-signal aggregation + spend multiplier calculation."""
        try:
            from processor.meta_signal_aggregator import aggregate_meta_signals
            stats = await aggregate_meta_signals()
            logger.info("[schedule] Meta-signal aggregate done: %s", stats)
        except Exception:
            logger.exception("[schedule] Meta-signal aggregate failed")

    async def _run_news_collection(self):
        """Daily news mention collection via Naver News API."""
        try:
            from processor.news_collector import collect_news_mentions
            stats = await collect_news_mentions()
            logger.info("[schedule] News collection done: %s", stats)
        except Exception:
            logger.exception("[schedule] News collection failed")

    async def _run_social_impact_score(self):
        """Daily social impact score calculation."""
        try:
            from processor.social_impact_scorer import calculate_social_impact_scores
            stats = await calculate_social_impact_scores()
            logger.info("[schedule] Social impact score done: %s", stats)
        except Exception:
            logger.exception("[schedule] Social impact score failed")

    async def _run_journey_ingest(self):
        """Daily journey event ingestion from existing data."""
        try:
            from processor.journey_ingestor import ingest_journey_events
            stats = await ingest_journey_events()
            logger.info("[schedule] Journey ingest done: %s", stats)
        except Exception:
            logger.exception("[schedule] Journey ingest failed")

    async def _run_campaign_enrich(self):
        """Daily campaign metadata AI enrichment."""
        try:
            from processor.campaign_enricher import enrich_campaign_metadata
            stats = await enrich_campaign_metadata(limit=50)
            logger.info("[schedule] Campaign enrich done: %s", stats)
        except Exception:
            logger.exception("[schedule] Campaign enrich failed")

    async def _run_lift_calculate(self):
        """Daily campaign lift calculation."""
        try:
            from processor.lift_calculator import calculate_campaign_lifts
            stats = await calculate_campaign_lifts()
            logger.info("[schedule] Lift calculate done: %s", stats)
        except Exception:
            logger.exception("[schedule] Lift calculate failed")

    async def _run_marketing_schedule_update(self):
        """Daily marketing schedule incremental update."""
        try:
            from processor.marketing_schedule_builder import update_marketing_schedule
            stats = await update_marketing_schedule(days_back=2)
            logger.info("[schedule] Marketing schedule update done: %s", stats)
        except Exception:
            logger.exception("[schedule] Marketing schedule update failed")

    async def _run_advertiser_link_collector(self):
        """Daily advertiser website/social link extraction from ad_details."""
        try:
            from processor.advertiser_link_collector import collect_advertiser_links
            stats = await collect_advertiser_links(limit=100)
            logger.info("[schedule] Advertiser link collector done: %s", stats)
        except Exception:
            logger.exception("[schedule] Advertiser link collector failed")

    async def _run_lii_media_crawl(self):
        """LII: Crawl mentions from registered media sources (RSS/YouTube/HTML)."""
        try:
            from processor.launch_mention_collector import crawl_media_sources
            stats = await crawl_media_sources()
            logger.info("[schedule] LII media crawl done: %s", stats)
        except Exception:
            logger.exception("[schedule] LII media crawl failed")

    async def _run_lii_collect_and_score(self):
        """LII: Collect Naver mentions + calculate impact scores."""
        try:
            from processor.launch_mention_collector import collect_launch_mentions
            stats1 = await collect_launch_mentions()
            logger.info("[schedule] LII mention collection done: %s", stats1)
        except Exception:
            logger.exception("[schedule] LII mention collection failed")

        try:
            from processor.launch_impact_scorer import calculate_launch_impact_scores
            stats2 = await calculate_launch_impact_scores()
            logger.info("[schedule] LII score calculation done: %s", stats2)
        except Exception:
            logger.exception("[schedule] LII score calculation failed")

    async def _run_dart_collector(self):
        """Monthly DART ad expense collection from electronic disclosure system."""
        try:
            from processor.dart_collector import collect_dart_expenses
            stats = await collect_dart_expenses()
            logger.info("[schedule] DART collector done: %s", stats)
        except Exception:
            logger.exception("[schedule] DART collector failed")

    async def _run_adic_collector(self):
        """Monthly ADIC top 100 advertiser ad expense collection."""
        try:
            from processor.adic_collector import collect_adic_top100, update_advertiser_benchmarks
            stats = await collect_adic_top100()
            logger.info("[schedule] ADIC collector done: %s", stats)
            bench = await update_advertiser_benchmarks()
            logger.info("[schedule] ADIC benchmarks updated: %s", bench)
        except Exception:
            logger.exception("[schedule] ADIC collector failed")

    async def _run_naver_keyword_update(self):
        """Weekly Naver keyword CPC/search volume update."""
        try:
            from processor.naver_keyword_collector import update_keyword_stats
            stats = await update_keyword_stats()
            logger.info("[schedule] Naver keyword update done: %s", stats)
        except Exception:
            logger.exception("[schedule] Naver keyword update failed")

    async def _run_openads_collector(self):
        """Weekly OpenAds market data collection."""
        try:
            from processor.openads_collector import collect_openads_data
            stats = await collect_openads_data()
            logger.info("[schedule] OpenAds collector done: %s", stats)
        except Exception:
            logger.exception("[schedule] OpenAds collector failed")

    async def _run_serpapi_collector(self):
        """Weekly SerpApi Google Ads Transparency collection."""
        try:
            from processor.serpapi_collector import collect_top_advertiser_ads
            stats = await collect_top_advertiser_ads(max_queries=25)
            logger.info("[schedule] SerpApi collector done: %s", stats)
        except Exception:
            logger.exception("[schedule] SerpApi collector failed")

    async def _run_db_backup(self):
        """Daily database backup."""
        try:
            from scripts.backup_db import backup_db
            result = backup_db()
            logger.info("[schedule] DB backup done: %s", result)
        except Exception:
            logger.exception("[schedule] DB backup failed")

    async def _check_plan_expiry(self):
        """Log expired plans for monitoring."""
        try:
            from sqlalchemy import select, and_
            from database.models import User
            now = datetime.now(UTC)
            async with async_session() as session:
                result = await session.execute(
                    select(User.id, User.email, User.plan, User.plan_expires_at).where(
                        and_(
                            User.plan_expires_at < now,
                            User.is_active == True,
                            User.role != "admin",
                        )
                    )
                )
                expired = result.fetchall()
                if expired:
                    logger.info("[schedule] %d expired plans: %s",
                                len(expired),
                                ", ".join(f"{r.email}({r.plan})" for r in expired))
                else:
                    logger.info("[schedule] No expired plans")
        except Exception:
            logger.exception("[schedule] Plan expiry check failed")

    async def _run_image_cleanup(self):
        """Weekly image cleanup -- delete images older than 90 days."""
        try:
            from processor.image_store import get_image_store
            store = get_image_store()
            deleted = await store.cleanup(older_than_days=90)
            logger.info("[schedule] Image cleanup done: %d files deleted", deleted)
        except Exception:
            logger.exception("[schedule] Image cleanup failed")

    async def _run_staging_cleanup(self):
        """Daily staging table cleanup -- remove processed records older than 48h."""
        try:
            from sqlalchemy import delete, or_
            from database.models import StagingAd
            from datetime import timedelta

            cutoff = datetime.now(UTC) - timedelta(hours=48)
            async with async_session() as session:
                result = await session.execute(
                    delete(StagingAd).where(
                        StagingAd.created_at < cutoff,
                        or_(
                            StagingAd.status == "approved",
                            StagingAd.status == "rejected",
                        ),
                    )
                )
                cleaned = result.rowcount
                await session.commit()
            if cleaned:
                logger.info("[schedule] Staging cleanup: %d old records removed", cleaned)
        except Exception:
            logger.exception("[schedule] Staging cleanup failed")

    def start(self):
        """Start scheduler."""
        self.scheduler.start()
        logger.info("AdScope scheduler started")

    def stop(self):
        """Stop scheduler."""
        self.scheduler.shutdown()
        logger.info("AdScope scheduler stopped")
