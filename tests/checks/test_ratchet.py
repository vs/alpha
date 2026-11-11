import importlib.util
import json
import shlex
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from alpha.baseline import Baseline
from alpha.recipes import RecipeBook
from alpha.registry import default_registry
from alpha.toml_write import dumps

SCRIPT = Path(__file__).parents[2] / "project-files" / "checks" / "ratchet.py"
OUTPUT = Path(__file__).parents[1] / "fixtures" / "baseline-output"
ROOT = Path("/ROOT")


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ratchet", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ratchet = _module()


def _kit(tool: str) -> Baseline:
    book = RecipeBook()
    steps = {
        "ruff": ("python", "lint"),
        "pyright": ("python", "typecheck"),
        "pytest": ("python", "test"),
        "deptry": ("python", "structure"),
        "biome": ("typescript", "lint"),
        "tsc": ("typescript", "typecheck"),
        "vitest": ("typescript", "test"),
    }
    if tool in steps:
        stack, step = steps[tool]
        return book.get(stack).baselines[step]
    pin = default_registry().tool(tool).pin
    assert pin is not None and pin.baseline is not None
    return pin.baseline


# What each recorded output (tests/fixtures/baseline-output/, from the
# kit's pinned tools on seeded violations) must read as: every seeded
# finding, and nothing from the tools' summary or notice lines.
EXPECTED: dict[str, dict[str, dict[str, int]]] = {
    "ruff": {
        "pkg/bad.py": {"I001": 1, "F401": 2},
        "pkg/syn.py": {"invalid-syntax": 2},
        "tests/test_bad.py": {"B011": 1},
    },
    "pyright": {
        "pkg/bad.py": {
            "reportUnusedImport": 2,
            "reportUnknownParameterType": 2,
            "reportMissingParameterType": 1,
            "reportUnknownVariableType": 1,
            "reportReturnType": 1,
        },
        "pkg/syn.py": {"-": 6},  # syntax errors carry no rule
    },
    "pytest": {"tests/test_bad.py": {"test_fails": 1, "TestGroup::test_also": 1}},
    "deptry": {"pkg/bad.py": {"DEP001": 1}, "pyproject.toml": {"DEP002": 1}},
    "biome": {
        "src/bad.ts": {
            "lint/correctness/noUnusedFunctionParameters": 1,
            "lint/suspicious/noExplicitAny": 1,
            "lint/suspicious/noDebugger": 1,
        }
    },
    "tsc": {"src/bad.ts": {"TS2322": 1}, "tsconfig.json": {"TS5023": 1}},
    "vitest": {"tests/bad.test.ts": {"group > fails": 1, "top fails": 1}},
    "typos": {"docs/guide.md": {"teh": 1, "recieve": 1}},
    "rumdl": {
        "docs/guide.md": {"MD059": 1, "MD057": 1, "MD012": 1, "MD022": 1},
        ".claude/skills/x/SKILL.md": {"MD041": 1},
    },
    "lychee": {"docs/guide.md": {"file://docs/missing.md": 1}},
    "agnix": {".claude/skills/x/SKILL.md": {"AS-001": 1}},
    "jactionlint": {
        ".github/workflows/ci.yml": {
            "concurrency-limits": 1,
            "missing-timeout": 1,
            "missing-permissions": 1,
            "unpinned-uses": 1,
            "artipacked": 1,
        }
    },
}


@pytest.mark.parametrize("tool", sorted(EXPECTED))
def test_kit_patterns_read_recorded_output(tool: str):
    baseline = _kit(tool)
    name = f"{tool}.json" if baseline.json is not None else f"{tool}.txt"
    output = (OUTPUT / name).read_text()
    found = ratchet.parse(baseline.to_data(), output, "", ROOT, ROOT)
    assert ratchet.count(found) == EXPECTED[tool]


def test_paths_normalize_to_root():
    cwd = ROOT / "api"
    for raw in ("/ROOT/api/a.py", "./a.py", "a.py", "file:///ROOT/api/a.py"):
        assert ratchet.normalize_file(raw, ROOT, cwd) == "api/a.py"
    assert ratchet.normalize_file("../web/b.ts", ROOT, cwd) == "web/b.ts"
    assert ratchet.normalize_file("", ROOT, cwd) == "-"


def test_ansi_colors_are_ignored():
    found = ratchet.parse_lines(
        "\x1b[1mpkg/a.py\x1b[m:1:2: DEP001 x\n",
        r"^(?P<file>[^:]+):\d+:\d+: (?P<rule>\w+)",
        ROOT,
        ROOT,
    )
    assert ratchet.count(found) == {"pkg/a.py": {"DEP001": 1}}


def test_missing_rule_counts_as_dash():
    pattern = r"^(?P<file>\S+): (?:(?P<rule>E\d+) )?oops"
    found = ratchet.parse_lines("a.py: oops\na.py: E1 oops\n", pattern, ROOT, ROOT)
    assert ratchet.count(found) == {"a.py": {"-": 1, "E1": 1}}


# --- the command, in a project ---

LINE = r"^(?P<file>[^:\s]+):\d+: (?P<rule>\w+)"


def _project(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "api").mkdir()
    (root / "docs" / "principles.toml").write_text(dumps({"baselines": entries}))
    return root


def _entry(output: str, exit_code: int = 1, **extra: Any) -> dict[str, Any]:
    script = f"printf '%s' {shlex.quote(output)}; exit {exit_code}"
    return {"id": "lint:api", "dir": "api", "command": script, "pattern": LINE, **extra}


