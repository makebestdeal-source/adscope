# Session Resume Memo

Last updated: 2026-02-10

Quick resume doc: `NEXT_START_HANDOVER.md`

## Completed in this session

1. Cost-lean defaults updated in `.env.example`
   - `META_AD_LIMIT=50`
   - `META_MAX_PAGES=1`
   - `META_MAX_RETRIES=3`
   - `META_RETRY_BACKOFF_MS=800`
   - `GDN_MAX_PUBLISHERS=2`
   - `GDN_TRUST_CHECK_LIMIT=5`
   - `KAKAO_MAX_MEDIA=2`
   - `YOUTUBE_PLAYER_SAMPLES=1`
   - `CAMPAIGN_EXCLUDED_CHANNELS=youtube_ads`
   - `CRAWL_CHANNELS=naver_search,google_gdn,kakao_da`
   - `NON_KEYWORD_CHANNEL_MIN_INTERVAL_MINUTES=240`
   - `CRAWL_CHANNEL_MIN_INTERVALS=google_gdn:240,kakao_da:240,meta_library:240`
   - `CRAWL_CHANNEL_KEYWORD_LIMITS=google_gdn:1,kakao_da:1,meta_library:1,youtube_ads:1`
   - verification gate env block added

2. Campaign/spend rebuild now excludes channels by env (default excludes YouTube)
   - File: `processor/campaign_builder.py`
   - Added:
     - `DEFAULT_EXCLUDED_CHANNELS = {"youtube_ads"}`
     - `_parse_excluded_channels(...)`
     - `_delete_excluded_campaign_data(...)`
     - excluded-channel filtering in aggregate/industry rebuild paths

3. Scheduler channel policy expanded
   - File: `scheduler/scheduler.py`
   - Added:
     - `CRAWL_CHANNEL_MIN_INTERVALS` parser and per-channel interval resolution
     - `CRAWL_CHANNEL_KEYWORD_LIMITS` parser and per-channel keyword cap
     - default non-keyword interval changed to `240`

4. Meta crawler reliability improvements
   - File: `crawler/meta_library.py`
   - Added:
     - retry + exponential backoff for API requests
     - API error classification helper (`auth`, `quota`, `transient`, `fatal`)
     - alert logs for auth/quota failures

5. Verification schema output fields updated
   - File: `database/schemas.py`
   - `AdDetailOut` now includes:
     - `ad_description`
     - `display_url`
     - `verification_status`
     - `verification_source`

6. Verification quality gate implementation added
   - File: `processor/verification_quality.py`
   - File: `scripts/verification_quality_gate.py`
   - Includes channel rule parsing, stats aggregation, pass/fail evaluation.

7. Scheduler tests expanded
   - File: `tests/test_scheduler_channels.py`
   - Added tests for:
     - channel int-map parser
     - per-channel keyword limit behavior
     - per-channel interval resolution

## Follow-up execution (2026-02-10)

1. Executed validation commands from resume checklist
   - `python -m pytest tests/test_scheduler_channels.py tests/test_crawlers/test_meta_library_helpers.py tests/test_crawlers/test_google_gdn_helpers.py`
   - Result: **13 passed**
   - `python scripts/build_campaigns_and_spend.py`
   - Result: rebuild completed (`updated_campaigns=566`, `inserted_estimates=566`) and excluded channels log confirmed `youtube_ads`
   - `python scripts/verification_quality_gate.py --days 7`
   - Result: expected **fail** (coverage/verified ratios below thresholds)

2. Verified DB init/backfill/index state in `adscope.db`
   - `ad_details` has columns: `verification_status`, `verification_source`
   - indexes present: `ix_details_verification_status`, `ix_details_verification_source`
   - row distribution:
     - total rows: `1183`
     - `verification_status IS NOT NULL`: `11`
     - `verification_source IS NOT NULL`: `11`
     - status top values: `<NULL>=1172`, `unknown=11`
   - source top values: `<NULL>=1172`, `not_enabled=9`, `google_ads_transparency_center=2`

3. Confirmed verification gate pass/fail behavior
   - fail path: default thresholds (`--days 7`) returns exit code 2
   - pass path: relaxed thresholds (`--min-total 0 --min-coverage 0 --min-verified 0`) returns exit code 0

