from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crawler.meta_library import _first_text


def test_first_text_with_string():
    assert _first_text("  hello   world  ") == "hello world"


def test_first_text_with_nested_list_dict():
    payload = [
        {"value": ""},
        {"text": "   "},
        {"title": "Ad Title"},
    ]
    assert _first_text(payload) == "Ad Title"


def test_first_text_none_when_empty():
    assert _first_text([{"text": "  "}, {}, []]) is None
