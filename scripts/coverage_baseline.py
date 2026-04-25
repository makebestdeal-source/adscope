"""Generate a coverage-first baseline report for the current AdScope DB.

This script produces:
- overall live/staging volumes
- per-channel freshness and volume
- retroactive/archive mix
- ADIC top advertiser coverage (all-time and recent-window)

Outputs are written to:
- cache/reports/coverage_baseline_latest.json
- cache/reports/coverage_baseline_latest.md

Usage:
    python scripts/coverage_baseline.py
    python scripts/coverage_baseline.py --top-n 300 --recent-days 90
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "adscope.db"
OUT_DIR = ROOT / "cache" / "reports"
NOW = datetime.now()


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


def _days_since(value: str | None) -> float | None:
    dt = _parse_dt(value)
    if not dt:
        return None
    return round((NOW - dt).total_seconds() / 86400, 2)


def _fmt_dt(value: str | None) -> str:
    if not value:
        return "-"
    dt = _parse_dt(value)
    if not dt:
        return value
    return dt.strftime("%Y-%m-%d %H:%M:%S")


_CORP_PATTERNS = [
    r"\(주\)",
    r"㈜",
    r"주식회사",
    r"\(유\)",
    r"유한회사",
    r"\(재\)",
    r"\(사\)",
]


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


def _name_match(target_norm: str, observed_norms: set[str], observed_list: list[str]) -> tuple[bool, str | None, str]:
    if not target_norm:
        return False, None, "none"

    if target_norm in observed_norms:
        return True, target_norm, "exact"

    if len(target_norm) < 3:
        return False, None, "none"

    for observed in observed_list:
        if len(observed) < 3:
            continue
        if target_norm in observed or observed in target_norm:
            return True, observed, "contains"

    return False, None, "none"


def _query_one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> sqlite3.Row:
    row = conn.execute(sql, params).fetchone()
    return row if row is not None else sqlite3.Row


def build_report(top_n: int, recent_days: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cutoff = (NOW.timestamp() - (recent_days * 86400))
    cutoff_text = datetime.fromtimestamp(cutoff).strftime("%Y-%m-%d %H:%M:%S")

    overall = {
        "ad_details": conn.execute("SELECT COUNT(*) FROM ad_details").fetchone()[0],
        "ad_snapshots": conn.execute("SELECT COUNT(*) FROM ad_snapshots").fetchone()[0],
        "advertisers": conn.execute("SELECT COUNT(*) FROM advertisers").fetchone()[0],
        "campaigns": conn.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0],
        "spend_estimates": conn.execute("SELECT COUNT(*) FROM spend_estimates").fetchone()[0],
        "users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "last_crawl_at": conn.execute("SELECT MAX(captured_at) FROM ad_snapshots").fetchone()[0],
    }
    overall["last_crawl_age_days"] = _days_since(overall["last_crawl_at"])

    staging_status = {
        row["status"]: row["cnt"]
        for row in conn.execute(
            """
            SELECT status, COUNT(*) AS cnt
            FROM staging_ads
            GROUP BY status
            ORDER BY cnt DESC
            """
        ).fetchall()
    }

    quality_overall_row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_ad_details,
            SUM(CASE WHEN advertiser_id IS NULL THEN 1 ELSE 0 END) AS missing_advertiser_id,
            SUM(CASE WHEN advertiser_name_raw IS NULL OR TRIM(advertiser_name_raw) = '' THEN 1 ELSE 0 END) AS missing_advertiser_name,
            SUM(CASE WHEN creative_image_path IS NULL OR TRIM(creative_image_path) = '' THEN 1 ELSE 0 END) AS missing_creative_image,
            SUM(CASE WHEN display_url IS NULL OR TRIM(display_url) = '' THEN 1 ELSE 0 END) AS missing_display_url,
            SUM(CASE WHEN ad_description IS NULL OR TRIM(ad_description) = '' THEN 1 ELSE 0 END) AS missing_ad_description
        FROM ad_details
        """
    ).fetchone()

    total_details = quality_overall_row["total_ad_details"] or 0
    quality_overall = {
        "total_ad_details": total_details,
        "missing_advertiser_id": quality_overall_row["missing_advertiser_id"] or 0,
        "missing_advertiser_name": quality_overall_row["missing_advertiser_name"] or 0,
        "missing_creative_image": quality_overall_row["missing_creative_image"] or 0,
        "missing_display_url": quality_overall_row["missing_display_url"] or 0,
        "missing_ad_description": quality_overall_row["missing_ad_description"] or 0,
    }
    for key in [
        "missing_advertiser_id",
        "missing_advertiser_name",
        "missing_creative_image",
        "missing_display_url",
        "missing_ad_description",
    ]:
        pct_key = f"{key}_pct"
        quality_overall[pct_key] = round((quality_overall[key] / total_details) * 100, 2) if total_details else 0.0

    channel_rows = conn.execute(
        """
        SELECT
            s.channel AS channel,
            COUNT(DISTINCT s.id) AS snapshot_count,
            COUNT(d.id) AS live_ad_count,
            COUNT(DISTINCT d.advertiser_id) AS live_advertiser_count,
            MIN(s.captured_at) AS first_seen_at,
            MAX(s.captured_at) AS last_seen_at,
            SUM(CASE WHEN d.is_retroactive = 1 THEN 1 ELSE 0 END) AS retroactive_ad_count,
            COUNT(DISTINCT CASE WHEN s.captured_at >= ? THEN s.id END) AS recent_snapshot_count,
            COUNT(DISTINCT CASE WHEN s.captured_at >= ? THEN d.advertiser_id END) AS recent_advertiser_count
        FROM ad_snapshots s
        LEFT JOIN ad_details d ON d.snapshot_id = s.id
        GROUP BY s.channel
        ORDER BY snapshot_count DESC
        """,
        (cutoff_text, cutoff_text),
    ).fetchall()

    quality_channel_rows = conn.execute(
        """
        SELECT
            s.channel AS channel,
            COUNT(*) AS total_ad_details,
            SUM(CASE WHEN d.advertiser_id IS NULL THEN 1 ELSE 0 END) AS missing_advertiser_id,
            SUM(CASE WHEN d.advertiser_name_raw IS NULL OR TRIM(d.advertiser_name_raw) = '' THEN 1 ELSE 0 END) AS missing_advertiser_name,
            SUM(CASE WHEN d.creative_image_path IS NULL OR TRIM(d.creative_image_path) = '' THEN 1 ELSE 0 END) AS missing_creative_image,
            SUM(CASE WHEN d.display_url IS NULL OR TRIM(d.display_url) = '' THEN 1 ELSE 0 END) AS missing_display_url
        FROM ad_details d
        JOIN ad_snapshots s ON s.id = d.snapshot_id
        GROUP BY s.channel
        ORDER BY total_ad_details DESC
        """
    ).fetchall()
    quality_by_channel = {row["channel"]: dict(row) for row in quality_channel_rows}

    staging_channel_rows = conn.execute(
        """
        SELECT
            channel,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
            SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) AS approved_count,
            SUM(CASE WHEN status = 'quarantine' THEN 1 ELSE 0 END) AS quarantine_count,
            SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
            SUM(CASE WHEN status = 'deduped' THEN 1 ELSE 0 END) AS deduped_count,
            COUNT(*) AS total_count
        FROM staging_ads
        GROUP BY channel
        ORDER BY total_count DESC
        """
    ).fetchall()
    staging_by_channel = {row["channel"]: dict(row) for row in staging_channel_rows}

    channels: list[dict] = []
    for row in channel_rows:
        staging = staging_by_channel.get(row["channel"], {})
        quality = quality_by_channel.get(row["channel"], {})
        channel_total_details = quality.get("total_ad_details", 0) or 0
        channels.append(
            {
                "channel": row["channel"],
                "snapshot_count": row["snapshot_count"],
                "live_ad_count": row["live_ad_count"],
                "live_advertiser_count": row["live_advertiser_count"],
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
                "last_seen_age_days": _days_since(row["last_seen_at"]),
                "recent_snapshot_count": row["recent_snapshot_count"],
                "recent_advertiser_count": row["recent_advertiser_count"],
                "retroactive_ad_count": row["retroactive_ad_count"] or 0,
                "staging_total_count": staging.get("total_count", 0),
                "staging_pending_count": staging.get("pending_count", 0),
                "staging_quarantine_count": staging.get("quarantine_count", 0),
                "staging_deduped_count": staging.get("deduped_count", 0),
                "missing_advertiser_id": quality.get("missing_advertiser_id", 0) or 0,
                "missing_advertiser_name": quality.get("missing_advertiser_name", 0) or 0,
                "missing_creative_image": quality.get("missing_creative_image", 0) or 0,
                "missing_display_url": quality.get("missing_display_url", 0) or 0,
                "missing_advertiser_id_pct": round(((quality.get("missing_advertiser_id", 0) or 0) / channel_total_details) * 100, 2) if channel_total_details else 0.0,
                "missing_creative_image_pct": round(((quality.get("missing_creative_image", 0) or 0) / channel_total_details) * 100, 2) if channel_total_details else 0.0,
            }
        )

    latest_adic_year = conn.execute(
        "SELECT MAX(year) FROM adic_ad_expenses WHERE medium = 'total'"
    ).fetchone()[0]

    adic_rows = conn.execute(
        """
        SELECT advertiser_name, ROUND(SUM(amount), 0) AS total_amount
        FROM adic_ad_expenses
        WHERE medium = 'total' AND year = ?
        GROUP BY advertiser_name
        ORDER BY total_amount DESC, advertiser_name ASC
        LIMIT ?
        """,
        (latest_adic_year, top_n),
    ).fetchall()

    observed_all = [
        _normalize_name(row[0])
        for row in conn.execute("SELECT name FROM advertisers").fetchall()
        if _normalize_name(row[0])
    ]
    observed_recent = [
        _normalize_name(row[0])
        for row in conn.execute(
            """
            SELECT DISTINCT a.name
            FROM advertisers a
            JOIN ad_details d ON d.advertiser_id = a.id
            JOIN ad_snapshots s ON s.id = d.snapshot_id
            WHERE s.captured_at >= ?
            """,
            (cutoff_text,),
        ).fetchall()
        if _normalize_name(row[0])
    ]
    observed_all_set = set(observed_all)
    observed_recent_set = set(observed_recent)

    adic_top = []
    missing_all = []
    missing_recent = []
    exact_all = contains_all = 0
    exact_recent = contains_recent = 0

    for row in adic_rows:
        target_name = row["advertiser_name"]
        target_norm = _normalize_name(target_name)

        all_hit, all_match, all_mode = _name_match(target_norm, observed_all_set, observed_all)
        recent_hit, recent_match, recent_mode = _name_match(target_norm, observed_recent_set, observed_recent)

        if all_mode == "exact":
            exact_all += 1
        elif all_mode == "contains":
            contains_all += 1

        if recent_mode == "exact":
            exact_recent += 1
        elif recent_mode == "contains":
            contains_recent += 1

        item = {
            "advertiser_name": target_name,
            "adic_total_amount": row["total_amount"],
            "covered_all_time": all_hit,
            "covered_recent": recent_hit,
            "all_time_match_mode": all_mode,
            "recent_match_mode": recent_mode,
        }
        adic_top.append(item)

        if not all_hit:
            missing_all.append(item)
        if not recent_hit:
            missing_recent.append(item)

    retro_rows = conn.execute(
        """
        SELECT archive_source, COUNT(*) AS cnt
        FROM ad_details
        WHERE is_retroactive = 1
        GROUP BY archive_source
        ORDER BY cnt DESC
        """
    ).fetchall()

    mobile_overall = {
        "device_count": conn.execute("SELECT COUNT(*) FROM mobile_panel_devices").fetchone()[0],
        "exposure_count": conn.execute("SELECT COUNT(*) FROM mobile_panel_exposures").fetchone()[0],
        "last_observed_at": conn.execute("SELECT MAX(observed_at) FROM mobile_panel_exposures").fetchone()[0],
    }
    mobile_overall["last_observed_age_days"] = _days_since(mobile_overall["last_observed_at"])

    mobile_by_app = [
        {
            "app_name": row["app_name"] or "unknown",
            "count": row["cnt"],
        }
        for row in conn.execute(
            """
            SELECT app_name, COUNT(*) AS cnt
            FROM mobile_panel_exposures
            GROUP BY app_name
            ORDER BY cnt DESC
            """
        ).fetchall()
    ]

    report = {
        "generated_at": NOW.strftime("%Y-%m-%d %H:%M:%S"),
        "db_path": str(DB_PATH),
        "recent_days": recent_days,
        "adic_year": latest_adic_year,
        "overall": overall,
        "quality_overall": quality_overall,
        "staging_status": staging_status,
        "channels": channels,
        "retroactive_breakdown": [
            {"archive_source": row["archive_source"] or "unknown", "count": row["cnt"]}
            for row in retro_rows
        ],
        "mobile_panel": {
            "overall": mobile_overall,
            "by_app": mobile_by_app,
        },
        "adic_coverage": {
            "top_n": top_n,
            "exact_all_time": exact_all,
            "contains_all_time": contains_all,
            "covered_all_time": exact_all + contains_all,
            "exact_recent": exact_recent,
            "contains_recent": contains_recent,
            "covered_recent": exact_recent + contains_recent,
            "coverage_all_time_pct": round(((exact_all + contains_all) / top_n) * 100, 2) if top_n else 0.0,
            "coverage_recent_pct": round(((exact_recent + contains_recent) / top_n) * 100, 2) if top_n else 0.0,
            "top_advertisers": adic_top,
            "missing_all_time": missing_all,
            "missing_recent": missing_recent,
        },
    }

    conn.close()
    return report


