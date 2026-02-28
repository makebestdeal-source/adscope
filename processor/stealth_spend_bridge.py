"""Stealth persona surf -> spend estimation bridge.

Connects stealth_persona_surf.py collection data (serpapi_ads with 'stealth_' prefix)
to the ad spend reverse-estimation pipeline.

Logic:
  1. Aggregate serpapi_ads stealth_ rows by network and persona
  2. Normalize raw network request counts to estimated ad impressions
     (a single ad slot fires many requests: JS, pixels, trackers)
  3. Calculate per-persona contact rates (impressions per surfing session)
  4. Convert contact rates to monthly spend estimates using network-specific
     CPM and estimated daily impressions
  5. Cross-check with existing spend_estimates for calibration factors

Network CPM and daily impression assumptions (Korean market):
  - GDN:       CPM 2,000 x 1,000,000 daily impressions
  - Naver DA:  CPM 3,000 x   500,000 daily impressions
  - Kakao DA:  CPM 2,500 x   300,000 daily impressions
  - Meta:      CPM 5,000 x   800,000 daily impressions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from processor.spend_reverse_estimator import REAL_EXECUTION_BENCHMARKS

logger = logging.getLogger(__name__)

# ── Request-to-impression normalization ──
# A single ad impression (one visible ad slot) generates many network requests:
#   GDN: ~50 requests per impression (gpt.js, pubads, syndication, activeview, pixels)
#   Naver: ~6 requests per impression (veta openrtb, nbimp, nbackimp)
#   Kakao: ~6 requests per impression (adfit SDK, impression, click tracker)
#   Meta: ~5 requests per impression (tr pixel, connect.facebook.net, SDK)
# These ratios convert raw request counts to estimated visible ad impressions.
REQUEST_TO_IMPRESSION_RATIO: dict[str, float] = {
    "youtube": 8.0,  # player API + stats/ads + ptracking per ad
    "gdn": 50.0,
    "naver": 6.0,
    "naver_shopping": 3.0,  # ad.search.naver.com per ad
    "kakao": 6.0,
    "meta": 5.0,
}

# ── Articles visited per surfing session ──
# stealth_persona_surf visits ~13 sources (8 news + 5 publisher) x 2 articles each = ~26 pages
# Each page may have multiple ad slots. This normalizes to "ad impressions per page visit".
PAGES_PER_SESSION = 26

# ── Network-level CPM and daily impression parameters ──
# CPM = cost per 1,000 impressions (KRW)
# daily_impressions = estimated total daily ad impressions on that network (Korean market)
NETWORK_PARAMS: dict[str, dict] = {
    "youtube": {
        "cpm": 7_000,  # YouTube CPV 50원 × VTR 14% ≈ CPM 7,000
        "daily_impressions": 2_000_000,
        "benchmark_key": "google",
        "channel_name": "youtube_surf",
    },
    "gdn": {
        "cpm": 2_000,
        "daily_impressions": 1_000_000,
        "benchmark_key": "google",
        "channel_name": "google_gdn",
    },
    "naver": {
        "cpm": 3_000,
        "daily_impressions": 500_000,
        "benchmark_key": "naver_gfa",
        "channel_name": "naver_da",
    },
    "naver_shopping": {
        "cpm": 4_000,  # 쇼핑검색 CPC 300원 × CTR 7.5% ≈ CPM 4,000
        "daily_impressions": 300_000,
        "benchmark_key": "naver_gfa",
        "channel_name": "naver_shopping",
    },
    "kakao": {
        "cpm": 2_500,
        "daily_impressions": 300_000,
        "benchmark_key": "kakao",
        "channel_name": "kakao_da",
    },
    "meta": {
        "cpm": 5_000,
        "daily_impressions": 800_000,
        "benchmark_key": "meta",
        "channel_name": "facebook",
    },
}

# All 12 target personas (10-60대 남녀)
ALL_PERSONAS = ["M10", "F10", "M20", "F20", "M30", "F30", "M40", "F40", "M50", "F50", "M60", "F60"]

PERIOD_DAYS = 30


@dataclass
class StealthContactRate:
    """Per-network, per-persona contact rate result."""

    network: str
    persona: str
    raw_request_count: int
    estimated_impressions: float  # after normalization
    session_count: int
    contact_rate: float  # estimated impressions per page visit


@dataclass
class StealthSpendEstimate:
    """Network-level spend estimate derived from stealth contact rates."""

    network: str
    channel_name: str
    avg_contact_rate: float
    est_monthly_media_cost: float
    est_monthly_total_spend: float
    confidence: float
    persona_breakdown: dict[str, float] = field(default_factory=dict)
    factors: dict = field(default_factory=dict)


@dataclass
class CalibrationResult:
    """Cross-check result between stealth estimate and existing spend_estimates."""

    network: str
    channel_name: str
    stealth_monthly: float
    existing_monthly: float
    calibration_factor: float  # existing / stealth (>1 means stealth underestimates)
    sample_campaigns: int


# ──────────────────────────────────────────────────────────────────────
# 1. Calculate stealth contact rates
# ──────────────────────────────────────────────────────────────────────

async def calculate_stealth_contact_rates(
    db: AsyncSession,
    days: int = PERIOD_DAYS,
) -> dict:
    """Aggregate stealth_ data from serpapi_ads by network and persona.

    Returns:
        {
            "rates": [StealthContactRate, ...],
            "summary": {network: {persona: contact_rate, ...}, ...},
            "total_ads": int,
            "session_count_by_persona": {persona: int, ...},
        }
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    # Query stealth rows grouped by network and persona
    # We use json_extract since extra_data is stored as JSON text
    q = text("""
        SELECT
            json_extract(extra_data, '$.network') AS network,
            json_extract(extra_data, '$.persona') AS persona,
            COUNT(*) AS contact_count,
            COUNT(DISTINCT SUBSTR(collected_at, 1, 16)) AS session_count
        FROM serpapi_ads
        WHERE advertiser_name LIKE 'stealth_%'
          AND collected_at >= :since
        GROUP BY
            json_extract(extra_data, '$.network'),
            json_extract(extra_data, '$.persona')
        ORDER BY network, persona
    """)

    result = await db.execute(q, {"since": since_str})
    rows = result.fetchall()

    rates: list[StealthContactRate] = []
    summary: dict[str, dict[str, float]] = {}
    session_counts: dict[str, int] = {}
    total_raw = 0
    total_normalized = 0.0

    for row in rows:
        network = row[0]
        persona = row[1]
        raw_count = row[2]
        session_count = max(row[3], 1)  # at least 1 session

        total_raw += raw_count

        # Normalize: raw requests -> estimated ad impressions
        ratio = REQUEST_TO_IMPRESSION_RATIO.get(network, 10.0)
        estimated_impressions = raw_count / ratio
        total_normalized += estimated_impressions

        # Contact rate = estimated impressions per page visit in the session
        total_pages = session_count * PAGES_PER_SESSION
        contact_rate = round(estimated_impressions / total_pages, 4)

        rates.append(StealthContactRate(
            network=network,
            persona=persona,
            raw_request_count=raw_count,
            estimated_impressions=round(estimated_impressions, 2),
            session_count=session_count,
            contact_rate=contact_rate,
        ))

        if network not in summary:
            summary[network] = {}
        summary[network][persona] = contact_rate

        # Track total sessions per persona (max across networks since they share sessions)
        if persona not in session_counts or session_count > session_counts[persona]:
            session_counts[persona] = session_count

    logger.info(
        "[stealth_bridge] contact rates: %d rows, %d raw requests -> %.0f normalized impressions, %d networks",
        len(rates), total_raw, total_normalized, len(summary),
    )

    return {
        "rates": rates,
        "summary": summary,
        "total_raw_requests": total_raw,
        "total_estimated_impressions": round(total_normalized, 2),
        "session_count_by_persona": session_counts,
    }


