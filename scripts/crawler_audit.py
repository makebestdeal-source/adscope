"""Generate an end-to-end crawler audit report for current collection health.

This report focuses on four questions:
- Are crawlers still producing fresh live data?
- Do recent raw/staging rows contain the fields required downstream?
- Are rows being blocked in washing/promotion?
- Are there runtime blockers visible in scheduler logs?

Outputs:
- cache/reports/crawler_audit_latest.json
- cache/reports/crawler_audit_latest.md

Usage:
    python scripts/crawler_audit.py
    python scripts/crawler_audit.py --sample-size 100
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "adscope.db"
OUT_DIR = ROOT / "cache" / "reports"
LOG_PATH = ROOT / "logs" / "scheduler_service.log"
SCHEDULER_DISABLED_FLAG = ROOT / ".scheduler_disabled"
NOW = datetime.now()

CHANNEL_CRAWLERS = {
    "naver_search": "crawler.naver_search.NaverSearchCrawler",
    "naver_da": "crawler.naver_da.NaverDACrawler",
    "google_gdn": "crawler.google_gdn.GoogleGDNCrawler",
    "google_search_ads": "crawler.google_search_ads.GoogleSearchAdsCrawler",
    "kakao_da": "crawler.kakao_da.KakaoDACrawler",
    "youtube_ads": "crawler.youtube_ads.YouTubeAdsCrawler",
    "meta": "crawler.meta_library.MetaLibraryCrawler",
    "tiktok_ads": "crawler.tiktok_ads.TikTokAdsCrawler",
    "naver_shopping": "crawler.naver_shopping.NaverShoppingCrawler",
}

CHANNEL_ORDER = list(CHANNEL_CRAWLERS.keys())

RAW_CORE_FIELDS = [
    "advertiser_name",
    "ad_text",
    "url",
    "display_url",
    "ad_type",
    "ad_placement",
    "ad_product_name",
    "ad_format_type",
    "campaign_purpose",
]

LIVE_FIELDS = [
    "advertiser_name_raw",
    "ad_text",
    "ad_description",
    "url",
    "display_url",
    "ad_type",
    "ad_placement",
    "ad_product_name",
    "campaign_purpose",
    "ad_format_type",
    "creative_image_path",
]

GALLERY_REQUIRED_FIELDS = [
    "advertiser_name",
    "ad_text",
    "ad_type",
    "url",
]

RESEARCH_REQUIRED_FIELDS = [
    "advertiser_name",
    "ad_placement",
]

SHOPPING_REQUIRED_EXTRA_FIELDS = [
    "keyword",
    "price",
    "shopping_category",
]

CHANNEL_NOTES = {
    "naver_search": "Core search fields are extracted directly from SERP HTML. Bizsite path intentionally leaves display_url empty.",
    "naver_da": "Display crawler resolves click/adomain URLs before promotion and skips ads without a final URL.",
    "google_gdn": "Transparency crawl uses placeholder text/display domain; image quality improves only after preview download.",
    "google_search_ads": "Crawler only trusts transparency landing_url. If landing_url is absent, URL/display_url stay empty and washing quarantines the row.",
    "kakao_da": "Advertiser name often falls back to profile/domain heuristics, which is fragile on SDK banner/native payloads.",
    "youtube_ads": "Transparency video rows depend on landing_url from Google payload; many rows end up with no usable destination URL.",
    "meta": "Rows with missing URL are still emitted and later filtered in washing. Creative screenshots depend on card-level capture success.",
    "tiktok_ads": "Advertiser extraction is weak and fallback URL can be a Creative Center modal rather than the real landing page.",
    "naver_shopping": "Shopping rows rely on mall/store metadata and adcr resolution; missing mall info weakens advertiser quality.",
}


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


def _pct(value: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((value / total) * 100, 2)


def _missing_text(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _payload_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _field_present(payload: dict, field: str) -> bool:
    value = payload.get(field)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _extra_field_present(payload: dict, field: str) -> bool:
    extra = _payload_dict(payload.get("extra_data"))
    value = extra.get(field)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _load_snapshot_health(conn: sqlite3.Connection) -> dict[str, dict]:
    rows = conn.execute(
        """
        SELECT
            s.channel,
            COUNT(DISTINCT s.id) AS snapshot_count,
            COUNT(d.id) AS live_ad_count,
            COUNT(DISTINCT d.advertiser_id) AS live_advertiser_count,
            MIN(s.captured_at) AS first_captured_at,
            MAX(s.captured_at) AS last_captured_at
        FROM ad_snapshots s
        LEFT JOIN ad_details d ON d.snapshot_id = s.id
        GROUP BY s.channel
        ORDER BY s.channel
        """
    ).fetchall()
    return {
        row["channel"]: {
            "snapshot_count": int(row["snapshot_count"] or 0),
            "live_ad_count": int(row["live_ad_count"] or 0),
            "live_advertiser_count": int(row["live_advertiser_count"] or 0),
            "first_captured_at": row["first_captured_at"],
            "last_captured_at": row["last_captured_at"],
            "last_captured_age_days": _days_since(row["last_captured_at"]),
        }
        for row in rows
    }


def _load_live_completeness(conn: sqlite3.Connection) -> dict[str, dict]:
    sum_sql = []
    for field in LIVE_FIELDS:
        sum_sql.append(
            f"SUM(CASE WHEN d.{field} IS NULL OR TRIM(CAST(d.{field} AS TEXT)) = '' THEN 1 ELSE 0 END) AS missing_{field}"
        )
    sql = f"""
        SELECT
            s.channel AS channel,
            COUNT(*) AS total_rows,
            {", ".join(sum_sql)}
        FROM ad_details d
        JOIN ad_snapshots s ON s.id = d.snapshot_id
        GROUP BY s.channel
        ORDER BY s.channel
    """
    rows = conn.execute(sql).fetchall()
    output: dict[str, dict] = {}
    for row in rows:
        total = int(row["total_rows"] or 0)
        fields = {}
        for field in LIVE_FIELDS:
            missing = int(row[f"missing_{field}"] or 0)
            fields[field] = {
                "missing": missing,
                "present": max(total - missing, 0),
                "present_pct": round(100.0 - _pct(missing, total), 2),
                "missing_pct": _pct(missing, total),
            }
        output[row["channel"]] = {
            "total_rows": total,
            "fields": fields,
        }
    return output


def _load_latest_batches(conn: sqlite3.Connection) -> dict[str, dict]:
    rows = conn.execute(
        """
        SELECT
            channel,
            batch_id,
            MIN(created_at) AS batch_started_at,
            MAX(created_at) AS batch_finished_at,
            COUNT(*) AS total_rows
        FROM staging_ads
        GROUP BY channel, batch_id
        ORDER BY channel, MAX(created_at) DESC
        """
    ).fetchall()

    latest: dict[str, dict] = {}
    for row in rows:
        channel = row["channel"]
        if channel in latest:
            continue
        batch_id = row["batch_id"]
        status_rows = conn.execute(
            """
            SELECT status, COUNT(*) AS cnt
            FROM staging_ads
            WHERE batch_id = ?
            GROUP BY status
            ORDER BY cnt DESC, status
            """,
            (batch_id,),
        ).fetchall()
        rejection_rows = conn.execute(
            """
            SELECT rejection_reason, COUNT(*) AS cnt
            FROM staging_ads
            WHERE batch_id = ?
              AND rejection_reason IS NOT NULL
              AND TRIM(rejection_reason) <> ''
            GROUP BY rejection_reason
            ORDER BY cnt DESC, rejection_reason
            LIMIT 5
            """,
            (batch_id,),
        ).fetchall()
        latest[channel] = {
            "batch_id": batch_id,
            "batch_started_at": row["batch_started_at"],
            "batch_finished_at": row["batch_finished_at"],
            "batch_age_days": _days_since(row["batch_finished_at"]),
            "total_rows": int(row["total_rows"] or 0),
            "status_counts": {r["status"]: int(r["cnt"] or 0) for r in status_rows},
            "top_rejection_reasons": [
                {"reason": r["rejection_reason"], "count": int(r["cnt"] or 0)}
                for r in rejection_rows
            ],
        }
    return latest


def _load_recent_staging_sample(conn: sqlite3.Connection, channel: str, sample_size: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, created_at, status, rejection_reason, raw_payload
        FROM staging_ads
        WHERE channel = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (channel, sample_size),
    ).fetchall()


def _summarize_recent_raw(rows: list[sqlite3.Row], channel: str) -> dict:
    total = len(rows)
    field_missing = Counter()
    status_counts = Counter()
    rejection_counts = Counter()
    gallery_ready = 0
    research_ready = 0
    shopping_ready = 0

    for row in rows:
        payload = _payload_dict(row["raw_payload"])
        status_counts[row["status"] or "unknown"] += 1
        if row["rejection_reason"]:
            rejection_counts[row["rejection_reason"]] += 1

        for field in RAW_CORE_FIELDS:
            if not _field_present(payload, field):
                field_missing[field] += 1

        if all(_field_present(payload, field) for field in GALLERY_REQUIRED_FIELDS):
            gallery_ready += 1
        if all(_field_present(payload, field) for field in RESEARCH_REQUIRED_FIELDS):
            research_ready += 1
        if channel == "naver_shopping":
            if all(_extra_field_present(payload, field) for field in SHOPPING_REQUIRED_EXTRA_FIELDS):
                shopping_ready += 1

    fields = {}
    for field in RAW_CORE_FIELDS:
        missing = int(field_missing[field])
        fields[field] = {
            "missing": missing,
            "present": max(total - missing, 0),
            "present_pct": round(100.0 - _pct(missing, total), 2),
            "missing_pct": _pct(missing, total),
        }

    output = {
        "sample_size": total,
        "field_completeness": fields,
        "status_counts": dict(status_counts),
        "top_rejection_reasons": [
            {"reason": reason, "count": count}
            for reason, count in rejection_counts.most_common(5)
        ],
        "gallery_ready_pct": _pct(gallery_ready, total),
        "research_ready_pct": _pct(research_ready, total),
    }
    if channel == "naver_shopping":
        output["shopping_sheet_ready_pct"] = _pct(shopping_ready, total)
    return output


def _parse_scheduler_log() -> dict:
    data = {
        "log_exists": LOG_PATH.exists(),
        "playwright_launch_failures": Counter(),
        "circuit_open_events": Counter(),
        "latest_crawl_finished": {},
    }
    if not LOG_PATH.exists():
        return data

    launch_re = re.compile(r"channel ([a-z_]+) attempt \d+/\d+ failed: BrowserType\.launch")
    circuit_re = re.compile(r"circuit breaker OPEN(?:ED)? for ([a-z_]+)")
    finished_re = re.compile(r"crawl finished: .* ads (\d+), errors (\d+), saved (\d+)")

    last_finished_line = None
    for line in LOG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = launch_re.search(line)
        if m:
            data["playwright_launch_failures"][m.group(1)] += 1
        m = circuit_re.search(line)
        if m:
            data["circuit_open_events"][m.group(1)] += 1
        m = finished_re.search(line)
        if m:
            last_finished_line = {
                "ads": int(m.group(1)),
                "errors": int(m.group(2)),
                "saved": int(m.group(3)),
                "line": line.strip(),
            }

    data["playwright_launch_failures"] = dict(data["playwright_launch_failures"])
    data["circuit_open_events"] = dict(data["circuit_open_events"])
    data["latest_crawl_finished"] = last_finished_line or {}
    return data


def _verdict(channel: str, snapshot: dict, raw_recent: dict, latest_batch: dict, log_data: dict, scheduler_disabled: bool) -> tuple[str, list[str]]:
    reasons: list[str] = []
    score = 100

    age_days = snapshot.get("last_captured_age_days")
    if age_days is None:
        score -= 40
        reasons.append("no live snapshots")
    elif age_days > 21:
        score -= 35
        reasons.append("live data is older than 21 days")
    elif age_days > 7:
        score -= 20
        reasons.append("live data is older than 7 days")

    sample_size = int(raw_recent.get("sample_size") or 0)
    gallery_ready_pct = float(raw_recent.get("gallery_ready_pct") or 0.0)
    research_ready_pct = float(raw_recent.get("research_ready_pct") or 0.0)
    if sample_size > 0 and gallery_ready_pct < 50:
        score -= 20
        reasons.append("recent raw rows are not gallery-ready")
    if sample_size > 0 and research_ready_pct < 60:
        score -= 15
        reasons.append("recent raw rows are missing advertiser or placement")

    url_missing_pct = raw_recent.get("field_completeness", {}).get("url", {}).get("missing_pct", 0.0)
    advertiser_missing_pct = raw_recent.get("field_completeness", {}).get("advertiser_name", {}).get("missing_pct", 0.0)
    if sample_size > 0 and url_missing_pct >= 80:
        score -= 20
        reasons.append("recent raw rows are mostly missing URL")
    if sample_size > 0 and advertiser_missing_pct >= 40:
        score -= 15
        reasons.append("recent raw rows are often missing advertiser_name")

    total_batch_rows = int(latest_batch.get("total_rows") or 0)
    status_counts = latest_batch.get("status_counts", {})
    quarantine_ratio = _pct(int(status_counts.get("quarantine", 0)), total_batch_rows)
    if total_batch_rows > 0 and quarantine_ratio >= 50:
        score -= 20
        reasons.append("latest staging batch is heavily quarantined")

    if scheduler_disabled:
        score -= 25
        reasons.append("automatic scheduler is disabled")

    if log_data.get("playwright_launch_failures", {}).get(channel, 0) > 0:
        score -= 15
        reasons.append("scheduler log shows Playwright launch failures")

    if score >= 80:
        label = "healthy"
    elif score >= 60:
        label = "degraded"
    elif score >= 40:
        label = "at_risk"
    else:
        label = "broken"

    return label, reasons[:4]


def build_report(sample_size: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    snapshot_health = _load_snapshot_health(conn)
    live_completeness = _load_live_completeness(conn)
    latest_batches = _load_latest_batches(conn)
    log_data = _parse_scheduler_log()
    scheduler_disabled = SCHEDULER_DISABLED_FLAG.exists()

    channels = []
    for channel in CHANNEL_ORDER:
        snapshot = snapshot_health.get(channel, {})
        live = live_completeness.get(channel, {"total_rows": 0, "fields": {}})
        latest_batch = latest_batches.get(channel, {})
        recent_rows = _load_recent_staging_sample(conn, channel, sample_size)
        raw_recent = _summarize_recent_raw(recent_rows, channel)
        verdict, reasons = _verdict(channel, snapshot, raw_recent, latest_batch, log_data, scheduler_disabled)

        channels.append(
            {
                "channel": channel,
                "crawler_class": CHANNEL_CRAWLERS[channel],
                "verdict": verdict,
                "verdict_reasons": reasons,
                "snapshot_health": snapshot,
                "latest_batch": latest_batch,
                "recent_raw": raw_recent,
                "live_completeness": live,
                "code_note": CHANNEL_NOTES.get(channel, ""),
                "log_summary": {
                    "playwright_launch_failures": int(log_data.get("playwright_launch_failures", {}).get(channel, 0) or 0),
                    "circuit_open_events": int(log_data.get("circuit_open_events", {}).get(channel, 0) or 0),
                },
            }
        )

    overview = {
        "generated_at": NOW.strftime("%Y-%m-%d %H:%M:%S"),
        "db_path": str(DB_PATH),
        "scheduler_disabled": scheduler_disabled,
        "scheduler_disabled_updated_at": (
            datetime.fromtimestamp(SCHEDULER_DISABLED_FLAG.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            if scheduler_disabled
            else None
        ),
        "channels_audited": len(channels),
        "raw_sample_size_per_channel": sample_size,
        "latest_live_crawl_at": conn.execute("SELECT MAX(captured_at) FROM ad_snapshots").fetchone()[0],
        "latest_staging_created_at": conn.execute("SELECT MAX(created_at) FROM staging_ads").fetchone()[0],
        "staging_status_totals": {
            row["status"]: int(row["cnt"] or 0)
            for row in conn.execute(
                "SELECT status, COUNT(*) AS cnt FROM staging_ads GROUP BY status ORDER BY cnt DESC"
            ).fetchall()
        },
        "runtime_blockers": [
            blocker
            for blocker, present in [
                ("scheduler_disabled_flag", scheduler_disabled),
                ("playwright_launch_failures_in_scheduler_log", bool(log_data.get("playwright_launch_failures"))),
            ]
            if present
        ],
    }

    expected_fields = {
        "base_crawler_minimum": [
            "keyword",
            "persona_code",
            "device",
            "channel",
            "captured_at",
            "screenshot_path",
            "ads[].advertiser_name",
            "ads[].ad_text",
            "ads[].url",
            "ads[].position",
            "ads[].ad_type",
            "ads[].extra_data",
        ],
        "raw_core_fields_checked": RAW_CORE_FIELDS,
        "gallery_required_fields": GALLERY_REQUIRED_FIELDS,
        "research_sheet_required_fields": RESEARCH_REQUIRED_FIELDS,
        "naver_shopping_extra_fields": SHOPPING_REQUIRED_EXTRA_FIELDS,
    }

    conn.close()

    return {
        "overview": overview,
        "expected_fields": expected_fields,
        "log_summary": log_data,
        "channels": channels,
    }


def render_markdown(report: dict) -> str:
    overview = report["overview"]
    lines = [
        "# Crawler Audit",
        "",
        f"- Generated at: {overview['generated_at']}",
        f"- Latest live crawl: {_fmt_dt(overview.get('latest_live_crawl_at'))}",
        f"- Latest staging row: {_fmt_dt(overview.get('latest_staging_created_at'))}",
        f"- Scheduler disabled: {'yes' if overview.get('scheduler_disabled') else 'no'}",
        f"- Raw sample size per channel: {overview.get('raw_sample_size_per_channel')}",
        "",
        "## What Counts As Raw-Ready",
        "",
        f"- Gallery export needs: {', '.join(report['expected_fields']['gallery_required_fields'])}",
        f"- Research sheet needs: {', '.join(report['expected_fields']['research_sheet_required_fields'])}",
        f"- Naver Shopping extra fields: {', '.join(report['expected_fields']['naver_shopping_extra_fields'])}",
        "",
        "## Global Blockers",
        "",
    ]

    blockers = overview.get("runtime_blockers") or []
    if blockers:
        for blocker in blockers:
            lines.append(f"- {blocker}")
    else:
        lines.append("- none detected")

    lines.extend([
        "",
        "## Channel Summary",
        "",
        "| Channel | Verdict | Last Live | Live Rows | Recent Raw Sample | Gallery Ready | Research Ready | Latest Batch |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ])

    for row in report["channels"]:
        snapshot = row.get("snapshot_health", {})
        raw_recent = row.get("recent_raw", {})
        batch = row.get("latest_batch", {})
        status_counts = batch.get("status_counts", {})
        status_text = ", ".join(f"{k}:{v}" for k, v in sorted(status_counts.items())) or "-"
        lines.append(
            "| {channel} | {verdict} | {last_live} | {live_rows} | {sample} | {gallery:.1f}% | {research:.1f}% | {batch_status} |".format(
                channel=row["channel"],
                verdict=row["verdict"],
                last_live=_fmt_dt(snapshot.get("last_captured_at")),
                live_rows=snapshot.get("live_ad_count", 0),
                sample=raw_recent.get("sample_size", 0),
                gallery=float(raw_recent.get("gallery_ready_pct") or 0.0),
                research=float(raw_recent.get("research_ready_pct") or 0.0),
                batch_status=status_text,
            )
        )

    for row in report["channels"]:
        snapshot = row.get("snapshot_health", {})
        raw_recent = row.get("recent_raw", {})
        live = row.get("live_completeness", {})
        batch = row.get("latest_batch", {})
        lines.extend([
            "",
            f"## {row['channel']}",
            "",
            f"- Crawler: `{row['crawler_class']}`",
            f"- Verdict: `{row['verdict']}`",
            f"- Why: {', '.join(row.get('verdict_reasons') or ['no major issue detected'])}",
            f"- Last live snapshot: {_fmt_dt(snapshot.get('last_captured_at'))} ({snapshot.get('last_captured_age_days')} days ago)",
            f"- Latest staging batch: `{batch.get('batch_id', '-')}` at {_fmt_dt(batch.get('batch_finished_at'))}",
            f"- Latest batch status counts: {json.dumps(batch.get('status_counts', {}), ensure_ascii=False)}",
            f"- Recent raw sample size: {raw_recent.get('sample_size', 0)}",
            f"- Recent raw gallery-ready: {raw_recent.get('gallery_ready_pct', 0.0)}%",
            f"- Recent raw research-ready: {raw_recent.get('research_ready_pct', 0.0)}%",
            f"- Log failures: Playwright={row.get('log_summary', {}).get('playwright_launch_failures', 0)}, circuit_open={row.get('log_summary', {}).get('circuit_open_events', 0)}",
            f"- Code note: {row.get('code_note') or '-'}",
        ])
        if row["channel"] == "naver_shopping":
            lines.append(f"- Recent raw shopping-sheet ready: {raw_recent.get('shopping_sheet_ready_pct', 0.0)}%")

        top_raw = sorted(
            raw_recent.get("field_completeness", {}).items(),
            key=lambda item: item[1].get("missing_pct", 0.0),
            reverse=True,
        )[:3]
        top_live = sorted(
            live.get("fields", {}).items(),
            key=lambda item: item[1].get("missing_pct", 0.0),
            reverse=True,
        )[:3]
        if top_raw:
            lines.append(
                "- Worst recent raw fields: "
                + ", ".join(f"{field} {stats['missing_pct']}% missing" for field, stats in top_raw)
            )
        if top_live:
            lines.append(
                "- Worst live fields: "
                + ", ".join(f"{field} {stats['missing_pct']}% missing" for field, stats in top_live)
            )
        rejection_reasons = raw_recent.get("top_rejection_reasons") or batch.get("top_rejection_reasons") or []
        if rejection_reasons:
            lines.append(
                "- Top rejection reasons: "
                + ", ".join(f"{item['reason']} ({item['count']})" for item in rejection_reasons)
            )

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate crawler audit report")
    parser.add_argument("--sample-size", type=int, default=100, help="recent staging rows per channel to inspect")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report(args.sample_size)

    json_path = OUT_DIR / "crawler_audit_latest.json"
    md_path = OUT_DIR / "crawler_audit_latest.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
