# AdScope - Ad Intelligence Platform

> 한국 디지털 광고 통합 모니터링 솔루션  
> Project Design Document v1.0 | 2026.02.06

---

## 1. Executive Summary

AdScope는 한국 디지털 광고 시장 대상 멀티채널 광고 모니터링 광고 인텔리전스 플랫폼이다. 경쟁사가 어떤 브랜드를, 어떤 타겟에게, 얼마나 오래, 얼마의 예산으로 광고하는지를 파악한다.

### 1.1 핵심 목표 - 7가지 광고 인텔리전스 질문

| 질문 | 설명 |
|------|------|
| 누가 (Who) | 광고주/브랜드 식별 |
| 무엇을 (What) | 제품/서비스 카테고리 |
| 왜 (Why) | 프로모션 목적/캠페인 성격 |
| 언제 (When) | 캠페인 시작/종료 추적 |
| 어디서 (Where) | 채널/매체별 집행 현황 |
| 누구에게 (Whom) | 타겟 연령/성별 분석 |
| 얼마나 (How much) | 추정 광고비 산출 |

---

## 2. 경쟁사 분석

### 2.1 국내 경쟁사

#### 리서치애드 (ResearchAd)

- 유튜브, 페이스북, 공중파 3사, 종편 포함 114개 매체에서 프리롤 광고 수집
- 자체 광고단가 모형으로 광고비 산출 (블랙박스)
- 페이스북은 패널 기반 수집 방식
- 월간 리포트 중심, 실시간성 부족
- **한계:** 광고비 추정 로직 비공개, 타겟팅 분석 없음, 레거시 UI

#### 유광기 (UGwanggi)

- 유튜브 광고 데이터 전문 - 경쟁사/산업군별 분류
- 매일 5만개+ 브랜드, 25만개+ 채널 데이터 제공
- 조회수, 반응, 예상 CPV 등 제공
- PPL 광고까지 추적 가능
- **한계:** 유튜브 전용, 멀티채널 미지원

### 2.2 해외 경쟁사

#### Pathmatics (Sensor Tower)

- 크로스채널 광고 인텔리전스 (소셜, 디스플레이, 비디오, 모바일)
- 센서 네트워크 + 독자적 데이터 파이프라인으로 크리에이티브/노출/추정 광고비 수집
- Share-of-Voice 및 카테고리 벤치마킹
- P&G, Unilever 급 엔터프라이즈 대상 (커스텀 가격)
- **한계:** 한국 시장 미지원, 네이버 데이터 없음

#### SEMrush / SpyFu

- 검색광고(Google/Bing) 특화 - 키워드, 광고 카피, 추정 광고비
- SpyFu: 수년간 히스토리 아카이브, 월 $39부터
- SEMrush: 통합 마케팅 툴, 월 $99~$220
- **한계:** 디스플레이/영상 광고 약함, 네이버 미지원

#### SimilarWeb

- 사이트 트래픽/채널 믹스/오디언스 분석
- 패널 데이터 + 공개 클릭스트림 + 직접 측정 결합
- 월 $125~$540+
- **한계:** 광고 크리에이티브 수준 분석 부족

#### 공개 광고 라이브러리

- Meta 광고 라이브러리 - 현재 라이브 광고 검색 (무료)
- Google 광고 투명성 센터 - 과거/현재 광고 조회 (무료)
- TikTok 상업용 콘텐츠 라이브러리 (무료)
- **한계:** 광고비 추정 불가, 개별 플랫폼별 분산

### 2.3 경쟁 우위 분석

| 구분 | 기존 서비스 | AdScope |
|------|------------|---------|
| 커버리지 | 단일 채널 특화 | 네이버+유튜브+메타 통합 |
| 한국 특화 | 리서치애드만 커버 | 네이버 검색/DA 중심 한국 시장 특화 |
| 타겟팅 분석 | 대부분 없음 | 연령대 × 시간대 × 요일 페르소나 기반 |
| 실시간성 | 월간 리포트 중심 | 하루 4회 수집, 시간대별 변화 추적 |
| 광고비 추정 | 블랙박스 모형 | 공개 CPC/단가 + 트렌드 보정 = 투명한 로직 |
| 데이터 방식 | 패널 의존 | Playwright 자동화 + 공개 API |
| 디바이스 | PC 중심 | PC + 모바일웹 동시 커버 |

