"""Generate a channel-priority report for remaining collection gaps.

This report turns ADIC collection gaps into a concrete crawler worklist by
combining:
- current advertiser gap state
- advertiser master metadata (industry / website / official channels)
- recent live channel breadth by industry

Outputs:
- cache/reports/channel_priority_latest.json
- cache/reports/channel_priority_latest.md

Usage:
    python scripts/channel_priority_report.py
    python scripts/channel_priority_report.py --top-n 100 --recent-days 90
"""

from __future__ import annotations

import argparse
import json
import math
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

from processor.advertiser_verifier import normalize_name
from scripts.advertiser_gap_report import build_report as build_gap_report


CHANNEL_LABELS = {
    "naver_search": "Naver Search",
    "google_search_ads": "Google Search",
    "naver_da": "Naver DA",
    "google_gdn": "Google GDN",
    "meta": "Meta",
    "youtube_ads": "YouTube",
    "kakao_da": "Kakao DA",
    "naver_shopping": "Naver Shopping",
    "tiktok_ads": "TikTok",
}

SOCIAL_HINT_MAP = {
    "youtube": "youtube_ads",
    "instagram": "meta",
    "facebook": "meta",
    "tiktok": "tiktok_ads",
    "smartstore": "naver_shopping",
}

GLOBAL_CHANNEL_WEIGHTS = {
    "naver_search": 1.35,
    "google_search_ads": 1.15,
    "naver_da": 1.25,
    "kakao_da": 1.2,
    "naver_shopping": 1.15,
    "youtube_ads": 1.0,
    "meta": 0.95,
    "google_gdn": 0.9,
    "tiktok_ads": 0.85,
}

INDUSTRY_BOOSTS = {
    "금융/보험": {
        "naver_search": 10.0,
        "google_search_ads": 10.0,
        "naver_da": 6.0,
        "kakao_da": 6.0,
        "youtube_ads": 5.0,
    },
    "IT/통신": {
        "naver_search": 8.0,
        "google_search_ads": 8.0,
        "youtube_ads": 7.0,
        "google_gdn": 6.0,
        "naver_da": 4.0,
    },
    "제약/헬스케어": {
        "naver_search": 9.0,
        "google_search_ads": 8.0,
        "youtube_ads": 6.0,
        "naver_da": 5.0,
    },
    "교육": {
        "naver_search": 10.0,
        "google_search_ads": 9.0,
        "youtube_ads": 6.0,
        "naver_da": 4.0,
        "kakao_da": 4.0,
    },
    "공공기관": {
        "naver_search": 10.0,
        "google_search_ads": 8.0,
        "naver_da": 6.0,
        "kakao_da": 6.0,
        "youtube_ads": 4.0,
    },
    "식품/음료": {
        "meta": 8.0,
        "youtube_ads": 7.0,
        "naver_search": 6.0,
        "google_search_ads": 5.0,
        "naver_shopping": 4.0,
    },
    "가전/전자": {
        "naver_search": 8.0,
        "google_search_ads": 8.0,
        "youtube_ads": 8.0,
        "naver_shopping": 6.0,
        "meta": 4.0,
    },
}

E_COMMERCE_HINT_INDUSTRIES = {
    "식품/음료",
    "가전/전자",
    "뷰티/화장품",
    "패션/의류",
    "생활/가정",
}


def _cutoff_text(recent_days: int) -> str:
    return datetime.fromtimestamp(NOW.timestamp() - (recent_days * 86400)).strftime("%Y-%m-%d %H:%M:%S")


def _norm(value: str | None) -> str:
    if not value:
        return ""
    return normalize_name(value).lower().strip()


def _safe_json_dict(value) -> dict:
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


def _channel_label(channel: str) -> str:
    return CHANNEL_LABELS.get(channel, channel)


def _load_master_metadata(conn: sqlite3.Connection) -> dict[str, dict]:
    rows = conn.execute(
        """
        SELECT
            a.name,
            i.name AS industry,
            a.website,
            a.official_channels
        FROM advertisers a
        LEFT JOIN industries i ON i.id = a.industry_id
        """
    ).fetchall()

    data: dict[str, dict] = {}
    for row in rows:
        key = _norm(row["name"])
        if not key or key in data:
            continue
        data[key] = {
            "name": row["name"],
            "industry": row["industry"],
            "website": row["website"],
            "official_channels": _safe_json_dict(row["official_channels"]),
        }
    return data


