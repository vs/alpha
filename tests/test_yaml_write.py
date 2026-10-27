import pytest
import yaml

from alpha.yaml_write import dumps


def test_round_trips_through_pyyaml():
    data: dict[str, object] = {
        "on": {"push": {"branches": ["main"]}, "pull_request": {}},
        "jobs": {
            "api": {
                "steps": [
                    {"uses": "actions/checkout@v9"},
                    {"name": "lint", "run": 'uv run ruff check # x: "y" {file}'},
                    {"with": {"enable-cache": True, "glob": "*.lock"}},
                ]
            }
        },
        "n": 3,
        "ok": True,
        "empty": [],
        "none": {},
        "text": "line one\nline two: 'quoted'",
        "lists": [["a", "b"], []],
    }
    assert yaml.safe_load(dumps(data)) == data


def test_boolean_word_keys_are_quoted():
    assert dumps({"on": 1}).startswith('"on": 1')
    assert dumps({"No": 1}).startswith('"No": 1')
    assert dumps({"node-version": 1}).startswith("node-version: 1")


def test_unsupported_value_names_its_path():
    with pytest.raises(TypeError, match=r"a\.b"):
        dumps({"a": {"b": 1.5}})
    with pytest.raises(TypeError, match=r"a\[0\]"):
        dumps({"a": [None]})


@pytest.mark.parametrize("key", ["null", "Null", "~", "1", "0x1f", "1e3", "0o17", ".5"])
def test_keys_yaml_reads_as_non_strings_are_quoted(key: str):
    assert yaml.safe_load(dumps({key: "v"})) == {key: "v"}


def test_characters_outside_the_bmp_round_trip():
    data = {"emoji": "ship it 🚀", "control": "a\x7fb\x85c d﻿e"}
    assert yaml.safe_load(dumps(data)) == data
