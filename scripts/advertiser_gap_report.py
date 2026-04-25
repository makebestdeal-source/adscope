"""Generate a target advertiser gap report for the current AdScope DB.

This report ties together:
- ADIC top advertiser coverage
- recent/live/archive coverage state
- unresolved live rows and staging signals
- mobile panel signals and data quality

Outputs are written to:
- cache/reports/advertiser_gap_latest.json
- cache/reports/advertiser_gap_latest.md

Usage:
    python scripts/advertiser_gap_report.py
    python scripts/advertiser_gap_report.py --top-n 100 --recent-days 90
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "adscope.db"
OUT_DIR = ROOT / "cache" / "reports"
NOW = datetime.now()

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from processor.advertiser_verifier import NameQuality, verify_advertiser_name

_CORP_PATTERNS = [
    r"\(주\)",
    r"㈜",
    r"주식회사",
    r"\(유\)",
    r"유한회사",
    r"\(재\)",
    r"\(사\)",
]


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def _fmt_dt(value: str | None) -> str:
    dt = _parse_dt(value)
    if not dt:
        return value or "-"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _days_since(value: str | None) -> float | None:
    dt = _parse_dt(value)
    if not dt:
        return None
    return round((NOW - dt).total_seconds() / 86400, 2)


def _normalize_name(name: str | None) -> str:
    if not name:
        return ""
    cleaned = name.strip().lower()
    for pattern in _CORP_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)
    cleaned = re.sub(r"https?://", "", cleaned)
    cleaned = re.sub(r"www\.", "", cleaned)
    cleaned = re.sub(r"[^0-9a-z가-힣]", "", cleaned)
    return cleaned


def _match_records(target_norm: str, records: list[dict]) -> tuple[list[dict], str]:
    if not target_norm:
        return [], "none"

    exact = [row for row in records if row["normalized_name"] == target_norm]
    if exact:
        return exact, "exact"

    if len(target_norm) < 3:
        return [], "none"

    contains = [
        row
        for row in records
        if len(row["normalized_name"]) >= 3
        and (target_norm in row["normalized_name"] or row["normalized_name"] in target_norm)
    ]
    if contains:
        return contains, "contains"

    return [], "none"


def _latest_dt(values: list[str | None]) -> str | None:
    parsed = [(_parse_dt(value), value) for value in values if value]
    parsed = [item for item in parsed if item[0] is not None]
    if not parsed:
        return None
    parsed.sort(key=lambda item: item[0], reverse=True)
    return parsed[0][1]


def _sum_by(records: list[dict], key: str, value_key: str) -> list[dict]:
    totals: dict[str, int] = defaultdict(int)
    for row in records:
        name = row.get(key) or "unknown"
        totals[name] += int(row.get(value_key, 0) or 0)
    return [
        {key: name, value_key: count}
        for name, count in sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    ]


def _format_channel_counts(items: list[dict], key: str = "channel", value_key: str = "count", limit: int = 4) -> str:
    if not items:
        return "-"
    return ", ".join(f"{row[key]}:{row[value_key]}" for row in items[:limit])


def _pct(part: int, total: int) -> float:
    if not total:
        return 0.0
    return round((part / total) * 100, 2)


def _build_live_records(conn: sqlite3.Connection, cutoff_text: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            a.name AS advertiser_name,
            s.channel AS channel,
            COUNT(*) AS ad_count,
            SUM(CASE WHEN s.captured_at >= ? THEN 1 ELSE 0 END) AS recent_ad_count,
            MAX(s.captured_at) AS last_seen_at,
            SUM(CASE WHEN d.is_retroactive = 1 THEN 1 ELSE 0 END) AS retroactive_ad_count
        FROM ad_details d
        JOIN ad_snapshots s ON s.id = d.snapshot_id
        JOIN advertisers a ON a.id = d.advertiser_id
        GROUP BY a.name, s.channel
        ORDER BY ad_count DESC
        """,
        (cutoff_text,),
    ).fetchall()
    return [
        {
            "advertiser_name": row["advertiser_name"],
            "normalized_name": _normalize_name(row["advertiser_name"]),
            "channel": row["channel"] or "unknown",
            "count": row["ad_count"] or 0,
            "recent_count": row["recent_ad_count"] or 0,
            "retroactive_count": row["retroactive_ad_count"] or 0,
            "last_seen_at": row["last_seen_at"],
        }
        for row in rows
        if _normalize_name(row["advertiser_name"])
    ]


