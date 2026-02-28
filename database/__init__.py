"""Database session/engine bootstrap for AdScope."""

import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database.models import (
    Base, PasswordResetToken, AdvertiserFavorite, StagingAd,
    LaunchProduct, LaunchMention, LaunchImpactScore,
    ParseProfile, MediaSource, ReactionTimeseries,
    JourneyEvent, CampaignLift,
    AdProductMaster, AdvertiserProduct, ProductAdActivity,
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///adscope.db",
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"timeout": 30},
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """Provide DB session dependency for FastAPI."""
    async with async_session() as session:
        yield session


async def init_db():
    """Create base tables and apply lightweight compatibility migrations."""
    async with engine.begin() as conn:
        # SQLite performance pragmas
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.exec_driver_sql("PRAGMA synchronous=NORMAL")
        await conn.exec_driver_sql("PRAGMA cache_size=10000")

        await conn.run_sync(Base.metadata.create_all)
        await _ensure_ad_detail_verification_columns(conn)
        await _ensure_ad_detail_verification_indexes(conn)
        await _ensure_ad_detail_6w_columns(conn)
        await _ensure_phase3_columns(conn)
        await _ensure_phase3b_persona_columns(conn)
        await _ensure_advertiser_profile_columns(conn)
        await _ensure_persona_ranking_indexes(conn)
        await _backfill_ad_detail_verification_columns(conn)
        await _backfill_missing_verification_defaults(conn)
        await _ensure_is_contact_column(conn)
        await _ensure_product_category_columns(conn)
        await _ensure_channel_stats_table(conn)
        await _ensure_meta_signal_tables(conn)
        await _ensure_payment_tables(conn)
        await _ensure_persona_and_hash_columns(conn)
        await _ensure_smartstore_sales_columns(conn)
        await _ensure_social_impact_tables(conn)
        await _ensure_password_reset_tokens_table(conn)
        await _ensure_advertiser_favorites_table(conn)
        await _ensure_staging_ads_table(conn)
        await _ensure_launch_impact_tables(conn)
        await _ensure_campaign_journey_tables(conn)
        await _ensure_marketing_plan_columns(conn)
        await _ensure_ad_product_consolidation(conn)
        await _ensure_mobile_panel_tables(conn)
        await _ensure_dart_columns(conn)
        await _ensure_dedup_tracking_columns(conn)
        await _ensure_ad_platforms_table(conn)
        await _ensure_composite_indexes(conn)
        await _ensure_visual_mark_columns(conn)
        await _ensure_oauth_columns(conn)


async def _ensure_oauth_columns(conn):
    """Add OAuth columns to users table."""
    cols = {
        "oauth_provider": "VARCHAR(20)",
        "oauth_id": "VARCHAR(200)",
        "payment_confirmed": "BOOLEAN DEFAULT 0",
    }
    for col, typ in cols.items():
        try:
            await conn.exec_driver_sql(f"ALTER TABLE users ADD COLUMN {col} {typ}")
        except Exception:
            pass


async def _ensure_visual_mark_columns(conn):
    """Add visual mark detection columns to ad_details + unknown_ad_marks table."""
    rows = await conn.exec_driver_sql("PRAGMA table_info(ad_details)")
    existing = {row[1] for row in rows.fetchall()}

    for col, typ in [
        ("visual_mark_detected", "VARCHAR(200)"),
        ("visual_mark_network", "VARCHAR(50)"),
        ("visual_mark_confidence", "FLOAT"),
        ("visual_mark_analyzed", "BOOLEAN DEFAULT 0"),
        ("visual_mark_result", "JSON"),
    ]:
        if col not in existing:
            try:
                await conn.exec_driver_sql(
                    f"ALTER TABLE ad_details ADD COLUMN {col} {typ}"
                )
            except Exception:
                pass

    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_details_visual_mark_analyzed "
        "ON ad_details(visual_mark_analyzed)"
    )

    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS unknown_ad_marks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad_detail_id INTEGER NOT NULL REFERENCES ad_details(id) ON DELETE CASCADE,
            mark_description TEXT NOT NULL,
            mark_location VARCHAR(50),
            suggested_network VARCHAR(100),
            status VARCHAR(20) DEFAULT 'new',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_unknown_marks_status ON unknown_ad_marks(status)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_unknown_marks_network ON unknown_ad_marks(suggested_network)"
    )


async def _ensure_composite_indexes(conn):
    """Add composite indexes for common JOIN/WHERE patterns (M4 performance)."""
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS ix_details_advertiser_snapshot ON ad_details(advertiser_id, snapshot_id)",
        "CREATE INDEX IF NOT EXISTS ix_spend_campaign_channel_date ON spend_estimates(campaign_id, channel, date)",
        "CREATE INDEX IF NOT EXISTS ix_channel_stats_adv_collected ON channel_stats(advertiser_id, collected_at)",
    ]:
        try:
            await conn.exec_driver_sql(idx_sql)
        except Exception:
            pass


