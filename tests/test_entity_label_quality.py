from __future__ import annotations

from datetime import datetime
import json
import sqlite3
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processor.advertiser_verifier import NameQuality, validate_name
from processor.entity_label_quality import (
    LabelQuality,
    repair_material_text,
    validate_entity_label,
    validate_material_text,
)
from scripts.reject_invalid_labels import run_label_quality_repair


def test_entity_label_rejects_cta_ids_and_person_names():
    cases = {
        "Learn More": "generic_cta_label",
        "CR987654321": "creative_id_label",
        "google_search_123456": "channel_library_id",
        "youtube_transparency_987654321": "channel_library_id",
        "라이브러리 ID: 576434418048307": "raw_library_id",
        "123456789012": "long_numeric_id",
        "김민수": "personal_name_advertiser",
        "이해수": "personal_name_advertiser",
        "태경호": "personal_name_advertiser",
        "문한수": "personal_name_advertiser",
        "최설아": "personal_name_advertiser",
        "John Smith": "personal_name_advertiser",
    }

    for label, reason in cases.items():
        result = validate_entity_label(label, field="advertiser")
        assert result.quality == LabelQuality.INVALID
        assert result.reason == reason


def test_entity_label_allows_brand_like_names():
    assert validate_entity_label("삼성전자", field="advertiser").quality == LabelQuality.VALID
    assert validate_entity_label("Acme Korea", field="advertiser").quality == LabelQuality.VALID
    assert validate_entity_label("김앤장", field="advertiser").quality == LabelQuality.VALID
    assert validate_entity_label("한샘", field="advertiser").quality == LabelQuality.VALID
    assert validate_entity_label("오토카", field="advertiser").quality == LabelQuality.VALID
    assert validate_entity_label("윤선생", field="advertiser").quality == LabelQuality.VALID
    assert validate_entity_label("박문각", field="advertiser").quality == LabelQuality.VALID
    assert validate_entity_label("안다르", field="advertiser").quality == LabelQuality.VALID
    assert validate_entity_label("정관장", field="advertiser").quality == LabelQuality.VALID
    assert validate_entity_label("나이키", field="advertiser").quality == LabelQuality.VALID
    assert validate_entity_label("이투스", field="advertiser").quality == LabelQuality.VALID
    assert validate_entity_label("유세린", field="advertiser").quality == LabelQuality.VALID
    assert validate_entity_label("공단기", field="advertiser").quality == LabelQuality.VALID
    assert validate_entity_label("오랄비", field="advertiser").quality == LabelQuality.VALID
    assert validate_entity_label("crassiang", field="advertiser").quality == LabelQuality.VALID


def test_material_text_rejects_and_repairs_library_placeholders():
    assert validate_material_text("youtube_transparency_3").reason == "channel_library_id"
    assert validate_material_text("0:00 / 0:10").reason == "duration_only_text"
    assert validate_material_text("CR123456789").reason == "creative_id_label"
    assert (
        repair_material_text(
            "youtube_transparency_3",
            {"matched_video_title": "젊음이 길어진 시대에 가장 젊게 사는 시니어"},
        )
        == "젊음이 길어진 시대에 가장 젊게 사는 시니어"
    )
    assert repair_material_text("0:00 / 0:10", {}) is None
    assert repair_material_text("활성 라이브러리 ID: 123456789 메뉴 광고 상세 정보 보기 강남언니 광고 성큼 찾아온 봄") == "강남언니 광고 성큼 찾아온 봄"


def test_advertiser_verifier_uses_entity_label_quality():
    result = validate_name("CR123456789")
    assert result.quality == NameQuality.REJECTED
    assert result.rejection_reason == "creative_id_label"