def _build_unresolved_live_records(conn: sqlite3.Connection, cutoff_text: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            d.advertiser_name_raw AS advertiser_name,
            s.channel AS channel,
            COUNT(*) AS ad_count,
            SUM(CASE WHEN s.captured_at >= ? THEN 1 ELSE 0 END) AS recent_ad_count,
            MAX(s.captured_at) AS last_seen_at
        FROM ad_details d
        JOIN ad_snapshots s ON s.id = d.snapshot_id
        WHERE d.advertiser_id IS NULL
          AND d.advertiser_name_raw IS NOT NULL
          AND TRIM(d.advertiser_name_raw) <> ''
        GROUP BY d.advertiser_name_raw, s.channel
        ORDER BY ad_count DESC
        """,
        (cutoff_text,),
    ).fetchall()
    return [
        {
            "advertiser_name": row["advertiser_name"],
            "normalized_name": _normalize_name(row["advertiser_name"]),
            "channel": row["channel"] or "unknown",
            "count": row["ad_count"] or 0,
            "recent_count": row["recent_ad_count"] or 0,
            "last_seen_at": row["last_seen_at"],
        }
        for row in rows
        if _normalize_name(row["advertiser_name"])
    ]


def _build_staging_records(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            advertiser_name,
            channel,
            status,
            COUNT(*) AS row_count,
            MAX(captured_at) AS last_seen_at
        FROM (
            SELECT
                COALESCE(
                    resolved_advertiser_name,
                    json_extract(raw_payload, '$.advertiser_name'),
                    ''
                ) AS advertiser_name,
                channel,
                status,
                captured_at
            FROM staging_ads
        ) t
        WHERE advertiser_name IS NOT NULL
          AND TRIM(advertiser_name) <> ''
        GROUP BY advertiser_name, channel, status
        ORDER BY row_count DESC
        """
    ).fetchall()
    return [
        {
            "advertiser_name": row["advertiser_name"],
            "normalized_name": _normalize_name(row["advertiser_name"]),
            "channel": row["channel"] or "unknown",
            "status": row["status"] or "unknown",
            "count": row["row_count"] or 0,
            "last_seen_at": row["last_seen_at"],
        }
        for row in rows
        if _normalize_name(row["advertiser_name"])
    ]


