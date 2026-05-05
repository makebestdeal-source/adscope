# Claude Handoff - 2026-05-03

This note summarizes the Codex work after the machine reboot, focused on the May 2 crawl data cleanup, merge, upload, and production deployment.

## User Goal

The user wants yesterday's crawled ad data inspected, filtered, merged, uploaded, and deployed end to end. They also asked whether the problematic advertiser data already present in the existing DB was cleaned.

## Crawl Run Checked

Source log:

- `logs/run_all_2026-05-02.log`

Result:

- Run completed at `2026-05-03 08:46:21`.
- Post-process summary: 9 OK, 0 FAIL.
- Brand Monitor: 1,219 advertisers, 5,931 new items.
- Social Stats: 1,504 collected.
- Social Impact Score: 4,503 processed, 512 created, 3,991 updated.
- Campaign chain inserted 21,207 journey rows and updated/created lift data.

## Local DB Backup And Filtering

Backup created:

- `backups/adscope_pre_filter_20260503_101706.db`

Filter command:

```powershell
python scripts/filter_and_deploy_current.py --days 2 --active-days 7 --no-upload --keep-snapshot
```

Important filter results:

- `ad_rows_scanned`: 2,737
- `ad_rows_rejected`: 135
- `ad_text_repaired`: 153
- `ad_text_cleared`: 573
- `campaigns_scanned`: 3,408
- `campaigns_marked`: 197
- creative rows scanned: 2,602
- creative rows rejected: 2

Post-filter quality gate passed for:

- Meta
- Naver Search
- YouTube Ads

Filtered snapshot kept:

- `cache/deploy/adscope_filtered_20260503_101749.db`
- `cache/deploy/adscope_filtered_20260503_101749.db.gz`

## Existing Bad Advertiser Cleanup

`scripts/merge_dbs.py` was strengthened so existing DB cleanup also handles old bad advertiser names:

- Added garbage patterns for exact `Library` and `라이브러리`.
- Deletes garbage advertisers during merge cleanup.
- Sets `ad_details.advertiser_name_raw` to `NULL` when the raw name is a garbage library placeholder.

Compile check:

```powershell
python -m py_compile scripts/merge_dbs.py
```

Final merged DB check:

- Library-style advertiser names: 0
- Library-style raw advertiser names: 0
- Greek spam text sample rows: 0
- Garbage advertisers deleted during merge: 220
- Garbage raw advertiser names nulled during merge: 1,320
- Duplicate old text ads deleted during merge cleanup: 2,178

Important caveat:

- Display/API name normalization also remains active through `api/services/advertiser_names.py`, so low-confidence person/library-style names should not be surfaced as primary advertiser labels even when historical raw text exists.

## R2 Image Upload

The first upload attempt timed out but the process kept running. It was stopped safely and retried with lower concurrency.

Retry method:

```powershell
$env:PYTHONIOENCODING='utf-8'
@'
import scripts.upload_images_to_r2 as uploader
uploader.WORKERS = 16
uploader.main()
'@ | python -
```

Final R2 upload state:

- Current files: 182,280
- Completed: 182,280
- Remaining: 0
- Failures: 0

## Merge And DB Upload

Merge command:

```powershell
python scripts/merge_dbs.py
```

Merged DB:

- `merged_db.db`
- `merged_db.db.gz`

Uploaded to production API with `_upload_data`.

Upload response:

```json
{"status":"ok","file":"/data/adscope.db","size_mb":555.61}
```

## Final Count Delta

Baseline: `server_db.db`

Final: `merged_db.db`

Latest final snapshot:

- `2026-05-02 22:22:19.441112`

Net deltas after cleanup:

- `ad_snapshots`: +1,318
- `advertisers`: +346
- `campaigns`: +428
- `spend_estimates`: +3,473
- `brand_channel_contents`: +9,563
- `news_mentions`: +331
- `social_impact_scores`: +4,503
- `ad_details`: -59 net