# ──────────────────────────────────────────────────────────────────────
# 2. Estimate spend from contact rates
# ──────────────────────────────────────────────────────────────────────

async def estimate_spend_from_contacts(
    db: AsyncSession,
    days: int = PERIOD_DAYS,
) -> list[StealthSpendEstimate]:
    """Convert normalized stealth contact rates into monthly spend estimates.

    After normalization, contact_rate = estimated ad impressions per page visit.
    This represents the probability that a given page view shows an ad from
    the network's inventory.

    Formula per network:
        avg_contact_rate = mean(persona contact rates)  [impressions/page]
        daily_media_cost = avg_contact_rate * (CPM / 1000) * daily_impressions
        monthly_media_cost = daily_media_cost * 30
        monthly_total_spend = monthly_media_cost * total_multiplier

    Returns list of StealthSpendEstimate per network.
    """
    cr_data = await calculate_stealth_contact_rates(db, days=days)
    summary = cr_data["summary"]

    estimates: list[StealthSpendEstimate] = []

    for network, params in NETWORK_PARAMS.items():
        persona_rates = summary.get(network, {})
        if not persona_rates:
            continue

        # Average contact rate across all personas that have data
        all_rates = list(persona_rates.values())
        avg_rate = sum(all_rates) / len(all_rates) if all_rates else 0.0

        if avg_rate <= 0:
            continue

        cpm = params["cpm"]
        daily_imp = params["daily_impressions"]
        benchmark_key = params["benchmark_key"]
        channel_name = params["channel_name"]

        # daily_media_cost = contact_rate * (CPM / 1000) * daily_impressions
        # contact_rate represents probability of seeing the ad in one session.
        # If we assume the session represents a sample of the total ad inventory,
        # then: estimated_daily_spend = contact_rate * CPM_per_impression * total_daily_impressions
        daily_media_cost = avg_rate * (cpm / 1000.0) * daily_imp
        monthly_media_cost = daily_media_cost * 30

        # Apply total_multiplier (media cost -> total advertiser spend incl. agency fees)
        benchmark = REAL_EXECUTION_BENCHMARKS.get(benchmark_key, {})
        total_multiplier = benchmark.get("total_multiplier", 1.20)
        monthly_total = monthly_media_cost * total_multiplier

        # Confidence is higher with more personas and higher contact rates
        persona_coverage = len(all_rates) / len(ALL_PERSONAS)
        base_confidence = 0.25 + (persona_coverage * 0.15)
        # Higher contact rates mean more reliable signal
        if avg_rate > 5.0:
            base_confidence += 0.10
        elif avg_rate > 2.0:
            base_confidence += 0.05
        confidence = min(0.65, base_confidence)

        est = StealthSpendEstimate(
            network=network,
            channel_name=channel_name,
            avg_contact_rate=round(avg_rate, 4),
            est_monthly_media_cost=round(monthly_media_cost, 0),
            est_monthly_total_spend=round(monthly_total, 0),
            confidence=round(confidence, 2),
            persona_breakdown={p: round(r, 4) for p, r in persona_rates.items()},
            factors={
                "cpm": cpm,
                "daily_impressions": daily_imp,
                "daily_media_cost": round(daily_media_cost, 0),
                "total_multiplier": total_multiplier,
                "benchmark_key": benchmark_key,
                "persona_count": len(all_rates),
                "request_to_impression_ratio": REQUEST_TO_IMPRESSION_RATIO.get(network, 10.0),
                "pages_per_session": PAGES_PER_SESSION,
                "method": "stealth_contact_reverse",
            },
        )
        estimates.append(est)

        logger.info(
            "[stealth_bridge] %s: avg_rate=%.4f, monthly_media=%s, monthly_total=%s",
            network, avg_rate,
            f"{monthly_media_cost:,.0f}",
            f"{monthly_total:,.0f}",
        )

    return estimates