async def _ensure_ad_platforms_table(conn):
    """Create ad_platforms table if not exists."""
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ad_platforms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_name VARCHAR(200) NOT NULL,
            platform_name VARCHAR(200) NOT NULL,
            service_name VARCHAR(200),
            platform_type VARCHAR(50),
            sub_type VARCHAR(50),
            url VARCHAR(500),
            description TEXT,
            logo_url VARCHAR(500),
            billing_types JSON,
            min_budget FLOAT,
            is_self_serve BOOLEAN DEFAULT 1,
            is_active BOOLEAN DEFAULT 1,
            country VARCHAR(10) DEFAULT 'KR',
            monthly_reach VARCHAR(50),
            data_source VARCHAR(100),
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(operator_name, platform_name, service_name)
        )
    """))
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_ad_platform_type ON ad_platforms(platform_type)
    """))


async def _ensure_dedup_tracking_columns(conn):
    """Add dedup tracking columns (first_seen_at, last_seen_at, seen_count) to ad_details."""
    rows = await conn.exec_driver_sql("PRAGMA table_info(ad_details)")
    existing = {row[1] for row in rows.fetchall()}

    for col, typ in [
        ("first_seen_at", "DATETIME"),
        ("last_seen_at", "DATETIME"),
        ("seen_count", "INTEGER DEFAULT 1"),
    ]:
        if col not in existing:
            try:
                await conn.exec_driver_sql(
                    f"ALTER TABLE ad_details ADD COLUMN {col} {typ}"
                )
            except Exception:
                pass

    # Index for dedup lookups
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_details_dedup "
        "ON ad_details(creative_hash, snapshot_id)"
    )


async def _ensure_dart_columns(conn):
    """Add DART ad expense columns to advertisers table."""
    rows = await conn.exec_driver_sql("PRAGMA table_info(advertisers)")
    existing = {row[1] for row in rows.fetchall()}

    for col, typ in [
        ("dart_ad_expense", "REAL"),
        ("dart_fiscal_year", "TEXT"),
    ]:
        if col not in existing:
            try:
                await conn.exec_driver_sql(
                    f"ALTER TABLE advertisers ADD COLUMN {col} {typ}"
                )
            except Exception:
                pass


async def _ensure_campaign_journey_tables(conn):
    """Campaign 체계화 컬럼 + journey_events/campaign_lifts 테이블."""
    # Campaign 테이블에 새 컬럼 추가
    rows = await conn.exec_driver_sql("PRAGMA table_info(campaigns)")
    existing = {row[1] for row in rows.fetchall()}

    new_cols = {
        "campaign_name": "VARCHAR(300)",
        "objective": "VARCHAR(30)",
        "product_service": "VARCHAR(200)",
        "promotion_copy": "TEXT",
        "model_info": "VARCHAR(200)",
        "target_keywords": "JSON",
        "start_at": "DATETIME",
        "end_at": "DATETIME",
        "creative_ids": "JSON",
        "status": "VARCHAR(20) DEFAULT 'active'",
        "enrichment_status": "VARCHAR(20) DEFAULT 'pending'",
        "enriched_at": "DATETIME",
    }

    for col, col_type in new_cols.items():
        if col not in existing:
            await conn.exec_driver_sql(
                f"ALTER TABLE campaigns ADD COLUMN {col} {col_type}"
            )

    # journey_events, campaign_lifts는 create_all로 이미 생성됨
    # 인덱스만 보장
    for stmt in [
        "CREATE INDEX IF NOT EXISTS ix_je_campaign_ts ON journey_events(campaign_id, ts)",
        "CREATE INDEX IF NOT EXISTS ix_je_advertiser_ts ON journey_events(advertiser_id, ts)",
        "CREATE INDEX IF NOT EXISTS ix_je_campaign_stage ON journey_events(campaign_id, stage, ts)",
        "CREATE INDEX IF NOT EXISTS ix_lift_campaign ON campaign_lifts(campaign_id)",
        "CREATE INDEX IF NOT EXISTS ix_lift_advertiser ON campaign_lifts(advertiser_id)",
    ]:
        await conn.exec_driver_sql(stmt)