def _load_recent_channel_stats(conn: sqlite3.Connection, cutoff_text: str) -> dict:
    by_industry_rows = conn.execute(
        """
        SELECT
            COALESCE(i.name, '(미분류)') AS industry,
            s.channel AS channel,
            COUNT(*) AS recent_ad_count,
            COUNT(DISTINCT d.advertiser_id) AS recent_advertiser_count
        FROM ad_details d
        JOIN ad_snapshots s ON s.id = d.snapshot_id
        JOIN advertisers a ON a.id = d.advertiser_id
        LEFT JOIN industries i ON i.id = a.industry_id
        WHERE s.captured_at >= ?
        GROUP BY COALESCE(i.name, '(미분류)'), s.channel
        ORDER BY recent_advertiser_count DESC, recent_ad_count DESC
        """,
        (cutoff_text,),
    ).fetchall()

    industry_totals_rows = conn.execute(
        """
        SELECT
            COALESCE(i.name, '(미분류)') AS industry,
            COUNT(DISTINCT d.advertiser_id) AS recent_advertiser_total
        FROM ad_details d
        JOIN ad_snapshots s ON s.id = d.snapshot_id
        JOIN advertisers a ON a.id = d.advertiser_id
        LEFT JOIN industries i ON i.id = a.industry_id
        WHERE s.captured_at >= ?
        GROUP BY COALESCE(i.name, '(미분류)')
        """,
        (cutoff_text,),
    ).fetchall()

    overall_rows = conn.execute(
        """
        SELECT
            s.channel AS channel,
            COUNT(*) AS recent_ad_count,
            COUNT(DISTINCT d.advertiser_id) AS recent_advertiser_count
        FROM ad_details d
        JOIN ad_snapshots s ON s.id = d.snapshot_id
        WHERE s.captured_at >= ?
          AND d.advertiser_id IS NOT NULL
        GROUP BY s.channel
        ORDER BY recent_advertiser_count DESC, recent_ad_count DESC
        """,
        (cutoff_text,),
    ).fetchall()

    industry_totals = {
        row["industry"]: row["recent_advertiser_total"] or 0 for row in industry_totals_rows
    }
    industry_channels: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in by_industry_rows:
        industry_channels[row["industry"]][row["channel"]] = {
            "recent_ad_count": row["recent_ad_count"] or 0,
            "recent_advertiser_count": row["recent_advertiser_count"] or 0,
        }

    overall_total = sum(row["recent_advertiser_count"] or 0 for row in overall_rows)
    overall_channels = {
        row["channel"]: {
            "recent_ad_count": row["recent_ad_count"] or 0,
            "recent_advertiser_count": row["recent_advertiser_count"] or 0,
        }
        for row in overall_rows
    }

    return {
        "industry_totals": industry_totals,
        "industry_channels": industry_channels,
        "overall_total": overall_total,
        "overall_channels": overall_channels,
    }


def _add_score(
    scores: dict[str, float],
    reasons: dict[str, list[str]],
    channel: str,
    points: float,
    reason: str,
) -> None:
    scores[channel] += points
    reasons[channel].append(reason)


def _apply_industry_peer_scores(
    industry: str | None,
    stats: dict,
    scores: dict[str, float],
    reasons: dict[str, list[str]],
) -> int:
    if not industry:
        return 0

    industry_total = stats["industry_totals"].get(industry, 0)
    channel_rows = stats["industry_channels"].get(industry, {})
    if not industry_total or not channel_rows:
        return 0

    supporting_channels = 0
    for channel, row in channel_rows.items():
        peer_adv_count = row["recent_advertiser_count"]
        share = peer_adv_count / industry_total if industry_total else 0.0
        points = round((share * 70.0) + min(peer_adv_count, 12), 2)
        _add_score(
            scores,
            reasons,
            channel,
            points,
            f"peer {industry}: {peer_adv_count}/{industry_total} advertisers observed recently",
        )
        supporting_channels += 1
    return supporting_channels


def _apply_global_fallback_scores(stats: dict, scores: dict[str, float], reasons: dict[str, list[str]]) -> None:
    overall_total = stats["overall_total"] or 0
    for channel, row in stats["overall_channels"].items():
        adv_count = row["recent_advertiser_count"]
        share = adv_count / overall_total if overall_total else 0.0
        base_points = (share * 30.0) + min(math.sqrt(max(adv_count, 1)), 8.0)
        points = round(base_points * GLOBAL_CHANNEL_WEIGHTS.get(channel, 1.0), 2)
        _add_score(
            scores,
            reasons,
            channel,
            points,
            f"global fallback: {adv_count} advertisers observed recently",
        )


