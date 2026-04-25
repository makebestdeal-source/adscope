# AdScope Crawler Status

- generated_at: 2026-04-22
- basis: crawler code + `adscope.db`
- viewpoint: `작년 데이터 백필`과 `국내 주요 매체 커버리지 복구`

## Overall

- 현재 실질 운영 채널은 `naver_search`, `naver_da`, `google_search_ads`, `google_gdn`, `meta`, `youtube_ads`, `kakao_da`, `naver_shopping`, `tiktok_ads`다.
- `google_search_ads`, `google_gdn`, `youtube_ads`, `meta`는 아카이브/라이브러리 기반 백필이 가능한 축이다.
- `naver_search`, `naver_da`, `kakao_da`, `naver_shopping`은 결국 실관측 품질과 수집량을 다시 세워야 하는 축이다.
- `tiktok_ads`와 모바일 패널은 아직 운영 지표로 보기 어렵다.

## Channel Snapshot

| Channel | Ads | Advertisers | Latest Capture | Retroactive | Key Status |
|---|---:|---:|---|---:|---|
| naver_search | 14,406 | 2,093 | 2026-04-13 | 0 | 볼륨 최상, 주요 갭 1순위, 신선도 정지 |
| google_search_ads | 9,248 | 1,346 | 2026-04-21 | 2,174 | 아카이브 백필 핵심, 승격 규칙 보강 필요 |
| google_gdn | 6,214 | 1,574 | 2026-04-13 | 951 | 아카이브 가능, 이미지 보존 양호 |
| meta | 5,339 | 1,796 | 2026-04-13 | 1,091 | 라이브러리/API 가능, 이미지 누락 큼 |
| naver_da | 4,947 | 407 | 2026-04-21 | 0 | 국내 실관측 핵심, 광고주 폭 확대 필요 |
| kakao_da | 2,753 | 141 | 2026-03-26 | 0 | 국내 중요도 대비 볼륨 부족 |
| youtube_ads | 2,610 | 712 | 2026-04-20 | 0 | 아카이브 가능, 백필 승격 로직 점검 필요 |
| naver_shopping | 554 | 158 | 2026-03-24 | 0 | 국내 중요도 대비 볼륨 매우 부족 |
| tiktok_ads | 33 | 16 | 2026-03-24 | 0 | 실험 단계 |

## Archive-First Group

### google_search_ads
- 구현: `crawler/google_search_ads.py`
- 상태: 2026-04-21 기준 실제 수집은 됨.
- 문제: 아카이브 row는 랜딩 URL이 자주 비어 있어 `staging -> live` 세척기에서 격리되기 쉬움.
- 의미: 2025 백필 관점에서 가장 먼저 뚫어야 할 채널.

### google_gdn
- 구현: `crawler/google_gdn.py`
- 상태: 아카이브 row가 이미 일부 live 반영됨.
- 강점: `creative_image_path` 누락이 낮아 소재 보존성이 가장 낫다.
- 문제: 최신성이 2026-04-13에 멈춤.

### youtube_ads
- 구현: `crawler/youtube_ads.py`, `crawler/youtube_surf.py`
- 상태: 최근 수집은 2026-04-20까지 있음.
- 강점: 이미지 누락이 낮고 채널 중요도도 높다.
- 문제: 아카이브 소급 적재는 아직 본격 반영되지 않음.

### meta
- 구현: `crawler/meta_library.py`, `crawler/meta_feed_surf.py`, `crawler/instagram_catalog.py`
- 상태: 라이브러리/API 경로와 피드 서프 경로가 공존.
- 강점: 아카이브 가능성과 광고주 폭은 높다.
- 문제: 이미지 누락이 크고, 기존 소급 데이터는 날짜 필드/월별 관리가 불완전한 흔적이 있다.

## Rebuild Group

### naver_search
- 구현: `crawler/naver_search.py`
- 상태: 전체 볼륨은 가장 크지만 최신 수집은 2026-04-13에 멈춤.
- 강점: 광고주 연결 복구 후 누락률이 크게 내려간 상태.
- 문제: 주요 갭 광고주를 가장 많이 놓치고 있고, 검색형이라 소재 이미지 축적은 거의 없다.

### naver_da
- 구현: `crawler/naver_da.py`
- 상태: 2026-04-21까지 비교적 최근 데이터 존재.
- 강점: 국내 대행사 실무에 중요한 실관측 매체.
- 문제: 광고주 수가 407개로 아직 좁다.

### kakao_da
- 구현: `crawler/kakao_da.py`
- 상태: 2026-03-26 이후 정체.
- 강점: 국내 커버리지 관점에서 빠질 수 없는 채널.
- 문제: 볼륨과 최신성이 모두 부족하다.

### naver_shopping
- 구현: `crawler/naver_shopping.py`
- 상태: 2026-03-24 이후 정체.
- 강점: 쇼핑형 광고주/스마트스토어 연결에는 중요.
- 문제: 절대 수집량이 너무 적다.

## Low-Readiness Group

### tiktok_ads
- 구현: `crawler/tiktok_ads.py`
- 상태: 33건, 광고주 16개 수준.
- 판단: 지금은 우선순위 하위. 특정 업종 수요가 생기기 전까지 파일럿 수준 유지가 적절하다.

### mobile panel
- 구현: `scripts/mobile_capture.py`, `scripts/mobile_app_capture.py`, `processor/mobile_ad_detector.py`
- 상태: `mobile_panel_exposures` 12건.
- 판단: 현재 상태로는 품질/볼륨 지표로 쓸 수 없다.

## Immediate Priorities

1. `google_search_ads -> google_gdn -> youtube_ads -> meta` 순으로 2025 아카이브 백필 경로를 확정한다.
2. `naver_search -> naver_da -> kakao_da -> naver_shopping` 순으로 실관측 수집량과 품질을 재건한다.
3. `tiktok_ads`와 모바일 패널은 핵심 커버리지 복구 뒤로 미룬다.