# ──────────────────────────────────────────────────────────────────────
# 3. Calibrate with existing spend_estimates
# ──────────────────────────────────────────────────────────────────────

async def calibrate_with_existing_spend(
    db: AsyncSession,
    days: int = PERIOD_DAYS,
) -> dict:
    """Cross-check stealth estimates with existing spend_estimates table.

    Stealth estimates are market-level (total spend on the network as seen
    by our sample). Existing spend_estimates are per-advertiser sums. We
    compare the stealth market-level estimate with the DB aggregate to derive
    a calibration factor.

    Additionally computes per-advertiser average from existing data for
    a sanity check.

    Returns:
        {
            "calibrations": [CalibrationResult, ...],
            "stealth_estimates": [StealthSpendEstimate, ...],
            "recommended_factors": {network: factor, ...},
        }
    """
    stealth_estimates = await estimate_spend_from_contacts(db, days=days)

    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    calibrations: list[CalibrationResult] = []
    recommended_factors: dict[str, float] = {}

    for est in stealth_estimates:
        channel = est.channel_name

        # Sum existing spend_estimates for this channel in the period
        # Count campaigns and distinct advertisers
        q = text("""
            SELECT
                COALESCE(SUM(se.est_daily_spend), 0) AS total_daily,
                COUNT(DISTINCT se.campaign_id) AS campaign_count,
                COUNT(DISTINCT c.advertiser_id) AS advertiser_count
            FROM spend_estimates se
            JOIN campaigns c ON se.campaign_id = c.id
            WHERE se.channel = :channel
              AND se.date >= :since
        """)
        result = await db.execute(q, {"channel": channel, "since": since_str})
        row = result.fetchone()

        existing_total_daily = row[0] if row else 0
        campaign_count = row[1] if row else 0
        advertiser_count = row[2] if row else 0

        # Convert to monthly (existing data is daily spend summed over period)
        if existing_total_daily > 0:
            days_q = text("""
                SELECT COUNT(DISTINCT DATE(se.date))
                FROM spend_estimates se
                WHERE se.channel = :channel
                  AND se.date >= :since
            """)
            days_result = await db.execute(days_q, {"channel": channel, "since": since_str})
            actual_days = days_result.scalar() or 1
            existing_monthly = (existing_total_daily / actual_days) * 30
        else:
            existing_monthly = 0

        stealth_monthly = est.est_monthly_total_spend

        # Calibration factor = existing_total / stealth_estimate
        # This tells us how our stealth sampling compares to the DB aggregate.
        # A factor > 1 means stealth underestimates (our sample sees fewer ads
        # than the total spend implies). This is normal since stealth captures
        # only what one persona sees, not all advertisers.
        if stealth_monthly > 0 and existing_monthly > 0:
            factor = round(existing_monthly / stealth_monthly, 4)
        elif stealth_monthly > 0:
            factor = 0.0  # No existing data to compare
        else:
            factor = 1.0

        # Clamp to reasonable range
        clamped_factor = max(0.1, min(50.0, factor)) if factor > 0 else 0.0

        cal = CalibrationResult(
            network=est.network,
            channel_name=channel,
            stealth_monthly=round(stealth_monthly, 0),
            existing_monthly=round(existing_monthly, 0),
            calibration_factor=clamped_factor,
            sample_campaigns=campaign_count,
        )
        calibrations.append(cal)

        if clamped_factor > 0:
            recommended_factors[est.network] = clamped_factor

        per_adv_avg = (
            round(existing_monthly / advertiser_count, 0)
            if advertiser_count > 0 else 0
        )
        logger.info(
            "[stealth_bridge] calibration %s: stealth=%s, existing=%s (avg/adv=%s, %d advs), factor=%.4f (%d campaigns)",
            channel,
            f"{stealth_monthly:,.0f}",
            f"{existing_monthly:,.0f}",
            f"{per_adv_avg:,.0f}",
            advertiser_count,
            clamped_factor,
            campaign_count,
        )

    return {
        "calibrations": calibrations,
        "stealth_estimates": stealth_estimates,
        "recommended_factors": recommended_factors,
    }