def _build_mobile_records(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            advertiser_name_raw AS advertiser_name,
            app_name,
            channel,
            COUNT(*) AS row_count,
            MAX(observed_at) AS last_seen_at,
            SUM(CASE WHEN advertiser_id IS NULL THEN 1 ELSE 0 END) AS missing_advertiser_id_count,
            SUM(CASE WHEN creative_url IS NULL OR TRIM(creative_url) = '' THEN 1 ELSE 0 END) AS missing_creative_url_count,
            SUM(CASE WHEN click_url IS NULL OR TRIM(click_url) = '' THEN 1 ELSE 0 END) AS missing_click_url_count
        FROM mobile_panel_exposures
        WHERE advertiser_name_raw IS NOT NULL
          AND TRIM(advertiser_name_raw) <> ''
        GROUP BY advertiser_name_raw, app_name, channel
        ORDER BY row_count DESC
        """
    ).fetchall()
    return [
        {
            "advertiser_name": row["advertiser_name"],
            "normalized_name": _normalize_name(row["advertiser_name"]),
            "app_name": row["app_name"] or "unknown",
            "channel": row["channel"] or "unknown",
            "count": row["row_count"] or 0,
            "last_seen_at": row["last_seen_at"],
            "missing_advertiser_id_count": row["missing_advertiser_id_count"] or 0,
            "missing_creative_url_count": row["missing_creative_url_count"] or 0,
            "missing_click_url_count": row["missing_click_url_count"] or 0,
        }
        for row in rows
        if _normalize_name(row["advertiser_name"])
    ]


def _build_mobile_quality(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS exposure_count,
            COUNT(DISTINCT device_id) AS device_count,
            COUNT(DISTINCT app_name) AS app_count,
            MAX(observed_at) AS last_observed_at,
            SUM(CASE WHEN advertiser_id IS NULL THEN 1 ELSE 0 END) AS missing_advertiser_id_count,
            SUM(CASE WHEN creative_url IS NULL OR TRIM(creative_url) = '' THEN 1 ELSE 0 END) AS missing_creative_url_count,
            SUM(CASE WHEN click_url IS NULL OR TRIM(click_url) = '' THEN 1 ELSE 0 END) AS missing_click_url_count
        FROM mobile_panel_exposures
        """
    ).fetchone()
    exposure_count = row["exposure_count"] or 0

    rejected_examples: list[str] = []
    rejected_count = 0
    for exposure_row in conn.execute(
        """
        SELECT advertiser_name_raw
        FROM mobile_panel_exposures
        WHERE advertiser_name_raw IS NOT NULL
          AND TRIM(advertiser_name_raw) <> ''
        """
    ).fetchall():
        result = verify_advertiser_name(exposure_row["advertiser_name_raw"])
        if result.quality == NameQuality.REJECTED:
            rejected_count += 1
            if exposure_row["advertiser_name_raw"] not in rejected_examples and len(rejected_examples) < 8:
                rejected_examples.append(exposure_row["advertiser_name_raw"])

    by_app = [
        {"app_name": row["app_name"] or "unknown", "count": row["cnt"]}
        for row in conn.execute(
            """
            SELECT app_name, COUNT(*) AS cnt
            FROM mobile_panel_exposures
            GROUP BY app_name
            ORDER BY cnt DESC
            """
        ).fetchall()
    ]

    return {
        "device_count": row["device_count"] or 0,
        "app_count": row["app_count"] or 0,
        "exposure_count": exposure_count,
        "last_observed_at": row["last_observed_at"],
        "last_observed_age_days": _days_since(row["last_observed_at"]),
        "missing_advertiser_id_count": row["missing_advertiser_id_count"] or 0,
        "missing_advertiser_id_pct": _pct(row["missing_advertiser_id_count"] or 0, exposure_count),
        "missing_creative_url_count": row["missing_creative_url_count"] or 0,
        "missing_creative_url_pct": _pct(row["missing_creative_url_count"] or 0, exposure_count),
        "missing_click_url_count": row["missing_click_url_count"] or 0,
        "missing_click_url_pct": _pct(row["missing_click_url_count"] or 0, exposure_count),
        "rejected_name_count": rejected_count,
        "rejected_name_pct": _pct(rejected_count, exposure_count),
        "rejected_name_examples": rejected_examples,
        "by_app": by_app,
    }


def _classify_gap(live_total: int, live_recent: int, live_retroactive: int, unresolved_total: int, staging_total: int, mobile_total: int) -> str:
    if live_recent > 0:
        return "covered_recent"
    if live_total > 0 and live_retroactive >= live_total:
        return "archive_only"
    if live_total > 0:
        return "stale_live"
    if unresolved_total > 0 or staging_total > 0:
        return "pipeline_quality_gap"
    if mobile_total > 0:
        return "mobile_only_signal"
    return "collection_gap"


def _build_target_rows(
    targets: list[sqlite3.Row],
    live_records: list[dict],
    unresolved_records: list[dict],
    staging_records: list[dict],
    mobile_records: list[dict],
) -> list[dict]:
    items: list[dict] = []
    for row in targets:
        advertiser_name = row["advertiser_name"]
        target_norm = _normalize_name(advertiser_name)

        live_matches, live_match_mode = _match_records(target_norm, live_records)
        unresolved_matches, unresolved_match_mode = _match_records(target_norm, unresolved_records)
        staging_matches, staging_match_mode = _match_records(target_norm, staging_records)
        mobile_matches, mobile_match_mode = _match_records(target_norm, mobile_records)

        live_total = sum(item["count"] for item in live_matches)
        live_recent = sum(item["recent_count"] for item in live_matches)
        live_retroactive = sum(item["retroactive_count"] for item in live_matches)
        unresolved_total = sum(item["count"] for item in unresolved_matches)
        staging_total = sum(item["count"] for item in staging_matches)
        mobile_total = sum(item["count"] for item in mobile_matches)

        live_channel_counts = _sum_by(live_matches, "channel", "count")
        live_recent_channels = _sum_by(
            [item for item in live_matches if item["recent_count"] > 0],
            "channel",
            "recent_count",
        )
        unresolved_channels = _sum_by(unresolved_matches, "channel", "count")
        staging_status_counts = _sum_by(staging_matches, "status", "count")
        mobile_app_counts = _sum_by(mobile_matches, "app_name", "count")

        last_signal_at = _latest_dt(
            [item["last_seen_at"] for item in live_matches + unresolved_matches + staging_matches + mobile_matches]
        )
        bucket = _classify_gap(
            live_total=live_total,
            live_recent=live_recent,
            live_retroactive=live_retroactive,
            unresolved_total=unresolved_total,
            staging_total=staging_total,
            mobile_total=mobile_total,
        )

        items.append(
            {
                "advertiser_name": advertiser_name,
                "adic_amount": round(row["total_amount"] or 0, 0),
                "industry": row["industry"] or "",
                "match_modes": {
                    "live": live_match_mode,
                    "unresolved_live": unresolved_match_mode,
                    "staging": staging_match_mode,
                    "mobile": mobile_match_mode,
                },
                "live_total_count": live_total,
                "live_recent_count": live_recent,
                "live_retroactive_count": live_retroactive,
                "live_channels": live_channel_counts,
                "live_recent_channels": live_recent_channels,
                "unresolved_live_count": unresolved_total,
                "unresolved_live_channels": unresolved_channels,
                "staging_total_count": staging_total,
                "staging_statuses": staging_status_counts,
                "mobile_total_count": mobile_total,
                "mobile_apps": mobile_app_counts,
                "last_signal_at": last_signal_at,
                "last_signal_age_days": _days_since(last_signal_at),
                "gap_bucket": bucket,
                "matched_live_names": sorted({item["advertiser_name"] for item in live_matches}),
                "matched_unresolved_names": sorted({item["advertiser_name"] for item in unresolved_matches}),
                "matched_staging_names": sorted({item["advertiser_name"] for item in staging_matches}),
                "matched_mobile_names": sorted({item["advertiser_name"] for item in mobile_matches}),
            }
        )

    return sorted(items, key=lambda item: (-item["adic_amount"], item["advertiser_name"]))


