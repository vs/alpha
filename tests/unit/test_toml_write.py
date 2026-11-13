import tomllib
from collections.abc import Mapping
from typing import Any

import pytest

from alpha.toml_write import dumps


def roundtrip(d: Mapping[str, object]) -> dict[str, object]:
    return tomllib.loads(dumps(d))


def test_scalars_and_quoting() -> None:
    d = {"a": 'say "hi" \\ ok', "n": 3, "b": True, "xs": ["x", "y"]}
    assert roundtrip(d) == d


def test_multiline_string() -> None:
    d = {"rationale": 'line one\nline two "quoted"\n'}
    assert roundtrip(d) == d and '"""' in dumps(d)


def test_nested_tables_and_odd_keys() -> None:
    d = {
        "docs_map": {"api/src/**": ["docs/architecture.md"]},
        "review": {"max_lines": 200},
    }
    assert roundtrip(d) == d


def test_array_of_tables_with_subtable() -> None:
    d: dict[str, Any] = {
        "components": [
            {"name": "api", "commands": {"test": "uv run pytest"}},
            {"name": "web", "commands": {}},
        ]
    }
    assert roundtrip(d) == d


def test_rejects_floats_with_key_path() -> None:
    with pytest.raises(TypeError, match="review.ratio"):
        dumps({"review": {"ratio": 0.5}})


def test_scalars_before_subtables_and_order_kept() -> None:
    d = {"t": {"x": 1}, "z": 1, "a": 2}
    assert list(roundtrip(d)) == ["z", "a", "t"]
    assert dumps(d) == dumps(d)


def test_control_chars_and_multiline_with_triple_quotes() -> None:
    d = {"a": "tab\there\x01", "b": 'x\n"""\ny\\', "c": "cr\r\nlf"}
    assert roundtrip(d) == d


def test_empty_lists_and_int_lists() -> None:
    d = {"a": [], "b": [1, 2]}
    assert roundtrip(d) == d
