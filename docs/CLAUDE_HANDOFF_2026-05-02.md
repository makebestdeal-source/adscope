# Claude Handoff - 2026-05-02

This note summarizes the work Codex did in this session so Claude can continue without rediscovering the same context.

## User Goal

The user wants AdScope to be searchable on Google and Naver without exposing private/internal data. They also want site traffic/access details visible in the admin area, and the campaign effect page should stop prioritizing meaningless ad library placeholder data such as `라이브러리 ID: 878...` when there is no before/after effect data.

## Completed: Admin Access Logs

Added persistent site access logging and an admin UI for traffic details.

Changed files:

- `database/models.py`
  - Added `SiteAccessLog` model.
- `api/main.py`
  - Updated request logging middleware to persist access logs.
- `api/routers/admin.py`
  - Added `/api/admin/access-logs`.
- `frontend/src/lib/api.ts`
  - Added admin access log API types/client method.
- `frontend/src/app/admin/page.tsx`
  - Added `접속 분석` tab for viewing access log details.

Verification performed:

- Python compile passed for touched backend files.
- `npx tsc --noEmit` passed.
- `npm run lint` could not be used cleanly because Next.js tried to enter interactive ESLint setup.

## Completed: SEO / Robots / Noindex Hardening

Goal was to let Google and Naver index public marketing pages while blocking private app pages, API routes, generated media, screenshots, and account/admin flows.

Changed files:

- `frontend/public/robots.txt`
  - Added explicit `User-agent: Yeti` rules for Naver.
  - Kept public site crawlable.
  - Added/kept disallow rules for internal/private areas.
- `frontend/next.config.js`
  - Added 301 redirect from `www.adscope.kr` to `https://adscope.kr/:path*`.
  - Added `X-Robots-Tag: noindex, nofollow, noarchive, nosnippet, noimageindex` headers for:
    - `/api/:path*`
    - `/images/:path*`
    - `/screenshots/:path*`
    - private app routes
    - `/login`, `/signup`, `/forgot-password`
- `frontend/src/middleware.ts`
  - Added path guards for private routes and sensitive asset routes.
  - Adds noindex headers on private/sensitive responses.
  - Redirects unauthenticated `/admin` to `/login` while preserving noindex headers.
- `api/main.py`
  - Backend security middleware now adds noindex headers for `/api`, `/images`, and `/screenshots`.
- `frontend/src/app/sitemap.ts`
  - Removed `/login` and `/signup`.
  - Public sitemap now keeps only public pages:
    - `/`
    - `/about`
    - `/pricing`
    - `/guide`
    - `/manual`
    - `/faq`
    - `/terms`
    - `/privacy`
- Added noindex metadata layouts:
  - `frontend/src/app/login/layout.tsx`
  - `frontend/src/app/signup/layout.tsx`
  - `frontend/src/app/forgot-password/layout.tsx`
  - `frontend/src/app/payment/layout.tsx`
  - `frontend/src/app/admin/layout.tsx`
- Added explicit SEO metadata layouts:
  - `frontend/src/app/privacy/layout.tsx`
  - `frontend/src/app/terms/layout.tsx`
- `frontend/src/app/page.tsx`
  - Replaced the root page with server-rendered Korean SEO landing content.
  - Public visitors see crawlable public content.
  - Authenticated users are handed to the product dashboard.
- `frontend/src/components/AuthenticatedHome.tsx`
  - Client component that checks auth and renders the dashboard for signed-in users while hiding the public landing section.

Verification performed:

- `npx tsc --noEmit` passed.
- Backend Python compile passed.
- Local checks confirmed:
  - `/` and `/about` do not emit `X-Robots-Tag`.
  - `/gallery`, `/login`, `/admin` emit noindex headers.
  - proxied `/api/products/categories` emits noindex after backend change.
  - existing `/images/...webp` and `/screenshots/...png` assets emit noindex through the frontend/backend route path.

Notes:

- Live `https://adscope.kr/` was checked with a normal user agent and Naver `Yeti`; it already returned title, description, and Open Graph tags.
- Naver Search Advisor may still show stale missing title/description diagnostics until redeploy and recrawl.
- The Naver `리다이렉션된 페이지` warning is expected for URLs such as `http://adscope.kr` redirecting to `https://adscope.kr/`. The added `www` redirect should make canonicalization cleaner.