---

## 3. 시스템 아키텍처

### 3.1 기술 스택

| 구성요소 | 기술 | 선택 이유 |
|---------|------|----------|
| 크롤러 | Python + Playwright | 브라우저 자동화, PC/모바일 에뮬레이션 |
| 스케줄러 | APScheduler / Cron | 시간대/요일/페르소나별 유연한 스케줄링 |
| 데이터베이스 | PostgreSQL | 시계열 데이터 + 복잡한 조인 쿼리 |
| 캐싱 | Redis | 중복 광고 필터링, 세션 관리 |
| 백엔드 API | FastAPI (Python) | 비동기 처리, 자동 문서화 |
| 프론트엔드 | Next.js + React | 대시보드 UI |
| 인프라 | Docker + AWS/GCP | 컨테이너 기반 배포 |

### 3.2 데이터 수집 파이프라인

```
[1단계] 스케줄러가 수집 작업 트리거
    ↓
[2단계] Playwright 브라우저 실행 (페르소나별 프로필 적용)
    ↓
[3단계] 페이지 로드 + 광고 영역 DOM 파싱 + 스크린샷 캡처
    ↓
[4단계] 광고 데이터 정규화 + 중복 필터링
    ↓
[5단계] DB 적재 + 광고비 추정 엔진 실행
```

### 3.3 프로젝트 디렉토리 구조

```
adscope/
├── README.md
├── docker-compose.yml
├── .env.example
│
├── crawler/                    # 데이터 수집 모듈
│   ├── __init__.py
│   ├── config.py              # 크롤러 설정 (UA, viewport, 타임아웃)
│   ├── base_crawler.py        # 크롤러 베이스 클래스
│   ├── naver_search.py        # 네이버 검색광고 크롤러
│   ├── naver_da.py            # 네이버 DA 배너 크롤러
│   ├── youtube_ads.py         # 유튜브 영상광고 크롤러
│   ├── meta_library.py        # Meta 광고 라이브러리 크롤러
│   ├── google_transparency.py # Google 광고 투명성 센터 크롤러
│   ├── trend_collector.py     # 네이버 트렌드 / Google Trends 수집
│   └── personas/
│       ├── __init__.py
│       ├── profiles.py        # 페르소나 프로필 정의 (P1~P4)
│       └── device_config.py   # PC/모바일 디바이스 설정
│
├── scheduler/                  # 스케줄링 모듈
│   ├── __init__.py
│   ├── scheduler.py           # APScheduler 메인 스케줄러
│   ├── schedules.py           # 페르소나별/요일별 수집 스케줄 정의
│   └── weekend_rules.py       # 주말 수집 조정 규칙
│
├── processor/                  # 데이터 처리 모듈
│   ├── __init__.py
│   ├── normalizer.py          # 광고 데이터 정규화
│   ├── deduplicator.py        # 중복 광고 필터링 (Redis)
│   ├── advertiser_matcher.py  # 광고주 자동 매칭/분류
│   └── spend_estimator.py     # 광고비 추정 엔진
│
├── database/                   # DB 관련
│   ├── models.py              # SQLAlchemy 모델 (ORM)
│   ├── schemas.py             # Pydantic 스키마
│   ├── migrations/            # Alembic 마이그레이션
│   └── seed_data/
│       ├── industries.json    # 업종 마스터 데이터
│       └── keywords.json      # 키워드 시드 데이터
│
├── api/                        # FastAPI 백엔드
│   ├── __init__.py
│   ├── main.py                # FastAPI 앱 엔트리포인트
│   ├── routers/
│   │   ├── ads.py             # 광고 스냅샷 조회 API
│   │   ├── campaigns.py       # 캠페인 추적 API
│   │   ├── advertisers.py     # 광고주 분석 API
│   │   ├── spend.py           # 광고비 추정 API
│   │   └── trends.py          # 트렌드 데이터 API
│   └── dependencies.py        # 인증, DB 세션 등
│
├── frontend/                   # Next.js 프론트엔드
│   ├── package.json
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   │   ├── Dashboard.tsx      # 메인 대시보드
│   │   │   ├── AdTimeline.tsx     # 광고 타임라인
│   │   │   ├── SpendChart.tsx     # 광고비 차트
│   │   │   ├── PersonaView.tsx    # 페르소나별 뷰
│   │   │   └── CampaignTracker.tsx # 캠페인 추적기
│   │   └── lib/
│   │       └── api.ts             # API 클라이언트
│   └── tailwind.config.ts
│
├── seeds/                      # 시드 데이터 관리
│   ├── generate_keywords.py   # 키워드 시드 생성 스크립트
│   └── industry_keyword_map.py # 업종-키워드 매핑
│
└── tests/
    ├── test_crawlers/
    ├── test_processor/
    └── test_api/
```