# ──────────────────────────────────────────────────────────────────────
# Convenience: run all steps and return a combined report
# ──────────────────────────────────────────────────────────────────────

async def generate_stealth_spend_report(
    db: AsyncSession | None = None,
    days: int = PERIOD_DAYS,
) -> dict:
    """Full pipeline: contact rates -> spend estimation -> calibration.

    Can be called from scheduler or API endpoint.

    Returns JSON-serializable dict:
        {
            "generated_at": str,
            "period_days": int,
            "contact_rates": {...},
            "estimates": [...],
            "calibrations": [...],
            "recommended_factors": {...},
        }
    """
    own_session = db is None
    if own_session:
        db = async_session()

    try:
        # Step 1: Contact rates
        cr_data = await calculate_stealth_contact_rates(db, days=days)

        # Step 2+3: Estimates + calibration
        cal_data = await calibrate_with_existing_spend(db, days=days)

        # Serialize dataclasses for JSON output
        def _serialize_estimate(e: StealthSpendEstimate) -> dict:
            return {
                "network": e.network,
                "channel_name": e.channel_name,
                "avg_contact_rate": e.avg_contact_rate,
                "est_monthly_media_cost": e.est_monthly_media_cost,
                "est_monthly_total_spend": e.est_monthly_total_spend,
                "confidence": e.confidence,
                "persona_breakdown": e.persona_breakdown,
                "factors": e.factors,
            }

        def _serialize_calibration(c: CalibrationResult) -> dict:
            return {
                "network": c.network,
                "channel_name": c.channel_name,
                "stealth_monthly": c.stealth_monthly,
                "existing_monthly": c.existing_monthly,
                "calibration_factor": c.calibration_factor,
                "sample_campaigns": c.sample_campaigns,
            }

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period_days": days,
            "contact_rates": {
                "total_raw_requests": cr_data["total_raw_requests"],
                "total_estimated_impressions": cr_data["total_estimated_impressions"],
                "session_count_by_persona": cr_data["session_count_by_persona"],
                "normalization_ratios": REQUEST_TO_IMPRESSION_RATIO,
                "pages_per_session": PAGES_PER_SESSION,
                "summary": cr_data["summary"],
            },
            "estimates": [_serialize_estimate(e) for e in cal_data["stealth_estimates"]],
            "calibrations": [_serialize_calibration(c) for c in cal_data["calibrations"]],
            "recommended_factors": cal_data["recommended_factors"],
        }

        logger.info(
            "[stealth_bridge] report generated: %d networks, %d calibrations",
            len(report["estimates"]),
            len(report["calibrations"]),
        )

        return report

    finally:
        if own_session:
            await db.close()


