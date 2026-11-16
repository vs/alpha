"""The spec's Requirements table names tests that exist."""

import re

from alpha.cli import PLUGIN_ROOT

SPEC = PLUGIN_ROOT / "docs" / "specification.md"
ROW = re.compile(r"^\| (R\d+\.\d+) \|(.*)$", re.MULTILINE)
REF = re.compile(r"`(tests/[\w/.\-]+\.py)::(\w+)`")


def test_each_requirement_names_tests_that_exist():
    rows = ROW.findall(SPEC.read_text("utf-8"))
    assert rows, "no requirement rows found in docs/specification.md"
    problems: list[str] = []
    for rid, rest in rows:
        refs = REF.findall(rest)
        if not refs:
            problems.append(f"{rid}: names no test")
        prefix = f"test_{rid.replace('.', '_')}_"
        for path, name in refs:
            file = PLUGIN_ROOT / path
            if not name.startswith(prefix):
                problems.append(f"{rid}: {name} doesn't start with {prefix}")
            if not file.is_file():
                problems.append(f"{rid}: {path} doesn't exist")
            elif not re.search(rf"^def {name}\(", file.read_text("utf-8"), re.M):
                problems.append(f"{rid}: {path} has no {name}")
    assert problems == []