def _build_bucket_summary(targets: list[dict]) -> list[dict]:
    totals: dict[str, dict] = {}
    total_amount = sum(int(item["adic_amount"]) for item in targets)
    for item in targets:
        bucket = item["gap_bucket"]
        bucket_row = totals.setdefault(
            bucket,
            {
                "bucket": bucket,
                "advertiser_count": 0,
                "total_amount": 0,
            },
        )
        bucket_row["advertiser_count"] += 1
        bucket_row["total_amount"] += int(item["adic_amount"])

    rows = sorted(totals.values(), key=lambda item: (-item["total_amount"], item["bucket"]))
    for row in rows:
        row["amount_share_pct"] = _pct(row["total_amount"], total_amount)
    return rows


def _build_industry_summary(targets: list[dict]) -> list[dict]:
    industries: dict[str, dict] = {}
    for item in targets:
        industry = item["industry"] or "미분류"
        row = industries.setdefault(
            industry,
            {
                "industry": industry,
                "advertiser_count": 0,
                "recent_covered_count": 0,
                "gap_count": 0,
                "total_amount": 0,
                "gap_amount": 0,
            },
        )
        row["advertiser_count"] += 1
        row["total_amount"] += int(item["adic_amount"])
        if item["gap_bucket"] == "covered_recent":
            row["recent_covered_count"] += 1
        else:
            row["gap_count"] += 1
            row["gap_amount"] += int(item["adic_amount"])

    rows = sorted(industries.values(), key=lambda item: (-item["gap_amount"], item["industry"]))
    for row in rows:
        row["recent_coverage_pct"] = _pct(row["recent_covered_count"], row["advertiser_count"])
        row["gap_amount_share_pct"] = _pct(row["gap_amount"], row["total_amount"])
    return rows