---

## 4. 데이터 소스별 수집 방법

| 채널 | 수집 방법 | 추출 데이터 |
|------|----------|------------|
| 네이버 검색광고 | Playwright로 키워드 검색 → 파워링크/비즈사이트 파싱 | 광고주, URL, 광고문구, 순위, 시간대 |
| 네이버 DA | 네이버 메인/서브페이지 배너 캡처 + 광고주 추출 | 배너 이미지, 광고주, 지면, 노출 빈도 |
| 유튜브 영상광고 | 브라우저 영상 재생 → 광고 트리거 시 DOM/네트워크 메타데이터 | 광고주, 광고 유형, 길이, 타겟팅 정보 |
| Meta 광고 | Meta 광고 라이브러리 (API/웹) | 광고주, 크리에이티브, 집행기간, 플랫폼 |
| Google GDN | Google 광고 투명성 센터 + 사이트 방문 시 캡처 | 광고주, 광고 포맷, 게재 사이트 |
| 검색 트렌드 | 네이버 트렌드 API + Google Trends | 키워드별 검색량, 시계열 변화 |
| 광고 단가 베이스 | 네이버 광고센터 CPC/검색량 정보 | CPC, 예상 클릭률, 예상 노출수 |

---

## 5. 페르소나 및 수집 스케줄

### 5.1 페르소나 프로필

| 페르소나 | 연령대 | 성별 | 로그인 | 주요 미디어 특성 |
|---------|--------|------|--------|----------------|
| P1 | 20대 | 여성 | 네이버 계정 | 인스타 릴스 > 유튜브, 퇴근후 피크 |
| P2 | 30대 | 남성 | 네이버 계정 | OTT 최다 이용, 출퇴근+점심 분산 |
| P3 | 50대 | 여성 | 네이버 계정 | 오전/오후 활발, 20시 이후 최대 피크 |
| P4 | - | - | 비로그인 | 타겟팅 없는 기본 광고 노출 기준선 |

### 5.2 연령대별 수집 시간대 (평일)

> 메조미디어 2025 타겟 리포트 + 나스미디어 NPR 기반

| 페르소나 | 수집 1회 | 수집 2회 | 수집 3회 | 수집 4회 |
|---------|---------|---------|---------|---------|
| P1 (20대여) | 12:00 점심 | 18:00 퇴근길 | 22:00 저녁피크 | 00:00 심야 |
| P2 (30대남) | 08:00 출근길 | 12:00 점심 | 18:00 퇴근길 | 22:00 저녁 |
| P3 (50대여) | 08:00 오전 | 10:00 오전 | 14:00 오후 | 20:00 저녁피크 |
| P4 (비로그인) | 08:00 오전 | 12:00 점심 | 18:00 퇴근 | 22:00 야간피크 |

### 5.3 주말 수집 조정

- 주말은 오전 늦게 시작 + 오후~저녁 몰림
- 쇼핑/여가/여행 키워드 급증
- 금요일 저녁~토요일: 여행/맛집/문화 키워드 추가 수집
- 월요일 오전: 금융/업무 키워드 강화

### 5.4 디바이스별 수집

| 디바이스 | 방법 | 비율 | 비고 |
|---------|------|------|------|
| PC | Playwright 기본 viewport (1920×1080) | 30% | 업무시간 중심 |
| 모바일웹 | Playwright device emulation (iPhone/Galaxy) | 70% | 전 시간대 |

