# Archive Prefix Queue

- channel: `google_gdn`
- months: `2026-01`
- batch_size: 1
- candidate_count: 432
- selected_prefixes: `제`

## Batch

| Prefix | Pending Months | Month Approved | Month Deduped | Approved | Deduped | Total Seen | Priority |
|---|---|---:|---:|---:|---:|---:|---:|
| 제 | 2026-01 | 3 | 15 | 117 | 300 | 417 | 477 |

## Suggested Command

```powershell
python scripts/archive_crawl_dated.py --months 2026-01 --channels gdn --prefixes 제 --timeout 3600
```