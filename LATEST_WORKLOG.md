# AdScope Latest Worklog

Last updated: 2026-04-24 22:23 KST

Archive detail: `docs/archive/adscope_worklog_2026-04-24.md`

## Current Status

- Data quality gate: pass across all channels for the full 3650-day window.
- Tests: targeted backend tests 15 passed; frontend TypeScript check passed.
- Railway DB sync: completed at 22:18 KST, uploaded DB size 536.04MB.
- Railway backend deploy: completed, latest deployment `7d2f8b20-8db3-4a3d-bc3c-bf395592c458` is `SUCCESS`.
- Railway frontend deploy: completed, latest deployment `73dc53d2-51c0-49db-9855-f09a0446e0c2` is `SUCCESS`.
- Public API check: `https://api.adscope.kr/api/public/stats` returned 200 with quality-filtered active totals.
- Gallery API check: Google GDN gallery returned 200 with no `transparency_` or raw library ID text exposure.
- Scheduler: still disabled by `.scheduler_disabled`.
- 12h archive boost: completed normally at 2026-04-24 22:10 KST, 108 tasks completed, 36 skipped, 0 failures.

## Completed Today

- Reopened and integrated all agent work: keyword-material gallery, public social read access, login logo home link, data label guard, and worklog archive.
- Reclassified keyword/search ads as text-first materials and separated image materials from keyword materials in the gallery UI.
- Excluded low-quality `naver_shopping` from the default creative gallery and grouped YouTube/Meta variants.
- Opened social creative/channel read-only pages to guests while keeping private export/download routes protected.
- Added and tightened advertiser/material label quality checks for CTA labels, library IDs, creative IDs, duration-only copy, and person-name advertiser artifacts.
- Cleaned local DB quality issues before deployment:
  - Rejected 5,317 media rows with missing/broken required creative assets.
  - Cleared 4,083 `gdn_transparency_*` material placeholders and 1 duration-only material string.
  - Rejected 2,198 Google/Youtube person-name advertiser rows plus 18 remaining cross-channel suspect rows.
  - Preserved known brand-like Korean labels such as `오토카`, `안다르`, `박문각`, `윤선생`, `정관장`, `나이키`, `유세린`, `공단기`, and `오랄비`.
- Rebuilt campaigns and spend estimates after cleanup.
- Uploaded refreshed DB and deployed backend/frontend to Railway.
- Refreshed company/service introduction docs with usage-credit pricing direction and DB-backed positioning.

## Latest Numbers

- Active/non-rejected ad details: 27,977
- Rejected/quality-excluded ad details: 18,628
- Campaigns: 8,336
- Spend estimates: 45,541
- Public API active 7d advertisers: 257
- Public API 30d active ads by channel: `naver_search` 3,663, `google_search_ads` 1,114, `meta` 436, `google_gdn` 400, `kakao_da` 389, `youtube_ads` 161, `naver_da` 113, `tiktok_ads` 5.
- Placeholder material text remaining in active DB: 0
- Required creative path missing in active media rows: 0

## Remaining Work

- Continue improving source crawler extraction so fewer Google/Youtube rows arrive as personal-name transparency artifacts.
- Improve `kakao_da` and `tiktok_ads` advertiser-name extraction quality.
- Decide whether to restart the scheduler or keep manual low-load archive/crawl mode.
- Investigate local `.pytest_tmp` permission corruption; Railway deploys currently use a clean temp deployment directory to avoid that broken local folder.
