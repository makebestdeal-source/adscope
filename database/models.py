"""AdScope DB 모델 — 10개 핵심 테이블. (SQLite/PostgreSQL 호환)"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────
# 1. 업종 마스터
# ─────────────────────────────────────────────
class Industry(Base):
    __tablename__ = "industries"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    avg_cpc_min = Column(Integer)
    avg_cpc_max = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    keywords = relationship("Keyword", back_populates="industry")
    advertisers = relationship("Advertiser", back_populates="industry")
    product_categories = relationship("ProductCategory", back_populates="industry")


# ─────────────────────────────────────────────
# 1-1. 제품/서비스 카테고리
# ─────────────────────────────────────────────
class ProductCategory(Base):
    __tablename__ = "product_categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    parent_id = Column(Integer, ForeignKey("product_categories.id"), nullable=True)
    industry_id = Column(Integer, ForeignKey("industries.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    industry = relationship("Industry", back_populates="product_categories")
    parent = relationship("ProductCategory", remote_side="ProductCategory.id", backref="children")
    ad_details = relationship("AdDetail", back_populates="product_category_rel")

    __table_args__ = (
        Index("ix_product_categories_parent", "parent_id"),
        Index("ix_product_categories_industry", "industry_id"),
    )


# ─────────────────────────────────────────────
# 2. 키워드 시드
# ─────────────────────────────────────────────
class Keyword(Base):
    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True)
    industry_id = Column(Integer, ForeignKey("industries.id"), nullable=False)
    keyword = Column(String(200), nullable=False)
    naver_cpc = Column(Integer)
    monthly_search_vol = Column(Integer)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    industry = relationship("Industry", back_populates="keywords")
    snapshots = relationship("AdSnapshot", back_populates="keyword")
    trends = relationship("TrendData", back_populates="keyword")

    __table_args__ = (
        Index("ix_keywords_industry", "industry_id"),
        Index("ix_keywords_keyword", "keyword"),
    )


# ─────────────────────────────────────────────
# 3. 페르소나 프로필
# ─────────────────────────────────────────────
class Persona(Base):
    __tablename__ = "personas"

    id = Column(Integer, primary_key=True)
    code = Column(String(20), nullable=False, unique=True)
    age_group = Column(String(10))
    gender = Column(String(10))
    login_type = Column(String(20), nullable=False)
    ua_string = Column(Text)
    description = Column(String(200))
    # ── Phase 3B 확장 ──
    targeting_category = Column(String(20))   # "demographic", "control"
    is_clean = Column(Boolean, default=False)
    primary_device = Column(String(20))       # "mobile_iphone", "mobile_galaxy", "pc"

    schedules = relationship("CrawlSchedule", back_populates="persona")
    snapshots = relationship("AdSnapshot", back_populates="persona")
    ad_details = relationship("AdDetail", back_populates="persona")


# ─────────────────────────────────────────────
# 4. 수집 스케줄
# ─────────────────────────────────────────────
class CrawlSchedule(Base):
    __tablename__ = "crawl_schedules"

    id = Column(Integer, primary_key=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False)
    day_type = Column(String(10), nullable=False)
    time_slot = Column(String(5), nullable=False)
    device_type = Column(String(10), nullable=False)
    label = Column(String(50))

    persona = relationship("Persona", back_populates="schedules")

    __table_args__ = (
        Index("ix_schedules_persona_day", "persona_id", "day_type"),
    )


# ─────────────────────────────────────────────
# 5. 광고 스냅샷 (핵심 — 시계열 데이터)
# ─────────────────────────────────────────────
class AdSnapshot(Base):
    __tablename__ = "ad_snapshots"

    id = Column(Integer, primary_key=True)
    keyword_id = Column(Integer, ForeignKey("keywords.id"), nullable=False)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False)
    device = Column(String(10), nullable=False)
    channel = Column(String(30), nullable=False)
    captured_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    page_url = Column(Text)
    screenshot_path = Column(Text)
    raw_html_path = Column(Text)
    ad_count = Column(Integer, default=0)
    crawl_duration_ms = Column(Integer)

    keyword = relationship("Keyword", back_populates="snapshots")
    persona = relationship("Persona", back_populates="snapshots")
    details = relationship("AdDetail", back_populates="snapshot", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_snapshots_captured", "captured_at"),
        Index("ix_snapshots_channel_time", "channel", "captured_at"),
        Index("ix_snapshots_keyword_persona", "keyword_id", "persona_id"),
    )


# ─────────────────────────────────────────────
# 6. 광고 상세
# ─────────────────────────────────────────────
class AdDetail(Base):
    __tablename__ = "ad_details"

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("ad_snapshots.id", ondelete="CASCADE"), nullable=False)
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=True)
    # 쿼리 최적화용 비정규화 컬럼. 원본: ad_snapshots.persona_id
    # 새 쿼리에서는 AdSnapshot.persona_id를 JOIN으로 사용 권장
    # 현재 AdDetail.persona_id 직접 조인: api/routers/analytics.py (ad-persona-breakdown)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=True,
                        comment="비정규화: ad_snapshots.persona_id 복사본. JOIN 권장")
    advertiser_name_raw = Column(String(200))
    brand = Column(String(200))
    ad_text = Column(Text)
    ad_description = Column(Text)
    position = Column(Integer)
    url = Column(Text)
    display_url = Column(String(500))
    ad_type = Column(String(50))
    verification_status = Column(String(30))  # verified | unverified | likely_verified | unknown
    verification_source = Column(String(100))  # e.g., meta_ads_library / google_ads_transparency_center
    screenshot_path = Column(Text)
    # ── 6W 확장 필드 ──
    product_name = Column(String(200))         # What: 제품/서비스명 (e.g. "갤럭시 Z Fold")
    # DEPRECATED: AI 자동분류 결과 문자열. 정규화된 분류는 product_category_id FK를 사용할 것
    # ai_enricher.py에서 product_category 텍스트 설정 시 product_category_id도 동시에 설정됨 (line 373-377)
    # 신규 코드에서는 product_category_id -> ProductCategory.name 조인을 사용할 것
    product_category = Column(String(100), nullable=True, comment="[DEPRECATED] AI 분류 텍스트. product_category_id 사용 권장")
    ad_placement = Column(String(100))         # Where: 광고 지면 코드 (e.g. "naver_main_timeboard")
    promotion_type = Column(String(50))        # Why: 광고 목적 (e.g. "product_launch", "sale")
    creative_image_path = Column(Text)         # 광고 소재/영역 element 스냅샷 경로
    creative_hash = Column(String(64))         # 소재 중복 제거용 이미지 해시 (perceptual hash)
    # ── 중복 추적 (캠페인 연속성) ──
    first_seen_at = Column(DateTime)             # 최초 수집 시점
    last_seen_at = Column(DateTime)              # 최근 수집 시점
    seen_count = Column(Integer, default=1)      # 수집 횟수 (캠페인 연속성 추적)
    # ── Phase 3: 광고 분류 필드 ──
    position_zone = Column(String(20))         # "top", "middle", "bottom", "unknown"
    is_inhouse = Column(Boolean, default=False)  # 인하우스(자사) 광고 여부
    is_retargeted = Column(Boolean, default=False)  # 리타겟팅 광고 여부
    retargeting_network = Column(String(50))   # "criteo", "adroll", "rtbhouse" 등
    ad_marker_type = Column(String(50))        # "url_pattern", "text_label", "adchoices_icon", "visual_mark"
    # ── Visual Mark Detection (이미지 내 i마크/AD뱃지/x마크 탐지) ──
    visual_mark_detected = Column(String(200))    # 발견된 마크 쉼표 구분 ("i_mark,ad_badge,x_mark")
    visual_mark_network = Column(String(50))      # 추정 네트워크 ("google","naver","kakao","meta","unknown")
    visual_mark_confidence = Column(Float)        # 0.0~1.0
    visual_mark_analyzed = Column(Boolean, default=False)  # Vision AI 분석 완료 여부
    visual_mark_result = Column(JSON)             # Vision API 전체 응답
    # ── 접촉/카탈로그 구분 ──
    is_contact = Column(Boolean, default=True)  # True=실접촉, False=카탈로그(Transparency/Library)
    # ── 제품/서비스 카테고리 (정규화 FK — 이것이 정식 분류 컬럼) ──
    product_category_id = Column(Integer, ForeignKey("product_categories.id"), nullable=True,
                                 comment="정규화된 제품 카테고리 FK. product_category(텍스트)보다 이것을 사용할 것")
    # ── 마케팅 플랜 계층 필드 ──
    campaign_purpose = Column(String(30))        # commerce/event/branding/awareness/performance/launch/promotion/retargeting
    ad_format_type = Column(String(30))          # search/display/video/social/shopping/message
    # 크롤링 시 원본 텍스트. 정규화된 광고상품은 ad_product_master 테이블 참조.
    # ad_product_master_id FK로 정본 연결, 이 필드는 원본 보존 용도로 유지.
    ad_product_name = Column(String(100))        # 파워링크, 트루뷰 인스트림, 릴스광고 등 (원본 텍스트)
    ad_product_master_id = Column(Integer, ForeignKey("ad_product_master.id"), nullable=True)  # 정규화된 광고상품 FK
    model_name = Column(String(200))             # 모델/셀럽 이름
    estimated_budget = Column(Float)             # 건별 추정 예산
    extra_data = Column(JSON)

    snapshot = relationship("AdSnapshot", back_populates="details")
    advertiser = relationship("Advertiser", back_populates="ad_details")
    persona = relationship("Persona", back_populates="ad_details")
    product_category_rel = relationship("ProductCategory", back_populates="ad_details")
    ad_product_master = relationship("AdProductMaster", backref="ad_details")

    __table_args__ = (
        Index("ix_details_snapshot", "snapshot_id"),
        Index("ix_details_advertiser", "advertiser_id"),
        Index("ix_details_persona", "persona_id"),
        Index("ix_details_creative_hash", "creative_hash"),
        Index("ix_details_verification_status", "verification_status"),
        Index("ix_details_verification_source", "verification_source"),
    )


# ─────────────────────────────────────────────
# 7. 광고주 마스터
# ─────────────────────────────────────────────
class Advertiser(Base):
    __tablename__ = "advertisers"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    industry_id = Column(Integer, ForeignKey("industries.id"), nullable=True)
    parent_id = Column(Integer, ForeignKey("advertisers.id"), nullable=True)  # 모회사/그룹사
    advertiser_type = Column(String(20))  # "group", "company", "brand", "product"
    brand_name = Column(String(200))
    website = Column(String(500))
    aliases = Column(JSON)  # ["samsung", "삼성"] — list로 저장
    # -- 백데이터 (기업 프로필) --
    annual_revenue = Column(Float)                    # 연매출 (원)
    employee_count = Column(Integer)                  # 직원수
    founded_year = Column(Integer)                    # 설립연도
    description = Column(Text)                        # 기업 설명
    logo_url = Column(String(500))                    # 로고 이미지 URL
    headquarters = Column(String(200))                # 본사 위치
    is_public = Column(Boolean, default=False)        # 상장 여부
    market_cap = Column(Float)                        # 시가총액 (원)
    business_category = Column(String(50))            # KSIC 세부 업종
    official_channels = Column(JSON)                  # {"youtube": "url", "instagram": "handle"}
    data_source = Column(String(100))                 # 데이터 출처 (manual, csv, dart)
    profile_updated_at = Column(DateTime)             # 프로필 최종 업데이트
    smartstore_url = Column(String(500))              # 네이버 스마트스토어 URL
    dart_ad_expense = Column(Float)                   # DART 광고비 (원)
    dart_fiscal_year = Column(String(10))             # DART 회계연도
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    industry = relationship("Industry", back_populates="advertisers")
    ad_details = relationship("AdDetail", back_populates="advertiser")
    campaigns = relationship("Campaign", back_populates="advertiser")
    parent = relationship("Advertiser", remote_side="Advertiser.id", backref="children")

    __table_args__ = (
        Index("ix_advertisers_name", "name"),
        Index("ix_advertisers_industry", "industry_id"),
        Index("ix_advertisers_parent", "parent_id"),
    )


# ─────────────────────────────────────────────
# 8. 캠페인 추적
# ─────────────────────────────────────────────
class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True)
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=False)
    keyword_id = Column(Integer, ForeignKey("keywords.id"), nullable=True)
    channel = Column(String(30), nullable=False)
    first_seen = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    total_est_spend = Column(Float, default=0.0)
    snapshot_count = Column(Integer, default=0)
    channels = Column(JSON)  # ["naver_search", "youtube"]
    extra_data = Column(JSON)

    # ── 캠페인 체계화 필드 (Phase: journey_lift) ──
    campaign_name = Column(String(300))                     # AI 생성 또는 수동 입력
    objective = Column(String(30))                          # brand_awareness/traffic/engagement/conversion/retention
    product_service = Column(String(200),                   # 캠페인 설명용 자유 텍스트. 제품 분류 체계(product_categories)와 별개
                                 comment="캠페인별 상품/서비스 자유 텍스트. 분류 체계(ProductCategory)와 별개")
    promotion_copy = Column(Text)                           # 핵심 프로모션 카피
    model_info = Column(String(200))                        # 모델/셀럽 정보
    target_keywords = Column(JSON)                          # {"brand":[], "product":[], "competitor":[]}
    start_at = Column(DateTime)                             # 캠페인 시작 (초기값=first_seen)
    end_at = Column(DateTime)                               # 캠페인 종료 (초기값=last_seen)
    creative_ids = Column(JSON)                             # 연결된 ad_detail ID 목록
    status = Column(String(20), default="active")           # active/completed/paused
    enrichment_status = Column(String(20), default="pending")  # pending/enriched/manual_override
    enriched_at = Column(DateTime)
    spend_category = Column(String(20))  # shopping/search/banner/video/social

    advertiser = relationship("Advertiser", back_populates="campaigns")
    spend_estimates = relationship("SpendEstimate", back_populates="campaign", cascade="all, delete-orphan")
    journey_events = relationship("JourneyEvent", back_populates="campaign", cascade="all, delete-orphan")
    lifts = relationship("CampaignLift", back_populates="campaign", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_campaigns_advertiser", "advertiser_id"),
        Index("ix_campaigns_active", "is_active", "last_seen"),
    )


# ─────────────────────────────────────────────
# 9. 트렌드 데이터
# ─────────────────────────────────────────────
class TrendData(Base):
    __tablename__ = "trend_data"

    id = Column(Integer, primary_key=True)
    keyword_id = Column(Integer, ForeignKey("keywords.id"), nullable=False)
    date = Column(DateTime, nullable=False)
    naver_trend = Column(Float)
    google_trend = Column(Float)
    naver_search_vol = Column(Integer)

    keyword = relationship("Keyword", back_populates="trends")

    __table_args__ = (
        Index("ix_trend_keyword_date", "keyword_id", "date", unique=True),
    )


# ─────────────────────────────────────────────
# 10. 광고비 추정
# ─────────────────────────────────────────────
class SpendEstimate(Base):
    __tablename__ = "spend_estimates"

    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    date = Column(DateTime, nullable=False)
    channel = Column(String(30), nullable=False)
    est_daily_spend = Column(Float, nullable=False)
    confidence = Column(Float)
    calculation_method = Column(String(50))
    factors = Column(JSON)

    campaign = relationship("Campaign", back_populates="spend_estimates")

    __table_args__ = (
        Index("ix_spend_campaign_date", "campaign_id", "date"),
        Index("ix_spend_channel_date", "channel", "date"),
    )


# ─────────────────────────────────────────────
# 11. 사용자 (인증)
# ─────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=True)
    role = Column(String, default="viewer")  # "admin", "viewer"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # OAuth 소셜 로그인
    oauth_provider = Column(String, nullable=True)  # "google", "kakao", "naver", None(local)
    oauth_id = Column(String, nullable=True)  # provider-specific user ID

    # 기업회원 정보
    company_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    plan = Column(String, default="lite")  # "lite", "full", "admin"
    plan_period = Column(String, nullable=True)  # "monthly", "yearly"
    plan_started_at = Column(DateTime, nullable=True)
    plan_expires_at = Column(DateTime, nullable=True)
    trial_started_at = Column(DateTime, nullable=True)  # 무료체험 시작일
    payment_confirmed = Column(Boolean, default=False)  # 결제 확인 여부


# ─────────────────────────────────────────────
# 11-b. 사용자 세션 (보안 - 동시접속 차단)
# ─────────────────────────────────────────────
class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_token = Column(String(64), unique=True, nullable=False)
    device_fingerprint = Column(String(128), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    revoke_reason = Column(String(100), nullable=True)

    user = relationship("User", backref="sessions")

    __table_args__ = (
        Index("ix_user_session_user", "user_id"),
        Index("ix_user_session_token", "session_token"),
        Index("ix_user_session_active", "user_id", "is_active"),
    )


class LoginHistory(Base):
    __tablename__ = "login_history"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    email = Column(String, nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    device_fingerprint = Column(String(128), nullable=True)
    success = Column(Boolean, default=True)
    failure_reason = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="login_history")

    __table_args__ = (
        Index("ix_login_history_user", "user_id"),
        Index("ix_login_history_created", "created_at"),
    )



# ─────────────────────────────────────────────
# 11-d. 비밀번호 리셋 토큰
# ─────────────────────────────────────────────
class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(128), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="password_reset_tokens")

    __table_args__ = (
        Index("ix_password_reset_token", "token"),
        Index("ix_password_reset_user", "user_id"),
    )

# ─────────────────────────────────────────────
# 12. 매체 광고 상품 (단가/지면 정보)
#     [DEPRECATED] ad_product_master로 통합됨.
#     pricing 정보는 ad_product_master에 흡수됨.
#     기존 데이터 보존을 위해 테이블 유지, 신규 코드에서는 사용 금지.
# ─────────────────────────────────────────────
class MediaAdProduct(Base):
    """DEPRECATED: ad_product_master 테이블로 통합됨. 신규 코드에서 사용 금지."""
    __tablename__ = "media_ad_products"

    id = Column(Integer, primary_key=True)
    channel = Column(String(30), nullable=False)      # "naver_search", "kakao_da" 등
    product_name = Column(String(100), nullable=False)  # "파워링크", "비즈보드" 등
    position_zone = Column(String(20))                  # "top", "middle", "bottom"
    pricing_model = Column(String(10), nullable=False)  # "CPC", "CPM", "CPT", "CPV"
    base_price = Column(Float)                          # 기본 단가
    price_range_min = Column(Float)
    price_range_max = Column(Float)
    device = Column(String(10), default="all")          # "pc", "mobile", "all"
    is_active = Column(Boolean, default=True)
    extra_data = Column(JSON)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # FK to canonical master (마이그레이션 후 연결)
    ad_product_master_id = Column(Integer, ForeignKey("ad_product_master.id"), nullable=True)

    ad_product_master = relationship("AdProductMaster", backref="legacy_media_products")

    __table_args__ = (
        Index("ix_media_products_channel", "channel"),
        Index("ix_media_products_channel_zone", "channel", "position_zone"),
    )


# ─────────────────────────────────────────────
# 13. 브랜드 채널 콘텐츠 (공식 채널 모니터링)
# ─────────────────────────────────────────────
class BrandChannelContent(Base):
    __tablename__ = "brand_channel_contents"

    id = Column(Integer, primary_key=True)
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=False)
    platform = Column(String(30), nullable=False)         # "youtube", "instagram"
    channel_url = Column(String(500), nullable=False)
    content_id = Column(String(200), nullable=False)      # video_id or post shortcode
    content_type = Column(String(30))                     # "video", "short", "reel", "post"
    title = Column(String(500))
    description = Column(Text)
    thumbnail_url = Column(String(500))
    upload_date = Column(DateTime)
    view_count = Column(Integer)
    like_count = Column(Integer)
    duration_seconds = Column(Integer)
    is_ad_content = Column(Boolean, default=False)
    ad_indicators = Column(JSON)
    extra_data = Column(JSON)
    discovered_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    advertiser = relationship("Advertiser", backref="brand_contents")

    __table_args__ = (
        Index("ix_brand_content_advertiser", "advertiser_id"),
        Index("ix_brand_content_platform", "platform"),
        Index("ix_brand_content_discovered", "discovered_at"),
        Index("ix_brand_content_unique", "platform", "content_id", unique=True),
    )


# ─────────────────────────────────────────────
# 14. 소셜 채널 통계 (채널 레벨 일별 스냅샷)
# ─────────────────────────────────────────────
class ChannelStats(Base):
    __tablename__ = "channel_stats"

    id = Column(Integer, primary_key=True)
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=False)
    platform = Column(String(30), nullable=False)        # "youtube", "instagram"
    channel_url = Column(String(500), nullable=False)
    subscribers = Column(Integer)                         # YouTube 구독자
    followers = Column(Integer)                           # Instagram 팔로워
    total_posts = Column(Integer)                         # 총 게시물 수
    total_views = Column(Integer)                         # 총 조회수 (YouTube)
    avg_likes = Column(Float)                             # 최근 게시물 평균 좋아요
    avg_views = Column(Float)                             # 최근 게시물 평균 조회수
    engagement_rate = Column(Float)                       # 인게이지먼트율 (%)
    collected_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    advertiser = relationship("Advertiser", backref="channel_stats")

    __table_args__ = (
        Index("ix_channel_stats_advertiser", "advertiser_id"),
        Index("ix_channel_stats_platform", "platform"),
        Index("ix_channel_stats_collected", "collected_at"),
        Index("ix_channel_stats_adv_plat", "advertiser_id", "platform", "collected_at"),
    )


# ─────────────────────────────────────────────
# 15-a. 스마트스토어 추적 상품 (사용자 등록)
# ─────────────────────────────────────────────
class SmartStoreTrackedProduct(Base):
    __tablename__ = "smartstore_tracked_products"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=True)
    product_url = Column(String(500), nullable=False)
    store_name = Column(String(200))
    product_name = Column(String(500))
    label = Column(String(200))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="tracked_products")

    __table_args__ = (
        Index("ix_tracked_user", "user_id"),
        Index("ix_tracked_product_url", "product_url"),
        Index("ix_tracked_active", "user_id", "is_active"),
    )


# ─────────────────────────────────────────────
# 15-b. 스마트스토어 메타신호 스냅샷
# ─────────────────────────────────────────────
class SmartStoreSnapshot(Base):
    __tablename__ = "smartstore_snapshots"

    id = Column(Integer, primary_key=True)
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=False)
    tracked_product_id = Column(Integer, ForeignKey("smartstore_tracked_products.id"), nullable=True)
    store_name = Column(String(200))
    product_url = Column(String(500))
    product_name = Column(String(500))
    review_count = Column(Integer)
    review_delta = Column(Integer, default=0)           # 전일 대비 리뷰 증가
    avg_rating = Column(Float)
    price = Column(Integer)
    discount_pct = Column(Float, default=0.0)
    ranking_position = Column(Integer)
    ranking_category = Column(String(200))
    wishlist_count = Column(Integer)
    qa_count = Column(Integer)
    estimated_sales_level = Column(String(10))           # "low", "mid", "high"
    # ── 매출 추정 확장 ──
    stock_quantity = Column(Integer)                     # 현재 재고 수량
    purchase_cnt = Column(Integer)                       # 누적 구매수
    purchase_cnt_delta = Column(Integer, default=0)      # 전일 대비 구매수 증가
    estimated_daily_sales = Column(Integer)              # 추정 일 판매량
    estimation_method = Column(String(30))               # "stock"/"purchase_cnt"/"review"/"composite"
    category_name = Column(String(500))                  # 네이버 카테고리명
    seller_grade = Column(String(50))                    # 파워/빅파워/프리미엄
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    advertiser = relationship("Advertiser", backref="smartstore_snapshots")
    tracked_product = relationship("SmartStoreTrackedProduct", backref="snapshots")

    __table_args__ = (
        Index("ix_ss_snap_advertiser", "advertiser_id"),
        Index("ix_ss_snap_captured", "captured_at"),
        Index("ix_ss_snap_adv_date", "advertiser_id", "captured_at"),
        Index("ix_ss_snap_tracked", "tracked_product_id"),
        Index("ix_ss_snap_product_url", "product_url"),
    )


# ─────────────────────────────────────────────
# 16. 트래픽 신호 (검색 트렌드 기반)
# ─────────────────────────────────────────────
class TrafficSignal(Base):
    __tablename__ = "traffic_signals"

    id = Column(Integer, primary_key=True)
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=False)
    date = Column(DateTime, nullable=False)
    brand_keyword = Column(String(200))
    naver_search_index = Column(Float)                   # 0-100
    google_trend_index = Column(Float)                   # 0-100
    composite_index = Column(Float)                      # 가중 합산
    wow_change_pct = Column(Float)                       # 전주 대비 %
    traffic_level = Column(String(10))                   # "low", "mid", "high"

    advertiser = relationship("Advertiser", backref="traffic_signals")

    __table_args__ = (
        Index("ix_traffic_advertiser", "advertiser_id"),
        Index("ix_traffic_date", "date"),
        Index("ix_traffic_adv_date", "advertiser_id", "date", unique=True),
    )


# ─────────────────────────────────────────────
# 17. 디지털 활동 점수
# ─────────────────────────────────────────────
class ActivityScore(Base):
    __tablename__ = "activity_scores"

    id = Column(Integer, primary_key=True)
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=False)
    date = Column(DateTime, nullable=False)
    active_campaigns = Column(Integer, default=0)
    new_creatives = Column(Integer, default=0)
    creative_variants = Column(Integer, default=0)
    social_post_count = Column(Integer, default=0)
    channel_count = Column(Integer, default=0)
    composite_score = Column(Float, default=0.0)         # 0-100
    activity_state = Column(String(20))                  # test/scale/push/peak/cooldown
    factors = Column(JSON)

    advertiser = relationship("Advertiser", backref="activity_scores")

    __table_args__ = (
        Index("ix_activity_advertiser", "advertiser_id"),
        Index("ix_activity_date", "date"),
        Index("ix_activity_adv_date", "advertiser_id", "date", unique=True),
    )


# ─────────────────────────────────────────────
# 18. 메타신호 통합 (일별 종합)
# ─────────────────────────────────────────────
class MetaSignalComposite(Base):
    __tablename__ = "meta_signal_composites"

    id = Column(Integer, primary_key=True)
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=False)
    date = Column(DateTime, nullable=False)
    smartstore_score = Column(Float, default=0.0)        # 0-100
    traffic_score = Column(Float, default=0.0)           # 0-100
    activity_score = Column(Float, default=0.0)          # 0-100
    panel_calibration = Column(Float, default=1.0)
    composite_score = Column(Float, default=0.0)         # 0-100
    spend_multiplier = Column(Float, default=1.0)        # 0.7 ~ 1.5
    raw_factors = Column(JSON)

    advertiser = relationship("Advertiser", backref="meta_signal_composites")

    __table_args__ = (
        Index("ix_metasig_advertiser", "advertiser_id"),
        Index("ix_metasig_date", "date"),
        Index("ix_metasig_adv_date", "advertiser_id", "date", unique=True),
    )


# ─────────────────────────────────────────────
# 19. 패널 관측 (하이브리드 패널)
# ─────────────────────────────────────────────
class PanelObservation(Base):
    __tablename__ = "panel_observations"

    id = Column(Integer, primary_key=True)
    panel_type = Column(String(10), nullable=False)      # "ai", "human"
    panel_id = Column(String(50), nullable=False)        # persona_code 또는 user_id
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=True)
    channel = Column(String(30))
    ad_detail_id = Column(Integer, ForeignKey("ad_details.id"), nullable=True)
    observed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    device = Column(String(20))
    location = Column(String(50))
    is_verified = Column(Boolean, default=False)
    extra_data = Column(JSON)

    advertiser = relationship("Advertiser", backref="panel_observations")

    __table_args__ = (
        Index("ix_panel_type", "panel_type"),
        Index("ix_panel_advertiser", "advertiser_id"),
        Index("ix_panel_observed", "observed_at"),
        Index("ix_panel_type_date", "panel_type", "observed_at"),
    )


# ─────────────────────────────────────────────
# 20. 광고비 벤치마크 (사례 기반 보정)
# ─────────────────────────────────────────────
class SpendBenchmark(Base):
    __tablename__ = "spend_benchmarks"

    id = Column(Integer, primary_key=True)
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=False)
    channel = Column(String(30))                             # null=전체
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    actual_monthly_spend = Column(Float, nullable=False)     # 실제 월 광고비 (원)
    estimated_monthly_spend = Column(Float)                  # 시스템 추정치 (자동 계산)
    calibration_factor = Column(Float)                       # actual / estimated
    advertiser_size = Column(String(10), default="medium")   # large / medium / small
    source = Column(String(50))                              # public_disclosure, industry_report, direct_input
    industry_id = Column(Integer, ForeignKey("industries.id"), nullable=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    advertiser = relationship("Advertiser", backref="spend_benchmarks")

    __table_args__ = (
        Index("ix_benchmark_advertiser", "advertiser_id"),
        Index("ix_benchmark_size", "advertiser_size"),
        Index("ix_benchmark_industry", "industry_id"),
    )


# ─────────────────────────────────────────────
# 21. 랜딩 URL 캐시 (도메인→브랜드 매핑)
# ─────────────────────────────────────────────
class LandingUrlCache(Base):
    __tablename__ = "landing_url_cache"

    id = Column(Integer, primary_key=True)
    domain = Column(String(500), nullable=False, unique=True)   # e.g. "samsung.com"
    brand_name = Column(String(200))                             # 해석된 브랜드명
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=True)
    business_name = Column(String(200))                          # 사업자명
    page_title = Column(String(500))                             # 랜딩 페이지 타이틀
    resolved_at = Column(DateTime, default=datetime.utcnow)
    hit_count = Column(Integer, default=1)                       # 캐시 히트 카운트

    __table_args__ = (
        Index("ix_landing_cache_domain", "domain"),
        Index("ix_landing_cache_brand", "brand_name"),
    )


# ─────────────────────────────────────────────
# 22. 결제 기록
# ─────────────────────────────────────────────
class PaymentRecord(Base):
    __tablename__ = "payment_records"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    merchant_uid = Column(String(100), unique=True, nullable=False)
    imp_uid = Column(String(100), nullable=True)
    plan = Column(String(20), nullable=False)
    plan_period = Column(String(20), nullable=False)
    amount = Column(Integer, nullable=False)
    pay_method = Column(String(30), nullable=True)
    status = Column(String(30), default="pending")  # pending/paid/activated/failed/refunded
    paid_at = Column(DateTime, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    activated_by = Column(String(100), nullable=True)
    portone_response = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="payments")

    __table_args__ = (
        Index("ix_payment_user", "user_id"),
        Index("ix_payment_status", "status"),
    )


# ─────────────────────────────────────────────
# 23. API 사용량 로그
# ─────────────────────────────────────────────
class ApiUsageLog(Base):
    __tablename__ = "api_usage_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(DateTime, nullable=False)
    endpoint_group = Column(String(50), nullable=False)
    request_count = Column(Integer, default=0)

    __table_args__ = (
        Index("ix_usage_user_date", "user_id", "date"),
    )


# ─────────────────────────────────────────────
# 24. 뉴스 멘션 (뉴스/PR 수집)
# ─────────────────────────────────────────────
class NewsMention(Base):
    __tablename__ = "news_mentions"

    id = Column(Integer, primary_key=True)
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=False)
    source = Column(String(30), nullable=False)            # "naver_news"
    article_url = Column(String(1000), nullable=False)
    article_title = Column(String(500))
    article_description = Column(Text)
    publisher = Column(String(200))
    published_at = Column(DateTime)
    search_keyword = Column(String(200))
    sentiment = Column(String(10))                         # positive / neutral / negative
    sentiment_score = Column(Float)                        # -1.0 ~ 1.0
    is_pr = Column(Boolean, default=False)
    extra_data = Column(JSON)
    collected_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    advertiser = relationship("Advertiser", backref="news_mentions")

    __table_args__ = (
        Index("ix_news_mentions_advertiser", "advertiser_id"),
        Index("ix_news_mentions_published", "published_at"),
        Index("ix_news_mentions_adv_date", "advertiser_id", "published_at"),
    )


# ─────────────────────────────────────────────
# 25. 소셜 임팩트 스코어 (일별)
# ─────────────────────────────────────────────
class SocialImpactScore(Base):
    __tablename__ = "social_impact_scores"

    id = Column(Integer, primary_key=True)
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=False)
    date = Column(DateTime, nullable=False)

    # Sub-scores (0-100)
    news_impact_score = Column(Float, default=0.0)
    social_posting_score = Column(Float, default=0.0)
    search_lift_score = Column(Float, default=0.0)
    composite_score = Column(Float, default=0.0)

    # Raw metrics
    news_article_count = Column(Integer, default=0)
    news_sentiment_avg = Column(Float)
    social_engagement_delta_pct = Column(Float)
    social_posting_delta_pct = Column(Float)
    search_volume_delta_pct = Column(Float)

    # Campaign correlation
    has_active_campaign = Column(Boolean, default=False)
    campaign_days_active = Column(Integer, default=0)
    impact_phase = Column(String(20))                      # pre / during / post / none

    factors = Column(JSON)

    advertiser = relationship("Advertiser", backref="social_impact_scores")

    __table_args__ = (
        Index("ix_social_impact_advertiser", "advertiser_id"),
        Index("ix_social_impact_date", "date"),
        Index("ix_social_impact_adv_date", "advertiser_id", "date", unique=True),
    )


# ─────────────────────────────────────────────
# 26. 광고주 즐겨찾기
# ─────────────────────────────────────────────
class AdvertiserFavorite(Base):
    __tablename__ = "advertiser_favorites"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=False)
    category = Column(String(50), default="monitoring")  # competing, monitoring, interested, other
    notes = Column(Text, nullable=True)
    is_pinned = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="favorite_advertisers")
    advertiser = relationship("Advertiser", backref="favorited_by")

    __table_args__ = (
        UniqueConstraint("user_id", "advertiser_id", name="uq_user_advertiser_favorite"),
        Index("ix_fav_user", "user_id"),
        Index("ix_fav_advertiser", "advertiser_id"),
        Index("ix_fav_user_category", "user_id", "category"),
    )


# ─────────────────────────────────────────────
# 27. 데이터 워싱 스테이징
# ─────────────────────────────────────────────
class StagingAd(Base):
    __tablename__ = "staging_ads"

    id = Column(Integer, primary_key=True)
    batch_id = Column(String(36), nullable=False)
    channel = Column(String(30), nullable=False)
    persona_code = Column(String(20))
    keyword = Column(String(200))
    device = Column(String(10))
    page_url = Column(Text)
    captured_at = Column(DateTime)

    raw_payload = Column(JSON, nullable=False)

    status = Column(String(20), default="pending")  # pending/approved/rejected/quarantine
    rejection_reason = Column(String(200))
    wash_score = Column(Float)

    resolved_advertiser_name = Column(String(200))
    resolved_advertiser_id = Column(Integer)

    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)
    promoted_at = Column(DateTime)
    promoted_ad_detail_id = Column(Integer)

    __table_args__ = (
        Index("ix_staging_batch", "batch_id"),
        Index("ix_staging_status", "status"),
        Index("ix_staging_channel", "channel"),
        Index("ix_staging_created", "created_at"),
    )


# ─────────────────────────────────────────────
# 28-A. 출시 영향력 — HTML 파싱 프로파일
# ─────────────────────────────────────────────
class ParseProfile(Base):
    __tablename__ = "parse_profiles"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    list_selector = Column(Text)
    detail_selector = Column(Text)
    title_selector = Column(Text)
    date_selector = Column(Text)
    content_selector = Column(Text)
    test_url = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    media_sources = relationship("MediaSource", back_populates="parse_profile")


# ─────────────────────────────────────────────
# 28-B. 출시 영향력 — 매체 소스 관리
# ─────────────────────────────────────────────
class MediaSource(Base):
    __tablename__ = "media_sources"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    url = Column(String(500), nullable=False)
    connector_type = Column(String(30), nullable=False)     # rss / api_youtube / html_list_detail
    weight = Column(Float, default=1.0)
    schedule_interval = Column(Integer, default=60)          # minutes
    is_active = Column(Boolean, default=True)
    last_crawl_at = Column(DateTime, nullable=True)
    error_count = Column(Integer, default=0)
    error_rate = Column(Float, default=0.0)
    parse_profile_id = Column(Integer, ForeignKey("parse_profiles.id"), nullable=True)
    extra_config = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    parse_profile = relationship("ParseProfile", back_populates="media_sources")

    __table_args__ = (
        Index("ix_media_sources_active", "is_active"),
        Index("ix_media_sources_connector", "connector_type"),
        Index("ix_media_sources_last_crawl", "last_crawl_at"),
    )


# ─────────────────────────────────────────────
# 28-C. 출시 영향력 — 반응 시계열
# ─────────────────────────────────────────────
class ReactionTimeseries(Base):
    __tablename__ = "reaction_timeseries"

    id = Column(Integer, primary_key=True)
    launch_product_id = Column(Integer, ForeignKey("launch_products.id"), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    metric_type = Column(String(30), nullable=False)         # views / likes / comments / shares
    value = Column(Float, nullable=False)
    source = Column(String(50))                              # youtube / naver_news / ...

    launch_product = relationship("LaunchProduct", backref="reaction_timeseries")

    __table_args__ = (
        Index("ix_reaction_product", "launch_product_id"),
        Index("ix_reaction_product_metric", "launch_product_id", "metric_type", "timestamp"),
        Index("ix_reaction_timestamp", "timestamp"),
    )


# ─────────────────────────────────────────────
# 28. 신상품 영향력 분석 — 상품 등록
# ─────────────────────────────────────────────
class LaunchProduct(Base):
    __tablename__ = "launch_products"

    id = Column(Integer, primary_key=True)
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=False)
    name = Column(String(500), nullable=False)
    category = Column(String(30), nullable=False)       # game / commerce / product
    launch_date = Column(DateTime, nullable=False)
    product_url = Column(String(1000))
    external_id = Column(String(200))
    keywords = Column(JSON, nullable=False)              # ["갤럭시 S26", "galaxy s26"]
    is_active = Column(Boolean, default=True)
    extra_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    advertiser = relationship("Advertiser", backref="launch_products")

    __table_args__ = (
        Index("ix_launch_products_advertiser", "advertiser_id"),
        Index("ix_launch_products_category", "category"),
        Index("ix_launch_products_launch_date", "launch_date"),
        Index("ix_launch_products_active", "is_active"),
    )


# ─────────────────────────────────────────────
# 29. 신상품 영향력 분석 — 매체 언급
# ─────────────────────────────────────────────
class LaunchMention(Base):
    __tablename__ = "launch_mentions"

    id = Column(Integer, primary_key=True)
    launch_product_id = Column(Integer, ForeignKey("launch_products.id"), nullable=False)
    source_type = Column(String(30), nullable=False)    # news/blog/community/youtube/sns/review
    source_platform = Column(String(50))                # naver_news/naver_blog/youtube/instagram
    url = Column(String(1000), nullable=False)
    title = Column(String(500))
    description = Column(Text)
    author = Column(String(200))
    published_at = Column(DateTime)
    view_count = Column(Integer)
    like_count = Column(Integer)
    comment_count = Column(Integer)
    sentiment = Column(String(10))                      # positive/neutral/negative
    sentiment_score = Column(Float)
    matched_keyword = Column(String(200))
    media_source_id = Column(Integer, ForeignKey("media_sources.id"), nullable=True)
    extra_data = Column(JSON)
    collected_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    launch_product = relationship("LaunchProduct", backref="mentions")
    media_source = relationship("MediaSource", backref="launch_mentions")

    __table_args__ = (
        Index("ix_launch_mentions_product", "launch_product_id"),
        Index("ix_launch_mentions_source_type", "source_type"),
        Index("ix_launch_mentions_published", "published_at"),
        Index("ix_launch_mentions_product_source", "launch_product_id", "source_type"),
        Index("ix_launch_mentions_media_source", "media_source_id"),
    )


# ─────────────────────────────────────────────
# 30. 신상품 영향력 분석 — 일별 점수
# ─────────────────────────────────────────────
class LaunchImpactScore(Base):
    __tablename__ = "launch_impact_scores"

    id = Column(Integer, primary_key=True)
    launch_product_id = Column(Integer, ForeignKey("launch_products.id"), nullable=False)
    date = Column(DateTime, nullable=False)

    mrs_score = Column(Float, default=0.0)              # Media Reach Score 0-100
    rv_score = Column(Float, default=0.0)               # Reaction Velocity 0-100
    cs_score = Column(Float, default=0.0)               # Conversion Signal 0-100
    lii_score = Column(Float, default=0.0)              # Launch Impact Index

    total_mentions = Column(Integer, default=0)
    mention_by_type = Column(JSON)                      # {"news":5, "blog":12, ...}
    search_index = Column(Float)
    search_delta_pct = Column(Float)
    wishlist_count = Column(Integer)
    review_count = Column(Integer)
    review_delta = Column(Integer, default=0)

    days_since_launch = Column(Integer, default=0)
    impact_phase = Column(String(20))                   # pre_launch/launch_week/growth/plateau/decline

    factors = Column(JSON)

    launch_product = relationship("LaunchProduct", backref="impact_scores")

    __table_args__ = (
        Index("ix_launch_impact_product", "launch_product_id"),
        Index("ix_launch_impact_date", "date"),
        UniqueConstraint("launch_product_id", "date", name="uq_launch_impact_product_date"),
    )


# ─────────────────────────────────────────────
# 31. 저니 이벤트 (캠페인별 시간축 통합)
# ─────────────────────────────────────────────
class JourneyEvent(Base):
    __tablename__ = "journey_events"

    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=False)
    ts = Column(DateTime, nullable=False)                   # 날짜 단위
    stage = Column(String(20), nullable=False)              # exposure / interest / consideration / conversion
    source = Column(String(30), nullable=False)             # ad_crawl / search / social / smartstore / news
    metric = Column(String(30), nullable=False)             # spend / impressions / queries / mentions / engagements / reviews / orders / revenue
    value = Column(Float, default=0.0)
    dims = Column(JSON)                                     # {"channel":"youtube", "keyword":"..."}

    campaign = relationship("Campaign", back_populates="journey_events")
    advertiser = relationship("Advertiser", backref="journey_events")

    __table_args__ = (
        Index("ix_je_campaign_ts", "campaign_id", "ts"),
        Index("ix_je_advertiser_ts", "advertiser_id", "ts"),
        Index("ix_je_campaign_stage", "campaign_id", "stage", "ts"),
    )


# ─────────────────────────────────────────────
# 32. 캠페인 리프트 (사전/사후 효과)
# ─────────────────────────────────────────────
class CampaignLift(Base):
    __tablename__ = "campaign_lifts"

    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=False)
    calculated_at = Column(DateTime, default=datetime.utcnow)

    # Query Lift
    query_lift_pct = Column(Float)
    pre_query_avg = Column(Float)
    post_query_avg = Column(Float)

    # Social Lift
    social_lift_pct = Column(Float)
    pre_social_avg = Column(Float)
    post_social_avg = Column(Float)

    # Sales Lift
    sales_lift_pct = Column(Float)
    pre_sales_avg = Column(Float)
    post_sales_avg = Column(Float)

    confidence = Column(Float)                              # 0~1 (데이터 완성도)
    factors = Column(JSON)

    campaign = relationship("Campaign", back_populates="lifts")

    __table_args__ = (
        Index("ix_lift_campaign", "campaign_id"),
        Index("ix_lift_advertiser", "advertiser_id"),
        UniqueConstraint("campaign_id", name="uq_campaign_lift"),
    )


# ─────────────────────────────────────────────
# 33. 광고상품 마스터 (매체별 광고상품 분류표) -- 정본(canonical)
#     media_ad_products의 pricing 정보를 흡수하여 통합 마스터로 운영.
#     ad_details.ad_product_master_id FK로 참조.
# ─────────────────────────────────────────────
class AdProductMaster(Base):
    __tablename__ = "ad_product_master"

    id = Column(Integer, primary_key=True)
    channel = Column(String(30), nullable=False)       # naver_search, youtube_ads, facebook 등
    product_code = Column(String(50), nullable=False)   # powerlink, trueview_instream 등
    product_name_ko = Column(String(100), nullable=False)  # 파워링크, 트루뷰 인스트림
    product_name_en = Column(String(100))               # Powerlink, TrueView In-Stream
    format_type = Column(String(30))                    # search/display/video/social/shopping/message
    billing_type = Column(String(20))                   # CPC/CPM/CPV/CPT/CPA
    description = Column(String(500))
    # ── media_ad_products에서 흡수한 pricing 컬럼 ──
    position_zone = Column(String(20))                  # "top", "middle", "bottom"
    base_price = Column(Float)                          # 기본 단가 (원)
    price_range_min = Column(Float)                     # 최저 단가
    price_range_max = Column(Float)                     # 최고 단가
    device = Column(String(10), default="all")          # "pc", "mobile", "all"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("channel", "product_code", name="uq_ad_product_channel_code"),
        Index("ix_ad_product_channel", "channel"),
    )


# ─────────────────────────────────────────────
# 33-1. 광고 플랫폼/매체 마스터 (디지털 광고 매체 인덱스)
# ─────────────────────────────────────────────
class AdPlatform(Base):
    __tablename__ = "ad_platforms"

    id = Column(Integer, primary_key=True)
    operator_name = Column(String(200), nullable=False)       # 운영사 (NHN, Google, Meta 등)
    platform_name = Column(String(200), nullable=False)       # 플랫폼명 (네이버, 구글, 메타 등)
    service_name = Column(String(200))                        # 서비스명 (네이버광고, Google Ads 등)
    platform_type = Column(String(50))                        # search/display/video/social/commerce/programmatic/reward/affiliate/ott/audio/dooh
    sub_type = Column(String(50))                             # dsp/ssp/ad_network/media_rep/offerwall 등
    url = Column(String(500))                                 # 공식 URL
    description = Column(Text)                                # 설명
    logo_url = Column(String(500))                            # 로고
    billing_types = Column(JSON)                              # ["CPC", "CPM", "CPV"]
    min_budget = Column(Float)                                # 최소 집행 예산 (원)
    is_self_serve = Column(Boolean, default=True)             # 셀프서브 가능 여부
    is_active = Column(Boolean, default=True)                 # 현재 운영 여부
    country = Column(String(10), default="KR")                # 국가 코드
    monthly_reach = Column(String(50))                        # MAU 등 도달 규모
    data_source = Column(String(100))                         # 데이터 출처 (openads, manual, web_search)
    notes = Column(Text)                                      # 비고
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("operator_name", "platform_name", "service_name", name="uq_ad_platform"),
        Index("ix_ad_platform_type", "platform_type"),
    )


# ─────────────────────────────────────────────
# 34. 광고주별 상품/서비스 포트폴리오
# ─────────────────────────────────────────────
class AdvertiserProduct(Base):
    __tablename__ = "advertiser_products"

    id = Column(Integer, primary_key=True)
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=False)
    product_name = Column(String(200), nullable=False)
    product_category_id = Column(Integer, ForeignKey("product_categories.id"), nullable=True)
    is_flagship = Column(Boolean, default=False)
    status = Column(String(20), default="active")       # active/discontinued/seasonal/unknown
    source = Column(String(20), default="ad_observed")  # ad_observed/ai_detected/manual
    first_ad_seen = Column(DateTime, nullable=True)
    last_ad_seen = Column(DateTime, nullable=True)
    total_campaigns = Column(Integer, default=0)
    total_spend_est = Column(Float, default=0.0)
    channels = Column(JSON)                              # ["youtube_ads", "facebook"]
    ad_count = Column(Integer, default=0)
    extra_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    advertiser = relationship("Advertiser", backref="products")
    product_category_rel = relationship("ProductCategory")

    __table_args__ = (
        UniqueConstraint("advertiser_id", "product_name", name="uq_advertiser_product_name"),
        Index("ix_advprod_advertiser", "advertiser_id"),
        Index("ix_advprod_category", "product_category_id"),
        Index("ix_advprod_status", "status"),
    )


# ─────────────────────────────────────────────
# 35. 제품별 일별 광고활동 (간트차트 데이터)
# ─────────────────────────────────────────────
class ProductAdActivity(Base):
    __tablename__ = "product_ad_activities"

    id = Column(Integer, primary_key=True)
    advertiser_product_id = Column(Integer, ForeignKey("advertiser_products.id"), nullable=False)
    date = Column(DateTime, nullable=False)
    channel = Column(String(30), nullable=False)
    # 크롤링 원본 텍스트. 정규화된 광고상품은 ad_product_master 테이블 참조.
    ad_product_name = Column(String(100))                # 광고상품명 (원본 텍스트)
    ad_product_master_id = Column(Integer, ForeignKey("ad_product_master.id"), nullable=True)  # 정규화된 광고상품 FK
    ad_count = Column(Integer, default=0)
    est_daily_spend = Column(Float, default=0.0)
    unique_creatives = Column(Integer, default=0)
    campaign_purposes = Column(JSON)                     # ["branding", "commerce"]

    advertiser_product = relationship("AdvertiserProduct", backref="activities")
    ad_product_master = relationship("AdProductMaster", backref="product_activities")

    __table_args__ = (
        UniqueConstraint("advertiser_product_id", "date", "channel", name="uq_product_activity_day_channel"),
        Index("ix_prodact_product", "advertiser_product_id"),
        Index("ix_prodact_date", "date"),
    )


# ─────────────────────────────────────────────
# 36. 모바일 패널 디바이스 (AI 가상 + 실제 혼용)
# ─────────────────────────────────────────────
class MobilePanelDevice(Base):
    __tablename__ = "mobile_panel_devices"

    id = Column(Integer, primary_key=True)
    device_id = Column(String(64), unique=True, nullable=False)   # SHA-256 핑거프린트
    device_type = Column(String(10), default="ai")                # "ai" | "real"
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=True)
    os_type = Column(String(20), nullable=False)                  # android | ios
    os_version = Column(String(20))
    device_model = Column(String(100))
    carrier = Column(String(50))                                  # SKT | KT | LGU+ | WiFi
    screen_res = Column(String(20))                               # "1080x2400"
    app_list = Column(JSON)                                       # 설치 앱 목록 (광고 타겟팅 시뮬레이션용)
    age_group = Column(String(10))                                # "20", "30" 등
    gender = Column(String(5))                                    # "M", "F"
    region = Column(String(50), default="서울")
    is_active = Column(Boolean, default=True)
    last_seen = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    persona = relationship("Persona", backref="mobile_devices")

    __table_args__ = (
        Index("ix_mpd_device_id", "device_id"),
        Index("ix_mpd_type", "device_type"),
        Index("ix_mpd_active", "is_active"),
    )


# ─────────────────────────────────────────────
# 37. 모바일 패널 광고 노출 이벤트
# ─────────────────────────────────────────────
class MobilePanelExposure(Base):
    __tablename__ = "mobile_panel_exposures"

    id = Column(Integer, primary_key=True)
    device_id = Column(String(64), ForeignKey("mobile_panel_devices.device_id"), nullable=False)
    app_name = Column(String(100))                                # 노출 앱 (YouTube, Instagram 등)
    channel = Column(String(30))                                  # 매핑된 채널명
    advertiser_id = Column(Integer, ForeignKey("advertisers.id"), nullable=True)
    advertiser_name_raw = Column(String(200))
    ad_text = Column(String(500))
    ad_type = Column(String(30))                                  # video_preroll, banner, native, story 등
    creative_url = Column(String(1000))                           # 소재 이미지/영상 URL
    click_url = Column(String(1000))                              # 랜딩 URL
    duration_ms = Column(Integer)                                 # 노출 시간 (ms)
    was_clicked = Column(Boolean, default=False)
    was_skipped = Column(Boolean, default=False)
    screen_position = Column(String(30))                          # top, mid, bottom, fullscreen
    observed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    extra_data = Column(JSON)

    device = relationship("MobilePanelDevice", backref="exposures")
    advertiser = relationship("Advertiser", backref="mobile_exposures")

    __table_args__ = (
        Index("ix_mpe_device", "device_id"),
        Index("ix_mpe_observed", "observed_at"),
        Index("ix_mpe_advertiser", "advertiser_id"),
        Index("ix_mpe_channel", "channel"),
        Index("ix_mpe_device_date", "device_id", "observed_at"),
    )


# ─────────────────────────────────────────────
# 미분류 광고 마크 (신규 매체 발굴용)
# ─────────────────────────────────────────────
class UnknownAdMark(Base):
    __tablename__ = "unknown_ad_marks"

    id = Column(Integer, primary_key=True)
    ad_detail_id = Column(Integer, ForeignKey("ad_details.id", ondelete="CASCADE"), nullable=False)
    mark_description = Column(Text, nullable=False)       # AI 설명 ("파란 삼각형 안에 ! 표시")
    mark_location = Column(String(50))                    # "top_right", "top_left", "bottom_right" 등
    suggested_network = Column(String(100))               # AI 추정 네트워크
    status = Column(String(20), default="new")            # new / reviewed / confirmed / dismissed
    created_at = Column(DateTime, default=datetime.utcnow)

    ad_detail = relationship("AdDetail", backref="unknown_marks")

    __table_args__ = (
        Index("ix_unknown_marks_status", "status"),
        Index("ix_unknown_marks_network", "suggested_network"),
    )