## International SEO Option

The user asked whether English or other languages can be supported.

Recommended approach:

- Add locale routes such as `/en`, `/ja`, etc.
- Keep Korean as default canonical for Naver/Korean search.
- Add `hreflang` alternates between locales.
- Translate public SEO pages only first; keep private dashboard routes noindexed.

No implementation was done for multilingual routing yet.

## In Progress / Not Completed: Campaign Effect Data Quality

The user reported that the campaign effect page shows meaningless advertiser/campaign entries such as:

- `라이브러리 ID: 878594781262469 5월캠페인`
- advertiser name `라이브러리 ID: 878594781262469`
- no search/social/sales lift
- no before/after data

Current relevant files:

- `api/routers/campaign_effect.py`
- `frontend/src/app/campaign-effect/page.tsx`

Observed backend behavior:

- `/api/campaign-effect/campaigns` currently orders mostly by recent `Campaign.first_seen`.
- It does not filter out placeholder advertiser names like `라이브러리 ID: ...`.
- It does not require `CampaignLift` or valid pre/post evidence before returning a campaign.
- As a result, newly collected Meta ad-library fragments can dominate the selector even when effect analysis is impossible.

Observed frontend behavior:

- `frontend/src/app/campaign-effect/page.tsx` fetches:
  - `/campaign-effect/campaigns?days=90&limit=30`
- It auto-selects the first campaign in render:

```tsx
if (!selectedCampaignId && campaigns.length > 0) {
  setSelectedCampaignId(campaigns[0].id);
}
```

This should be moved into `useEffect`, and the selected campaign should be the first analyzable campaign, not simply the newest row.

Recommended backend fix:

- Add a helper to detect placeholder advertiser/campaign names:

```py
LIBRARY_ID_RE = re.compile(r"라이브러리\s*ID\s*:\s*\d+|library\s*id\s*:\s*\d+", re.I)
```

- In `list_campaigns_for_effect`, exclude placeholder advertiser/campaign names.
- Only return campaigns that have:
  - a `CampaignLift`, or
  - at least one pre-period signal and one post-period signal around the campaign window.
- Add response fields such as:
  - `effect_ready`
  - `has_lift`
  - `pre_points`
  - `post_points`
  - `traffic_points`
  - `news_points`
  - `social_points`
- Order by quality/readiness first, then recency.
- Apply similar filtering to `/comparison` so comparison tables do not include empty campaigns.

Recommended frontend fix:

- Defensively filter returned campaigns again:

```tsx
const isPlaceholderCampaign = (campaign: any) =>
  /라이브러리\s*ID\s*:|library\s*id\s*:/i.test(
    `${campaign.advertiser_name ?? ""} ${campaign.campaign_name ?? ""}`,
  );
```

- Use `useEffect` for auto-selection.
- If no campaign is effect-ready, show a clear empty state:

```text
효과 분석 가능한 캠페인이 없습니다.
사전/사후 검색, 뉴스, 소셜 데이터 또는 캠페인 lift 계산이 필요합니다.
```

- In the before/after chart, replace the current generic empty message with a clearer reason when there is no pre/post data.

DB inspection note:

- A quick local SQLite inspection showed many recent rows with advertiser names like `라이브러리 ID: ...`, no lift values, and almost no useful signal data.
- The first attempted query used a non-existing column `c.name`; use `c.campaign_name` instead.
- Use UTF-8 output in PowerShell when printing DB rows:

```powershell
$env:PYTHONIOENCODING='utf-8'
```

## Completed: One-Click Advertiser Report Bundle MVP

The user asked for a one-click way to turn selected data into polished report files: PPT, PDF, and XLSX.

Implemented a first working MVP that generates a ZIP bundle containing all three formats for an advertiser.

Changed files:

- `api/routers/reports.py`
  - New router mounted at `/api/reports`.
  - New endpoint:
    - `GET /api/reports/advertiser/{advertiser_id}/bundle?days=30`
  - Requires paid authentication through the router dependency.
  - Collects advertiser report data:
    - advertiser profile
    - industry name
    - channel-level ad counts and spend
    - recent campaigns
    - recent creatives
    - social contents
    - summary insights
  - Generates:
    - `.xlsx` using `openpyxl`
    - `.pptx` using `python-pptx`
    - `.pdf` using `reportlab`
    - wraps all files into one ZIP response
  - Hides raw DB IDs and filters campaign names containing `라이브러리 ID:` from the campaign section.
