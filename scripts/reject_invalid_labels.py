"""Reject or mark rows whose advertiser/campaign labels are parser artifacts.

Dry-run is the default. Use --apply to write changes. No rows are deleted.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from processor.entity_label_quality import (
    LabelQuality,
    repair_material_text,
    validate_entity_label,
    validate_material_text,
)


DB_PATH = ROOT / "adscope.db"


def _load_extra(raw: object) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    if not raw:
        return {}
    try:
        value = json.loads(str(raw))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _dump_extra(extra: dict) -> str:
    return json.dumps(extra, ensure_ascii=False, sort_keys=True)


def _mark_extra(extra: dict, *, field: str, value: str, reason: str, evidence: str | None) -> dict:
    marked = dict(extra)
    marked.setdefault("quality_evidence", {})
    marked["quality_evidence"][field] = {
        "value": value,
        "reason": reason,
        "evidence": evidence,
        "checked_at": datetime.utcnow().isoformat(timespec="seconds"),
    }
    marked["quality_rejection_reason"] = reason
    return marked


def _mark_repair_extra(
    extra: dict,
    *,
    field: str,
    original_value: str,
    repaired_value: str | None,
    reason: str,
    evidence: str | None,
) -> dict:
    marked = dict(extra)
    marked.setdefault("quality_repairs", {})
    marked["quality_repairs"][field] = {
        "original_value": original_value,
        "repaired_value": repaired_value,
        "reason": reason,
        "evidence": evidence,
        "checked_at": datetime.utcnow().isoformat(timespec="seconds"),
    }
    return marked


def _campaign_repair_name(advertiser_name: str | None, channel: str | None, first_seen: str | None) -> str | None:
    if not advertiser_name:
        return None
    adv_check = validate_entity_label(advertiser_name, field="advertiser")
    if adv_check.quality == LabelQuality.INVALID:
        return None
    month = ""
    if first_seen:
        try:
            month = f" {datetime.fromisoformat(str(first_seen).replace('Z', '+00:00')).month}월"
        except Exception:
            month = ""
    channel_label = f" {channel}" if channel else ""
    return f"{advertiser_name}{channel_label}{month} campaign"


def run_label_quality_repair(
    db_path: str | Path = DB_PATH,
    days: int = 30,
    channels: tuple[str, ...] | None = None,
    apply: bool = False,
    repair_campaign_names: bool = False,
    reject_person_names: bool = True,
) -> dict:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    channel_filter = ""
    params: list[object] = [f"-{max(0, days)} day"]
    if channels:
        placeholders = ",".join("?" for _ in channels)
        channel_filter = f" AND s.channel IN ({placeholders})"
        params.extend(channels)

    ad_rows = conn.execute(
        f"""
        SELECT
            d.id,
            d.advertiser_name_raw,
            d.ad_text,
            d.creative_image_path,
            d.extra_data,
            a.name AS advertiser_name,
            s.channel
        FROM ad_details d
        JOIN ad_snapshots s ON s.id = d.snapshot_id
        LEFT JOIN advertisers a ON a.id = d.advertiser_id
        WHERE s.captured_at >= datetime('now', ?)
          AND (d.verification_status IS NULL OR d.verification_status != 'rejected')
          {channel_filter}
        """,
        params,
    ).fetchall()

    stats = {
        "ad_rows_scanned": len(ad_rows),
        "ad_rows_rejected": 0,
        "ad_text_repaired": 0,
        "ad_text_cleared": 0,
        "suspect_person_name_skipped": 0,
        "campaigns_scanned": 0,
        "campaigns_marked": 0,
        "campaigns_renamed": 0,
        "reasons": {},
    }
    ad_updates: list[tuple[str, str, str, str, int]] = []
    ad_text_updates: list[tuple[str | None, str, int]] = []

    for row in ad_rows:
        extra = _load_extra(row["extra_data"])
        candidates = [
            ("advertiser_name_raw", (row["advertiser_name_raw"] or "").strip()),
            ("advertiser_name", (row["advertiser_name"] or "").strip()),
        ]
        failures = [
            (field, value, check)
            for field, value in candidates
            if value
            for check in [validate_entity_label(value, field="advertiser", channel=row["channel"])]
            if check.quality == LabelQuality.INVALID
        ]
        if not failures:
            pass
        else:
            field, value, check = failures[0]
            reason = check.reason or "invalid_label"
            if reason.startswith("personal_name") and not reject_person_names:
                stats["suspect_person_name_skipped"] += 1
                stats["reasons"]["suspect_person_name_skipped"] = (
                    stats["reasons"].get("suspect_person_name_skipped", 0) + 1
                )
            else:
                extra = _mark_extra(
                    extra,
                    field=field,
                    value=value,
                    reason=reason,
                    evidence=check.evidence,
                )
                extra["original_advertiser_label"] = value
                ad_updates.append(
                    (
                        "rejected",
                        f"label_quality:{reason}",
                        _dump_extra(extra),
                        reason,
                        int(row["id"]),
                    )
                )
                stats["ad_rows_rejected"] += 1
                stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1
                continue

        ad_text = (row["ad_text"] or "").strip()
        if not ad_text:
            continue
        text_check = validate_material_text(ad_text)
        if text_check.quality != LabelQuality.INVALID:
            continue

        reason = text_check.reason or "invalid_material_text"
        repaired_text = repair_material_text(ad_text, extra)
        if repaired_text:
            extra = _mark_repair_extra(
                extra,
                field="ad_text",
                original_value=ad_text,
                repaired_value=repaired_text,
                reason=reason,
                evidence=text_check.evidence,
            )
            ad_text_updates.append((repaired_text, _dump_extra(extra), int(row["id"])))
            stats["ad_text_repaired"] += 1
            stats["reasons"][f"repaired_{reason}"] = stats["reasons"].get(f"repaired_{reason}", 0) + 1
            continue

        if (row["creative_image_path"] or "").strip():
            extra = _mark_repair_extra(
                extra,
                field="ad_text",
                original_value=ad_text,
                repaired_value=None,
                reason=reason,
                evidence=text_check.evidence,
            )
            ad_text_updates.append((None, _dump_extra(extra), int(row["id"])))
            stats["ad_text_cleared"] += 1
            stats["reasons"][f"cleared_{reason}"] = stats["reasons"].get(f"cleared_{reason}", 0) + 1
            continue

        extra = _mark_extra(
            extra,
            field="ad_text",
            value=ad_text,
            reason=reason,
            evidence=text_check.evidence,
        )
        ad_updates.append(
            (
                "rejected",
                f"label_quality:{reason}",
                _dump_extra(extra),
                reason,
                int(row["id"]),
            )
        )
        stats["ad_rows_rejected"] += 1
        stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1

    campaign_channel_filter = ""
    campaign_params: list[object] = [f"-{max(0, days)} day"]
    if channels:
        placeholders = ",".join("?" for _ in channels)
        campaign_channel_filter = f" AND c.channel IN ({placeholders})"
        campaign_params.extend(channels)

    campaign_rows = conn.execute(
        f"""
        SELECT
            c.id,
            c.campaign_name,
            c.channel,
            c.first_seen,
            c.extra_data,
            a.name AS advertiser_name
        FROM campaigns c
        LEFT JOIN advertisers a ON a.id = c.advertiser_id
        WHERE c.last_seen >= datetime('now', ?)
          {campaign_channel_filter}
        """,
        campaign_params,
    ).fetchall()
    stats["campaigns_scanned"] = len(campaign_rows)

    campaign_updates: list[tuple[str | None, str, int]] = []
    for row in campaign_rows:
        name = (row["campaign_name"] or "").strip()
        check = validate_entity_label(name, field="campaign", channel=row["channel"])
        if check.quality != LabelQuality.INVALID:
            continue

        reason = check.reason or "invalid_campaign_label"
        extra = _mark_extra(
            _load_extra(row["extra_data"]),
            field="campaign_name",
            value=name,
            reason=reason,
            evidence=check.evidence,
        )
        extra["original_campaign_name"] = name
        repaired_name = None
        if repair_campaign_names:
            repaired_name = _campaign_repair_name(row["advertiser_name"], row["channel"], row["first_seen"])
            if repaired_name:
                extra["campaign_name_repair_source"] = "advertiser_channel_month"
                stats["campaigns_renamed"] += 1

        campaign_updates.append((repaired_name or name, _dump_extra(extra), int(row["id"])))
        stats["campaigns_marked"] += 1
        stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1

    if apply:
        if ad_updates:
            conn.executemany(
                """
                UPDATE ad_details
                SET verification_status = ?, verification_source = ?, extra_data = ?
                WHERE id = ?
                """,
                [(status, source, extra, row_id) for status, source, extra, _reason, row_id in ad_updates],
            )
        if ad_text_updates:
            conn.executemany(
                """
                UPDATE ad_details
                SET ad_text = ?, extra_data = ?
                WHERE id = ?
                """,
                ad_text_updates,
            )
        if campaign_updates:
            conn.executemany(
                """
                UPDATE campaigns
                SET campaign_name = ?, extra_data = ?
                WHERE id = ?
                """,
                campaign_updates,
            )
        conn.commit()

    conn.close()
    stats["mode"] = "apply" if apply else "dry-run"
    return stats


def _parse_channels(raw: str) -> tuple[str, ...] | None:
    values = tuple(part.strip() for part in raw.split(",") if part.strip())
    return values or None


def main() -> None:
    parser = argparse.ArgumentParser(description="Reject invalid advertiser/campaign labels")
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite DB path")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days")
    parser.add_argument("--channels", default="", help="Optional comma-separated channel list")
    parser.add_argument("--apply", action="store_true", help="Write changes. Default is dry-run.")
    parser.add_argument(
        "--repair-campaign-names",
        action="store_true",
        help="When applying, replace invalid campaign names with advertiser/channel/month names when safe.",
    )
    parser.add_argument(
        "--reject-person-names",
        action="store_true",
        default=True,
        help="Reject Korean/English personal-name-looking labels. Enabled by default.",
    )
    parser.add_argument(
        "--skip-person-name-reject",
        action="store_false",
        dest="reject_person_names",
        help="Only report personal-name-looking labels as suspect without rejecting them.",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    stats = run_label_quality_repair(
        db_path=db_path,
        days=args.days,
        channels=_parse_channels(args.channels),
        apply=args.apply,
        repair_campaign_names=args.repair_campaign_names,
        reject_person_names=args.reject_person_names,
    )
    print(f"[reject-invalid-labels] db={db_path}")
    for key, value in stats.items():
        print(f"[reject-invalid-labels] {key}={value}")


if __name__ == "__main__":
    main()
