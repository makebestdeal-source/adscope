"""Build campaign and spend tables from collected ad snapshots.

금액 필드 정의 (모든 단위: KRW)
----------------------------------------------------------------------
- est_daily_spend      : 일일 매체비 추정 (KRW/day, 세금/마진 미포함)
- total_spend_multiplier : 매체비 -> 총수주액 환산 계수 (채널별 상이, 예: META 1.248)
- est_daily_total_cost : 일일 총비용 = est_daily_spend * total_spend_multiplier (factors JSON 내)
- Campaign.total_est_spend : 캠페인 활성 기간 내 est_daily_spend 합계 (KRW, 매체비 기준)
- SpendEstimate.est_daily_spend : 특정 일자의 매체비 추정 (KRW/day)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
import os

from sqlalchemy import delete, func, select

from database import async_session
from database.models import AdDetail, AdSnapshot, Advertiser, Campaign, Keyword, SpendEstimate
from processor.advertiser_name_cleaner import clean_name_for_pipeline
from processor.advertiser_verifier import NameQuality, verify_advertiser_name
from processor.advertiser_link_collector import extract_website_from_url
from processor.spend_estimator import SpendEstimatorV2

DEFAULT_EXCLUDED_CHANNELS: set[str] = set()  # youtube_ads 포함 (2,372건 활용)

# ── Channel -> spend_category mapping ──
_CHANNEL_SPEND_CATEGORY: dict[str, str] = {
    "naver_shopping": "shopping",
    "naver_search": "search",
    "google_search_ads": "search",
    "naver_da": "banner",
    "kakao_da": "banner",
    "google_gdn": "banner",
    "mobile_gdn": "banner",
    "youtube_ads": "video",
    "youtube_surf": "video",
    "tiktok_ads": "video",
    "meta": "social",
}


def _yt_compute_daily_views(agg, fallback_avg_views: float = 0) -> int:
    """YouTube 광고주의 일일 유료 조회수 계산.

    최근 30일 내 업로드된 10만회+ 영상만 대상.
    total_view_count는 최근 업로드 영상의 누적 조회수 합계이므로,
    30일로 나눠서 일일 평균 조회수를 구한다.

    우선순위:
    1. total_view_count > 0: (누적 조회수 × 0.95) / 30 = 일일 추정 유료 조회수
    2. fallback_avg_views > 0: 채널 평균 조회수에서 역산 (보수적)
    3. 둘 다 없으면 0 (catalog_creative_reverse fallback 사용)
    """
    if agg.total_view_count > 0:
        # 10만회+ 영상만 합산된 조회수 × 95% → 일 평균 (30일 기준)
        daily = int(agg.total_view_count * 0.95) // 30
        return max(100, daily)

    if fallback_avg_views > 0:
        # 채널 평균 조회수 fallback (보수적 추정)
        daily = int(fallback_avg_views / 30 * 0.3)
        return max(100, daily)

    return 0


def _get_spend_category(channel: str) -> str:
    """Return spend category for a given channel, default 'banner'."""
    return _CHANNEL_SPEND_CATEGORY.get(channel, "banner")


def _normalize_name(name: str) -> str:
    return name.lower().replace(" ", "").strip()


def _parse_excluded_channels(raw: str | None, default: set[str] | None = None) -> set[str]:
    if raw is None:
        return set(default or ())
    return {chunk.strip() for chunk in raw.split(",") if chunk.strip()}


@dataclass
class DayAggregate:
    ad_hits: int = 0
    positions: list[int] = field(default_factory=list)
    position_zones: list[str] = field(default_factory=list)
    inhouse_count: int = 0


@dataclass
class CampaignAggregate:
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    snapshot_ids: set[int] = field(default_factory=set)
    ad_occurrences: int = 0
    by_day: dict[date, DayAggregate] = field(default_factory=dict)
    placements: set[str] = field(default_factory=set)
    has_inhouse: bool = False
    has_contact: bool = False
    max_view_count: int = 0
    total_view_count: int = 0   # 모든 소재의 조회수 합계
    view_count_sources: int = 0  # view_count가 있는 소재 수


async def _backfill_advertiser_ids() -> tuple[int, int]:
    """advertiser_id가 NULL인 ad_details에 대해서만 광고주 매칭/생성을 수행한다.

    pipeline.py에서 1차 매칭이 이미 이루어진 레코드(advertiser_id IS NOT NULL)는
    건너뛰므로, 중복 Advertiser 생성이 방지된다.
    """
    async with async_session() as session:
        advertisers = (await session.execute(select(Advertiser))).scalars().all()
        name_to_id: dict[str, int] = {}
        norm_to_id: dict[str, int] = {}
        for adv in advertisers:
            name_to_id[adv.name] = adv.id
            norm_to_id[_normalize_name(adv.name)] = adv.id

        # advertiser_id가 NULL인 레코드만 조회 (이미 매칭된 건 스킵)
        # URL 필수: URL 없는 소재는 광고주 매칭에서 제외
        unmatched = (
            await session.execute(
                select(AdDetail).where(
                    AdDetail.advertiser_id.is_(None),
                    AdDetail.advertiser_name_raw.is_not(None),
                    AdDetail.url.is_not(None),
                    AdDetail.url != "",
                )
            )
        ).scalars().all()

        linked = 0
        created = 0
        for detail in unmatched:
            # 이미 advertiser_id가 할당된 ad_detail은 스킵
            # (위 쿼리에서 NULL 필터를 걸지만, flush 사이 race 방지용 이중 체크)
            if detail.advertiser_id is not None:
                continue

            raw_name = (detail.advertiser_name_raw or "").strip()
            if not raw_name:
                continue

            # ── 항상 먼저 이름 품질 검증 + URL/광고카피 제거 ──
            verification = verify_advertiser_name(raw_name)
            if verification.quality == NameQuality.REJECTED:
                continue
            clean_name = verification.cleaned_name or raw_name
            # 추가 정리: URL, 도메인, 이중공백 광고카피 제거
            clean_name = clean_name_for_pipeline(clean_name)

            # 정제된 이름으로 먼저 검색 (URL 제거된 이름)
            adv_id = name_to_id.get(clean_name)
            if adv_id is None:
                adv_id = norm_to_id.get(_normalize_name(clean_name))
            # 원본 이름으로도 검색 (기존 레코드 호환)
            if adv_id is None:
                adv_id = name_to_id.get(raw_name)
            if adv_id is None:
                adv_id = norm_to_id.get(_normalize_name(raw_name))

            if adv_id is None:
                # Extract website from this ad's URL/display_url
                website = extract_website_from_url(detail.url, detail.display_url)
                adv = Advertiser(name=clean_name, aliases=[], website=website)
                session.add(adv)
                await session.flush()
                adv_id = adv.id
                name_to_id[clean_name] = adv_id
                norm_to_id[_normalize_name(clean_name)] = adv_id
                created += 1

            detail.advertiser_id = adv_id
            linked += 1

        await session.commit()
        return linked, created


async def _delete_excluded_campaign_data(excluded_channels: set[str]) -> None:
    if not excluded_channels:
        return
    async with async_session() as session:
        excluded_list = list(excluded_channels)
        await session.execute(delete(SpendEstimate).where(SpendEstimate.channel.in_(excluded_list)))
        await session.execute(delete(Campaign).where(Campaign.channel.in_(excluded_list)))
        await session.commit()


async def _backfill_advertiser_industries(excluded_channels: set[str] | None = None) -> int:
    async with async_session() as session:
        query = (
            select(AdDetail.advertiser_id, Keyword.industry_id)
            .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
            .join(Keyword, Keyword.id == AdSnapshot.keyword_id)
            .where(AdDetail.advertiser_id.is_not(None))
            .where(Keyword.industry_id.is_not(None))
        )
        if excluded_channels:
            query = query.where(AdSnapshot.channel.notin_(list(excluded_channels)))

        rows = await session.execute(query)

        counts: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        for advertiser_id, industry_id in rows.all():
            counts[int(advertiser_id)][int(industry_id)] += 1

        dominant: dict[int, int] = {}
        for advertiser_id, industry_counts in counts.items():
            dominant[advertiser_id] = max(industry_counts.items(), key=lambda kv: kv[1])[0]

        if not dominant:
            return 0

        advertisers = (
            await session.execute(
                select(Advertiser).where(
                    Advertiser.id.in_(list(dominant.keys())),
                    Advertiser.industry_id.is_(None),
                )
            )
        ).scalars().all()

        updated = 0
        for adv in advertisers:
            new_industry = dominant.get(adv.id)
            if new_industry is None:
                continue
            adv.industry_id = new_industry
            updated += 1

        await session.commit()
        return updated


async def _collect_aggregates(
    excluded_channels: set[str] | None = None,
) -> dict[tuple[int, str], CampaignAggregate]:
    """Collect per-(advertiser, channel) aggregates.

    Grouping key: (advertiser_id, channel) — 동일 광고주의 동일 채널 소재는
    하나의 캠페인으로 합산. keyword_id는 가장 빈번한 것을 대표값으로 저장.
    """
    async with async_session() as session:
        query = (
            select(
                AdDetail.advertiser_id,
                AdSnapshot.keyword_id,
                AdSnapshot.channel,
                AdSnapshot.id,
                AdSnapshot.captured_at,
                AdDetail.position,
                AdDetail.position_zone,
                AdDetail.is_inhouse,
                AdDetail.ad_placement,
                AdDetail.is_contact,
                AdDetail.extra_data,
                AdDetail.seen_count,
                AdDetail.first_seen_at,
                AdDetail.last_seen_at,
            )
            .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
            .where(AdDetail.advertiser_id.is_not(None))
            # URL 필수: 광고주 URL 없는 소재는 캠페인 집계에서 제외
            .where(AdDetail.url.is_not(None))
            .where(AdDetail.url != "")
        )
        if excluded_channels:
            query = query.where(AdSnapshot.channel.notin_(list(excluded_channels)))

        rows = await session.execute(query)

        aggregates: dict[tuple[int, str], CampaignAggregate] = {}
        keyword_counts: dict[tuple[int, str], dict[int, int]] = {}  # track dominant keyword
        for row in rows.all():
            advertiser_id, keyword_id, channel, snapshot_id, captured_at, position, \
                position_zone, is_inhouse, ad_placement, is_contact, extra_data, \
                seen_count, first_seen_at, last_seen_at = row
            key = (int(advertiser_id), str(channel))
            agg = aggregates.get(key)
            if agg is None:
                agg = CampaignAggregate()
                aggregates[key] = agg
                keyword_counts[key] = {}

            # Track keyword frequency for dominant keyword selection
            if keyword_id is not None:
                kw_id = int(keyword_id)
                keyword_counts[key][kw_id] = keyword_counts[key].get(kw_id, 0) + 1

            # Use seen_count to reflect true observation frequency (post-dedup)
            effective_count = max(1, seen_count or 1)
            agg.ad_occurrences += effective_count
            agg.snapshot_ids.add(int(snapshot_id))
            # Use dedup-tracked timestamps if available, fallback to snapshot captured_at
            effective_first = first_seen_at or captured_at
            effective_last = last_seen_at or captured_at
            agg.first_seen = effective_first if agg.first_seen is None else min(agg.first_seen, effective_first)
            agg.last_seen = effective_last if agg.last_seen is None else max(agg.last_seen, effective_last)

            if ad_placement:
                agg.placements.add(str(ad_placement))
            if is_inhouse:
                agg.has_inhouse = True
            if is_contact:
                agg.has_contact = True
            # YouTube view_count from extra_data
            # 최근 30일 내 업로드 + 10만회 초과 영상만 광고비 계산 대상
            if isinstance(extra_data, dict):
                vc = extra_data.get("view_count")
                if isinstance(vc, (int, float)) and vc > 0:
                    vc_int = int(vc)
                    if vc_int > agg.max_view_count:
                        agg.max_view_count = vc_int
                    # 최근 30일 내 업로드된 10만회+ 영상만 광고비 추정에 사용
                    if vc_int >= 100_000:
                        upload_date_str = extra_data.get("upload_date", "")
                        is_recent = False
                        if upload_date_str:
                            try:
                                from datetime import datetime as _dt
                                ud = _dt.strptime(str(upload_date_str)[:8], "%Y%m%d")
                                is_recent = (_dt.utcnow() - ud).days <= 30
                            except (ValueError, TypeError):
                                is_recent = False
                        if is_recent:
                            agg.total_view_count += vc_int
                            agg.view_count_sources += 1

            # Distribute ad_hits across observed date range (dedup-aware)
            start_date = (first_seen_at or captured_at).date()
            end_date = (last_seen_at or captured_at).date()
            active_days_range = max(1, (end_date - start_date).days + 1)
            hits_per_day = max(1, effective_count // active_days_range)

            from datetime import timedelta
            current_day = start_date
            while current_day <= end_date:
                day_agg = agg.by_day.get(current_day)
                if day_agg is None:
                    day_agg = DayAggregate()
                    agg.by_day[current_day] = day_agg
                day_agg.ad_hits += hits_per_day
                if position is not None and position > 0:
                    day_agg.positions.append(int(position))
                if position_zone:
                    day_agg.position_zones.append(str(position_zone))
                if is_inhouse:
                    day_agg.inhouse_count += 1
                current_day += timedelta(days=1)

        return aggregates, keyword_counts


# ── Channel ↔ Stealth network mapping ──
_CHANNEL_TO_STEALTH_NETWORK = {
    "youtube_ads": "youtube",
    "youtube_surf": "youtube",
    "google_gdn": "gdn",
    "mobile_gdn": "gdn",
    "naver_da": "naver",
    "naver_search": "naver",
    "naver_shopping": "naver_shopping",
    "kakao_da": "kakao",
    "facebook": "meta",
    "instagram": "meta",
}

# Expected baseline contact rate per network (impressions per page visit)
# Calibrated from actual stealth data (2026-02 observations):
#   gdn:   ~0.37 imp/page (GDN ads on news sites, 50 req/imp normalization)
#   naver: ~0.12 imp/page (naver ads mostly on naver properties)
#   kakao: ~0.43 imp/page (kakao aggressive placement on daum/kakao sites)
#   meta:  ~0.06 imp/page (meta mostly in-app, rare on external news)
# Baselines set at "expected normal" → deviation = market intensity signal
_BASELINE_CONTACT_RATE = {
    "youtube": 0.50,
    "gdn": 0.30,
    "naver": 0.15,
    "naver_shopping": 0.20,
    "kakao": 0.25,
    "meta": 0.05,
}


async def _load_stealth_contact_multipliers(
    session,
) -> dict[str, float]:
    """페르소나 서프 접촉률 데이터에서 채널별 보정 계수 산출.

    로직:
    1. serpapi_ads에서 stealth_ 데이터를 네트워크별로 집계
    2. 네트워크별 평균 접촉률 계산 (REQUEST_TO_IMPRESSION 보정)
    3. 기대 접촉률 대비 비율 → 보정 계수 (0.8 ~ 1.4 클램핑)
    4. 채널 매핑하여 반환

    높은 접촉률 = 해당 네트워크 광고 시장 활발 = 광고비 높음
    """
    from sqlalchemy import text
    from datetime import timedelta

    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    # Request-to-impression normalization ratios
    # youtube: 인스트림 광고는 API 호출 많음 (ptracking, get_midroll_info 등)
    req_to_imp = {"gdn": 50.0, "naver": 6.0, "kakao": 6.0, "meta": 5.0, "youtube": 20.0, "naver_shopping": 4.0}
    pages_per_session = 26

    q = text("""
        SELECT
            json_extract(extra_data, '$.network') AS network,
            COUNT(*) AS raw_count,
            COUNT(DISTINCT SUBSTR(collected_at, 1, 16)) AS session_count
        FROM serpapi_ads
        WHERE advertiser_name LIKE 'stealth_%'
          AND collected_at >= :since
        GROUP BY json_extract(extra_data, '$.network')
    """)
    result = await session.execute(q, {"since": since_str})
    rows = result.fetchall()

    # 데이터 없는 채널에도 기본 보정 적용 (모든 매체 대상)
    # 기본값: 1.0 (데이터 없으면 변동 없음)
    _DEFAULT_CHANNEL_MULTIPLIERS: dict[str, float] = {
        "youtube_ads": 1.2,        # 유튜브 영상광고 시장 활발 (stealth 데이터 부족 보완)
        "youtube_surf": 1.2,
        "google_gdn": 1.1,
        "mobile_gdn": 1.1,
        "naver_da": 1.0,
        "naver_search": 1.0,
        "naver_shopping": 1.0,
        "kakao_da": 1.1,
        "facebook": 1.1,
        "instagram": 1.1,
        "google_search_ads": 1.05,  # 검색광고 기본 보정
        "tiktok_ads": 1.1,
    }

    if not rows:
        # stealth 데이터 없어도 기본값 반환
        return dict(_DEFAULT_CHANNEL_MULTIPLIERS)

    multipliers: dict[str, float] = dict(_DEFAULT_CHANNEL_MULTIPLIERS)
    MIN_STEALTH_ENTRIES = 50  # 최소 50건 이상이어야 신뢰 가능한 보정
    for row in rows:
        network = row[0]
        raw_count = row[1]
        session_count = max(row[2], 1)

        if network not in req_to_imp:
            continue
        # 데이터 부족 시 기본값 유지 (불안정한 보정 방지)
        if raw_count < MIN_STEALTH_ENTRIES:
            continue

        # Normalize: raw requests → estimated impressions
        impressions = raw_count / req_to_imp[network]
        # Contact rate = impressions per page visit
        contact_rate = impressions / (session_count * pages_per_session)

        baseline = _BASELINE_CONTACT_RATE.get(network, 1.0)
        if baseline <= 0:
            continue

        # Ratio: actual / expected → multiplier
        # Higher than baseline → market hotter → spend higher
        ratio = contact_rate / baseline
        # Clamp to 0.8 ~ 1.4 to avoid extreme swings
        multiplier = round(max(0.8, min(1.4, ratio)), 3)

        # Map network to all matching channels (stealth 데이터로 기본값 덮어쓰기)
        for channel, net in _CHANNEL_TO_STEALTH_NETWORK.items():
            if net == network:
                multipliers[channel] = multiplier

    return multipliers


async def _upsert_campaigns_and_spend(
    active_days: int = 7,
    excluded_channels: set[str] | None = None,
) -> tuple[int, int]:
    estimator_v2 = SpendEstimatorV2()
    now = datetime.now(UTC).replace(tzinfo=None)
    active_cutoff = now.timestamp() - (active_days * 24 * 60 * 60)

    result = await _collect_aggregates(excluded_channels=excluded_channels)
    if not result:
        return 0, 0
    aggregates, keyword_counts = result
    if not aggregates:
        return 0, 0

    async with async_session() as session:
        keywords = (await session.execute(select(Keyword))).scalars().all()
        keyword_map = {k.id: k for k in keywords}

        campaigns_query = select(Campaign)
        if excluded_channels:
            campaigns_query = campaigns_query.where(Campaign.channel.notin_(list(excluded_channels)))
        campaigns = (await session.execute(campaigns_query)).scalars().all()

        # Index by (advertiser_id, channel) — merge old keyword-based campaigns
        campaign_by_key: dict[tuple[int, str], Campaign] = {}
        duplicate_campaigns: list[Campaign] = []
        for campaign in campaigns:
            key = (campaign.advertiser_id, campaign.channel)
            if key in campaign_by_key:
                # Merge: keep earliest first_seen, latest last_seen, sum spend
                existing = campaign_by_key[key]
                if campaign.first_seen and (not existing.first_seen or campaign.first_seen < existing.first_seen):
                    existing.first_seen = campaign.first_seen
                if campaign.last_seen and (not existing.last_seen or campaign.last_seen > existing.last_seen):
                    existing.last_seen = campaign.last_seen
                existing.total_est_spend = (existing.total_est_spend or 0) + (campaign.total_est_spend or 0)
                existing.snapshot_count = (existing.snapshot_count or 0) + (campaign.snapshot_count or 0)
                duplicate_campaigns.append(campaign)
                continue
            campaign_by_key[key] = campaign

        # Reassign spend_estimates from duplicates before deleting
        for duplicate in duplicate_campaigns:
            key = (duplicate.advertiser_id, duplicate.channel)
            keeper = campaign_by_key[key]
            await session.execute(
                SpendEstimate.__table__.update()
                .where(SpendEstimate.campaign_id == duplicate.id)
                .values(campaign_id=keeper.id)
            )
            await session.delete(duplicate)

        touched_campaigns: list[Campaign] = []
        for key, agg in aggregates.items():
            advertiser_id, channel = key
            # Pick dominant keyword_id for this (advertiser, channel)
            kw_freqs = keyword_counts.get(key, {})
            dominant_keyword_id = max(kw_freqs, key=kw_freqs.get) if kw_freqs else None

            campaign = campaign_by_key.get(key)
            if campaign is None:
                # 캠페인명 자동 생성
                adv = await session.get(Advertiser, advertiser_id)
                first = agg.first_seen or now
                adv_name = adv.name if adv else "Unknown"
                auto_name = f"{adv_name} {first.month}월캠페인"

                campaign = Campaign(
                    advertiser_id=advertiser_id,
                    keyword_id=dominant_keyword_id,
                    channel=channel,
                    campaign_name=auto_name,
                    first_seen=first,
                    last_seen=agg.last_seen or now,
                    is_active=True,
                    total_est_spend=0.0,
                    snapshot_count=0,
                    channels=[channel],
                    extra_data={},
                    spend_category=_get_spend_category(channel),
                )
                session.add(campaign)
                campaign_by_key[key] = campaign

            campaign.keyword_id = dominant_keyword_id or campaign.keyword_id
            campaign.first_seen = agg.first_seen or campaign.first_seen
            campaign.last_seen = agg.last_seen or campaign.last_seen
            campaign.snapshot_count = len(agg.snapshot_ids)
            campaign.channels = [channel]
            campaign.is_active = campaign.last_seen.timestamp() >= active_cutoff
            # 기존 캠페인 중 이름이 없으면 자동 생성
            if not campaign.campaign_name:
                adv = await session.get(Advertiser, advertiser_id)
                adv_name = adv.name if adv else "Unknown"
                campaign.campaign_name = f"{adv_name} {campaign.first_seen.month}월캠페인"
            if not campaign.spend_category:
                campaign.spend_category = _get_spend_category(channel)
            campaign.extra_data = {
                "ad_occurrences": agg.ad_occurrences,
                "active_days_observed": len(agg.by_day),
            }

            # -- Campaign metadata fields --
            if not campaign.start_at:
                campaign.start_at = agg.first_seen
            campaign.end_at = agg.last_seen
            campaign.status = "active" if campaign.is_active else "completed"
            campaign.creative_ids = sorted(agg.snapshot_ids) if agg.snapshot_ids else None

            touched_campaigns.append(campaign)

        await session.flush()

        total_estimate_rows = 0
        for campaign in touched_campaigns:
            key = (campaign.advertiser_id, campaign.channel)
            agg = aggregates[key]

            await session.execute(delete(SpendEstimate).where(SpendEstimate.campaign_id == campaign.id))

            # campaign_total: 이 캠페인의 모든 일자별 est_daily_spend 합계 (KRW)
            campaign_total = 0.0
            for day, day_agg in agg.by_day.items():
                # 인하우스 여부
                is_day_inhouse = day_agg.inhouse_count > 0 and day_agg.inhouse_count >= day_agg.ad_hits

                ad_data = {
                    "keyword": "unknown",
                    "is_inhouse": is_day_inhouse or agg.has_inhouse,
                }
                frequency_data = {"ad_hits": day_agg.ad_hits}

                est = estimator_v2.estimate(
                    channel=campaign.channel,
                    ad_data=ad_data,
                    frequency_data=frequency_data,
                )

                est_daily_spend = est.est_daily_spend
                confidence = est.confidence

                session.add(
                    SpendEstimate(
                        campaign_id=campaign.id,
                        date=datetime.combine(day, time.min),
                        channel=campaign.channel,
                        est_daily_spend=est_daily_spend,
                        confidence=confidence,
                        calculation_method=est.calculation_method,
                        factors=est.factors,
                    )
                )
                total_estimate_rows += 1
                campaign_total += est_daily_spend

            # Campaign.total_est_spend: 30일 투영 추정 매체비 (KRW)
            # 관측일 기반 일평균을 구하여 30일로 투영
            observed_days = max(1, len(agg.by_day))
            avg_daily = campaign_total / observed_days if observed_days > 0 else 0
            campaign.total_est_spend = round(avg_daily * 30, 2)

        await session.commit()
        return len(touched_campaigns), total_estimate_rows


async def _merge_cross_channel_campaigns() -> int:
    """같은 광고주 + 같은 상품 → 크로스채널 캠페인 병합.

    그룹핑 규칙 (기초 DB 룰):
    - 동일 advertiser_id
    - 동일 product_name (정규화)
    → 채널 무관하게 하나의 캠페인으로 합침
    - campaign_name 자동 생성: "광고주명 N월캠페인"
    - model_info, promotion_copy 자동 수집
    """
    from datetime import UTC as _utc

    async with async_session() as session:
        # 1. 캠페인별 대표 product_name 조회 (가장 빈번한 것)
        product_rows = (await session.execute(
            select(
                AdDetail.advertiser_id,
                AdSnapshot.channel,
                AdDetail.product_name,
                func.count().label("cnt"),
            )
            .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
            .where(
                AdDetail.advertiser_id.is_not(None),
                AdDetail.product_name.is_not(None),
                AdDetail.product_name != "",
            )
            .group_by(AdDetail.advertiser_id, AdSnapshot.channel, AdDetail.product_name)
            .order_by(AdDetail.advertiser_id, AdSnapshot.channel, func.count().desc())
        )).all()

        dominant_product: dict[tuple[int, str], str] = {}
        for row in product_rows:
            key = (int(row[0]), str(row[1]))
            if key not in dominant_product:
                dominant_product[key] = row[2]

        # 2. 대표 model_name 조회
        model_rows = (await session.execute(
            select(
                AdDetail.advertiser_id,
                AdSnapshot.channel,
                AdDetail.model_name,
                func.count().label("cnt"),
            )
            .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
            .where(
                AdDetail.advertiser_id.is_not(None),
                AdDetail.model_name.is_not(None),
                AdDetail.model_name != "",
            )
            .group_by(AdDetail.advertiser_id, AdSnapshot.channel, AdDetail.model_name)
            .order_by(func.count().desc())
        )).all()

        dominant_model: dict[tuple[int, str], str] = {}
        for row in model_rows:
            key = (int(row[0]), str(row[1]))
            if key not in dominant_model:
                dominant_model[key] = row[2]

        # 3. 대표 ad_text(카피) 조회
        copy_rows = (await session.execute(
            select(
                AdDetail.advertiser_id,
                AdSnapshot.channel,
                AdDetail.ad_text,
                func.count().label("cnt"),
            )
            .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
            .where(
                AdDetail.advertiser_id.is_not(None),
                AdDetail.ad_text.is_not(None),
                AdDetail.ad_text != "",
            )
            .group_by(AdDetail.advertiser_id, AdSnapshot.channel, AdDetail.ad_text)
            .order_by(func.count().desc())
        )).all()

        dominant_copy: dict[tuple[int, str], str] = {}
        for row in copy_rows:
            key = (int(row[0]), str(row[1]))
            if key not in dominant_copy:
                dominant_copy[key] = row[2]

        # 4. 전체 캠페인 로드
        campaigns = (await session.execute(
            select(Campaign).order_by(Campaign.advertiser_id)
        )).scalars().all()

        # 5. (advertiser_id, normalized_product) 기준 그룹핑
        groups: dict[tuple[int, str], list[Campaign]] = defaultdict(list)
        for c in campaigns:
            product = dominant_product.get((c.advertiser_id, c.channel))
            if not product and c.product_service:
                product = c.product_service
            norm_key = _normalize_name(product) if product else "default"
            groups[(c.advertiser_id, norm_key)].append(c)

        # 6. 병합 실행
        merged_count = 0
        adv_cache: dict[int, Advertiser] = {}

        for (adv_id, product_key), group in groups.items():
            # 싱글 캠페인 → 메타데이터만 업데이트
            if len(group) == 1:
                c = group[0]
                if product_key != "default" and not c.product_service:
                    c.product_service = product_key
                model = dominant_model.get((c.advertiser_id, c.channel))
                if model and not c.model_info:
                    c.model_info = model
                copy = dominant_copy.get((c.advertiser_id, c.channel))
                if copy and not c.promotion_copy:
                    c.promotion_copy = copy[:200]
                # 캠페인명 자동 생성 (수동 편집 보호)
                if not c.campaign_name or c.enrichment_status != "manual_override":
                    if adv_id not in adv_cache:
                        adv_cache[adv_id] = await session.get(Advertiser, adv_id)
                    adv = adv_cache[adv_id]
                    if adv and c.first_seen:
                        c.campaign_name = f"{adv.name} {c.first_seen.month}월캠페인"
                continue

            # product 없는 그룹은 병합하지 않음 (오병합 방지)
            if product_key == "default":
                continue

            # 데이터 가장 많은 캠페인을 keeper로 선택
            group.sort(key=lambda c: (c.snapshot_count or 0), reverse=True)
            keeper = group[0]

            # 전체 채널/메타데이터 수집
            all_channels = set()
            all_models = set()
            all_copies = set()
            total_spend = 0.0
            total_snapshots = 0
            earliest = keeper.first_seen
            latest = keeper.last_seen

            for c in group:
                if c.channels:
                    all_channels.update(c.channels)
                elif c.channel:
                    all_channels.add(c.channel)
                total_spend += (c.total_est_spend or 0)
                total_snapshots += (c.snapshot_count or 0)
                if c.first_seen and (not earliest or c.first_seen < earliest):
                    earliest = c.first_seen
                if c.last_seen and (not latest or c.last_seen > latest):
                    latest = c.last_seen
                m = dominant_model.get((c.advertiser_id, c.channel))
                if m:
                    all_models.add(m)
                cp = dominant_copy.get((c.advertiser_id, c.channel))
                if cp:
                    all_copies.add(cp[:100])

            # keeper 업데이트
            keeper.channels = sorted(all_channels)
            keeper.first_seen = earliest
            keeper.last_seen = latest
            keeper.start_at = earliest
            keeper.end_at = latest
            keeper.snapshot_count = total_snapshots
            keeper.total_est_spend = total_spend
            keeper.product_service = product_key
            if all_models:
                keeper.model_info = ", ".join(sorted(all_models))
            if all_copies:
                keeper.promotion_copy = sorted(all_copies, key=len)[-1][:200]

            # 캠페인명 자동 생성
            if not keeper.campaign_name or keeper.enrichment_status != "manual_override":
                if adv_id not in adv_cache:
                    adv_cache[adv_id] = await session.get(Advertiser, adv_id)
                adv = adv_cache[adv_id]
                month = earliest.month if earliest else datetime.now(_utc).month
                adv_name = adv.name if adv else "Unknown"
                keeper.campaign_name = f"{adv_name} {month}월캠페인"

            # 피병합 캠페인의 SpendEstimate/JourneyEvent/CampaignLift 재배정 후 삭제
            for c in group[1:]:
                await session.execute(
                    SpendEstimate.__table__.update()
                    .where(SpendEstimate.campaign_id == c.id)
                    .values(campaign_id=keeper.id)
                )
                try:
                    from database.models import JourneyEvent
                    await session.execute(
                        JourneyEvent.__table__.update()
                        .where(JourneyEvent.campaign_id == c.id)
                        .values(campaign_id=keeper.id)
                    )
                except Exception:
                    pass
                try:
                    from database.models import CampaignLift
                    await session.execute(
                        CampaignLift.__table__.update()
                        .where(CampaignLift.campaign_id == c.id)
                        .values(campaign_id=keeper.id)
                    )
                except Exception:
                    pass
                await session.delete(c)
                merged_count += 1

        await session.commit()
        return merged_count


async def _counts() -> tuple[int, int]:
    async with async_session() as session:
        campaign_count = (await session.execute(select(func.count(Campaign.id)))).scalar_one()
        estimate_count = (await session.execute(select(func.count(SpendEstimate.id)))).scalar_one()
        return int(campaign_count or 0), int(estimate_count or 0)


async def rebuild_campaigns_and_spend(active_days: int = 30) -> dict[str, int]:
    """Rebuild campaign and spend tables and return execution stats."""
    excluded_channels = _parse_excluded_channels(
        os.getenv("CAMPAIGN_EXCLUDED_CHANNELS"),
        default=DEFAULT_EXCLUDED_CHANNELS,
    )
    await _delete_excluded_campaign_data(excluded_channels)
    # Clean advertiser names (strip ad copy, merge duplicates)
    from processor.advertiser_name_cleaner import clean_advertiser_names
    name_clean_stats = await clean_advertiser_names()
    linked, created = await _backfill_advertiser_ids()
    industry_backfilled = await _backfill_advertiser_industries(excluded_channels=excluded_channels)
    updated_campaigns, inserted_estimates = await _upsert_campaigns_and_spend(
        active_days=active_days,
        excluded_channels=excluded_channels,
    )

    # 크로스채널 캠페인 병합: 같은 광고주 + 같은 상품 → 하나의 캠페인
    merged = await _merge_cross_channel_campaigns()

    campaign_total, spend_estimates_total = await _counts()

    result = {
        "names_cleaned": name_clean_stats.get("cleaned", 0) + name_clean_stats.get("merged", 0),
        "linked_details": linked,
        "created_advertisers": created,
        "industry_backfilled": industry_backfilled,
        "updated_campaigns": updated_campaigns,
        "inserted_estimates": inserted_estimates,
        "merged_campaigns": merged,
        "campaigns_total": campaign_total,
        "spend_estimates_total": spend_estimates_total,
    }

    # SSE 이벤트 발행
    try:
        from api.event_bus import event_bus
        await event_bus.publish("campaign_rebuilt", {
            "campaigns": campaign_total,
            "spend_estimates": spend_estimates_total,
        })
    except Exception:
        pass

    return result
