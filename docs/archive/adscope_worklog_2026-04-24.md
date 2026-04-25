# AdScope Worklog Archive

Modified date: 2026-04-24 22:23 KST

## Summary

Today's work focused on restoring creative-data quality, filtering unusable rows, rebuilding campaign/spend outputs, deploying the corrected database/API, validating live crawler behavior with low memory pressure, and refreshing product/service documentation for the next pricing and keyword-material direction.

## Code And Data Changes

- Added `scripts/fix_meta_generic_advertisers.py` to repair Meta rows where CTA text such as `Learn More` or `Shop Now` was incorrectly used as advertiser name.
- Added `tests/test_fix_meta_generic_advertisers.py`.
- Updated `processor/campaign_builder.py` to join `Advertiser` explicitly during aggregate collection, removing a slow cartesian-product query path.
- Ran image backfill and unusable-creative rejection for recent media rows.
- Rebuilt campaigns and spend estimates after quality corrections.
- Updated ad creative gallery policy so low-quality `naver_shopping` creatives are hidden from the gallery.
- Updated ad creative gallery policy so `youtube_ads`/`youtube_surf` and `meta`/`meta_feed` are grouped instead of shown as separate creative channels.

## Quality Fix Results

- Meta generic advertiser repair:
  - Rows scanned: 492
  - Generic rows found: 25
  - Renamed from landing-domain fallback: 20
  - Rejected: 5
- Creative image backfill:
  - Rows scanned: 1,402
  - Rows needing backfill: 171
  - Rows updated: 133
  - Downloaded assets: 133
  - Resolved from preview: 163
  - Failed downloads: 30
- Unusable creative rejection:
  - Rows rejected: 38
  - Google GDN: 33
  - YouTube Ads: 5

## Validation

- Python compile checks passed for edited scripts.
- Targeted tests passed: 24 passed, 2 warnings.
- Data quality gate passed for:
  - `google_gdn`
  - `google_search_ads`
  - `kakao_da`
  - `meta`
  - `naver_da`
  - `naver_search`
  - `tiktok_ads`
  - `youtube_ads`

## Campaign And Spend Rebuild

- Rebuild completed without the previous cartesian-product warning.
- Linked details: 8
- Created advertisers: 1
- Industry backfilled: 10
- Updated campaigns: 6,679
- Inserted spend estimates: 38,765
- Total campaigns: 8,331
- Total spend estimates: 46,214

## Deployment

- DB sync to Railway completed.
- Compressed DB upload was accepted by Railway.
- Backend deployment completed successfully.
- Latest deployment ID: `dbc8d565-e0ed-4343-bc26-ccda2c708ce8`
- API health check passed: `/api/auth/plans` returned `200`.
- Public stats check passed:
  - Total ads: 46,562
  - Total advertisers: 6,091
  - Active advertisers in 7 days: 419

## Live Crawler Validation

Low-load sequential validation completed across 9 channels.

- `naver_search`: ok, 5 ads, advertiser missing 0%, URL missing 0%.
- `naver_da`: ok, 2 ads, advertiser missing 0%, URL missing 0%.
- `naver_shopping`: ok, 2 ads, advertiser missing 0%, URL missing 0%, but gallery quality is poor and should be hidden from ad creative view.
- `kakao_da`: ok, 18 ads, URL missing 0%, advertiser missing 77.78%.
- `google_gdn`: ok, 31 ads from 1,819 raw candidates, advertiser missing 0%, URL missing 0%.
- `google_search_ads`: ok, 10 ads from 506 raw candidates, advertiser missing 0%, URL missing 0%.
- `youtube_ads`: ok, 37 ads from 1,699 raw candidates, 31 preview images saved, advertiser missing 0%, URL missing 0%.
- `tiktok_ads`: ok, 13 ads from 26 raw candidates, covers 13/13 downloaded, advertiser missing 84.62%.
- `meta`: ok, 14 ads, advertiser missing 0%, URL missing 0%.

## Known Issues

- `.scheduler_disabled` still exists, so continuous scheduled crawling is not currently active.
- Railway variables still use default `ADMIN_PASSWORD=admin1234`, which triggers a production warning.
- `kakao_da` can collect volume and images, but advertiser-name and final landing resolution still need improvement.
- `tiktok_ads` can collect volume and covers, but advertiser-name extraction still needs improvement.
- Archive round-robin previously stopped during Google GDN due to Playwright driver connection closure.
- 12h archive boost has been running in low-memory sequential mode since 2026-04-24 15:59 KST.

## Product Documentation Refresh

