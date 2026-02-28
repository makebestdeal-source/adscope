from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crawler.media_targets import select_media_targets


def test_select_media_targets_lean_rotates_but_has_limit():
    targets = select_media_targets("google_gdn", profile="lean", hard_limit=2, rotation_key="seed-a")
    assert len(targets) == 2
    assert all(url.startswith("https://") for url in targets)


def test_select_media_targets_balanced_has_more_or_equal_than_lean():
    lean = select_media_targets("kakao_da", profile="lean", hard_limit=2, rotation_key="seed-a")
    balanced = select_media_targets("kakao_da", profile="balanced", hard_limit=4, rotation_key="seed-a")
    assert len(balanced) >= len(lean)


def test_select_media_targets_unknown_channel_empty():
    assert select_media_targets("unknown_channel", profile="lean", hard_limit=2, rotation_key="x") == []