async def _ensure_ad_detail_verification_columns(conn):
    """Add verification columns to ad_details when missing."""
    dialect = conn.dialect.name

    if dialect == "sqlite":
        rows = await conn.exec_driver_sql("PRAGMA table_info(ad_details)")
        columns = {row[1] for row in rows.fetchall()}
    else:
        result = await conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'ad_details'
                """
            )
        )
        columns = {row[0] for row in result.fetchall()}

    if "verification_status" not in columns:
        await conn.exec_driver_sql("ALTER TABLE ad_details ADD COLUMN verification_status VARCHAR(30)")
    if "verification_source" not in columns:
        await conn.exec_driver_sql("ALTER TABLE ad_details ADD COLUMN verification_source VARCHAR(100)")


async def _ensure_ad_detail_verification_indexes(conn):
    """Create verification indexes if they do not exist."""
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_details_verification_status ON ad_details (verification_status)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_details_verification_source ON ad_details (verification_source)"
    )


async def _ensure_ad_detail_6w_columns(conn):
    """Add 6W framework columns to ad_details when missing."""
    dialect = conn.dialect.name

    if dialect == "sqlite":
        rows = await conn.exec_driver_sql("PRAGMA table_info(ad_details)")
        columns = {row[1] for row in rows.fetchall()}
    else:
        result = await conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'ad_details'
                """
            )
        )
        columns = {row[0] for row in result.fetchall()}

    new_cols = {
        "product_name": "VARCHAR(200)",
        "product_category": "VARCHAR(100)",
        "ad_placement": "VARCHAR(100)",
        "promotion_type": "VARCHAR(50)",
        "creative_image_path": "TEXT",
    }
    for col_name, col_type in new_cols.items():
        if col_name not in columns:
            await conn.exec_driver_sql(
                f"ALTER TABLE ad_details ADD COLUMN {col_name} {col_type}"
            )


async def _ensure_phase3_columns(conn):
    """Add Phase 3 classification columns to ad_details and advertisers."""
    dialect = conn.dialect.name

    # --- ad_details 새 컬럼 ---
    if dialect == "sqlite":
        rows = await conn.exec_driver_sql("PRAGMA table_info(ad_details)")
        ad_columns = {row[1] for row in rows.fetchall()}
    else:
        result = await conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'ad_details'
                """
            )
        )
        ad_columns = {row[0] for row in result.fetchall()}

    ad_new_cols = {
        "position_zone": "VARCHAR(20)",
        "is_inhouse": "BOOLEAN DEFAULT FALSE",
        "is_retargeted": "BOOLEAN DEFAULT FALSE",
        "retargeting_network": "VARCHAR(50)",
        "ad_marker_type": "VARCHAR(50)",
    }
    for col_name, col_type in ad_new_cols.items():
        if col_name not in ad_columns:
            await conn.exec_driver_sql(
                f"ALTER TABLE ad_details ADD COLUMN {col_name} {col_type}"
            )

    # --- advertisers 새 컬럼 ---
    if dialect == "sqlite":
        rows = await conn.exec_driver_sql("PRAGMA table_info(advertisers)")
        adv_columns = {row[1] for row in rows.fetchall()}
    else:
        result = await conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'advertisers'
                """
            )
        )
        adv_columns = {row[0] for row in result.fetchall()}

    adv_new_cols = {
        "parent_id": "INTEGER REFERENCES advertisers(id)",
        "advertiser_type": "VARCHAR(20)",
    }
    for col_name, col_type in adv_new_cols.items():
        if col_name not in adv_columns:
            await conn.exec_driver_sql(
                f"ALTER TABLE advertisers ADD COLUMN {col_name} {col_type}"
            )

    # --- 인덱스 ---
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_details_position_zone ON ad_details (position_zone)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_details_is_inhouse ON ad_details (is_inhouse)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_advertisers_parent ON advertisers (parent_id)"
    )


async def _backfill_ad_detail_verification_columns(conn):
    """Backfill verification columns from legacy extra_data JSON payload."""
    dialect = conn.dialect.name
    if dialect == "sqlite":
        await conn.exec_driver_sql(
            """
            UPDATE ad_details
            SET verification_status = COALESCE(
                verification_status,
                json_extract(extra_data, '$.verification_status')
            )
            WHERE verification_status IS NULL
            """
        )
        await conn.exec_driver_sql(
            """
            UPDATE ad_details
            SET verification_source = COALESCE(
                verification_source,
                json_extract(extra_data, '$.verification_source')
            )
            WHERE verification_source IS NULL
            """
        )
    else:
        await conn.exec_driver_sql(
            """
            UPDATE ad_details
            SET verification_status = COALESCE(
                verification_status,
                extra_data->>'verification_status'
            )
            WHERE verification_status IS NULL
            """
        )
        await conn.exec_driver_sql(
            """
            UPDATE ad_details
            SET verification_source = COALESCE(
                verification_source,
                extra_data->>'verification_source'
            )
            WHERE verification_source IS NULL
            """
        )


