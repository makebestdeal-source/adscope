"""Verification quality gate helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select

from database import async_session
from database.models import AdDetail, AdSnapshot


@dataclass(frozen=True)
class VerificationRule:
    min_total: int = 1
    min_coverage: float = 0.0
    min_verified: float = 0.0


@dataclass
class ChannelVerificationStats:
    channel: str
    total: int = 0
    verified: int = 0
    likely_verified: int = 0
    unverified: int = 0
    unknown: int = 0
    missing: int = 0

    @property
    def coverage_ratio(self) -> float:
        if self.total <= 0:
            return 0.0
        covered = self.verified + self.likely_verified + self.unverified
        return covered / self.total

    @property
    def verified_ratio(self) -> float:
        if self.total <= 0:
            return 0.0
        return self.verified / self.total


def parse_channels(raw: str | None) -> list[str]:
    if raw is None or not raw.strip():
        return []
    return [chunk.strip() for chunk in raw.split(",") if chunk.strip()]


def parse_channel_rules(raw: str | None) -> dict[str, VerificationRule]:
    """Parse 'channel:min_coverage:min_verified[:min_total]' entries."""
    out: dict[str, VerificationRule] = {}
    if raw is None or not raw.strip():
        return out

    for chunk in raw.split(","):
        entry = chunk.strip()
        if not entry:
            continue
        parts = [p.strip() for p in entry.split(":")]
        if len(parts) < 3:
            continue
        channel = parts[0]
        try:
            min_coverage = float(parts[1])
            min_verified = float(parts[2])
            min_total = int(parts[3]) if len(parts) >= 4 else 1
        except Exception:
            continue

        out[channel] = VerificationRule(
            min_total=max(0, min_total),
            min_coverage=max(0.0, min(1.0, min_coverage)),
            min_verified=max(0.0, min(1.0, min_verified)),
        )
    return out


def _normalize_status(value: str | None) -> str:
    if value is None:
        return "missing"
    normalized = value.strip().lower()
    if not normalized:
        return "missing"
    if normalized in {"verified", "likely_verified", "unverified", "unknown"}:
        return normalized
    return "unknown"


async def collect_verification_stats(
    active_days: int = 7,
    channels: list[str] | None = None,
) -> dict[str, ChannelVerificationStats]:
    cutoff = datetime.utcnow() - timedelta(days=max(0, active_days))
    channel_set = set(channels or [])

    async with async_session() as session:
        query = (
            select(AdSnapshot.channel, AdDetail.verification_status)
            .join(AdDetail, AdDetail.snapshot_id == AdSnapshot.id)
            .where(AdSnapshot.captured_at >= cutoff)
        )
        if channel_set:
            query = query.where(AdSnapshot.channel.in_(list(channel_set)))

        rows = await session.execute(query)

    stats: dict[str, ChannelVerificationStats] = {}
    for channel, verification_status in rows.all():
        channel_name = str(channel)
        item = stats.get(channel_name)
        if item is None:
            item = ChannelVerificationStats(channel=channel_name)
            stats[channel_name] = item

        item.total += 1
        status = _normalize_status(verification_status)
        if status == "verified":
            item.verified += 1
        elif status == "likely_verified":
            item.likely_verified += 1
        elif status == "unverified":
            item.unverified += 1
        elif status == "unknown":
            item.unknown += 1
        else:
            item.missing += 1

    for channel in channel_set:
        stats.setdefault(channel, ChannelVerificationStats(channel=channel))

    return stats


def evaluate_verification_gate(
    stats_by_channel: dict[str, ChannelVerificationStats],
    default_rule: VerificationRule,
    channel_rules: dict[str, VerificationRule] | None = None,
) -> list[dict]:
    rules = channel_rules or {}
    report: list[dict] = []

    for channel in sorted(stats_by_channel.keys()):
        stats = stats_by_channel[channel]
        rule = rules.get(channel, default_rule)

        total_ok = stats.total >= rule.min_total
        coverage_ok = stats.coverage_ratio >= rule.min_coverage if stats.total > 0 else False
        verified_ok = stats.verified_ratio >= rule.min_verified if stats.total > 0 else False

        reasons: list[str] = []
        if not total_ok:
            reasons.append(f"min_total({rule.min_total}) not met")
        if stats.total > 0 and not coverage_ok:
            reasons.append(f"coverage<{rule.min_coverage:.2f}")
        if stats.total > 0 and not verified_ok:
            reasons.append(f"verified<{rule.min_verified:.2f}")

        report.append(
            {
                "channel": channel,
                "passed": total_ok and coverage_ok and verified_ok,
                "reasons": reasons,
                "total": stats.total,
                "verified": stats.verified,
                "likely_verified": stats.likely_verified,
                "unverified": stats.unverified,
                "unknown": stats.unknown,
                "missing": stats.missing,
                "coverage_ratio": stats.coverage_ratio,
                "verified_ratio": stats.verified_ratio,
                "rule": {
                    "min_total": rule.min_total,
                    "min_coverage": rule.min_coverage,
                    "min_verified": rule.min_verified,
                },
            }
        )

    return report