def _channel_table_md(channels: list[dict]) -> str:
    lines = [
        "| 채널 | 스냅샷 | 라이브 광고 | 광고주 | 최근 광고주 | 마지막 수집 | 경과일 | 아카이브 광고 | 광고주누락% | 이미지누락% | staging |",
        "|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in channels:
        lines.append(
            "| {channel} | {snapshot_count} | {live_ad_count} | {live_advertiser_count} | "
            "{recent_advertiser_count} | {last_seen_at} | {last_seen_age_days} | "
            "{retroactive_ad_count} | {missing_advertiser_id_pct} | {missing_creative_image_pct} | {staging_total_count} |".format(
                channel=row["channel"],
                snapshot_count=row["snapshot_count"],
                live_ad_count=row["live_ad_count"],
                live_advertiser_count=row["live_advertiser_count"],
                recent_advertiser_count=row["recent_advertiser_count"],
                last_seen_at=_fmt_dt(row["last_seen_at"]),
                last_seen_age_days=row["last_seen_age_days"] if row["last_seen_age_days"] is not None else "-",
                retroactive_ad_count=row["retroactive_ad_count"],
                missing_advertiser_id_pct=row["missing_advertiser_id_pct"],
                missing_creative_image_pct=row["missing_creative_image_pct"],
                staging_total_count=row["staging_total_count"],
            )
        )
    return "\n".join(lines)


def _top_missing_md(rows: list[dict], limit: int = 20) -> str:
    if not rows:
        return "- 없음"
    lines = []
    for row in rows[:limit]:
        lines.append(f"- {row['advertiser_name']} ({int(row['adic_total_amount'])})")
    return "\n".join(lines)


def build_markdown(report: dict) -> str:
    overall = report["overall"]
    quality = report["quality_overall"]
    adic = report["adic_coverage"]
    staging = report["staging_status"]
    mobile = report["mobile_panel"]["overall"]

    return f"""# AdScope Coverage Baseline

- 생성 시각: {report['generated_at']}
- 기준 DB: `{report['db_path']}`
- 최근 관측 기준 창: 최근 {report['recent_days']}일
- ADIC 비교 기준 연도: {report['adic_year']}

## 전체 현황

- 라이브 광고 수: {overall['ad_details']:,}
- 스냅샷 수: {overall['ad_snapshots']:,}
- 광고주 수: {overall['advertisers']:,}
- 캠페인 수: {overall['campaigns']:,}
- spend estimate 수: {overall['spend_estimates']:,}
- 마지막 수집 시각: {_fmt_dt(overall['last_crawl_at'])}
- 마지막 수집 경과일: {overall['last_crawl_age_days']}

## 데이터 품질 기준선

- advertiser_id 누락: {quality['missing_advertiser_id']:,} ({quality['missing_advertiser_id_pct']}%)
- advertiser_name_raw 누락: {quality['missing_advertiser_name']:,} ({quality['missing_advertiser_name_pct']}%)
- creative_image_path 누락: {quality['missing_creative_image']:,} ({quality['missing_creative_image_pct']}%)
- display_url 누락: {quality['missing_display_url']:,} ({quality['missing_display_url_pct']}%)
- ad_description 누락: {quality['missing_ad_description']:,} ({quality['missing_ad_description_pct']}%)

## 스테이징 현황

- pending: {staging.get('pending', 0):,}
- approved: {staging.get('approved', 0):,}
- quarantine: {staging.get('quarantine', 0):,}
- rejected: {staging.get('rejected', 0):,}
- deduped: {staging.get('deduped', 0):,}

## 채널별 기준선

{_channel_table_md(report['channels'])}

## 아카이브 비중

{os.linesep.join(f"- {row['archive_source']}: {row['count']:,}" for row in report['retroactive_breakdown']) or '- 없음'}

## 모바일 패널 기준선

- 등록 디바이스 수: {mobile['device_count']:,}
- 노출 수: {mobile['exposure_count']:,}
- 마지막 관측 시각: {_fmt_dt(mobile['last_observed_at'])}
- 마지막 관측 경과일: {mobile['last_observed_age_days']}

{os.linesep.join(f"- {row['app_name']}: {row['count']:,}" for row in report['mobile_panel']['by_app']) or '- 없음'}

## ADIC Top {adic['top_n']} 커버리지

- all-time exact match: {adic['exact_all_time']}
- all-time contains match: {adic['contains_all_time']}
- all-time coverage: {adic['covered_all_time']} / {adic['top_n']} ({adic['coverage_all_time_pct']}%)
- recent exact match: {adic['exact_recent']}
- recent contains match: {adic['contains_recent']}
- recent coverage: {adic['covered_recent']} / {adic['top_n']} ({adic['coverage_recent_pct']}%)

## ADIC Top 누락 광고주 (all-time 상위 20)

{_top_missing_md(adic['missing_all_time'])}

## ADIC Top 누락 광고주 (recent 상위 20)

{_top_missing_md(adic['missing_recent'])}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate AdScope coverage baseline report")
    parser.add_argument("--top-n", type=int, default=100, help="ADIC top advertiser pool size")
    parser.add_argument("--recent-days", type=int, default=90, help="Recent coverage window")
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    report = build_report(top_n=args.top_n, recent_days=args.recent_days)
    md_text = build_markdown(report)

    json_path = OUT_DIR / "coverage_baseline_latest.json"
    md_path = OUT_DIR / "coverage_baseline_latest.md"

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(md_text, encoding="utf-8")

    print(f"[coverage] wrote {json_path}")
    print(f"[coverage] wrote {md_path}")
    print(
        "[coverage] ADIC top {top_n} recent coverage: {covered}/{top_n} ({pct}%)".format(
            top_n=report["adic_coverage"]["top_n"],
            covered=report["adic_coverage"]["covered_recent"],
            pct=report["adic_coverage"]["coverage_recent_pct"],
        )
    )
    print(
        "[coverage] last crawl: {last} ({age} days ago)".format(
            last=_fmt_dt(report["overall"]["last_crawl_at"]),
            age=report["overall"]["last_crawl_age_days"],
        )
    )


if __name__ == "__main__":
    main()