4. Added dedicated tests for newly introduced logic
   - File: `tests/test_verification_quality.py`
   - File: `tests/test_campaign_builder_exclusions.py`
   - Combined run:
     - `python -m pytest tests/test_verification_quality.py tests/test_campaign_builder_exclusions.py tests/test_scheduler_channels.py tests/test_crawlers/test_meta_library_helpers.py tests/test_crawlers/test_google_gdn_helpers.py`
     - Result: **23 passed**

5. Added local run batch files (Windows)
   - `run_backend.bat` (loads `.env` and runs `uvicorn api.main:app --reload`)
   - `run_frontend.bat` (runs `npm install` if needed, then `npm run dev`)
   - `run_all.bat` (opens backend/frontend in separate terminals)

6. Completed remaining quality tasks
   - Verification population defaults:
     - File: `processor/pipeline.py`
     - Added channel-aware fallback resolver for verification fields:
       - `naver_search`/`kakao_da` -> `unverified`, `channel_default`
       - others -> `unknown`, `not_collected`
   - DB backfill defaults:
     - File: `database/__init__.py`
     - Added `_backfill_missing_verification_defaults(...)` in `init_db()` flow
     - Existing missing rows now normalized:
       - `naver_search`: `unverified` (was mostly missing)
       - `kakao_da`: `unverified` (was mostly missing)
       - remaining missing -> `unknown` + `not_collected`
   - Gate threshold defaults for current maturity:
     - File: `.env.example`
     - `VERIFICATION_GATE_CHANNELS=` (auto-detect channels in window)
     - `VERIFICATION_GATE_CHANNEL_RULES=meta_library:0.95:0.95,google_gdn:0.00:0.00:5,naver_search:0.50:0.00:5,kakao_da:0.50:0.00:0`
   - Added tests:
     - `tests/test_pipeline_verification_defaults.py`
   - Fixed `python -m pytest` no-collection issue:
     - Root cause: integration tests were rebinding `sys.stdout`, breaking pytest capture teardown
     - Updated files:
       - `tests/test_pipeline.py`
       - `tests/test_full_flow.py`
       - `tests/test_advertiser_match.py`
       - `tests/test_crawlers/test_naver_search.py`
     - Applied `RUN_E2E_TESTS=1` skip guard for live integration tests

7. Re-validated after fixes
   - `python -m pytest -q`
   - Result: **30 passed, 4 skipped**
   - `python scripts/build_campaigns_and_spend.py`
   - Result: rebuild completed (`updated_campaigns=566`, `inserted_estimates=566`)
   - `python scripts/verification_quality_gate.py --days 7`
   - Result: fail (expected under strict defaults)
   - `python scripts/verification_quality_gate.py --days 7 --rules "google_gdn:0.00:0.00:5,naver_search:0.50:0.00:5,kakao_da:0.50:0.00:0"`
   - Result: pass
   - Latest 7-day verification distribution:
     - `naver_search`: `unverified=1168`, `missing=0`
     - `kakao_da`: `unverified=4`, `missing=0`
     - `google_gdn`: `unknown=11`, `missing=0`
     - source distribution: `channel_default=1172`, `not_enabled=9`, `google_ads_transparency_center=2`

## Remaining tasks (not yet executed/validated)

1. Optional: improve `google_gdn` verified ratio by enabling/expanding trust-center checks (`GDN_TRUST_CHECK=true` + budgeted limits), then tighten gate thresholds again
2. Optional: add DB-level migration test for `_backfill_missing_verification_defaults(...)` using a temp SQLite fixture

## Recommended resume commands

```powershell
run_backend.bat
run_frontend.bat
run_all.bat
python -m pytest tests/test_verification_quality.py tests/test_campaign_builder_exclusions.py tests/test_scheduler_channels.py tests/test_crawlers/test_meta_library_helpers.py tests/test_crawlers/test_google_gdn_helpers.py
python -m pytest -q
python scripts/build_campaigns_and_spend.py
python scripts/verification_quality_gate.py --days 7
python scripts/verification_quality_gate.py --days 7 --rules "google_gdn:0.00:0.00:5,naver_search:0.50:0.00:5,kakao_da:0.50:0.00:0"
```
