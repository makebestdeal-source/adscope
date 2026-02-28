# Next Start Handover

Last updated: 2026-02-10

## 1) Current Project Status

- Core code changes are applied.
- Test baseline is stable.
- Local run scripts are ready:
  - `run_backend.bat`
  - `run_frontend.bat`
  - `run_all.bat`

## 2) Verified Results

- Test run:
  - `python -m pytest -q`
  - Result: `30 passed, 4 skipped`
- Backend health check (when running):
  - `GET http://127.0.0.1:8000/health` -> `200`
- Frontend check (when running):
  - `GET http://127.0.0.1:3000` -> `200`

## 3) Important Runtime Note

- `run_backend.bat` uses SQLite by default for local stability.
- If you must use DB from `.env` (PostgreSQL), run with:
  - `set BACKEND_USE_ENV_DB=1`
  - then start backend.
- If local PostgreSQL is not running on `localhost:5432`, backend startup can fail when env DB mode is enabled.

## 4) Quick Start (Recommended)

1. Open project root:
   - `C:\Users\makeb\Desktop\adscopre`
2. Run:
   - `run_all.bat`
3. Wait for startup.
4. Verify:
   - backend: `http://127.0.0.1:8000/health`
   - frontend: `http://127.0.0.1:3000`

## 5) Validation Commands

- Fast check:
  - `python -m pytest -q`
- Verification gate (strict defaults):
  - `python scripts/verification_quality_gate.py --days 7`
- Verification gate (current relaxed channel rules):
  - `python scripts/verification_quality_gate.py --days 7 --rules "google_gdn:0.00:0.00:5,naver_search:0.50:0.00:5,kakao_da:0.50:0.00:0"`

## 6) Where To Continue

- Primary history log:
  - `SESSION_RESUME.md`
- Recent logic changes:
  - `processor/pipeline.py`
  - `database/__init__.py`
  - `.env.example`
- Recent test additions:
  - `tests/test_pipeline_verification_defaults.py`
  - `tests/test_verification_quality.py`
  - `tests/test_campaign_builder_exclusions.py`

## 7) Suggested Next Work

- Improve `google_gdn` verified ratio, then tighten verification gate thresholds.
- Add a DB migration-style test for verification default backfill behavior.

## 8) Next Session Start Prompt

Use this to resume quickly:

`Read NEXT_START_HANDOVER.md and SESSION_RESUME.md, then continue from section "Suggested Next Work".`