- Service intro docs were refreshed with DB-backed counts: `ad_details` 46,575, valid ads 42,550, recent 30d ads 13,100, advertisers 6,091, recent 7d active advertisers 428, campaigns 8,331, spend estimates 46,214, recent 30d estimated spend about KRW 1.98B, and 2025 archive ads 1,903.
- Pricing direction changed from fixed Lite/Full packages to a basic subscription plus usage credits. Enterprise remains a separate contract path.
- Keyword/search ads material direction is in progress: these should be modeled and presented as text-first assets containing copy, landing URL, and exposed keyword. UI/API may need a separate menu or tab from image-first creative galleries.

## Latest UI/Data Cleanup

User requested gallery simplification. Implemented code changes:

- API gallery excludes `naver_shopping` from default ad creative results.
- API gallery treats `youtube`, `youtube_ads`, and `youtube_surf` as one query group.
- API gallery treats `meta`, `meta_feed`, `facebook`, and `instagram` as one query group.
- Gallery CSV/XLSX export applies the same grouped-channel policy.
- Frontend gallery filter chips now remove `naver_shopping`, `youtube_surf`, and `meta_feed`.

Verification completed:

- Python compile passed for gallery-related backend modules.
- Pytest passed for gallery channel policy, guest public access, and data quality gate tests: 7 passed.
- TypeScript check passed for frontend.
- Local API sample confirmed:
  - `channel=naver_shopping` returns 0 gallery items.
  - `channel=youtube_ads` returns normalized `youtube_ads` items.
  - `channel=meta` returns normalized `meta` items.
- Railway API deploy completed: `2dbb5c68-59df-4106-91bd-382bb42130bc`.
- Railway frontend deploy completed: `b4d63fc9-6c97-4809-85f7-cb42d976ea83`.
- Production API sample confirmed:
  - `/api/ads/gallery?source=ads&channel=naver_shopping&limit=5` returns 0 gallery items.
  - `/api/ads/gallery?source=ads&channel=youtube_ads&limit=20` returns only normalized `youtube_ads`.
  - `/api/ads/gallery?source=ads&channel=meta&limit=20` returns only normalized `meta`.
- Production frontend `/gallery` returned 200 and no longer contains `naver_shopping`, `youtube_surf`, or `meta_feed` filter keys.

## Final 22:23 Quality/Deploy Update

The agent work was integrated and the remaining data-quality issues were handled directly in the main workflow.

- 12h archive boost completed normally at 2026-04-24 22:10 KST.
- Archive boost result: 108 tasks completed, 36 skipped, 0 failures, elapsed 371.1 minutes.
- Full-window data quality gate passed across all active channels after cleanup.
- Required media creative missing count in active rows is now 0.
- Placeholder material text remaining in active rows is now 0.
- Active/non-rejected ad details: 27,977.
- Rejected/quality-excluded ad details: 18,628.
- Campaigns after rebuild: 8,336.
- Spend estimates after rebuild: 45,541.

Cleanup applied:

- Rejected 5,317 active media rows with missing or broken required creative assets.
- Cleared 4,083 `gdn_transparency_*` material placeholders.
- Cleared 1 duration-only material text row.
- Rejected 2,198 Google/Youtube person-name advertiser artifacts.
- Rejected 18 remaining cross-channel suspect person/location labels.
- Preserved known brand-like Korean labels including `오토카`, `안다르`, `박문각`, `윤선생`, `정관장`, `나이키`, `유세린`, `공단기`, and `오랄비`.

Public/API fixes:

- `/api/public/stats` now excludes `verification_status='rejected'` rows from total ads, active 7d advertisers, by-channel counts, and top advertiser ranking.
- `/api/ads/gallery` hides repaired/invalid material text before it reaches the frontend.
- Production public stats returned 200 with quality-filtered total ads 27,977 and active 7d advertisers 257.
- Production Google GDN gallery returned 200 and did not expose `transparency_` or raw library ID text.

Deployments:

- DB sync completed at 2026-04-24 22:18 KST; uploaded DB size was 536.04MB.
- Backend deployment `7d2f8b20-8db3-4a3d-bc3c-bf395592c458` succeeded.
- Frontend deployment `73dc53d2-51c0-49db-9855-f09a0446e0c2` succeeded.

Verification:

- `python -m pytest tests/test_entity_label_quality.py tests/test_data_quality_gate.py tests/test_gallery_channel_policy.py tests/test_guest_public_access.py -q`: 15 passed.
- `npm.cmd exec -- tsc --noEmit --pretty false`: passed.
- `python scripts/data_quality_gate.py --days 3650`: passed.
