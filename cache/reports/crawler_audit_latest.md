# Crawler Audit

- Generated at: 2026-04-24 10:34:35
- Latest live crawl: 2026-04-23 13:52:17
- Latest staging row: 2026-04-23 13:52:17
- Scheduler disabled: yes
- Raw sample size per channel: 25

## What Counts As Raw-Ready

- Gallery export needs: advertiser_name, ad_text, ad_type, url
- Research sheet needs: advertiser_name, ad_placement
- Naver Shopping extra fields: keyword, price, shopping_category

## Global Blockers

- scheduler_disabled_flag
- playwright_launch_failures_in_scheduler_log

## Channel Summary

| Channel | Verdict | Last Live | Live Rows | Recent Raw Sample | Gallery Ready | Research Ready | Latest Batch |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| naver_search | broken | 2026-04-13 09:31:38 | 14406 | 25 | 100.0% | 0.0% | approved:4 |
| naver_da | degraded | 2026-04-21 00:31:42 | 4947 | 25 | 100.0% | 100.0% | deduped:20 |
| google_gdn | degraded | 2026-04-23 13:52:17 | 6380 | 25 | 100.0% | 100.0% | approved:2 |
| google_search_ads | degraded | 2026-04-23 09:23:56 | 9296 | 25 | 100.0% | 100.0% | deduped:2 |
| kakao_da | broken | 2026-03-26 13:49:25 | 2753 | 25 | 72.0% | 0.0% | pending:57 |
| youtube_ads | degraded | 2026-04-23 13:36:36 | 2783 | 25 | 100.0% | 100.0% | approved:13, deduped:5 |
| meta | degraded | 2026-04-23 13:40:05 | 5374 | 25 | 92.0% | 100.0% | deduped:1 |
| tiktok_ads | broken | 2026-04-23 13:42:15 | 38 | 25 | 36.0% | 36.0% | deduped:3 |
| naver_shopping | broken | 2026-03-24 13:48:06 | 554 | 4 | 0.0% | 0.0% | quarantine:2 |

## naver_search

- Crawler: `crawler.naver_search.NaverSearchCrawler`
- Verdict: `broken`
- Why: live data is older than 7 days, recent raw rows are missing advertiser or placement, automatic scheduler is disabled, scheduler log shows Playwright launch failures
- Last live snapshot: 2026-04-13 09:31:38 (11.04 days ago)
- Latest staging batch: `5fe83748-8d1c-464a-95f8-e9a7801cfc9c` at 2026-04-13 09:31:38
- Latest batch status counts: {"approved": 4}
- Recent raw sample size: 25
- Recent raw gallery-ready: 100.0%
- Recent raw research-ready: 0.0%
- Log failures: Playwright=70, circuit_open=72
- Code note: Core search fields are extracted directly from SERP HTML. Bizsite path intentionally leaves display_url empty.
- Worst recent raw fields: ad_placement 100.0% missing, display_url 96.0% missing, advertiser_name 0.0% missing
- Worst live fields: creative_image_path 100.0% missing, ad_product_name 96.88% missing, display_url 26.08% missing
- Top rejection reasons: name_rejected:ad_system_domain:ader.naver.com (6), name_rejected:non_ad_element (1), name_rejected:url_or_domain (1)

## naver_da

- Crawler: `crawler.naver_da.NaverDACrawler`
- Verdict: `degraded`
- Why: automatic scheduler is disabled, scheduler log shows Playwright launch failures
- Last live snapshot: 2026-04-21 00:31:42 (3.42 days ago)
- Latest staging batch: `b03902fa-94bd-4bcd-b8e5-5686c4efd233` at 2026-04-21 00:31:42
- Latest batch status counts: {"deduped": 20}
- Recent raw sample size: 25
- Recent raw gallery-ready: 100.0%
- Recent raw research-ready: 100.0%
- Log failures: Playwright=76, circuit_open=72
- Code note: Display crawler resolves click/adomain URLs before promotion and skips ads without a final URL.
- Worst recent raw fields: advertiser_name 0.0% missing, ad_text 0.0% missing, url 0.0% missing
- Worst live fields: ad_description 100.0% missing, ad_product_name 91.77% missing, creative_image_path 20.34% missing