`ad_details` is net negative because 2,119 new rows were merged, then 2,178 old duplicate/junk text rows were removed by cleanup. This is expected and is not a failed crawl merge.

May 2 detail rows now in final DB:

- Total: 1,518
- Naver Search: 714
- Meta: 775
- YouTube transparency: 29

## Build Verification

Backend compile passed:

```powershell
python -m py_compile api/services/advertiser_names.py api/routers/campaign_effect.py api/routers/campaigns.py api/routers/advertisers.py api/routers/reports.py api/main.py scripts/merge_dbs.py
```

Frontend type check passed:

```powershell
npx tsc --noEmit
```

Frontend production build passed:

```powershell
npm run build
```

Two frontend imports were fixed after type check:

- `frontend/src/app/gallery/page.tsx`
- `frontend/src/app/gallery/keyword/page.tsx`

Both now import `DataFreshness`.

## Production Deployment

Frontend:

- Service: `frontend`
- Deployment ID: `c5d5f352-506c-4246-bab0-5d58caaff48c`
- Status: SUCCESS

Backend:

- Service: `adscope`
- Final deployment ID: `2a7f7d49-5320-4a39-98a1-0d03b655b391`
- Status: SUCCESS

The first backend retry failed because the temporary deployment package did not include `crawler`, which is imported indirectly by staging/data washer code. The second retry included `crawler`.

The next backend retry failed because the app reached startup after about 50 seconds while Railway's healthcheck timeout was 30 seconds. This was fixed by changing:

- `railway.toml`
  - `healthcheckTimeout = 120`

Live checks after deployment:

- `https://api.adscope.kr/api/auth/plans`: HTTP 200
- `https://adscope.kr`: HTTP 200

## Correction: Restore Service/Landing UI

After deployment, the user objected that Codex had changed the service intro/landing content too aggressively. The UI/content changes were reverted.

Restored:

- `frontend/src/app/page.tsx`
  - Restored the original client-side auth split:
    - unauthenticated users see `GuestLanding`
    - authenticated users see `Dashboard`
- `frontend/src/app/about/page.tsx`
  - Restored the service intro copy/menu content to the repository baseline.

Kept only non-visual SEO improvements:

- `frontend/src/app/layout.tsx`
  - Normalized root metadata, description, Open Graph, Twitter, and JSON-LD structured data.
  - This improves Naver/Google title and description detection without changing the service intro page layout or copy.

Verification after correction:

- `npx tsc --noEmit`: passed
- `npm run build`: passed
- Frontend redeployed:
  - Deployment ID: `723e4975-dcfd-4c55-a84b-ec7cbfebbcb1`
  - Status: SUCCESS
- Live `https://adscope.kr` returned:
  - HTTP 200
  - title: `AdScope | 광고 인텔리전스 플랫폼`
  - description present
  - Open Graph title present

## Files Changed In This Reboot Recovery

- `scripts/merge_dbs.py`
  - stronger cleanup for historical library-style advertiser names and raw names
- `railway.toml`
  - backend healthcheck timeout increased to 120 seconds
- `frontend/src/app/gallery/page.tsx`
  - added missing `DataFreshness` import
- `frontend/src/app/gallery/keyword/page.tsx`
  - added missing `DataFreshness` import
- `frontend/src/app/layout.tsx`
  - kept SEO metadata/OG/structured data improvements after restoring the visible service pages
- `frontend/src/app/page.tsx`
  - restored to repository baseline after the user rejected the earlier landing rewrite
- `frontend/src/app/about/page.tsx`
  - restored to repository baseline after the user rejected the service intro copy/menu changes
- `docs/CLAUDE_HANDOFF_2026-05-03.md`
  - this handoff note

Many other files were already modified before this reboot recovery, including SEO, report export, campaign effect, advertiser image display, and navigation changes. Do not assume all dirty files are from this last step.

