# Archive Shard Commands

- channel: `google_search_ads`
- script: `scripts/archive_crawl_dated.py`
- months: `2025-10, 2025-11, 2025-12`
- workers: 4
- timeout: 5400
- max_prefixes: full

## Commands

### Worker 0/4

```powershell
python scripts/archive_crawl_dated.py --months 2025-10,2025-11,2025-12 --channels search --timeout 5400 --worker-index 0 --worker-count 4
```

### Worker 1/4

```powershell
python scripts/archive_crawl_dated.py --months 2025-10,2025-11,2025-12 --channels search --timeout 5400 --worker-index 1 --worker-count 4
```

### Worker 2/4

```powershell
python scripts/archive_crawl_dated.py --months 2025-10,2025-11,2025-12 --channels search --timeout 5400 --worker-index 2 --worker-count 4
```

### Worker 3/4

```powershell
python scripts/archive_crawl_dated.py --months 2025-10,2025-11,2025-12 --channels search --timeout 5400 --worker-index 3 --worker-count 4
```

## Notes

- 같은 PC에서는 `2 workers` 정도부터 시작하는 편이 안전합니다.
- 여러 PC에서 독립 DB로 수집하면 병합은 `scripts/merge_dbs.py`가 더 안전합니다.
- 동일 DB에 너무 많은 worker를 붙이면 SQLite write lock이 병목이 될 수 있습니다.