## google_gdn

- Crawler: `crawler.google_gdn.GoogleGDNCrawler`
- Verdict: `degraded`
- Why: automatic scheduler is disabled, scheduler log shows Playwright launch failures
- Last live snapshot: 2026-04-23 13:52:17 (0.86 days ago)
- Latest staging batch: `92d17335-f0ae-4c45-b711-a44ace6b6320` at 2026-04-23 13:52:17
- Latest batch status counts: {"approved": 2}
- Recent raw sample size: 25
- Recent raw gallery-ready: 100.0%
- Recent raw research-ready: 100.0%
- Log failures: Playwright=78, circuit_open=72
- Code note: Transparency crawl uses placeholder text/display domain; image quality improves only after preview download.
- Worst recent raw fields: advertiser_name 0.0% missing, ad_text 0.0% missing, url 0.0% missing
- Worst live fields: ad_description 100.0% missing, ad_product_name 64.39% missing, creative_image_path 1.25% missing

## google_search_ads

- Crawler: `crawler.google_search_ads.GoogleSearchAdsCrawler`
- Verdict: `degraded`
- Why: automatic scheduler is disabled, scheduler log shows Playwright launch failures
- Last live snapshot: 2026-04-23 09:23:56 (1.05 days ago)
- Latest staging batch: `0b58d8bc-fa82-462b-a27a-9cd4a9e31ff7` at 2026-04-23 09:23:56
- Latest batch status counts: {"deduped": 2}
- Recent raw sample size: 25
- Recent raw gallery-ready: 100.0%
- Recent raw research-ready: 100.0%
- Log failures: Playwright=84, circuit_open=74
- Code note: Crawler only trusts transparency landing_url. If landing_url is absent, URL/display_url stay empty and washing quarantines the row.
- Worst recent raw fields: advertiser_name 0.0% missing, ad_text 0.0% missing, url 0.0% missing
- Worst live fields: ad_description 100.0% missing, creative_image_path 100.0% missing, ad_product_name 56.07% missing

## kakao_da

- Crawler: `crawler.kakao_da.KakaoDACrawler`
- Verdict: `broken`
- Why: live data is older than 21 days, recent raw rows are missing advertiser or placement, automatic scheduler is disabled, scheduler log shows Playwright launch failures
- Last live snapshot: 2026-03-26 13:49:25 (28.86 days ago)
- Latest staging batch: `75944b3d-9c3f-430f-8f03-4bc22627389c` at 2026-03-24 13:49:22
- Latest batch status counts: {"pending": 57}
- Recent raw sample size: 25
- Recent raw gallery-ready: 72.0%
- Recent raw research-ready: 0.0%
- Log failures: Playwright=82, circuit_open=72
- Code note: Advertiser name often falls back to profile/domain heuristics, which is fragile on SDK banner/native payloads.
- Worst recent raw fields: ad_placement 100.0% missing, advertiser_name 28.0% missing, ad_text 0.0% missing
- Worst live fields: ad_description 100.0% missing, ad_product_name 100.0% missing, creative_image_path 27.28% missing

## youtube_ads