## Correction: Market Analysis, Images, Campaign Effect

User reported that market analysis pages appeared broken after the reboot recovery:

- Industry overview looked empty/broken.
- Product/service and competitor comparison were not usable.
- YouTube creative images were broken.
- Campaign Effect showed identical estimated spend values for many one-hit Meta campaigns.

Root causes found:

- Production market APIs were still returning data, but the frontend deployment had not been refreshed with the restored page bundle.
- A frontend deployment attempt failed because it was run from `frontend_root/frontend` while Railway service config expects `rootDirectory = frontend` and `dockerfilePath = frontend/Dockerfile`. Correct deployment must be run from:
  - `C:\Users\user\Desktop\adscope_deploy_20260503_105313\frontend_root`
- `/images` was mounted as local `StaticFiles`, but production image storage had moved to R2 and local image files can be deleted on startup. Missing local files caused 500 responses instead of serving the R2 asset.
- `channel=youtube_ads` gallery results could include social YouTube rows without ad creative images because `youtube_ads` was incorrectly included in the social platform grouping.
- Campaign Effect tables had a missing period cell, causing spend values to visually appear under the wrong column. Also, low-confidence single-observation Meta estimates from `market_share_inverse` were shown as exact spend.

Fixes applied:

- `api/main.py`
  - Replaced `/images` static mount with a route that serves a local file when present, otherwise redirects to R2.
- `processor/channel_utils.py`
  - Removed `youtube_ads` from the social platform grouping so YouTube ad gallery filters return ad rows with creative image paths.
- `api/routers/campaign_effect.py`
  - Suppresses low-confidence single-row `market_share_inverse` spend estimates by returning `None` instead of showing a precise KRW value.
- `frontend/src/app/campaigns/page.tsx`
  - Added the missing period column in campaign-effect lists.
  - Shows `-` for missing/invalid spend instead of a fabricated exact value.
- `frontend/src/app/gallery/page.tsx`
  - Added fallback image candidate handling.
- `frontend/src/lib/image-utils.ts`
  - Uses R2 public image URLs first for stored images, with `/images` as fallback.
- Market pages were verified against repository baseline:
  - `frontend/src/app/industries/page.tsx`
  - `frontend/src/app/industries/[id]/page.tsx`
  - `frontend/src/app/products/page.tsx`
  - `frontend/src/app/competitors/page.tsx`

Verification:

- Backend compile passed:
  - `python -m py_compile api\main.py api\routers\campaign_effect.py api\routers\industries.py api\routers\products.py api\routers\competitors.py processor\channel_utils.py`
- Frontend type check passed:
  - `npx tsc --noEmit`
- Frontend production build passed:
  - `npm run build`

Production deployments:

- Backend:
  - Service: `adscope`
  - Deployment ID: `325c217c-1a74-4ff8-bfd2-23ce39ea885f`
  - Status: SUCCESS
- Failed frontend attempt:
  - Deployment ID: `3e90814a-2597-42b5-81b7-3f29723d2b14`
  - Status: FAILED
  - Cause: uploaded from the wrong directory, so Railway could not find `frontend/Dockerfile`.
- Correct frontend deployment:
  - Service: `frontend`
  - Deployment ID: `fc270fb4-e23b-4704-8d51-f05c0b8e7be8`
  - Status: SUCCESS

Live checks after deployment:

- `https://api.adscope.kr/api/industries`
  - HTTP 200
  - 24 industries
- `https://api.adscope.kr/api/industries/1/landscape?days=30`
  - HTTP 200
  - `advertiser_count`: 5,984
- `https://api.adscope.kr/api/products/categories?days=30`
  - HTTP 200
  - 22 top-level product/service categories
- `https://api.adscope.kr/api/competitors/1?days=30&limit=3`
  - HTTP 200
  - competitor rows returned
- `https://api.adscope.kr/api/ads/gallery?channel=youtube_ads&limit=5`
  - HTTP 200
  - `total`: 2,941
  - first row includes `creative_image_path`