async def _backfill_missing_verification_defaults(conn):
    """Fill missing verification fields with channel-aware defaults."""
    await conn.exec_driver_sql(
        """
        UPDATE ad_details
        SET verification_status = 'unverified'
        WHERE (verification_status IS NULL OR TRIM(verification_status) = '')
          AND snapshot_id IN (
              SELECT id
              FROM ad_snapshots
              WHERE channel IN ('naver_search', 'kakao_da')
          )
        """
    )
    await conn.exec_driver_sql(
        """
        UPDATE ad_details
        SET verification_source = 'channel_default'
        WHERE (verification_source IS NULL OR TRIM(verification_source) = '')
          AND snapshot_id IN (
              SELECT id
              FROM ad_snapshots
              WHERE channel IN ('naver_search', 'kakao_da')
          )
        """
    )
    await conn.exec_driver_sql(
        """
        UPDATE ad_details
        SET verification_status = 'unknown'
        WHERE verification_status IS NULL OR TRIM(verification_status) = ''
        """
    )
    await conn.exec_driver_sql(
        """
        UPDATE ad_details
        SET verification_source = 'not_collected'
        WHERE verification_source IS NULL OR TRIM(verification_source) = ''
        """
    )


async def _ensure_phase3b_persona_columns(conn):
    """Add Phase 3B columns to personas table when missing."""
    dialect = conn.dialect.name

    if dialect == "sqlite":
        rows = await conn.exec_driver_sql("PRAGMA table_info(personas)")
        columns = {row[1] for row in rows.fetchall()}
    else:
        result = await conn.execute(
            text(
                """
                SELECT column_name, character_maximum_length
                FROM information_schema.columns
                WHERE table_name = 'personas'
                """
            )
        )
        col_info = {row[0]: row[1] for row in result.fetchall()}
        columns = set(col_info.keys())

        # code 컬럼 크기 확장 (VARCHAR(10) → VARCHAR(20), CTRL_RETARGET 수용)
        if "code" in col_info and col_info["code"] is not None and col_info["code"] < 20:
            await conn.exec_driver_sql(
                "ALTER TABLE personas ALTER COLUMN code TYPE VARCHAR(20)"
            )

    new_cols = {
        "targeting_category": "VARCHAR(20)",
        "is_clean": "BOOLEAN DEFAULT FALSE",
        "primary_device": "VARCHAR(20)",
    }
    for col_name, col_type in new_cols.items():
        if col_name not in columns:
            await conn.exec_driver_sql(
                f"ALTER TABLE personas ADD COLUMN {col_name} {col_type}"
            )


async def _ensure_advertiser_profile_columns(conn):
    """Add advertiser background data + brand channel columns."""
    dialect = conn.dialect.name

    if dialect == "sqlite":
        rows = await conn.exec_driver_sql("PRAGMA table_info(advertisers)")
        columns = {row[1] for row in rows.fetchall()}
    else:
        result = await conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'advertisers'
                """
            )
        )
        columns = {row[0] for row in result.fetchall()}

    new_cols = {
        "annual_revenue": "FLOAT",
        "employee_count": "INTEGER",
        "founded_year": "INTEGER",
        "description": "TEXT",
        "logo_url": "VARCHAR(500)",
        "headquarters": "VARCHAR(200)",
        "is_public": "BOOLEAN DEFAULT FALSE",
        "market_cap": "FLOAT",
        "business_category": "VARCHAR(50)",
        "official_channels": "JSON",
        "data_source": "VARCHAR(100)",
        "profile_updated_at": "DATETIME",
    }
    for col_name, col_type in new_cols.items():
        if col_name not in columns:
            await conn.exec_driver_sql(
                f"ALTER TABLE advertisers ADD COLUMN {col_name} {col_type}"
            )


async def _ensure_is_contact_column(conn):
    """Add is_contact column to ad_details and backfill from channel info."""
    dialect = conn.dialect.name

    if dialect == "sqlite":
        rows = await conn.exec_driver_sql("PRAGMA table_info(ad_details)")
        columns = {row[1] for row in rows.fetchall()}
    else:
        result = await conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'ad_details'
                """
            )
        )
        columns = {row[0] for row in result.fetchall()}

    if "is_contact" not in columns:
        await conn.exec_driver_sql(
            "ALTER TABLE ad_details ADD COLUMN is_contact BOOLEAN DEFAULT TRUE"
        )
        # backfill: catalog channels -> is_contact=FALSE
        await conn.exec_driver_sql(
            """
            UPDATE ad_details SET is_contact = 0
            WHERE snapshot_id IN (
                SELECT id FROM ad_snapshots
                WHERE channel IN ('youtube_ads', 'facebook')
            )
            """
        )
        await conn.exec_driver_sql(
            """
            UPDATE ad_details SET is_contact = 0
            WHERE ad_type = 'social_library'
              AND snapshot_id IN (
                  SELECT id FROM ad_snapshots WHERE channel = 'instagram'
              )
            """
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_details_is_contact ON ad_details (is_contact)"
        )


async def _ensure_persona_ranking_indexes(conn):
    """Add composite index for persona ranking queries."""
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_snapshots_persona_channel_time "
        "ON ad_snapshots (persona_id, channel, captured_at)"
    )


