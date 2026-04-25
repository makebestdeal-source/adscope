# 2025 Archive Backfill Plan

- generated_at: 2026-04-24 15:52:01
- db_path: `C:\Users\user\Desktop\adscopre\adscope.db`
- year: 2025
- workers: 1

## Summary

- archive task count: 60
- archive channels: 5
- postprocess:
  - `python scripts/backfill_advertiser_links.py --limit 800`
  - `python scripts/build_campaigns_and_spend.py`

## Channel Priorities

| Channel | Weighted Gap | Retro Rows | Missing Months | Thin Months | Covered Months | Notes |
|---|---:|---:|---:|---:|---:|---|
| Google Search | 92,861,704 | 2222 | 0 | 4 | 8 | - |
| Meta Ad Library | 48,567,448 | 1126 | 12 | 0 | 0 | META_ACCESS_TOKEN 기반 API 우선 모드 권장: 기존 meta archive rows에 delivery date가 없음 |
| YouTube Ads | 36,722,096 | 173 | 2 | 10 | 0 | - |
| Google GDN | 10,302,759 | 1117 | 0 | 12 | 0 | - |
| TikTok Creative | 0 | 5 | 12 | 0 | 0 | 현행 볼륨이 매우 낮아서 pilot 후 계속 여부 결정 |

## First Tasks

| Month | Channel | Status | Existing Rows | Priority | Command |
|---|---|---|---:|---:|---|
| 2025-04 | Google Search | thin | 59 | 75837058.27 | `python scripts/archive_crawl_dated.py --months 2025-04 --channels search --timeout 14400` |
| 2025-03 | Google Search | thin | 5 | 73128591.9 | `python scripts/archive_crawl_dated.py --months 2025-03 --channels search --timeout 14400` |
| 2025-12 | Meta Ad Library | missing | 0 | 72851172.0 | `python scripts/archive_crawl.py --months 2025-12 --channels meta --timeout 14400` |
| 2025-11 | Meta Ad Library | missing | 0 | 70827528.33 | `python scripts/archive_crawl.py --months 2025-11 --channels meta --timeout 14400` |
| 2025-02 | Google Search | thin | 1 | 70420125.53 | `python scripts/archive_crawl_dated.py --months 2025-02 --channels search --timeout 14400` |
| 2025-10 | Meta Ad Library | missing | 0 | 68803884.67 | `python scripts/archive_crawl.py --months 2025-10 --channels meta --timeout 14400` |
| 2025-01 | Google Search | thin | 3 | 67711659.17 | `python scripts/archive_crawl_dated.py --months 2025-01 --channels search --timeout 14400` |
| 2025-09 | Meta Ad Library | missing | 0 | 66780241.0 | `python scripts/archive_crawl.py --months 2025-09 --channels meta --timeout 14400` |
| 2025-08 | Meta Ad Library | missing | 0 | 64756597.33 | `python scripts/archive_crawl.py --months 2025-08 --channels meta --timeout 14400` |
| 2025-07 | Meta Ad Library | missing | 0 | 62732953.67 | `python scripts/archive_crawl.py --months 2025-07 --channels meta --timeout 14400` |
| 2025-06 | Meta Ad Library | missing | 0 | 60709310.0 | `python scripts/archive_crawl.py --months 2025-06 --channels meta --timeout 14400` |
| 2025-05 | Meta Ad Library | missing | 0 | 58685666.33 | `python scripts/archive_crawl.py --months 2025-05 --channels meta --timeout 14400` |
| 2025-04 | Meta Ad Library | missing | 0 | 56662022.67 | `python scripts/archive_crawl.py --months 2025-04 --channels meta --timeout 14400` |
| 2025-03 | Meta Ad Library | missing | 0 | 54638379.0 | `python scripts/archive_crawl.py --months 2025-03 --channels meta --timeout 14400` |
| 2025-02 | Meta Ad Library | missing | 0 | 52614735.33 | `python scripts/archive_crawl.py --months 2025-02 --channels meta --timeout 14400` |
| 2025-01 | Meta Ad Library | missing | 0 | 50591091.67 | `python scripts/archive_crawl.py --months 2025-01 --channels meta --timeout 14400` |
| 2025-02 | YouTube Ads | missing | 0 | 39782270.67 | `python scripts/archive_crawl_dated.py --months 2025-02 --channels yt --timeout 14400` |
| 2025-12 | YouTube Ads | thin | 12 | 38558200.8 | `python scripts/archive_crawl_dated.py --months 2025-12 --channels yt --timeout 14400` |
| 2025-01 | YouTube Ads | missing | 0 | 38252183.33 | `python scripts/archive_crawl_dated.py --months 2025-01 --channels yt --timeout 14400` |
| 2025-11 | YouTube Ads | thin | 15 | 37487139.67 | `python scripts/archive_crawl_dated.py --months 2025-11 --channels yt --timeout 14400` |

## Worker Plan

### Worker 1
- tasks: 60
- estimated_minutes: 4964
- first_tasks:
  - 2025-04 Google Search (thin)
  - 2025-03 Google Search (thin)
  - 2025-12 Meta Ad Library (missing)
  - 2025-11 Meta Ad Library (missing)
  - 2025-02 Google Search (thin)
  - 2025-10 Meta Ad Library (missing)