> ※ 30대 페르소나는 오전 PC, 저녁 모바일로 실제 사용 패턴 반영

### 5.5 일일 수집량 예상

```
키워드 200개 × 4개 페르소나 × 4회/일 = 3,200회/일
Playwright 한 건당 3~5초 → 한 회차당 약 15~25분 소요
```

---

## 6. 업종-키워드 시드 데이터

### 6.1 우선 업종 (CPC 높은 순)

| 업종 | 예시 키워드 | 예상 CPC 범위 |
|------|-----------|--------------|
| 금융 | 대출, 보험, 신용카드, 주식, 저축 | 3,000~10,000원 |
| 의료/뷰티 | 성형, 피부과, 다이어트, 탈모, 수술 | 2,000~8,000원 |
| 교육 | 영어, 코딩, 자격증, 공무원, 유학 | 1,500~5,000원 |
| 부동산 | 아파트, 분양, 전세, 월세, 재개발 | 2,000~6,000원 |
| 법률 | 변호사, 이혼, 상속, 손해배상 | 3,000~10,000원 |
| 쇼핑/커머스 | 가전, 패션, 유아용품, 반려동물 | 500~2,000원 |
| IT/테크 | SaaS, 호스팅, 도메인, 보안 | 1,000~4,000원 |
| 여행 | 항공권, 호텔, 패키지, 투어 | 800~3,000원 |
| 음식/외식 | 맛집, 배달, 프랜차이즈, 카페 | 300~1,500원 |
| 자동차 | 신차, 중고차, 리스, 보험 | 2,000~7,000원 |

> ※ 업종당 5~10개 핵심 키워드 + 확장 키워드 → 총 100~200개 목표

---

## 7. 광고비 추정 로직

### 7.1 추정 공식

```
추정 광고비 = 노출 빈도 × 단가 × 기간
```

### 7.2 채널별 추정 방법

| 채널 | 추정 방법 | 보정 요소 |
|------|----------|----------|
| 네이버 검색광고 | 키워드 CPC × 추정 클릭수 × 노출 기간 | 네이버 광고센터 CPC + 트렌드 검색량 |
| 네이버 DA | 지면별 공시 단가 × 노출 빈도 | CPT(Cost Per Time) 지면은 공시가 활용 |
| 유튜브 | CPV 업종 평균 × 추정 노출량 | 광고 유형(TrueView/Bumper)별 차등 적용 |
| Meta | 집행 기간 + 크리에이티브 수 → 규모 추정 | Meta 광고 라이브러리 공개 데이터 |
| Google GDN | 노출 빈도 × CPM 업종 평균 | 광고 투명성 센터 데이터 |

### 7.3 보정 변수

- 네이버 트렌드 / Google Trends 검색량 → 시즈널리티 보정
- 연령대별 미디어 사용량 가중치
- 요일/시간대별 광고 경쟁 강도 보정
- 키워드 경쟁도 지수 반영

---

## 8. DB 스키마

### 8.1 핵심 테이블

| 테이블명 | 설명 | 주요 컬럼 |
|---------|------|----------|
| `industries` | 업종 마스터 | id, name, avg_cpc_range |
| `keywords` | 키워드 시드 | id, industry_id, keyword, naver_cpc, monthly_search_vol |
| `personas` | 페르소나 프로필 | id, age_group, gender, login_type, ua_string |
| `crawl_schedules` | 수집 스케줄 | id, persona_id, day_type, time_slot, device_type |
| `ad_snapshots` | 광고 스냅샷 (핵심) | id, keyword_id, persona_id, device, channel, captured_at |
| `ad_details` | 광고 상세 | id, snapshot_id, advertiser, brand, ad_text, position, url, screenshot_path |
| `advertisers` | 광고주 마스터 | id, name, industry_id, brand_name |
| `campaigns` | 캠페인 추적 | id, advertiser_id, first_seen, last_seen, est_spend, channels |
| `trend_data` | 트렌드 데이터 | id, keyword_id, date, naver_trend, google_trend |
| `spend_estimates` | 광고비 추정 | id, campaign_id, date, channel, est_daily_spend, confidence |

