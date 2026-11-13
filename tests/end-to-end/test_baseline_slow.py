"""Baselines end to end (spec §8b): a web+API project with legacy findings
bootstraps green with them baselined, fails on a new one, tightens when one
is fixed, and refuses a pull request that grows a baseline."""

import json
import os
import subprocess
import tomllib
from pathlib import Path

import pytest
from helpers import TODAY, git, place_answers

from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.generate import bootstrap, generate
from alpha.gitops import commit_skeleton

CHECKS = [
    "lint:api",
    "typecheck:api",
    "test:api",
    "lint:web",
    "typecheck:web",
    "test:web",
    "typos",
    "markdown",
]
LEGACY = {
    # ruff F401; pyright reportUnusedImport and reportReturnType.
    "api/legacy.py": "import os\n\n\ndef double(x: int) -> int:\n    return str(x)\n",
    "api/tests/test_legacy.py": "def test_legacy() -> None:\n    assert 1 == 2\n",
    # tsc TS2322; biome noExplicitAny. The test imports it, so knip sees it used.
    "web/src/legacy.ts": (
        'const n: number = "s";\n\n'
        "export function f(x: any): number {\n  return n + x;\n}\n"
    ),
    "web/tests/legacy.test.ts": (
        'import { expect, test } from "vitest";\n'
        'import { f } from "../src/legacy.js";\n\n'
        'test("legacy", () => {\n  expect(f(1)).toBe(0);\n});\n'
    ),
    "docs/legacy.md": "# Legacy\n\nThis is teh old guide.\n\n\n## Two\n\nMore.\n",
}


def _sh(cwd: Path, command: str, **env: str) -> subprocess.CompletedProcess[str]:
    full = {k: v for k, v in os.environ.items() if k not in ("CI", "ALPHA_BASE")}
    return subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**full, **env},
    )


def _alpha(*args: str) -> subprocess.CompletedProcess[str]:
    return _sh(PLUGIN_ROOT, " ".join([str(PLUGIN_ROOT / "bin" / "alpha"), *args]))


def _counts(root: Path, check: str) -> dict[str, dict[str, int]]:
    path = root / ".claude/alpha/baselines" / f"{check.replace(':', '.')}.json"
    return json.loads(path.read_text())["counts"]


@pytest.mark.slow
def test_legacy_project_runs_green_and_ratchets(tmp_path: Path, git_env: None):
    answers = place_answers(tmp_path, "web-ts-plus-python-api")
    data = json.loads(answers.read_text())
    data["adoption"] = {"baselines": CHECKS}
    answers.write_text(json.dumps(data))
    generate(tmp_path, PLUGIN_ROOT, Source(PLUGIN_ROOT, True), 2026, TODAY)
    for rel, text in LEGACY.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    principles = tomllib.loads((tmp_path / "docs/principles.toml").read_text())

    bootstrap(tmp_path, principles, capture_baselines=True)  # mise run ci passes
    assert _counts(tmp_path, "lint:api") == {"api/legacy.py": {"F401": 1}}
    assert _counts(tmp_path, "typecheck:api")["api/legacy.py"] == {
        "reportUnusedImport": 1,
        "reportReturnType": 1,
    }
    assert _counts(tmp_path, "test:api") == {
        "api/tests/test_legacy.py": {"test_legacy": 1}
    }
    assert _counts(tmp_path, "typecheck:web") == {"web/src/legacy.ts": {"TS2322": 1}}
    assert _counts(tmp_path, "lint:web") == {
        "web/src/legacy.ts": {"lint/suspicious/noExplicitAny": 1}
    }
    assert _counts(tmp_path, "test:web") == {"web/tests/legacy.test.ts": {"legacy": 1}}
    assert _counts(tmp_path, "typos") == {"docs/legacy.md": {"teh": 1}}
    assert _counts(tmp_path, "markdown") == {"docs/legacy.md": {"MD012": 1}}
    commit_skeleton(tmp_path, principles, [])
    assert git(tmp_path, "status", "--porcelain") == ""

    # A new type error fails, naming it; the legacy ones still pass.
    legacy = tmp_path / "api/legacy.py"
    legacy.write_text(
        LEGACY["api/legacy.py"] + "\n\ndef triple(x: int) -> int:\n    return str(x)\n"
    )
    done = _sh(tmp_path, "mise run check:component:api")
    assert done.returncode != 0
    assert "reportReturnType: 2 now, 1 in the baseline" in done.stdout + done.stderr
    legacy.write_text(LEGACY["api/legacy.py"])

    # Fixing a legacy finding: CI fails until the baseline is tightened.
    legacy.write_text("def double(x: int) -> int:\n    return str(x)\n")
    done = _sh(
        tmp_path / "api",
        "python3 ../.claude/alpha/checks/ratchet.py lint:api",
        CI="true",
    )
    assert done.returncode == 1 and "alpha baseline tighten" in done.stderr
    done = _alpha("baseline", "tighten", str(tmp_path))
    assert done.returncode == 0, done.stderr
    assert "tightened: .claude/alpha/baselines/lint.api.json" in done.stdout
    assert _counts(tmp_path, "lint:api") == {}
    assert _counts(tmp_path, "typecheck:api")["api/legacy.py"] == {
        "reportReturnType": 1
    }
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "--no-verify", "-m", "fix: Drop an unused import")

    # A pull request that grows a baseline needs an accepted decision.
    git(tmp_path, "checkout", "-q", "-b", "feature")
    legacy.write_text(LEGACY["api/legacy.py"])
    done = _alpha("baseline", "capture", str(tmp_path), "--check", "lint:api")
    assert done.returncode == 1 and "would grow its baseline" in done.stderr
    baseline = tmp_path / ".claude/alpha/baselines/lint.api.json"
    baseline.write_text(
        json.dumps({"check": "lint:api", "counts": {"api/legacy.py": {"F401": 1}}})
    )
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "--no-verify", "-m", "chore: Keep the import")
    done = _sh(tmp_path, "mise run check:baselines", ALPHA_BASE="main")
    assert done.returncode != 0
    assert "baselines only shrink" in done.stdout + done.stderr
    record = tmp_path / "docs/decisions/0099-keep-the-os-import.md"
    record.write_text(
        "# 0099. Keep the os import\n\nDate: 2026-11-11\nStatus: accepted\n\n"
        "## Context\n\nThe `lint:api` baseline keeps one F401 until the module "
        "is rewritten.\n"
    )
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "--no-verify", "-m", "docs: Accept the import")
    done = _sh(tmp_path, "mise run check:baselines", ALPHA_BASE="main")
    assert done.returncode == 0, done.stdout + done.stderr