# ──────────────────────────────────────────────────────────────────────
# Standalone CLI execution
# ──────────────────────────────────────────────────────────────────────

async def _main():
    """Run the full pipeline and print results."""
    import sys
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    async with async_session() as db:
        report = await generate_stealth_spend_report(db)

    print("=== Stealth Spend Bridge Report ===")
    print(f"Period: {report['period_days']} days")
    cr = report["contact_rates"]
    print(f"Raw requests: {cr['total_raw_requests']}")
    print(f"Estimated impressions: {cr['total_estimated_impressions']:.0f}")
    print(f"Normalization: {cr['normalization_ratios']}")
    print()

    print("-- Contact Rate Summary --")
    for net, personas in report["contact_rates"]["summary"].items():
        rates_str = ", ".join(f"{p}:{r:.2f}" for p, r in sorted(personas.items()))
        print(f"  {net}: {rates_str}")
    print()

    print("-- Spend Estimates --")
    for e in report["estimates"]:
        print(
            f"  {e['network']:>8}: "
            f"media={e['est_monthly_media_cost']:>14,.0f} KRW  "
            f"total={e['est_monthly_total_spend']:>14,.0f} KRW  "
            f"(rate={e['avg_contact_rate']:.4f}, conf={e['confidence']:.2f})"
        )
    print()

    print("-- Calibration vs Existing --")
    for c in report["calibrations"]:
        print(
            f"  {c['network']:>8}: "
            f"stealth={c['stealth_monthly']:>14,.0f}  "
            f"existing={c['existing_monthly']:>14,.0f}  "
            f"factor={c['calibration_factor']:.4f}  "
            f"({c['sample_campaigns']} campaigns)"
        )
    print()

    if report["recommended_factors"]:
        print("-- Recommended Calibration Factors --")
        for net, factor in report["recommended_factors"].items():
            print(f"  {net}: {factor:.4f}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(_main())