async def _ensure_product_category_columns(conn):
    """Add product_category_id column to ad_details if missing."""
    dialect = conn.dialect.name

    if dialect == "sqlite":
        rows = await conn.exec_driver_sql("PRAGMA table_info(ad_details)")
        columns = {row[1] for row in rows.fetchall()}
    else:
        result = await conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'ad_details'
                """
            )
        )
        columns = {row[0] for row in result.fetchall()}

    if "product_category_id" not in columns:
        await conn.exec_driver_sql(
            "ALTER TABLE ad_details ADD COLUMN product_category_id INTEGER REFERENCES product_categories(id)"
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_details_product_category ON ad_details (product_category_id)"
        )


async def _ensure_channel_stats_table(conn):
    """Create channel_stats table if it does not exist (handled by create_all,
    but add indexes explicitly for safety)."""
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_channel_stats_advertiser ON channel_stats (advertiser_id)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_channel_stats_collected ON channel_stats (collected_at)"
    )


async def _ensure_meta_signal_tables(conn):
    """Create meta-signal tables (15~19) if they don't exist.
    create_all handles new tables, but add explicit indexes for safety."""
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS ix_ss_snap_adv_date ON smartstore_snapshots (advertiser_id, captured_at)",
        "CREATE INDEX IF NOT EXISTS ix_traffic_adv_date ON traffic_signals (advertiser_id, date)",
        "CREATE INDEX IF NOT EXISTS ix_activity_adv_date ON activity_scores (advertiser_id, date)",
        "CREATE INDEX IF NOT EXISTS ix_metasig_adv_date ON meta_signal_composites (advertiser_id, date)",
        "CREATE INDEX IF NOT EXISTS ix_panel_type_date ON panel_observations (panel_type, observed_at)",
    ]:
        try:
            await conn.exec_driver_sql(idx_sql)
        except Exception:
            pass


async def _ensure_persona_and_hash_columns(conn):
    """Add persona_id and creative_hash columns to ad_details + landing_url_cache table.

    NOTE: ad_details.persona_id는 ad_snapshots.persona_id의 비정규화 복사본.
    쿼리 최적화용으로 유지하되, 새 쿼리에서는 AdSnapshot.persona_id JOIN을 권장.
    """
    dialect = conn.dialect.name

    if dialect == "sqlite":
        rows = await conn.exec_driver_sql("PRAGMA table_info(ad_details)")
        columns = {row[1] for row in rows.fetchall()}
    else:
        result = await conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'ad_details'
                """
            )
        )
        columns = {row[0] for row in result.fetchall()}

    if "persona_id" not in columns:
        await conn.exec_driver_sql(
            "ALTER TABLE ad_details ADD COLUMN persona_id INTEGER REFERENCES personas(id)"
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_details_persona ON ad_details (persona_id)"
        )
        # Backfill persona_id from snapshot's persona_id
        await conn.exec_driver_sql(
            """
            UPDATE ad_details
            SET persona_id = (
                SELECT persona_id FROM ad_snapshots
                WHERE ad_snapshots.id = ad_details.snapshot_id
            )
            WHERE persona_id IS NULL
            """
        )

    if "creative_hash" not in columns:
        await conn.exec_driver_sql(
            "ALTER TABLE ad_details ADD COLUMN creative_hash VARCHAR(64)"
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_details_creative_hash ON ad_details (creative_hash)"
        )


async def _ensure_payment_tables(conn):
    """Add payment/billing tables and user trial column."""
    dialect = conn.dialect.name

    # Add trial_started_at to users
    if dialect == "sqlite":
        rows = await conn.exec_driver_sql("PRAGMA table_info(users)")
        columns = {row[1] for row in rows.fetchall()}
    else:
        result = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"
            )
        )
        columns = {row[0] for row in result.fetchall()}

    if "trial_started_at" not in columns:
        await conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN trial_started_at DATETIME"
        )

    # Indexes for new tables (create_all handles table creation)
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS ix_payment_user ON payment_records (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_payment_status ON payment_records (status)",
        "CREATE INDEX IF NOT EXISTS ix_usage_user_date ON api_usage_logs (user_id, date)",
    ]:
        try:
            await conn.exec_driver_sql(idx_sql)
        except Exception:
            pass