- Crawler: `crawler.youtube_ads.YouTubeAdsCrawler`
- Verdict: `degraded`
- Why: automatic scheduler is disabled, scheduler log shows Playwright launch failures
- Last live snapshot: 2026-04-23 13:36:36 (0.87 days ago)
- Latest staging batch: `f39a5882-b4ce-4308-80fe-60a7941603bc` at 2026-04-23 13:36:36
- Latest batch status counts: {"approved": 13, "deduped": 5}
- Recent raw sample size: 25
- Recent raw gallery-ready: 100.0%
- Recent raw research-ready: 100.0%
- Log failures: Playwright=76, circuit_open=72
- Code note: Transparency video rows depend on landing_url from Google payload; many rows end up with no usable destination URL.
- Worst recent raw fields: advertiser_name 0.0% missing, ad_text 0.0% missing, url 0.0% missing
- Worst live fields: ad_description 97.95% missing, ad_product_name 69.82% missing, creative_image_path 1.98% missing

## meta

- Crawler: `crawler.meta_library.MetaLibraryCrawler`
- Verdict: `degraded`
- Why: automatic scheduler is disabled, scheduler log shows Playwright launch failures
- Last live snapshot: 2026-04-23 13:40:05 (0.87 days ago)
- Latest staging batch: `d947d272-0e1c-4555-a836-b9aef021cf4a` at 2026-04-23 13:40:05
- Latest batch status counts: {"deduped": 1}
- Recent raw sample size: 25
- Recent raw gallery-ready: 92.0%
- Recent raw research-ready: 100.0%
- Log failures: Playwright=56, circuit_open=41
- Code note: Rows with missing URL are still emitted and later filtered in washing. Creative screenshots depend on card-level capture success.
- Worst recent raw fields: url 8.0% missing, display_url 8.0% missing, advertiser_name 0.0% missing
- Worst live fields: ad_description 100.0% missing, ad_product_name 69.35% missing, creative_image_path 63.32% missing
- Top rejection reasons: name_rejected:meta_library_id (7), korean_filter_fail (4), missing_or_invalid_url (2)

## tiktok_ads

- Crawler: `crawler.tiktok_ads.TikTokAdsCrawler`
- Verdict: `broken`
- Why: recent raw rows are not gallery-ready, recent raw rows are missing advertiser or placement, recent raw rows are often missing advertiser_name, automatic scheduler is disabled
- Last live snapshot: 2026-04-23 13:42:15 (0.87 days ago)
- Latest staging batch: `88834b23-bf69-431c-b77c-6b62b82f0c00` at 2026-04-23 13:42:16
- Latest batch status counts: {"deduped": 3}
- Recent raw sample size: 25
- Recent raw gallery-ready: 36.0%
- Recent raw research-ready: 36.0%
- Log failures: Playwright=88, circuit_open=76
- Code note: Advertiser extraction is weak and fallback URL can be a Creative Center modal rather than the real landing page.
- Worst recent raw fields: advertiser_name 64.0% missing, ad_text 0.0% missing, url 0.0% missing
- Worst live fields: ad_description 100.0% missing, ad_product_name 60.53% missing, advertiser_name_raw 34.21% missing

## naver_shopping

- Crawler: `crawler.naver_shopping.NaverShoppingCrawler`
- Verdict: `broken`
- Why: live data is older than 21 days, recent raw rows are not gallery-ready, recent raw rows are missing advertiser or placement, recent raw rows are mostly missing URL
- Last live snapshot: 2026-03-24 13:48:06 (30.87 days ago)
- Latest staging batch: `3dc73cac-234a-4e11-b6c8-432a12a3a02b` at 2026-03-24 09:27:19
- Latest batch status counts: {"quarantine": 2}
- Recent raw sample size: 4
- Recent raw gallery-ready: 0.0%
- Recent raw research-ready: 0.0%
- Log failures: Playwright=84, circuit_open=74
- Code note: Shopping rows rely on mall/store metadata and adcr resolution; missing mall info weakens advertiser quality.
- Recent raw shopping-sheet ready: 0.0%
- Worst recent raw fields: advertiser_name 100.0% missing, url 100.0% missing, ad_text 0.0% missing
- Worst live fields: ad_description 100.0% missing, ad_product_name 100.0% missing, creative_image_path 2.53% missing
- Top rejection reasons: missing_or_invalid_url (4)