def build_report(top_n: int, recent_days: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cutoff_text = datetime.fromtimestamp(NOW.timestamp() - (recent_days * 86400)).strftime("%Y-%m-%d %H:%M:%S")
    latest_adic_year = conn.execute(
        "SELECT MAX(year) FROM adic_ad_expenses WHERE medium = 'total'"
    ).fetchone()[0]

    targets = conn.execute(
        """
        SELECT advertiser_name, ROUND(SUM(amount), 0) AS total_amount, MAX(industry) AS industry
        FROM adic_ad_expenses
        WHERE medium = 'total'
          AND year = ?
        GROUP BY advertiser_name
        ORDER BY total_amount DESC, advertiser_name ASC
        LIMIT ?
        """,
        (latest_adic_year, top_n),
    ).fetchall()

    live_records = _build_live_records(conn, cutoff_text)
    unresolved_records = _build_unresolved_live_records(conn, cutoff_text)
    staging_records = _build_staging_records(conn)
    mobile_records = _build_mobile_records(conn)
    mobile_quality = _build_mobile_quality(conn)

    target_rows = _build_target_rows(
        targets=targets,
        live_records=live_records,
        unresolved_records=unresolved_records,
        staging_records=staging_records,
        mobile_records=mobile_records,
    )

    bucket_summary = _build_bucket_summary(target_rows)
    industry_summary = _build_industry_summary(target_rows)

    overall_recent_covered = sum(1 for item in target_rows if item["gap_bucket"] == "covered_recent")
    overall_amount = sum(int(item["adic_amount"]) for item in target_rows)
    recent_covered_amount = sum(
        int(item["adic_amount"]) for item in target_rows if item["gap_bucket"] == "covered_recent"
    )

    report = {
        "generated_at": NOW.strftime("%Y-%m-%d %H:%M:%S"),
        "db_path": str(DB_PATH),
        "recent_days": recent_days,
        "adic_year": latest_adic_year,
        "summary": {
            "top_n": top_n,
            "recent_covered_count": overall_recent_covered,
            "recent_covered_pct": _pct(overall_recent_covered, top_n),
            "recent_covered_amount": recent_covered_amount,
            "recent_covered_amount_pct": _pct(recent_covered_amount, overall_amount),
            "gap_count": top_n - overall_recent_covered,
            "gap_amount": overall_amount - recent_covered_amount,
            "gap_amount_pct": _pct(overall_amount - recent_covered_amount, overall_amount),
        },
        "bucket_summary": bucket_summary,
        "industry_summary": industry_summary,
        "mobile_quality": mobile_quality,
        "targets": target_rows,
    }

    conn.close()
    return report


def _bucket_table_md(rows: list[dict]) -> str:
    lines = [
        "| 버킷 | 광고주 수 | ADIC 합계 | 금액 비중 |",
        "|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['bucket']} | {row['advertiser_count']} | {row['total_amount']:,} | {row['amount_share_pct']}% |"
        )
    return "\n".join(lines)


def _industry_table_md(rows: list[dict], limit: int = 12) -> str:
    if not rows:
        return "- 없음"
    lines = [
        "| 업종 | 광고주 수 | 최근 커버 | 최근 커버율 | 갭 금액 | 갭 금액 비중 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows[:limit]:
        lines.append(
            "| {industry} | {advertiser_count} | {recent_covered_count} | {recent_coverage_pct}% | {gap_amount:,} | {gap_amount_share_pct}% |".format(
                industry=row["industry"],
                advertiser_count=row["advertiser_count"],
                recent_covered_count=row["recent_covered_count"],
                recent_coverage_pct=row["recent_coverage_pct"],
                gap_amount=row["gap_amount"],
                gap_amount_share_pct=row["gap_amount_share_pct"],
            )
        )
    return "\n".join(lines)


def _targets_table_md(rows: list[dict], limit: int = 20) -> str:
    if not rows:
        return "- 없음"
    lines = [
        "| 광고주 | ADIC 금액 | 버킷 | 최근 라이브 | unresolved | staging | mobile | 마지막 신호 | 라이브 채널 |",
        "|---|---:|---|---:|---:|---:|---:|---|---|",
    ]
    for row in rows[:limit]:
        lines.append(
            "| {advertiser_name} | {adic_amount:,} | {gap_bucket} | {live_recent_count} | {unresolved_live_count} | "
            "{staging_total_count} | {mobile_total_count} | {last_signal_at} | {live_channels} |".format(
                advertiser_name=row["advertiser_name"],
                adic_amount=int(row["adic_amount"]),
                gap_bucket=row["gap_bucket"],
                live_recent_count=row["live_recent_count"],
                unresolved_live_count=row["unresolved_live_count"],
                staging_total_count=row["staging_total_count"],
                mobile_total_count=row["mobile_total_count"],
                last_signal_at=_fmt_dt(row["last_signal_at"]),
                live_channels=_format_channel_counts(row["live_recent_channels"] or row["live_channels"]),
            )
        )
    return "\n".join(lines)


def _pipeline_candidates_md(rows: list[dict], limit: int = 15) -> str:
    candidates = [
        row
        for row in rows
        if row["gap_bucket"] in {"pipeline_quality_gap", "stale_live", "archive_only"}
        and (row["unresolved_live_count"] > 0 or row["staging_total_count"] > 0)
    ]
    if not candidates:
        return "- 없음"

    lines = [
        "| 광고주 | 버킷 | unresolved 채널 | staging 상태 | 매칭된 raw/staging 이름 |",
        "|---|---|---|---|---|",
    ]
    for row in candidates[:limit]:
        lines.append(
            "| {advertiser_name} | {gap_bucket} | {unresolved_channels} | {staging_statuses} | {matched_names} |".format(
                advertiser_name=row["advertiser_name"],
                gap_bucket=row["gap_bucket"],
                unresolved_channels=_format_channel_counts(row["unresolved_live_channels"]),
                staging_statuses=_format_channel_counts(row["staging_statuses"], key="status"),
                matched_names=", ".join((row["matched_unresolved_names"] + row["matched_staging_names"])[:3]) or "-",
            )
        )
    return "\n".join(lines)


def build_markdown(report: dict) -> str:
    summary = report["summary"]
    mobile = report["mobile_quality"]
    targets = report["targets"]
    gap_targets = [row for row in targets if row["gap_bucket"] != "covered_recent"]

    return f"""# AdScope Advertiser Gap Report

- 생성 시각: {report['generated_at']}
- 기준 DB: `{report['db_path']}`
- 최근 기준 창: 최근 {report['recent_days']}일
- ADIC 기준 연도: {report['adic_year']}

## 요약

- ADIC Top {summary['top_n']} 최근 커버 광고주: {summary['recent_covered_count']} / {summary['top_n']} ({summary['recent_covered_pct']}%)
- 최근 커버 금액 비중: {summary['recent_covered_amount']:,} ({summary['recent_covered_amount_pct']}%)
- 최근 커버 갭 광고주: {summary['gap_count']}
- 최근 커버 갭 금액: {summary['gap_amount']:,} ({summary['gap_amount_pct']}%)

## 갭 버킷

{_bucket_table_md(report['bucket_summary'])}

## 최근 갭 상위 광고주

{_targets_table_md(gap_targets)}

## 파이프라인 손실 후보

{_pipeline_candidates_md(gap_targets)}

## 업종별 최근 커버 갭

{_industry_table_md(report['industry_summary'])}

## 모바일 패널 품질

- 디바이스 수: {mobile['device_count']:,}
- 앱 수: {mobile['app_count']:,}
- 노출 수: {mobile['exposure_count']:,}
- 마지막 관측: {_fmt_dt(mobile['last_observed_at'])} ({mobile['last_observed_age_days']}일 전)
- advertiser_id 누락: {mobile['missing_advertiser_id_count']:,} ({mobile['missing_advertiser_id_pct']}%)
- creative_url 누락: {mobile['missing_creative_url_count']:,} ({mobile['missing_creative_url_pct']}%)
- click_url 누락: {mobile['missing_click_url_count']:,} ({mobile['missing_click_url_pct']}%)
- 검증기 기준 거절 이름: {mobile['rejected_name_count']:,} ({mobile['rejected_name_pct']}%)

{os.linesep.join(f"- {row['app_name']}: {row['count']:,}" for row in mobile['by_app']) or '- 없음'}

{os.linesep.join(f"- 품질 의심 이름 예시: {name}" for name in mobile['rejected_name_examples']) or '- 품질 의심 이름 예시 없음'}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate AdScope advertiser gap report")
    parser.add_argument("--top-n", type=int, default=100, help="ADIC top advertiser pool size")
    parser.add_argument("--recent-days", type=int, default=90, help="Recent coverage window")
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    report = build_report(top_n=args.top_n, recent_days=args.recent_days)
    md_text = build_markdown(report)

    json_path = OUT_DIR / "advertiser_gap_latest.json"
    md_path = OUT_DIR / "advertiser_gap_latest.md"

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(md_text, encoding="utf-8")

    print(f"[gap] wrote {json_path}")
    print(f"[gap] wrote {md_path}")
    print(
        "[gap] ADIC top {top_n} recent coverage: {covered}/{top_n} ({pct}%)".format(
            top_n=report["summary"]["top_n"],
            covered=report["summary"]["recent_covered_count"],
            pct=report["summary"]["recent_covered_pct"],
        )
    )
    print(
        "[gap] mobile exposures: {exposures} (adv_id_missing {missing}%, creative_missing {creative}%)".format(
            exposures=report["mobile_quality"]["exposure_count"],
            missing=report["mobile_quality"]["missing_advertiser_id_pct"],
            creative=report["mobile_quality"]["missing_creative_url_pct"],
        )
    )


if __name__ == "__main__":
    main()