async def _ensure_smartstore_sales_columns(conn):
    """Add sales estimation columns to smartstore_snapshots + tracked products table."""
    rows = await conn.exec_driver_sql("PRAGMA table_info(smartstore_snapshots)")
    columns = {row[1] for row in rows.fetchall()}

    new_cols = {
        "tracked_product_id": "INTEGER REFERENCES smartstore_tracked_products(id)",
        "product_name": "VARCHAR(500)",
        "stock_quantity": "INTEGER",
        "purchase_cnt": "INTEGER",
        "purchase_cnt_delta": "INTEGER DEFAULT 0",
        "estimated_daily_sales": "INTEGER",
        "estimation_method": "VARCHAR(30)",
        "category_name": "VARCHAR(500)",
        "seller_grade": "VARCHAR(50)",
    }
    for col_name, col_type in new_cols.items():
        if col_name not in columns:
            await conn.exec_driver_sql(
                f"ALTER TABLE smartstore_snapshots ADD COLUMN {col_name} {col_type}"
            )

    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS ix_ss_snap_tracked ON smartstore_snapshots (tracked_product_id)",
        "CREATE INDEX IF NOT EXISTS ix_ss_snap_product_url ON smartstore_snapshots (product_url)",
        "CREATE INDEX IF NOT EXISTS ix_tracked_user ON smartstore_tracked_products (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_tracked_product_url ON smartstore_tracked_products (product_url)",
        "CREATE INDEX IF NOT EXISTS ix_tracked_active ON smartstore_tracked_products (user_id, is_active)",
    ]:
        try:
            await conn.exec_driver_sql(idx_sql)
        except Exception:
            pass


async def _ensure_social_impact_tables(conn):
    """Create indexes for social impact tables (tables created by create_all)."""
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS ix_news_mentions_advertiser ON news_mentions (advertiser_id)",
        "CREATE INDEX IF NOT EXISTS ix_news_mentions_published ON news_mentions (published_at)",
        "CREATE INDEX IF NOT EXISTS ix_news_mentions_adv_date ON news_mentions (advertiser_id, published_at)",
        "CREATE INDEX IF NOT EXISTS ix_social_impact_advertiser ON social_impact_scores (advertiser_id)",
        "CREATE INDEX IF NOT EXISTS ix_social_impact_date ON social_impact_scores (date)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_social_impact_adv_date ON social_impact_scores (advertiser_id, date)",
    ]:
        try:
            await conn.exec_driver_sql(idx_sql)
        except Exception:
            pass


async def _ensure_password_reset_tokens_table(conn):
    """Create password_reset_tokens table if it does not exist."""
    # Table is created by create_all via PasswordResetToken model.
    # Add explicit indexes for safety.
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS ix_password_reset_token ON password_reset_tokens (token)",
        "CREATE INDEX IF NOT EXISTS ix_password_reset_user ON password_reset_tokens (user_id)",
    ]:
        try:
            await conn.exec_driver_sql(idx_sql)
        except Exception:
            pass


async def _ensure_advertiser_favorites_table(conn):
    """Create advertiser_favorites table if it does not exist."""
    # Table is created by create_all via AdvertiserFavorite model.
    # Add explicit indexes and unique constraint for safety.
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS ix_fav_user ON advertiser_favorites (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_fav_advertiser ON advertiser_favorites (advertiser_id)",
        "CREATE INDEX IF NOT EXISTS ix_fav_user_category ON advertiser_favorites (user_id, category)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_advertiser_favorite ON advertiser_favorites (user_id, advertiser_id)",
    ]:
        try:
            await conn.exec_driver_sql(idx_sql)
        except Exception:
            pass


async def _ensure_staging_ads_table(conn):
    """Create staging_ads table indexes (table created by create_all)."""
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS ix_staging_batch ON staging_ads (batch_id)",
        "CREATE INDEX IF NOT EXISTS ix_staging_status ON staging_ads (status)",
        "CREATE INDEX IF NOT EXISTS ix_staging_channel ON staging_ads (channel)",
        "CREATE INDEX IF NOT EXISTS ix_staging_created ON staging_ads (created_at)",
    ]:
        try:
            await conn.exec_driver_sql(idx_sql)
        except Exception:
            pass


async def _ensure_launch_impact_tables(conn):
    """Create indexes for launch impact tables (tables created by create_all)."""
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS ix_launch_products_advertiser ON launch_products (advertiser_id)",
        "CREATE INDEX IF NOT EXISTS ix_launch_products_category ON launch_products (category)",
        "CREATE INDEX IF NOT EXISTS ix_launch_products_launch_date ON launch_products (launch_date)",
        "CREATE INDEX IF NOT EXISTS ix_launch_products_active ON launch_products (is_active)",
        "CREATE INDEX IF NOT EXISTS ix_launch_mentions_product ON launch_mentions (launch_product_id)",
        "CREATE INDEX IF NOT EXISTS ix_launch_mentions_source_type ON launch_mentions (source_type)",
        "CREATE INDEX IF NOT EXISTS ix_launch_mentions_published ON launch_mentions (published_at)",
        "CREATE INDEX IF NOT EXISTS ix_launch_mentions_product_source ON launch_mentions (launch_product_id, source_type)",
        "CREATE INDEX IF NOT EXISTS ix_launch_mentions_media_source ON launch_mentions (media_source_id)",
        "CREATE INDEX IF NOT EXISTS ix_launch_impact_product ON launch_impact_scores (launch_product_id)",
        "CREATE INDEX IF NOT EXISTS ix_launch_impact_date ON launch_impact_scores (date)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_launch_impact_product_date ON launch_impact_scores (launch_product_id, date)",
        # MediaSource / ParseProfile / ReactionTimeseries
        "CREATE INDEX IF NOT EXISTS ix_media_sources_active ON media_sources (is_active)",
        "CREATE INDEX IF NOT EXISTS ix_media_sources_connector ON media_sources (connector_type)",
        "CREATE INDEX IF NOT EXISTS ix_media_sources_last_crawl ON media_sources (last_crawl_at)",
        "CREATE INDEX IF NOT EXISTS ix_reaction_product ON reaction_timeseries (launch_product_id)",
        "CREATE INDEX IF NOT EXISTS ix_reaction_product_metric ON reaction_timeseries (launch_product_id, metric_type, timestamp)",
        "CREATE INDEX IF NOT EXISTS ix_reaction_timestamp ON reaction_timeseries (timestamp)",
    ]:
        try:
            await conn.exec_driver_sql(idx_sql)
        except Exception:
            pass

    # Add media_source_id to launch_mentions if missing
    rows = await conn.exec_driver_sql("PRAGMA table_info(launch_mentions)")
    columns = {row[1] for row in rows.fetchall()}
    if "media_source_id" not in columns:
        try:
            await conn.exec_driver_sql(
                "ALTER TABLE launch_mentions ADD COLUMN media_source_id INTEGER REFERENCES media_sources(id)"
            )
        except Exception:
            pass


