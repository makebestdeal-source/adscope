from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processor.pipeline import _resolve_verification_fields


def _ad(
    verification_status=None,
    verification_source=None,
    extra_data=None,
):
    return SimpleNamespace(
        verification_status=verification_status,
        verification_source=verification_source,
        extra_data=extra_data,
    )


def test_resolve_verification_fields_channel_default_for_naver():
    status, source, extra = _resolve_verification_fields("naver_search", _ad())
    assert status == "unverified"
    assert source == "channel_default"
    assert extra["verification_status"] == "unverified"
    assert extra["verification_source"] == "channel_default"


def test_resolve_verification_fields_uses_existing_values():
    status, source, extra = _resolve_verification_fields(
        "google_gdn",
        _ad(extra_data={"verification_status": "verified", "verification_source": "meta_ads_library"}),
    )
    assert status == "verified"
    assert source == "meta_ads_library"
    assert extra["verification_status"] == "verified"
    assert extra["verification_source"] == "meta_ads_library"


def test_resolve_verification_fields_trims_blank_to_fallback():
    status, source, extra = _resolve_verification_fields(
        "kakao_da",
        _ad(verification_status="  ", verification_source=" "),
    )
    assert status == "unverified"
    assert source == "channel_default"
    assert extra["verification_status"] == "unverified"
    assert extra["verification_source"] == "channel_default"


def test_resolve_verification_fields_global_default_for_other_channel():
    status, source, extra = _resolve_verification_fields("facebook", _ad())
    assert status == "unknown"
    assert source == "not_collected"
    assert extra["verification_status"] == "unknown"
    assert extra["verification_source"] == "not_collected"
