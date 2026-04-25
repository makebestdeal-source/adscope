# Social Signal Boost

- started_at: 2026-04-25 20:10:34
- finished_at: 2026-04-25 20:36:38
- elapsed_seconds: 1564.0

## Coverage

| Metric | Before | After |
|---|---:|---:|
| official channel advertisers | 866 | 970 |
| channel stats advertisers | 606 | 682 |
| brand content advertisers | 399 | 437 |
| news mention advertisers | 430 | 430 |
| traffic signal advertisers | 119 | 133 |

## Steps

| Step | Status | Elapsed | Result |
|---|---|---:|---|
| discover_social_channels | ok | 446.8s | `{"processed": 500, "discovered": 104, "channels_added": 241, "errors": 0}` |
| collect_brand_content | ok | 651.0s | `{"targets": 80, "processed": 80, "new_items": 793, "youtube_channels": 44, "instagram_channels": 61, "errors": 0}` |
| collect_channel_stats | ok | 260.8s | `{"targets": 120, "youtube_success": 52, "instagram_success": 67, "errors": 0}` |
| collect_news | ok | 87.1s | `{"processed": 150, "saved": 375, "errors": 0}` |
| collect_search_trends | ok | 23.8s | `{"processed": 78, "saved": 364, "errors": 0}` |
| recompute_scores | ok | 93.9s | `{"activity_scores": {"processed": 743, "created": 23, "updated": 720}, "meta_signal_composites": {"processed": 2997, "created": 16, "updated": 2981}, "social_impact_scores": {"processed": 2630, "created": 49, "updated": 2581}, "social_category_rankings": {"processed": 686, "created": 93, "industries": 21}}` |