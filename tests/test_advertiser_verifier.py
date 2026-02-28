"""광고주명 검증 엔진 단위 테스트."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processor.advertiser_verifier import (
    ConfidenceLevel,
    NameQuality,
    normalize_name,
    validate_name,
    verify_advertiser_name,
)


# ── 거부 규칙 ──

def test_reject_empty():
    assert validate_name(None).quality == NameQuality.REJECTED
    assert validate_name("").quality == NameQuality.REJECTED
    assert validate_name("   ").quality == NameQuality.REJECTED


def test_reject_too_short():
    r = validate_name("A")
    assert r.quality == NameQuality.REJECTED
    assert "too_short" in r.rejection_reason


def test_reject_too_long():
    long = "경찰청사이버범죄 신고센터 사기피해 시 파출소 방문하여 신고 24시간 사이버범죄 신고 전화번호 안내 무료상담"
    assert len(long) > 50
    r = validate_name(long)
    assert r.quality == NameQuality.REJECTED
    assert "too_long" in r.rejection_reason


def test_reject_url():
    assert validate_name("www.daum.net").quality == NameQuality.REJECTED
    assert validate_name("https://example.com").quality == NameQuality.REJECTED


def test_reject_ad_system_hash():
    name = "9525216b1e63718bf8426bea9f8195e4.safeframe.googlesyndication.com"
    assert validate_name(name).quality == NameQuality.REJECTED


def test_reject_ad_system_domain():
    assert validate_name("googleads.g.doubleclick.net").quality == NameQuality.REJECTED
    assert validate_name("adcr.naver.com").quality == NameQuality.REJECTED


def test_reject_non_ad_element():
    assert validate_name("네이버 로그인").quality == NameQuality.REJECTED
    assert validate_name("네이버 톡톡").quality == NameQuality.REJECTED
    assert validate_name("더보기").quality == NameQuality.REJECTED


# ── 유효 이름 ──

def test_valid_korean():
    r = validate_name("삼성전자")
    assert r.quality == NameQuality.VALID
    assert r.cleaned_name == "삼성전자"


def test_valid_mixed():
    r = validate_name("KB국민카드")
    assert r.quality == NameQuality.VALID


def test_valid_english():
    r = validate_name("Temu")
    assert r.quality == NameQuality.VALID


# ── 정규화 ──

def test_normalize_corp_suffix():
    assert normalize_name("삼성전자(주)") == "삼성전자"
    assert normalize_name("주식회사 카카오") == "카카오"
    assert normalize_name("㈜LG생활건강") == "LG생활건강"


def test_normalize_excess_spaces():
    assert normalize_name("삼성   전자") == "삼성 전자"


def test_normalize_cleaned_quality():
    r = validate_name("삼성전자(주)")
    assert r.quality == NameQuality.CLEANED
    assert r.cleaned_name == "삼성전자"


# ── 신뢰도 점수 ──

def test_confidence_known():
    r = verify_advertiser_name("삼성전자", known_names={"삼성전자"})
    assert r.confidence == ConfidenceLevel.HIGH
    assert r.is_known_advertiser is True


def test_confidence_frequent():
    r = verify_advertiser_name("새로운브랜드", occurrence_count=5)
    assert r.confidence == ConfidenceLevel.MEDIUM


def test_confidence_unknown():
    r = verify_advertiser_name("처음보는이름")
    assert r.confidence == ConfidenceLevel.LOW


def test_confidence_rejected():
    r = verify_advertiser_name(None)
    assert r.confidence == ConfidenceLevel.INVALID