async def _ensure_marketing_plan_columns(conn):
    """Add marketing plan hierarchy columns to ad_details + ensure new tables."""
    # ad_details: 5 new columns
    rows = await conn.exec_driver_sql("PRAGMA table_info(ad_details)")
    existing = {row[1] for row in rows.fetchall()}

    new_cols = {
        "campaign_purpose": "VARCHAR(30)",
        "ad_format_type": "VARCHAR(30)",
        "ad_product_name": "VARCHAR(100)",
        "model_name": "VARCHAR(200)",
        "estimated_budget": "REAL",
    }
    for col, col_type in new_cols.items():
        if col not in existing:
            try:
                await conn.exec_driver_sql(
                    f"ALTER TABLE ad_details ADD COLUMN {col} {col_type}"
                )
            except Exception:
                pass

    # Indexes for new columns
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS ix_details_campaign_purpose ON ad_details(campaign_purpose)",
        "CREATE INDEX IF NOT EXISTS ix_details_ad_format_type ON ad_details(ad_format_type)",
        "CREATE INDEX IF NOT EXISTS ix_details_ad_product_name ON ad_details(ad_product_name)",
        # ad_product_master indexes
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_ad_product_channel_code ON ad_product_master(channel, product_code)",
        "CREATE INDEX IF NOT EXISTS ix_ad_product_channel ON ad_product_master(channel)",
        # advertiser_products indexes
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_advertiser_product_name ON advertiser_products(advertiser_id, product_name)",
        "CREATE INDEX IF NOT EXISTS ix_advprod_advertiser ON advertiser_products(advertiser_id)",
        "CREATE INDEX IF NOT EXISTS ix_advprod_category ON advertiser_products(product_category_id)",
        "CREATE INDEX IF NOT EXISTS ix_advprod_status ON advertiser_products(status)",
        # product_ad_activities indexes
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_product_activity_day_channel ON product_ad_activities(advertiser_product_id, date, channel)",
        "CREATE INDEX IF NOT EXISTS ix_prodact_product ON product_ad_activities(advertiser_product_id)",
        "CREATE INDEX IF NOT EXISTS ix_prodact_date ON product_ad_activities(date)",
    ]:
        try:
            await conn.exec_driver_sql(idx_sql)
        except Exception:
            pass