def test_reject_invalid_labels_dry_run_and_apply():
    db_path = Path(__file__).resolve().parent / f".quality_{uuid.uuid4().hex}.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE advertisers (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE ad_snapshots (
                id INTEGER PRIMARY KEY,
                channel TEXT,
                captured_at TEXT
            );
            CREATE TABLE ad_details (
                id INTEGER PRIMARY KEY,
                snapshot_id INTEGER,
                advertiser_id INTEGER,
                advertiser_name_raw TEXT,
                ad_text TEXT,
                creative_image_path TEXT,
                verification_status TEXT,
                verification_source TEXT,
                extra_data TEXT
            );
            CREATE TABLE campaigns (
                id INTEGER PRIMARY KEY,
                advertiser_id INTEGER,
                channel TEXT,
                first_seen TEXT,
                last_seen TEXT,
                campaign_name TEXT,
                extra_data TEXT
            );
            """
        )
        now = datetime.utcnow().isoformat(sep=" ")
        conn.execute("INSERT INTO advertisers (id, name) VALUES (1, '삼성전자')")
        conn.execute("INSERT INTO ad_snapshots (id, channel, captured_at) VALUES (1, 'meta', ?)", (now,))
        conn.execute(
            """
            INSERT INTO ad_details
                (id, snapshot_id, advertiser_id, advertiser_name_raw, ad_text, creative_image_path, verification_status, extra_data)
            VALUES (1, 1, 1, 'google_search_123456', NULL, NULL, NULL, '{}')
            """
        )
        conn.execute(
            """
            INSERT INTO ad_details
                (id, snapshot_id, advertiser_id, advertiser_name_raw, ad_text, creative_image_path, verification_status, extra_data)
            VALUES (2, 1, 1, '삼성전자', 'youtube_transparency_3', NULL, NULL, '{"matched_video_title":"삼성생명 캠페인 영상"}')
            """
        )
        conn.execute(
            """
            INSERT INTO ad_details
                (id, snapshot_id, advertiser_id, advertiser_name_raw, ad_text, creative_image_path, verification_status, extra_data)
            VALUES (3, 1, 1, '삼성전자', '0:00 / 0:10', 'stored_images/a.webp', NULL, '{}')
            """
        )
        conn.execute(
            """
            INSERT INTO ad_details
                (id, snapshot_id, advertiser_id, advertiser_name_raw, ad_text, creative_image_path, verification_status, extra_data)
            VALUES (4, 1, 1, '이해수', NULL, NULL, NULL, '{}')
            """
        )
        conn.execute(
            """
            INSERT INTO campaigns
                (id, advertiser_id, channel, first_seen, last_seen, campaign_name, extra_data)
            VALUES (1, 1, 'meta', ?, ?, 'CR987654321', '{}')
            """,
            (now, now),
        )
        conn.commit()
        conn.close()

        dry = run_label_quality_repair(db_path=db_path, days=1, apply=False)
        assert dry["ad_rows_rejected"] == 2
        assert dry["ad_text_repaired"] == 1
        assert dry["ad_text_cleared"] == 1
        assert dry["campaigns_marked"] == 1

        conn = sqlite3.connect(db_path)
        assert conn.execute("SELECT verification_status FROM ad_details WHERE id = 1").fetchone()[0] is None
        conn.close()

        applied = run_label_quality_repair(
            db_path=db_path,
            days=1,
            apply=True,
            repair_campaign_names=True,
        )
        assert applied["ad_rows_rejected"] == 2
        assert applied["campaigns_marked"] == 1
        assert applied["campaigns_renamed"] == 1

        conn = sqlite3.connect(db_path)
        status, source, extra_raw = conn.execute(
            "SELECT verification_status, verification_source, extra_data FROM ad_details WHERE id = 1"
        ).fetchone()
        campaign_name, campaign_extra_raw = conn.execute(
            "SELECT campaign_name, extra_data FROM campaigns WHERE id = 1"
        ).fetchone()
        repaired_text = conn.execute("SELECT ad_text FROM ad_details WHERE id = 2").fetchone()[0]
        cleared_text = conn.execute("SELECT ad_text FROM ad_details WHERE id = 3").fetchone()[0]
        person_status, person_source, person_extra_raw = conn.execute(
            "SELECT verification_status, verification_source, extra_data FROM ad_details WHERE id = 4"
        ).fetchone()
        conn.close()

        assert status == "rejected"
        assert source == "label_quality:channel_library_id"
        assert json.loads(extra_raw)["quality_rejection_reason"] == "channel_library_id"
        assert campaign_name == f"삼성전자 meta {datetime.utcnow().month}월 campaign"
        assert json.loads(campaign_extra_raw)["quality_rejection_reason"] == "creative_id_label"
        assert repaired_text == "삼성생명 캠페인 영상"
        assert cleared_text is None
        assert person_status == "rejected"
        assert person_source == "label_quality:personal_name_advertiser"
        assert json.loads(person_extra_raw)["quality_evidence"]["advertiser_name_raw"]["evidence"].startswith(
            "explicit_person_blacklist"
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            db_path.unlink()
        except FileNotFoundError:
            pass
