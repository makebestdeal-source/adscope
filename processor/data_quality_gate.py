"""Operational data quality gate helpers.

This gate checks whether recent collected ads are fit for downstream
campaign/spend calculation and deployment.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import os
from pathlib import Path
import sqlite3

from processor.advertiser_verifier import NON_AD_ELEMENTS
from processor.channel_utils import requires_creative_asset
from processor.entity_label_quality import LabelQuality, validate_entity_label, validate_material_text


_GENERIC_ADVERTISER_NAMES = {
    str(name).strip().lower() for name in NON_AD_ELEMENTS if str(name).strip()
}


@dataclass(frozen=True)
class QualityRule:
    min_total: int = 1
    max_missing_url_ratio: float = 0.0
    max_generic_advertiser_ratio: float = 0.02
    max_invalid_label_ratio: float = 0.0
    max_missing_creative_ratio: float = 0.05
    max_missing_asset_ratio: float = 0.05


@dataclass
class ChannelQualityStats:
    channel: str
    total: int = 0
    missing_url: int = 0
    missing_advertiser: int = 0
    generic_advertiser: int = 0
    invalid_label: int = 0
    missing_creative: int = 0
    missing_asset: int = 0

    @property
    def missing_url_ratio(self) -> float:
        return _ratio(self.missing_url, self.total)

    @property
    def generic_advertiser_ratio(self) -> float:
        return _ratio(self.generic_advertiser, self.total)

    @property
    def invalid_label_ratio(self) -> float:
        return _ratio(self.invalid_label, self.total)

    @property
    def missing_creative_ratio(self) -> float:
        return _ratio(self.missing_creative, self.total)

    @property
    def missing_asset_ratio(self) -> float:
        return _ratio(self.missing_asset, self.total)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def parse_channels(raw: str | None) -> list[str]:
    if raw is None or not raw.strip():
        return []
    return [chunk.strip() for chunk in raw.split(",") if chunk.strip()]


def parse_channel_rules(raw: str | None) -> dict[str, QualityRule]:
    """Parse channel rules.

    Format:
    channel:max_missing_url:max_generic_adv:max_missing_creative:max_missing_asset[:min_total[:max_invalid_label]]
    """
    out: dict[str, QualityRule] = {}
    if raw is None or not raw.strip():
        return out

    for chunk in raw.split(","):
        entry = chunk.strip()
        if not entry:
            continue
        parts = [part.strip() for part in entry.split(":")]
        if len(parts) < 5:
            continue
        try:
            min_total = int(parts[5]) if len(parts) >= 6 else 1
            max_invalid = float(parts[6]) if len(parts) >= 7 else 0.0
            out[parts[0]] = QualityRule(
                min_total=max(0, min_total),
                max_missing_url_ratio=max(0.0, min(1.0, float(parts[1]))),
                max_generic_advertiser_ratio=max(0.0, min(1.0, float(parts[2]))),
                max_invalid_label_ratio=max(0.0, min(1.0, max_invalid)),
                max_missing_creative_ratio=max(0.0, min(1.0, float(parts[3]))),
                max_missing_asset_ratio=max(0.0, min(1.0, float(parts[4]))),
            )
        except Exception:
            continue
    return out


def _normalize_image_path(path: str | None, image_store_dir: str) -> str | None:
    if not path:
        return None
    candidate = str(path).replace("\\", "/")
    if os.path.exists(candidate):
        return candidate
    if candidate.startswith("/images/"):
        resolved = os.path.join(image_store_dir, candidate[len("/images/"):])
        if os.path.exists(resolved):
            return resolved
    if candidate.startswith("stored_images/"):
        resolved = os.path.join(image_store_dir, candidate[len("stored_images/"):])
        if os.path.exists(resolved):
            return candidate
    return None


def _valid_url(url: str | None) -> bool:
    if not url:
        return False
    stripped = str(url).strip()
    return stripped.startswith(("http://", "https://"))


def collect_quality_stats(
    db_path: str | Path,
    active_days: int = 30,
    channels: list[str] | None = None,
    image_store_dir: str = "stored_images",
) -> dict[str, ChannelQualityStats]:
    cutoff = datetime.utcnow() - timedelta(days=max(0, active_days))
    channel_set = set(channels or [])

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        query = """
            SELECT
                s.channel AS channel,
                d.advertiser_name_raw AS advertiser_name_raw,
                a.name AS advertiser_name,
                d.url AS url,
                d.ad_text AS ad_text,
                d.creative_image_path AS creative_image_path
            FROM ad_details d
            JOIN ad_snapshots s ON s.id = d.snapshot_id
            LEFT JOIN advertisers a ON a.id = d.advertiser_id
            WHERE s.captured_at >= ?
              AND (d.verification_status IS NULL OR d.verification_status != 'rejected')
        """
        params: list[object] = [cutoff.isoformat(sep=" ")]
        if channel_set:
            placeholders = ",".join("?" for _ in channel_set)
            query += f" AND s.channel IN ({placeholders})"
            params.extend(sorted(channel_set))

        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    stats: dict[str, ChannelQualityStats] = {}
    for row in rows:
        channel = str(row["channel"])
        item = stats.get(channel)
        if item is None:
            item = ChannelQualityStats(channel=channel)
            stats[channel] = item

        item.total += 1

        raw_name = (row["advertiser_name_raw"] or "").strip()
        canonical_name = (row["advertiser_name"] or "").strip()
        effective_name = canonical_name or raw_name
        if not raw_name:
            item.missing_advertiser += 1
        if effective_name.lower() in _GENERIC_ADVERTISER_NAMES:
            item.generic_advertiser += 1
        if (
            effective_name
            and validate_entity_label(effective_name, field="advertiser", channel=channel).quality
            == LabelQuality.INVALID
        ):
            item.invalid_label += 1
        ad_text = (row["ad_text"] or "").strip()
        if ad_text and validate_material_text(ad_text).quality == LabelQuality.INVALID:
            item.invalid_label += 1

        if not _valid_url(row["url"]):
            item.missing_url += 1

        if requires_creative_asset(channel):
            creative_path = (row["creative_image_path"] or "").strip()
            if not creative_path:
                item.missing_creative += 1
            elif _normalize_image_path(creative_path, image_store_dir) is None:
                item.missing_asset += 1

    for channel in channel_set:
        stats.setdefault(channel, ChannelQualityStats(channel=channel))

    return stats


def evaluate_quality_gate(
    stats_by_channel: dict[str, ChannelQualityStats],
    default_rule: QualityRule,
    channel_rules: dict[str, QualityRule] | None = None,
) -> list[dict]:
    rules = channel_rules or {}
    report: list[dict] = []

    for channel in sorted(stats_by_channel.keys()):
        stats = stats_by_channel[channel]
        rule = rules.get(channel, default_rule)

        total_ok = stats.total >= rule.min_total
        url_ok = stats.missing_url_ratio <= rule.max_missing_url_ratio if stats.total > 0 else False
        advertiser_ok = (
            stats.generic_advertiser_ratio <= rule.max_generic_advertiser_ratio if stats.total > 0 else False
        )
        label_ok = stats.invalid_label_ratio <= rule.max_invalid_label_ratio if stats.total > 0 else False

        creative_ok = True
        asset_ok = True
        if requires_creative_asset(channel):
            creative_ok = stats.missing_creative_ratio <= rule.max_missing_creative_ratio if stats.total > 0 else False
            asset_ok = stats.missing_asset_ratio <= rule.max_missing_asset_ratio if stats.total > 0 else False

        reasons: list[str] = []
        if not total_ok:
            reasons.append(f"min_total({rule.min_total}) not met")
        if stats.total > 0 and not url_ok:
            reasons.append(f"missing_url>{rule.max_missing_url_ratio:.2f}")
        if stats.total > 0 and not advertiser_ok:
            reasons.append(f"generic_advertiser>{rule.max_generic_advertiser_ratio:.2f}")
        if stats.total > 0 and not label_ok:
            reasons.append(f"invalid_label>{rule.max_invalid_label_ratio:.2f}")
        if requires_creative_asset(channel) and stats.total > 0 and not creative_ok:
            reasons.append(f"missing_creative>{rule.max_missing_creative_ratio:.2f}")
        if requires_creative_asset(channel) and stats.total > 0 and not asset_ok:
            reasons.append(f"missing_asset>{rule.max_missing_asset_ratio:.2f}")

        report.append(
            {
                "channel": channel,
                "passed": total_ok and url_ok and advertiser_ok and label_ok and creative_ok and asset_ok,
                "reasons": reasons,
                "total": stats.total,
                "missing_url": stats.missing_url,
                "missing_advertiser": stats.missing_advertiser,
                "generic_advertiser": stats.generic_advertiser,
                "invalid_label": stats.invalid_label,
                "missing_creative": stats.missing_creative,
                "missing_asset": stats.missing_asset,
                "missing_url_ratio": stats.missing_url_ratio,
                "generic_advertiser_ratio": stats.generic_advertiser_ratio,
                "invalid_label_ratio": stats.invalid_label_ratio,
                "missing_creative_ratio": stats.missing_creative_ratio,
                "missing_asset_ratio": stats.missing_asset_ratio,
                "rule": {
                    "min_total": rule.min_total,
                    "max_missing_url_ratio": rule.max_missing_url_ratio,
                    "max_generic_advertiser_ratio": rule.max_generic_advertiser_ratio,
                    "max_invalid_label_ratio": rule.max_invalid_label_ratio,
                    "max_missing_creative_ratio": rule.max_missing_creative_ratio,
                    "max_missing_asset_ratio": rule.max_missing_asset_ratio,
                },
            }
        )

    return report
