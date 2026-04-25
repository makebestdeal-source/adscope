from scripts.fix_meta_generic_advertisers import _fallback_name


def test_fallback_name_uses_external_landing_domain():
    assert _fallback_name("https://www.infinitepay.io/tap", None) == "infinitepay.io"


def test_fallback_name_rejects_infra_domain():
    assert _fallback_name("https://ad.doubleclick.net/ddm/trackclk/foo", None) is None