### 8.2 ERD 관계도

```
industries ──1:N──> keywords ──1:N──> ad_snapshots
                                          │
personas ──1:N──> crawl_schedules         │
personas ──1:N──────────────────────> ad_snapshots
                                          │
                                     1:N  ↓
                                     ad_details ──N:1──> advertisers
                                                              │
                                                         1:N  ↓
                                                         campaigns ──1:N──> spend_estimates
                                                         
keywords ──1:N──> trend_data
```

---

## 9. 개발 로드맵

### Phase 1 - MVP (4주)

**목표:** 네이버 검색광고 수집 + DB 적재 + 기본 대시보드

| 주차 | 작업 내용 | 산출물 |
|------|----------|--------|
| Week 1 | 업종-키워드 시드 데이터 정의 + DB 스키마 구축 | `database/models.py`, `seed_data/` |
| Week 2 | Playwright 크롤러 개발 (네이버 검색 PC+모바일웹) | `crawler/naver_search.py` |
| Week 3 | 페르소나별 프로필 + 스케줄러 + 네이버 트렌드 API 연동 | `crawler/personas/`, `scheduler/` |
| Week 4 | 기본 대시보드 (Next.js) + 광고비 추정 v1 | `frontend/`, `processor/spend_estimator.py` |

### Phase 2 - 확장 (4주)

**목표:** 네이버 DA + 유튜브 광고 추가

| 주차 | 작업 내용 | 산출물 |
|------|----------|--------|
| Week 5-6 | 네이버 DA 배너 수집 + 유튜브 웹 광고 캡처 | `crawler/naver_da.py`, `crawler/youtube_ads.py` |
| Week 7 | Meta 광고 라이브러리 + Google 투명성 센터 연동 | `crawler/meta_library.py`, `crawler/google_transparency.py` |
| Week 8 | 캠페인 추적 엔진 + 광고주 자동 분류 | `processor/advertiser_matcher.py` |

### Phase 3 - 고도화 (4주)

**목표:** 앱 광고 수집 + AI 분석

| 주차 | 작업 내용 | 산출물 |
|------|----------|--------|
| Week 9-10 | Android 에뮬레이터 + Appium 앱 광고 수집 | `crawler/app_ads.py` |
| Week 11 | AI 기반 광고 크리에이티브 분석 (소재 유형, 톤앤매너) | `processor/ai_analyzer.py` |
| Week 12 | 리포트 자동 생성 + 알림 시스템 + SaaS 출시 준비 | `api/routers/reports.py` |

---

## 10. 수익 모델

| 플랜 | 대상 | 기능 | 월 가격(안) |
|------|------|------|-----------|
| Starter | 소규모 광고주 | 업종 3개, 키워드 30개, 기본 대시보드 | 29만원 |
| Pro | 마케팅 에이전시 | 전 업종, 키워드 200개, 페르소나 분석, API | 79만원 |
| Enterprise | 대형 광고주/미디어렙 | 커스텀 키워드, 전채널, 전용 리포트, SLA | 협의 |

---

## 11. 개발 컨벤션

### 11.1 코드 스타일

- Python: Black formatter + isort + flake8
- TypeScript: ESLint + Prettier
- 커밋 메시지: `feat:`, `fix:`, `refactor:`, `docs:`, `test:` 접두사 사용

### 11.2 환경 변수 관리

```env
# .env.example
DATABASE_URL=postgresql://user:pass@localhost:5432/adscope
REDIS_URL=redis://localhost:6379/0
NAVER_TREND_CLIENT_ID=
NAVER_TREND_CLIENT_SECRET=
NAVER_AD_API_KEY=
META_ACCESS_TOKEN=
```

### 11.3 Claude Code 작업 시 주의사항

- 지정된 파일/함수만 수정. 관련 없는 코드 변경 금지
- 새 파일 생성 전 기존 구조 확인 필수
- DB 마이그레이션은 Alembic으로 관리 - 직접 스키마 수정 금지
- 크롤러 수정 시 반드시 해당 채널 테스트 실행 후 커밋
- `.env` 파일 커밋 절대 금지

---

*--- End of Document ---*
