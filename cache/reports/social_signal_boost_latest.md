# Social Signal Boost

- started_at: 2026-04-29 23:08:55
- finished_at: 2026-04-30 00:05:13
- elapsed_seconds: 3378.5

## Coverage

| Metric | Before | After |
|---|---:|---:|
| official channel advertisers | 0 | 306 |
| channel stats advertisers | 0 | 280 |
| brand content advertisers | 0 | 238 |
| news mention advertisers | 0 | 279 |
| traffic signal advertisers | 0 | 0 |

## Steps

| Step | Status | Elapsed | Result |
|---|---|---:|---|
| discover_social_channels | ok | 360.6s | `{"processed": 623, "discovered": 306, "channels_added": 627, "errors": 0}` |
| collect_brand_content | ok | 2346.5s | `{"targets": 306, "processed": 306, "new_items": 5844, "youtube_channels": 162, "instagram_channels": 268, "errors": 0}` |
| collect_channel_stats | ok | 492.0s | `{"targets": 306, "youtube_success": 153, "instagram_success": 256, "errors": 0}` |
| collect_news | ok | 171.0s | `{"processed": 300, "saved": 2669, "errors": 0}` |
| collect_search_trends | ok | 0.0s | `{"processed": 0, "saved": 0, "errors": 0}` |
| recompute_scores | ok | 8.3s | `{"activity_scores_error": "(sqlite3.OperationalError) no such table: serpapi_ads\n[SQL: \n        SELECT json_extract(extra_data, '$.network') AS net,\n               COUNT(*) AS cnt\n        FROM serpapi_ads\n        WHERE advertis", "meta_signal_composites_error": "(sqlite3.OperationalError) no such table: serpapi_ads\n[SQL: \n        SELECT json_extract(extra_data, '$.network') AS net, COUNT(*) AS cnt\n        FROM serpapi_ads\n        WHERE advertiser_name LIKE 's", "social_impact_scores": {` |