- `api/main.py`
  - Imports and includes `reports.router`.
- `requirements.api.txt`
  - Added `python-pptx>=1.0`.
  - Added `reportlab>=4.0`.
- `requirements.txt`
  - Added `python-pptx>=1.0`.
  - Added `reportlab>=4.0`.
- `frontend/src/components/DownloadButtons.tsx`
  - Added `ReportBundleButton`.
  - Uses existing authenticated download helper.
- `frontend/src/app/advertisers/[id]/page.tsx`
  - Added `원클릭 보고서` button near existing advertiser download/export controls.

Verification performed:

- Installed local dependencies:

```powershell
python -m pip install python-pptx reportlab
```

- Python compile passed:

```powershell
python -m py_compile api/routers/reports.py api/main.py
```

- TypeScript compile passed:

```powershell
npx tsc --noEmit
```

- Direct local generation test passed for advertiser id `1`:
  - generated XLSX bytes
  - generated PPTX bytes
  - generated PDF bytes
  - generated ZIP bytes

Limitations / recommended next step:

- Advertiser/campaign detail image rendering was improved after the first MVP:
  - `frontend/src/lib/image-utils.ts` now tries proxied local `/images/...` URLs first and keeps R2 as a fallback.
  - `frontend/src/components/CreativeImage.tsx` was added for image fallback handling.
  - Advertiser detail and campaign detail use `CreativeImage`.
  - Campaign detail no longer forces search ads into text-only cards when an image exists.
- Report output was updated to be image-first:
  - PPTX now has a creative-thumbnail grid slide.
  - PDF now includes a thumbnail table for image creatives.
  - XLSX now includes an `이미지 소재` sheet with embedded thumbnails.
- Follow-up UI placement changes:
  - `frontend/src/components/Sidebar.tsx`: moved `캠페인 효과` out of the public `소셜 인사이트` group and into the admin-only `분석 도구` group as the last item.
  - `frontend/src/app/about/page.tsx`: menu structure copy now lists `캠페인효과` under `분석도구`, not `소셜인사이트`.
  - `frontend/src/components/DownloadButtons.tsx`: `자료 다운로드` dropdown now includes `원클릭 보고서` for the PPTX/PDF/XLSX ZIP bundle.
- PDF is functional and shareable, but still not as visually rich as the PPTX.
- PPTX includes thumbnails, but does not yet include generated charts.
- Good next step is to add:
  - channel spend charts
  - campaign effect section after the campaign-effect data quality filter is fixed
  - optional individual endpoints for only PPTX/PDF/XLSX if users do not always want ZIP

## Local Runtime State

During the session, local services were started and tested:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://localhost:3000`

Recheck running processes before assuming they are still alive.

## Git / Workspace Notes

The worktree was already dirty and contains unrelated/generated files. Do not revert unknown changes.

Known modified/new files from this work include:

- `api/main.py`
- `api/routers/admin.py`
- `database/models.py`
- `frontend/next.config.js`
- `frontend/public/robots.txt`
- `frontend/src/app/admin/page.tsx`
- `frontend/src/app/page.tsx`
- `frontend/src/app/sitemap.ts`
- `frontend/src/lib/api.ts`
- `frontend/src/middleware.ts`
- `frontend/src/app/admin/layout.tsx`
- `frontend/src/app/forgot-password/layout.tsx`
- `frontend/src/app/login/layout.tsx`
- `frontend/src/app/payment/layout.tsx`
- `frontend/src/app/privacy/layout.tsx`
- `frontend/src/app/signup/layout.tsx`
- `frontend/src/app/terms/layout.tsx`
- `frontend/src/components/AuthenticatedHome.tsx`
- `docs/CLAUDE_HANDOFF_2026-05-02.md`

Generated/possibly unrelated files also appeared or were already present, including database dumps, cache folders, and `frontend/tsconfig.tsbuildinfo`.

`git status` currently emits warnings about deeply nested paths under `cache/railway_deploy_root/...`. Be careful with broad recursive commands in `cache/`.

## 2026-05-02 Follow-up: Advertiser Detail Images / Bad Advertiser Names

Latest user issue:

