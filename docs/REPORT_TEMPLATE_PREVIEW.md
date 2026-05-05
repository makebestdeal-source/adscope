# AdScope Report Template Preview

This document describes the first one-click report template currently implemented.

## Template: Advertiser Activity Summary

Purpose:

- A quick advertiser-facing or internal summary report.
- One download creates a ZIP containing PPTX, PDF, and XLSX.
- Endpoint: `GET /api/reports/advertiser/{advertiser_id}/bundle?days=30`

## Generated Files

The bundle contains:

- `adscope_{advertiser}_{date}.pptx`
  - presentation/reporting deck
- `adscope_{advertiser}_{date}.pdf`
  - shareable compact document
- `adscope_{advertiser}_{date}.xlsx`
  - underlying data workbook

## PPTX Layout

Slide 1: Cover

- AdScope brand label
- Advertiser name
- Analysis period
- Generated timestamp

Slide 2: Executive Summary

- Ad creative count
- Campaign count
- Estimated spend
- Top channel
- 3 to 5 automatically generated insight bullets

Slide 3: Channel Summary

- Channel
- Creative count
- First observed date
- Last observed date
- Estimated spend

Slide 4: Key Creatives and Campaigns

- Image-first creative thumbnail grid when creative images are available
- Falls back to text summaries only when no image file exists

Slide 5: Recent Campaigns

- Recent campaigns
- Campaign channel and recent observation date

## PDF Layout

Page 1 currently contains:

- Report title and period
- Executive summary bullets
- KPI table
- Channel summary table
- Recent creatives
- Estimation caveat

The PDF is functional but intentionally simpler than the PPTX in this MVP.

## XLSX Layout

Sheets:

- `요약`
- `채널 요약`
- `캠페인`
- `소재`
- `이미지 소재`
- `소셜`

## Current Sample Output

Generated local sample files:

- `cache/report_previews/adscope_sample_LGECOM홈스타일_20260502.pptx`
- `cache/report_previews/adscope_sample_LGECOM홈스타일_20260502.pdf`
- `cache/report_previews/adscope_sample_LGECOM홈스타일_20260502.xlsx`
- `cache/report_previews/adscope_sample_LGECOM홈스타일_20260502_bundle.zip`
- `cache/report_previews/adscope_sample_LGECOM홈스타일_20260502.page1.png`

Image-first regenerated samples:

- `cache/report_previews/adscope_sample_images_LGECOM홈스타일_20260502.pptx`
- `cache/report_previews/adscope_sample_images_LGECOM홈스타일_20260502.pdf`
- `cache/report_previews/adscope_sample_images_LGECOM홈스타일_20260502.xlsx`
- `cache/report_previews/adscope_sample_images_LGECOM홈스타일_20260502_bundle.zip`
- `cache/report_previews/adscope_sample_images_LGECOM홈스타일_20260502.page1.png`
- `cache/report_previews/adscope_sample_images_LGECOM홈스타일_20260502.page2.png`

## Known Template Gaps

- No selectable template UI yet.
- No in-browser preview modal yet.
- PPTX includes creative thumbnails, but does not yet include chart images.
- PDF design needs richer visual hierarchy.
- Campaign effect section should be added after the campaign-effect data quality filtering is fixed.

## Recommended Next Template Options

Template A: Executive Summary

- Short 4 to 6 slide advertiser summary.
- Best for sales calls and quick sharing.

Template B: Detailed Analysis

- 10 to 15 slides with channel, campaign, creative, social, and competitor sections.
- Best for monthly reporting.

Template C: Raw Data Pack

- XLSX-heavy output with minimal PPT/PDF.
- Best for analysts and agency operations teams.