- Example YouTube creative proxy:
  - `/images/youtube_ads/20260503/creative/yt_preview_CR078664229040349511_9OLhY5oSypY_221054.webp`
  - No-follow: HTTP 302 to R2
  - Follow redirect: HTTP 200 `image/webp`, 8,386 bytes
- `https://api.adscope.kr/api/campaign-effect/campaigns?days=90&limit=5`
  - HTTP 200
  - one-hit low-confidence Meta campaign spend now returns `total_est_spend: null`
- Frontend routes:
  - `https://adscope.kr/industries`: HTTP 200
  - `https://adscope.kr/products`: HTTP 200
  - `https://adscope.kr/competitors`: HTTP 200
  - `https://adscope.kr/campaigns`: HTTP 200

Operational rule going forward:

- Treat the core flow as a required contract:
  - industry -> product/service -> advertiser -> spend -> creative image
- Do not expose library IDs, personal names, or low-confidence default estimates as if they were advertiser truth.
- Do not deploy frontend from `frontend_root/frontend`; deploy from `frontend_root`.
- For YouTube ads, verify image existence through the public R2 URL or `/images` redirect before calling the task done.

## Core Contract And Keyword Gallery Fix

The user clarified the actual product contract:

- clear industry category
- product/service classification
- cleaned advertiser
- media spend calculation
- social channel collection
- social content collection
- engagement collection
- performance/effect evaluation
- accurate image and text/keyword ad material collection
- social thumbnail and URL collection
- ad URL and official site URL collection
- menu-specific presentation only after common cleanup
- downloads centralized in Reports & Downloads

Added:

- `docs/ADSCOPE_CORE_SERVICE_CONTRACT.md`
  - Captures the non-negotiable service rules and menu mapping.
- `scripts/core_flow_gate.py`
  - Validates the core flow before upload/deploy.
  - Checks industry, product/service, advertiser cleanup, spend, effects, image creative, keyword text creative, social channels, social content, thumbnails, URLs, engagement, ad URL, and official site URL.

Current local `merged_db.db` gate result:

- PASS:
  - industries: 24
  - product categories: 164
  - keyword text ads: 9,626
  - generic advertiser ratio: 0.19%
  - ad URL coverage: 100%
  - official site coverage: 82.38%
  - campaign spend coverage: 100%
  - image path coverage: 90.09%
  - social channels: 119
  - social contents: 16,882
  - social URL coverage: 100%
  - social thumbnail coverage: 100%
  - social engagement coverage: 99.99%
- FAIL:
  - missing product/service ratio: 94.67%
  - campaign effect coverage: 0.06%

This means the next real data work should prioritize:

- product/service classification backfill and merge rules
- campaign effect pre/post event generation

Also fixed a keyword material bug:

- Problem:
  - On `frontend/src/app/gallery/keyword/page.tsx`, when both Naver and Google were selected, the frontend sent no `channel` filter.
  - `/api/ads/gallery?source=ads` interprets no `channel` as image-gallery mode and excludes search channels.
  - The frontend then filtered the returned image-gallery rows down to keyword channels, resulting in zero rows.
- Fix:
  - `api/routers/ads.py`
    - Added `channels` query parameter for comma-separated multi-channel filters.
    - Multi-channel filters are treated as union, not intersection.
  - `frontend/src/lib/api.ts`
    - Added `channels` parameter support for `getGallery` and `getPublicGallery`.
  - `frontend/src/app/gallery/keyword/page.tsx`
    - Default selected channels are now Naver + Google.
    - Sends `channels=["naver_search", "google_search_ads"]` when both are selected.
    - Empty selection now intentionally shows no rows instead of accidentally querying image gallery mode.

Verification:

- `python -m py_compile api\routers\ads.py`: passed
- `npx.cmd tsc --noEmit`: passed