- Advertiser detail page still showed some creative cards as text-only.
- Some advertiser names still appeared as platform parsing noise such as `Library ID: ...`, `라이브러리 ID: ...`, or short extracted English fragments.

Changes made:

- Added `api/services/advertiser_names.py`
  - Centralizes display filtering for obvious placeholder names.
  - Treats `Library ID`, `라이브러리 ID`, plain `library`/`라이브러리`, long numeric IDs, and a small set of scraper stopwords as non-display advertiser names.
  - Keeps raw DB values intact, but hides/sanitizes bad values before API responses.
  - Cleans campaign names containing library-id placeholders into safer fallback labels.
- Updated `api/routers/advertisers.py`
  - `media-breakdown` now uses `creative_image_path` first and `screenshot_path` as fallback.
  - `stored_images/...`, `screenshots/...`, remote HTTP image paths are returned even when local path probing fails, so the frontend can try `/images/...` and R2 fallback.
  - Recent creative gallery rows without any usable image path are skipped.
  - Advertiser list/search/tree/favorite/media responses now use sanitized display names.
- Updated `frontend/src/app/advertisers/[id]/page.tsx`
  - Recent creative cards filter for rows with `creative_image_path`, `screenshot_path`, or `thumbnail_url`.
  - Cards always render through `CreativeImage` using the first available image path.
- Updated `frontend/src/lib/api.ts`
  - `GalleryItem` now accepts optional `screenshot_path`.
- Updated `api/routers/campaign_effect.py` and `api/routers/campaigns.py`
  - Campaign-effect dropdown/overview/comparison and campaign list/detail responses now avoid library-id advertiser/campaign labels where possible.

Verification to rerun after changes:

```powershell
python -m py_compile api/services/advertiser_names.py api/routers/advertisers.py api/routers/campaigns.py api/routers/campaign_effect.py
npx tsc --noEmit
```

## 2026-05-02 Follow-up: KRW Amounts Should Be Whole Won

Latest user issue:

- Campaign effect/recent campaign table displayed estimated ad cost with decimal won values, e.g. `6,164,383.56원`.

Changes made:

- Updated `api/routers/campaign_effect.py`
  - Added `_won()` helper and returns integer KRW for campaign-effect overview, campaign list, and comparison `total_est_spend`.
- Updated `api/routers/advertisers.py`
  - Added `_won()` helper for advertiser-facing spend values.
  - Advertiser list, media breakdown channel/category totals, favorites, spend report totals, and daily spend points now return whole-won integers instead of 2-decimal floats.
- Updated `frontend/src/app/campaigns/page.tsx`
  - Added `formatWon()` and replaced raw `.toLocaleString() + "원"` spend rendering in campaign effect tab.
- Updated `frontend/src/app/campaign-effect/page.tsx`
  - `formatKRW()` now formats exact rounded whole-won values with `원`.
- Updated `frontend/src/lib/constants.ts`
  - `formatSpend()` rounds input to whole won before any abbreviated display.

Verification:

```powershell
python -m py_compile api/routers/campaign_effect.py api/routers/advertisers.py
npx tsc --noEmit
```

## 2026-05-02 Follow-up: Campaign Name Noise Still Showing

Latest user issue:

- Campaign tables still showed names like:
  - `라이브러리 ID: 820239857486469 4월캠페인`
  - long Greek discount ad copy used as an advertiser/campaign name.

Changes made:

- Updated `api/services/advertiser_names.py`
  - Added campaign-name noise detection:
    - strips month/campaign suffix for judging names,
    - treats `라이브러리 ID`, plain `라이브러리`, `Library ID`, long numeric IDs as invalid,
    - treats long Greek/ad-copy strings with discount/offer/percentage/urgent punctuation patterns as invalid.
  - `is_placeholder_advertiser_name()` now also rejects those long ad-copy names when they were parsed as advertisers.
  - `clean_campaign_name()` now falls back to advertiser-based or id-based names when campaign names are noisy.
- Existing campaign APIs now benefit from the helper:
  - `api/routers/campaign_effect.py`
  - `api/routers/campaigns.py`
  - advertiser detail report paths using shared campaign cleaning.

Verification:

```powershell
python -m py_compile api/services/advertiser_names.py api/routers/campaigns.py api/routers/campaign_effect.py api/routers/advertisers.py
npx tsc --noEmit
```