def _apply_metadata_boosts(meta: dict, scores: dict[str, float], reasons: dict[str, list[str]]) -> None:
    website = (meta.get("website") or "").strip()
    industry = meta.get("industry")
    official_channels = meta.get("official_channels") or {}

    if website:
        _add_score(scores, reasons, "naver_search", 8.0, "website present")
        _add_score(scores, reasons, "google_search_ads", 8.0, "website present")

    for key, channel in SOCIAL_HINT_MAP.items():
        value = official_channels.get(key)
        if value:
            _add_score(scores, reasons, channel, 16.0, f"official channel hint: {key}")

    if industry in E_COMMERCE_HINT_INDUSTRIES:
        _add_score(scores, reasons, "naver_shopping", 5.0, f"industry hint: {industry}")

    for channel, points in INDUSTRY_BOOSTS.get(industry, {}).items():
        _add_score(scores, reasons, channel, points, f"industry boost: {industry}")


def _build_target_priority_row(item: dict, meta: dict, stats: dict) -> dict:
    scores: defaultdict[str, float] = defaultdict(float)
    reasons: defaultdict[str, list[str]] = defaultdict(list)

    supporting_channels = _apply_industry_peer_scores(meta.get("industry"), stats, scores, reasons)
    _apply_metadata_boosts(meta, scores, reasons)
    if not scores or supporting_channels == 0:
        _apply_global_fallback_scores(stats, scores, reasons)

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    recommendations = []
    for channel, score in ranked[:5]:
        overall = stats["overall_channels"].get(channel, {})
        recommendations.append(
            {
                "channel": channel,
                "channel_label": _channel_label(channel),
                "score": round(score, 2),
                "recent_live_advertiser_count": overall.get("recent_advertiser_count", 0),
                "recent_live_ad_count": overall.get("recent_ad_count", 0),
                "reasons": reasons[channel][:3],
            }
        )

    return {
        "advertiser_name": item["advertiser_name"],
        "adic_amount": int(item["adic_amount"]),
        "industry": meta.get("industry") or "",
        "website": meta.get("website") or "",
        "official_channel_keys": sorted((meta.get("official_channels") or {}).keys()),
        "recommended_channels": recommendations,
    }


def _build_channel_summary(target_rows: list[dict]) -> list[dict]:
    channel_totals: dict[str, dict] = {}
    weights = [1.0, 0.7, 0.5, 0.35, 0.2]

    for row in target_rows:
        amount = row["adic_amount"]
        for index, rec in enumerate(row["recommended_channels"][: len(weights)]):
            channel = rec["channel"]
            total = channel_totals.setdefault(
                channel,
                {
                    "channel": channel,
                    "channel_label": rec["channel_label"],
                    "weighted_gap_amount": 0.0,
                    "gap_advertiser_count": 0,
                    "recent_live_advertiser_count": rec["recent_live_advertiser_count"],
                    "recent_live_ad_count": rec["recent_live_ad_count"],
                    "top_examples": [],
                    "industries": defaultdict(float),
                },
            )
            total["weighted_gap_amount"] += amount * weights[index]
            total["gap_advertiser_count"] += 1
            industry = row["industry"] or "(미분류)"
            total["industries"][industry] += amount * weights[index]
            total["top_examples"].append((amount * weights[index], row["advertiser_name"]))

    rows = []
    for total in channel_totals.values():
        industries = sorted(total["industries"].items(), key=lambda kv: (-kv[1], kv[0]))
        examples = sorted(total["top_examples"], key=lambda kv: (-kv[0], kv[1]))
        rows.append(
            {
                "channel": total["channel"],
                "channel_label": total["channel_label"],
                "weighted_gap_amount": round(total["weighted_gap_amount"], 0),
                "gap_advertiser_count": total["gap_advertiser_count"],
                "recent_live_advertiser_count": total["recent_live_advertiser_count"],
                "recent_live_ad_count": total["recent_live_ad_count"],
                "top_examples": [name for _, name in examples[:5]],
                "top_industries": [
                    {"industry": name, "weighted_gap_amount": round(value, 0)}
                    for name, value in industries[:4]
                ],
            }
        )

    return sorted(rows, key=lambda item: (-item["weighted_gap_amount"], item["channel"]))