async def _ensure_ad_product_consolidation(conn):
    """Consolidate ad product tables: migrate pricing from media_ad_products to ad_product_master.

    - Adds pricing columns (position_zone, base_price, price_range_min/max, device, is_active,
      updated_at) to ad_product_master.
    - Adds ad_product_master_id FK to ad_details, media_ad_products, product_ad_activities.
    - Does NOT drop media_ad_products (data preservation).
    """
    # ── ad_product_master: pricing columns ──
    rows = await conn.exec_driver_sql("PRAGMA table_info(ad_product_master)")
    apm_cols = {row[1] for row in rows.fetchall()}

    apm_new = {
        "position_zone": "VARCHAR(20)",
        "base_price": "FLOAT",
        "price_range_min": "FLOAT",
        "price_range_max": "FLOAT",
        "device": "VARCHAR(10) DEFAULT 'all'",
        "is_active": "BOOLEAN DEFAULT 1",
        "updated_at": "DATETIME",
    }
    for col, col_type in apm_new.items():
        if col not in apm_cols:
            try:
                await conn.exec_driver_sql(
                    f"ALTER TABLE ad_product_master ADD COLUMN {col} {col_type}"
                )
            except Exception:
                pass

    # ── ad_details: ad_product_master_id FK ──
    rows = await conn.exec_driver_sql("PRAGMA table_info(ad_details)")
    ad_cols = {row[1] for row in rows.fetchall()}

    if "ad_product_master_id" not in ad_cols:
        try:
            await conn.exec_driver_sql(
                "ALTER TABLE ad_details ADD COLUMN ad_product_master_id INTEGER REFERENCES ad_product_master(id)"
            )
        except Exception:
            pass

    # ── media_ad_products: ad_product_master_id FK ──
    rows = await conn.exec_driver_sql("PRAGMA table_info(media_ad_products)")
    map_cols = {row[1] for row in rows.fetchall()}

    if "ad_product_master_id" not in map_cols:
        try:
            await conn.exec_driver_sql(
                "ALTER TABLE media_ad_products ADD COLUMN ad_product_master_id INTEGER REFERENCES ad_product_master(id)"
            )
        except Exception:
            pass

    # ── product_ad_activities: ad_product_master_id FK ──
    rows = await conn.exec_driver_sql("PRAGMA table_info(product_ad_activities)")
    paa_cols = {row[1] for row in rows.fetchall()}

    if "ad_product_master_id" not in paa_cols:
        try:
            await conn.exec_driver_sql(
                "ALTER TABLE product_ad_activities ADD COLUMN ad_product_master_id INTEGER REFERENCES ad_product_master(id)"
            )
        except Exception:
            pass

    # ── Indexes ──
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS ix_details_ad_product_master ON ad_details(ad_product_master_id)",
        "CREATE INDEX IF NOT EXISTS ix_map_ad_product_master ON media_ad_products(ad_product_master_id)",
        "CREATE INDEX IF NOT EXISTS ix_prodact_ad_product_master ON product_ad_activities(ad_product_master_id)",
    ]:
        try:
            await conn.exec_driver_sql(idx_sql)
        except Exception:
            pass


async def _ensure_mobile_panel_tables(conn):
    """모바일 패널 디바이스 + 노출 이벤트 테이블."""
    tables = await conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    existing_tables = {row[0] for row in tables.fetchall()}

    if "mobile_panel_devices" not in existing_tables:
        await conn.exec_driver_sql("""
            CREATE TABLE mobile_panel_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id VARCHAR(64) UNIQUE NOT NULL,
                device_type VARCHAR(10) DEFAULT 'ai',
                persona_id INTEGER REFERENCES personas(id),
                os_type VARCHAR(20) NOT NULL,
                os_version VARCHAR(20),
                device_model VARCHAR(100),
                carrier VARCHAR(50),
                screen_res VARCHAR(20),
                app_list JSON,
                age_group VARCHAR(10),
                gender VARCHAR(5),
                region VARCHAR(50) DEFAULT '서울',
                is_active BOOLEAN DEFAULT TRUE,
                last_seen DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for idx_name in [
            "CREATE INDEX IF NOT EXISTS ix_mpd_device_id ON mobile_panel_devices(device_id)",
            "CREATE INDEX IF NOT EXISTS ix_mpd_type ON mobile_panel_devices(device_type)",
            "CREATE INDEX IF NOT EXISTS ix_mpd_active ON mobile_panel_devices(is_active)",
        ]:
            try:
                await conn.exec_driver_sql(idx_name)
            except Exception:
                pass

    if "mobile_panel_exposures" not in existing_tables:
        await conn.exec_driver_sql("""
            CREATE TABLE mobile_panel_exposures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id VARCHAR(64) REFERENCES mobile_panel_devices(device_id) NOT NULL,
                app_name VARCHAR(100),
                channel VARCHAR(30),
                advertiser_id INTEGER REFERENCES advertisers(id),
                advertiser_name_raw VARCHAR(200),
                ad_text VARCHAR(500),
                ad_type VARCHAR(30),
                creative_url VARCHAR(1000),
                click_url VARCHAR(1000),
                duration_ms INTEGER,
                was_clicked BOOLEAN DEFAULT FALSE,
                was_skipped BOOLEAN DEFAULT FALSE,
                screen_position VARCHAR(30),
                observed_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                extra_data JSON
            )
        """)
        for idx_name in [
            "CREATE INDEX IF NOT EXISTS ix_mpe_device ON mobile_panel_exposures(device_id)",
            "CREATE INDEX IF NOT EXISTS ix_mpe_observed ON mobile_panel_exposures(observed_at)",
            "CREATE INDEX IF NOT EXISTS ix_mpe_advertiser ON mobile_panel_exposures(advertiser_id)",
            "CREATE INDEX IF NOT EXISTS ix_mpe_channel ON mobile_panel_exposures(channel)",
            "CREATE INDEX IF NOT EXISTS ix_mpe_device_date ON mobile_panel_exposures(device_id, observed_at)",
        ]:
            try:
                await conn.exec_driver_sql(idx_name)
            except Exception:
                pass
