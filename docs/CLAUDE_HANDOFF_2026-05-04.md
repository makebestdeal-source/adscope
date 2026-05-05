# Claude Handoff - 2026-05-04 KST

## Context

User reported several production regressions and explicitly asked that future fixes be batched and deployed only when requested. On 2026-05-04 the user requested this handoff record and authorized one final deployment of today's changes.

## Important Operating Rule

- Do not deploy after each individual issue.
- Use `scripts/deploy_railway_batch.ps1` for Railway deployment so backend and frontend roots are checked before upload.
- Frontend Railway service root is the folder that contains `frontend/Dockerfile`; do not deploy from `frontend_root/frontend`.

## Changes Prepared

### Meta Signal Advertiser Quality

Files:
- `api/services/advertiser_quality.py`
- `api/routers/meta_signals.py`
- `processor/activity_scorer.py`
- `processor/meta_signal_aggregator.py`

Summary:
- Added advertiser eligibility checks for meta-signal/activity ranking.
- Excludes duplicate/placeholder/person-name/low-confidence advertisers and platform profile URLs from meta-signal ranking and scoring.
- `top-active` now overfetches candidates and returns only eligible advertisers, preventing name-like advertisers from dominating ranking.

Verification:
- `python -m py_compile api\services\advertiser_quality.py api\routers\meta_signals.py processor\activity_scorer.py processor\meta_signal_aggregator.py`
- Local DB probe confirmed screenshot names such as `태경호`, `이해수`, `무드미`, `문한수`, `차가람`, `두이헌`, `최설아`, `퍼널스`, `우보미`, `허순임` were excluded from top-active results.

### Social Content Facebook Option Removal

Files:
- `frontend/src/app/social-content/page.tsx`
- `api/routers/brand_channels.py`

Summary:
- Removed Facebook from the social content platform selector and guide copy because the content collector only stores YouTube and Instagram brand-channel content.
- Restricted `content-analysis` API to `youtube` and `instagram` content.
- Fixed platform distribution and daily upload charts to use the same active filter, so selecting an unsupported platform does not show unrelated chart data.

Verification:
- `python -m py_compile api\routers\brand_channels.py`
- `npx.cmd tsc --noEmit`

### Buzz Alert Meaning And Data Integrity

Files:
- `api/routers/buzz.py`
- `frontend/src/app/buzz-dashboard/page.tsx`

Summary:
- Fixed nameless buzz alert cards by joining `SocialImpactScore` to existing `Advertiser` rows and excluding empty advertiser names.
- Removed stale alert rows that pointed to deleted/cleaned advertiser IDs.
- Added meaningful card copy: buzz score surge/drop, recent score, previous score, main driver, and date.

Verification:
- `python -m py_compile api\routers\buzz.py`
- `npx.cmd tsc --noEmit`
- Local DB probe showed valid alert advertisers only, e.g. `아모레퍼시픽`, `쿠팡`, `다방`, `SLEEK`, `리더뮨`, `코웨이`, `하나투어`, `삼양식품`.

### Deployment Guard Update

File:
- `scripts/deploy_railway_batch.ps1`

Summary:
- Added the new backend/frontend files above to the guarded batch deployment copy list.
- The script validates backend Dockerfile/API entrypoint and frontend Railway root before uploading.
- The script runs backend `py_compile` and frontend TypeScript check before any deploy.

## Deployment

Status: completed.

Command:
- `powershell.exe -ExecutionPolicy Bypass -File scripts\deploy_railway_batch.ps1 -Deploy -BackendMessage "batch fix quality social buzz" -FrontendMessage "batch fix social buzz UI"`

Railway deployments:
- Backend `adscope`: `887be90e-a925-4013-8890-112c010dacad` - `SUCCESS`
- Frontend `frontend`: `1455652f-f7e4-4542-a55e-beea2eb78102` - `SUCCESS`

Production checks:
- `https://api.adscope.kr/api/auth/plans` returned `200`.
- `https://api.adscope.kr/api/brand-channels/content-analysis?days=30&platform=meta` returned `total_contents=0`, `platform_dist=[]`, `daily_uploads=[]`.
- `https://api.adscope.kr/api/buzz/alerts?days=7` returned no blank advertiser names; sample valid advertisers included `아모레퍼시픽`, `쿠팡`, `다방`, `SLEEK`, `리더뮨`.
- `https://api.adscope.kr/api/meta-signals/top-active?days=30&limit=30` returned no overlap with the reported bad names: `태경호`, `이해수`, `무드미`, `문한수`, `차가람`, `두이헌`, `최설아`, `퍼널스`, `우보미`, `허순임`.