def build_report(top_n: int, recent_days: int) -> dict:
    gap_report = build_gap_report(top_n=top_n, recent_days=recent_days)
    collection_gaps = [item for item in gap_report["targets"] if item["gap_bucket"] == "collection_gap"]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    master = _load_master_metadata(conn)
    stats = _load_recent_channel_stats(conn, _cutoff_text(recent_days))
    conn.close()

    target_rows = []
    for item in collection_gaps:
        meta = master.get(_norm(item["advertiser_name"]), {})
        target_rows.append(_build_target_priority_row(item=item, meta=meta, stats=stats))

    target_rows = sorted(target_rows, key=lambda row: (-row["adic_amount"], row["advertiser_name"]))
    channel_summary = _build_channel_summary(target_rows)

    return {
        "generated_at": NOW.strftime("%Y-%m-%d %H:%M:%S"),
        "db_path": str(DB_PATH),
        "recent_days": recent_days,
        "adic_year": gap_report["adic_year"],
        "summary": {
            "top_n": top_n,
            "collection_gap_count": len(collection_gaps),
            "collection_gap_amount": sum(item["adic_amount"] for item in collection_gaps),
            "collection_gap_amount_pct": next(
                (row["amount_share_pct"] for row in gap_report["bucket_summary"] if row["bucket"] == "collection_gap"),
                0.0,
            ),
        },
        "channel_summary": channel_summary,
        "targets": target_rows,
    }


def _channel_table_md(rows: list[dict], limit: int = 8) -> str:
    if not rows:
        return "- none"

    lines = [
        "| Priority Channel | Weighted Gap Amount | Gap Advertisers | Current Recent Advertisers | Top Gap Examples |",
        "|---|---:|---:|---:|---|",
    ]
    for row in rows[:limit]:
        lines.append(
            "| {label} | {amount:,.0f} | {count} | {recent_count} | {examples} |".format(
                label=row["channel_label"],
                amount=row["weighted_gap_amount"],
                count=row["gap_advertiser_count"],
                recent_count=row["recent_live_advertiser_count"],
                examples=", ".join(row["top_examples"][:3]) or "-",
            )
        )
    return "\n".join(lines)


def _target_table_md(rows: list[dict], limit: int = 20) -> str:
    if not rows:
        return "- none"

    lines = [
        "| Advertiser | ADIC Amount | Industry | Recommended Channels |",
        "|---|---:|---|---|",
    ]
    for row in rows[:limit]:
        channel_text = ", ".join(
            f"{rec['channel_label']}({rec['score']})" for rec in row["recommended_channels"][:3]
        )
        lines.append(
            "| {name} | {amount:,} | {industry} | {channels} |".format(
                name=row["advertiser_name"],
                amount=row["adic_amount"],
                industry=row["industry"] or "(미분류)",
                channels=channel_text or "-",
            )
        )
    return "\n".join(lines)


def _channel_notes_md(rows: list[dict], limit: int = 5) -> str:
    if not rows:
        return "- none"

    notes = []
    for row in rows[:limit]:
        industries = ", ".join(
            f"{item['industry']}:{item['weighted_gap_amount']:,.0f}" for item in row["top_industries"][:3]
        )
        notes.append(
            "- {label}: weighted gap {amount:,.0f}, current recent advertisers {recent}, key industries {industries}".format(
                label=row["channel_label"],
                amount=row["weighted_gap_amount"],
                recent=row["recent_live_advertiser_count"],
                industries=industries or "(미분류)",
            )
        )
    return "\n".join(notes)


def build_markdown(report: dict) -> str:
    summary = report["summary"]
    return f"""# AdScope Channel Priority Report

- generated_at: {report['generated_at']}
- db_path: `{report['db_path']}`
- recent_window_days: {report['recent_days']}
- adic_year: {report['adic_year']}

## Summary

- ADIC top {summary['top_n']} collection gaps: {summary['collection_gap_count']}
- collection gap amount: {summary['collection_gap_amount']:,} ({summary['collection_gap_amount_pct']}%)

## Channel Priorities

{_channel_table_md(report['channel_summary'])}

## Why These Channels

{_channel_notes_md(report['channel_summary'])}

## Top Gap Advertisers

{_target_table_md(report['targets'])}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate AdScope channel priority report")
    parser.add_argument("--top-n", type=int, default=100, help="ADIC top advertiser pool size")
    parser.add_argument("--recent-days", type=int, default=90, help="Recent coverage window")
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    report = build_report(top_n=args.top_n, recent_days=args.recent_days)
    md_text = build_markdown(report)

    json_path = OUT_DIR / "channel_priority_latest.json"
    md_path = OUT_DIR / "channel_priority_latest.md"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")

    print(f"[channel-priority] wrote {json_path}")
    print(f"[channel-priority] wrote {md_path}")
    if report["channel_summary"]:
        top = report["channel_summary"][0]
        print(
            "[channel-priority] top target: {channel} weighted_gap={amount:,.0f} advertisers={count}".format(
                channel=top["channel"],
                amount=top["weighted_gap_amount"],
                count=top["gap_advertiser_count"],
            )
        )


if __name__ == "__main__":
    main()