Direct local function checks for `/campaign-effect/campaigns?days=365` and `/campaigns/enriched` returned zero rows containing `라이브러리`, `Library`, or the Greek ad-copy marker.

## 2026-05-02 Follow-up: Campaign Effect Still Looked Like Social Insight

Latest user issue:

- User still saw/understood `캠페인 효과` as being under `소셜인사이트` on the frontend.

Findings:

- Main sidebar source `frontend/src/components/Sidebar.tsx` already has `/campaign-effect` only under the admin-only `분석 도구` group, not under `소셜 인사이트`.
- Remaining misleading frontend copy/cards existed in guide/about/FAQ/pricing-plan descriptions.

Changes made:

- `frontend/src/app/guide/page.tsx`
  - Removed `캠페인효과` card from the `소셜인사이트` section.
  - Added `캠페인효과` card to the `분석도구` section.
- `frontend/src/app/faq/page.tsx`
  - Removed `캠페인효과` from the social insight FAQ bullet list.
  - Changed plan table from `소셜인사이트 (채널/버즈/효과)` to `소셜인사이트 (채널/버즈)` plus separate `캠페인효과 (분석도구)` row.
- `frontend/src/app/about/page.tsx`
  - Removed campaign-effect wording from social insight descriptions/lists.
  - Describes campaign effect as an analysis-tool feature where mentioned.
- `frontend/src/lib/plans.ts`
  - Split `브랜드 채널/버즈/캠페인 효과 분석` into social brand analysis plus separate analysis-tool campaign-effect text.

Verification:

```powershell
npx tsc --noEmit
```

Local pages `/guide` and `/faq` returned 200.

## 2026-05-02 Follow-up: Systematic Advertiser Display Rules

Latest user issue:

- Person names, handles, library IDs, and ad-copy snippets were still appearing as advertiser/campaign names.
- User asked to rule this systematically instead of patching one visible row at a time.

Changes made:

- Updated `api/services/advertiser_names.py`
  - Centralized campaign display naming via `campaign_display_fields()`.
  - Treats Korean person names, handle-like names, library IDs, long numeric IDs, Greek/discount ad-copy, and short ad-copy phrases as low-confidence source names.
  - Low-confidence names are not displayed directly when a product/service/brand/category can be inferred.
  - Inference priority now uses structured product/brand/model fields, landing analysis, URL/domain, connected ad raw advertiser, and category patterns.
  - Added category fallbacks such as `부동산 분양`, `뷰티/화장품`, `건강/생활 상품`, `금융 서비스`, `동물병원/의료 서비스`, `교육 서비스`.
  - Known brand allowlist preserves names such as `마켓비`, `메디큐브`, `리리브`, `리쏘`, `올리브영`.
- Updated campaign APIs to use the centralized rule:
  - `api/routers/campaign_effect.py`
    - overview, comparison, campaign selector list.
    - pulls connected `AdDetail.advertiser_name_raw` only when the stored campaign advertiser is low-confidence.
  - `api/routers/campaigns.py`
    - enriched list, detail, effect card.
    - campaign detail uses connected creative context for display naming.
  - `api/routers/advertisers.py`
    - advertiser recent-ad gallery and search snippets no longer surface raw person/handle/library names directly.

Validation:

```powershell
python -m py_compile api/services/advertiser_names.py api/routers/campaign_effect.py api/routers/campaigns.py api/routers/advertisers.py
```

Direct local API function checks:

- `/api/campaign-effect/campaigns?days=365&limit=100`
  - No occurrences of `권이겸`, `이유정`, `모영지`, `마진기`, `라이브러리`, `a.precious_day`, `Chuu`, `Virtuoso`, or raw ad-copy phrase `세번도 할 수 있어요`.
  - Example replacements:
    - `권이겸` -> `호로파HRP`
    - `이유정` / `Chuu` / `a.precious_day` rows connected to pet-medical creative -> `동물병원/의료 서비스`
    - beauty copy rows -> `뷰티/화장품`
- `/api/campaigns/enriched?limit=100`
  - No occurrences of the same bad-name sample set.
  - Examples now show `건강/생활 상품`, `부동산 분양`, `금융 서비스`, `뷰티/화장품`, `교육 서비스` instead of person/ad-copy names.