def _set_baseline(root: Path, counts: dict[str, dict[str, int]]) -> Path:
    path = root / ".claude" / "alpha" / "baselines" / "lint.api.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"check": "lint:api", "counts": counts}))
    return path


def _run(root: Path, *args: str, ci: bool = False) -> subprocess.CompletedProcess[str]:
    env = {"PATH": "/usr/bin:/bin", "CI": "true" if ci else ""}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=root / "api",
        capture_output=True,
        text=True,
        env=env,
    )


def test_new_finding_fails(tmp_path: Path):
    root = _project(tmp_path, [_entry("a.py:1: E1 one\na.py:9: E1 two\n")])
    _set_baseline(root, {"api/a.py": {"E1": 1}})
    done = _run(root, "lint:api")
    assert done.returncode == 1
    assert "api/a.py E1: 2 now, 1 in the baseline" in done.stderr
    assert "a.py:1: E1 one" in done.stderr and "a.py:9: E1 two" in done.stderr
    assert "--decision" in done.stderr


def test_same_findings_pass(tmp_path: Path):
    root = _project(tmp_path, [_entry("a.py:1: E1 one\n")])
    path = _set_baseline(root, {"api/a.py": {"E1": 1}})
    before = path.read_text()
    assert _run(root, "lint:api").returncode == 0
    assert path.read_text() == before


def test_fewer_tightens_locally(tmp_path: Path):
    root = _project(tmp_path, [_entry("", exit_code=0)])
    path = _set_baseline(root, {"api/a.py": {"E1": 2}, "api/b.py": {"E2": 1}})
    done = _run(root, "lint:api")
    assert done.returncode == 0, done.stderr
    assert json.loads(path.read_text())["counts"] == {}
    assert "Commit .claude/alpha/baselines/lint.api.json" in done.stdout


def test_frozen_fails_on_stale(tmp_path: Path):
    root = _project(tmp_path, [_entry("", exit_code=0)])
    path = _set_baseline(root, {"api/a.py": {"E1": 2}})
    before = path.read_text()
    done = _run(root, "lint:api", ci=True)
    assert done.returncode == 1
    assert "alpha baseline tighten" in done.stderr and "commit" in done.stderr
    assert path.read_text() == before


def test_grown_and_shrunk_does_not_tighten(tmp_path: Path):
    root = _project(tmp_path, [_entry("a.py:1: E1 x\na.py:2: E1 y\n")])
    path = _set_baseline(root, {"api/a.py": {"E1": 1, "E2": 3}})
    before = path.read_text()
    assert _run(root, "lint:api").returncode == 1
    assert path.read_text() == before


def test_unparsed_failure_fails_closed(tmp_path: Path):
    root = _project(tmp_path, [_entry("Traceback: tool crashed\n")])
    _set_baseline(root, {"api/a.py": {"E1": 5}})
    done = _run(root, "lint:api")
    assert done.returncode == 2
    assert "can't be judged" in done.stderr and "tool crashed" in done.stderr


def test_unreadable_json_fails_closed(tmp_path: Path):
    entry = _entry("not json", exit_code=0)
    del entry["pattern"]
    entry["json"] = {"items": "items.*", "file": "file"}
    root = _project(tmp_path, [entry])
    _set_baseline(root, {})
    done = _run(root, "lint:api")
    assert done.returncode == 2 and "isn't JSON" in done.stderr


def test_file_mode_compares_one_file(tmp_path: Path):
    entry = _entry(
        "a.py:1: E1 x\nb.py:1: E9 other\n",
        file_command=(
            "printf 'a.py:1: E1 x\\nb.py:1: E9 other\\n'; echo {file} >&2; exit 1"
        ),
    )
    root = _project(tmp_path, [entry])
    path = _set_baseline(root, {"api/a.py": {"E1": 1, "E3": 2}, "api/b.py": {"E4": 1}})
    done = _run(root, "lint:api", "--file", "a.py")
    assert done.returncode == 0, done.stderr
    counts = json.loads(path.read_text())["counts"]
    assert counts == {"api/a.py": {"E1": 1}, "api/b.py": {"E4": 1}}


def test_capture_writes_counts(tmp_path: Path):
    root = _project(tmp_path, [_entry("b.py:1: E2 x\na.py:1: E1 y\na.py:2: E1 z\n")])
    done = _run(root, "lint:api", "--capture")
    assert done.returncode == 0, done.stderr
    path = root / ".claude" / "alpha" / "baselines" / "lint.api.json"
    data = json.loads(path.read_text())
    assert data == {
        "check": "lint:api",
        "counts": {"api/a.py": {"E1": 2}, "api/b.py": {"E2": 1}},
    }
    assert path.read_text().index('"api/a.py"') < path.read_text().index('"api/b.py"')


def test_missing_baseline_names_capture(tmp_path: Path):
    root = _project(tmp_path, [_entry("a.py:1: E1 x\n")])
    done = _run(root, "lint:api")
    assert done.returncode == 2
    assert "alpha baseline capture" in done.stderr and "--check lint:api" in done.stderr


def test_unknown_id_names_known(tmp_path: Path):
    root = _project(tmp_path, [_entry("")])
    done = _run(root, "typos")
    assert done.returncode == 2 and "baselined: lint:api" in done.stderr
