import ast
import copy
import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.generate import generate, load_project_principles
from alpha.gitops import commit_skeleton
from alpha.recipes import recipe_hash

SCENARIOS = PLUGIN_ROOT / "evals" / "scenarios"
SHIM = PLUGIN_ROOT / "bin" / "alpha"
TODAY = date(2026, 10, 19)


def place_answers(target: Path, scenario: str) -> Path:
    dest = target / ".claude" / "alpha" / "project.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SCENARIOS / f"{scenario}.json", dest)
    return dest


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def run_cli(*args: str, env: dict[str, str] | None = None):
    return subprocess.run(
        [sys.executable, str(SHIM), *args],
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


def generated_repo(tmp_path: Path, scenario: str) -> Path:
    place_answers(tmp_path, scenario)
    generate(tmp_path, PLUGIN_ROOT, Source(PLUGIN_ROOT, True), 2026, TODAY)
    git(tmp_path, "init", "-q", "-b", "main")
    commit_skeleton(tmp_path, load_project_principles(tmp_path), [])
    return tmp_path


def clone_component(data: dict[str, Any], source: str, name: str, path: str) -> None:
    comp = next(c for c in data["components"] if c["name"] == source)
    data["components"].append({**copy.deepcopy(comp), "name": name, "path": path})
    for section in data.values():
        if not isinstance(section, dict) or not isinstance(
            section.get("components"), list
        ):
            continue
        entries: list[Any] = section["components"]
        for entry in list(entries):
            if isinstance(entry, dict) and entry.get("name") == source:
                entries.append({**copy.deepcopy(entry), "name": name})
    if name not in data["git"]["scopes"]:
        data["git"]["scopes"].append(name)
    data["layout"] = "monorepo"


def old_python() -> str | None:
    for candidate in ("/usr/bin/python3", "python3.9", "python3.10"):
        exe = shutil.which(candidate)
        if exe is None:
            continue
        done = subprocess.run(
            [exe, "-c", "import sys; print(sys.version_info[:2] < (3, 11))"],
            capture_output=True,
            text=True,
        )
        if done.returncode == 0 and done.stdout.strip() == "True":
            return exe
    return None


def union_annotations(tree: ast.Module) -> list[int]:
    """Lines whose annotations use `X | Y`, which 3.9 evaluates at runtime."""
    lazy = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and any(a.name == "annotations" for a in node.names)
        for node in tree.body
    )
    if lazy:
        return []
    annotations: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            args = node.args
            every = [*args.posonlyargs, *args.args, *args.kwonlyargs]
            every += [a for a in (args.vararg, args.kwarg) if a is not None]
            annotations += [a.annotation for a in every if a.annotation is not None]
            if node.returns is not None:
                annotations.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
    return [
        sub.lineno
        for ann in annotations
        for sub in ast.walk(ann)
        if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr)
    ]


def single_component(
    data: dict[str, Any], component: dict[str, Any] | None = None
) -> None:
    comp = component or data["components"][0]
    name = comp["name"]
    data["components"] = [comp]
    data["components_talk"] = False
    data["architecture"]["components"] = [
        {"name": name, "responsibility": "Does the work.", "calls": []}
    ]
    data["architecture"]["contracts"] = {"format": "none", "paths": []}
    data["errors"]["components"] = [{"name": name, "format": "exceptions"}]
    data["testing"]["components"] = [{"name": name, "levels": ["unit"]}]
    hosting = "Fly.io" if comp["traits"]["deployed"] else ""
    data["build"]["components"] = [
        {"name": name, "artifact": "package", "hosting": hosting}
    ]
    log = {"log_format": "json", "correlation": "none", "telemetry": "none"}
    deployed = comp["traits"]["deployed"]
    data["observability"]["components"] = [{"name": name, **log}] if deployed else []
    ui = comp["traits"]["has_ui"] or comp["kind"] in ("frontend", "mobile")
    for area in ("ui", "accessibility"):
        if area in data:
            entries = data[area]["components"]
            data[area]["components"] = [{**entries[0], "name": name}] if ui else []
    if "accessibility" in data and not ui:
        data["accessibility"]["level"] = ""
    if "data" in data:
        stores = data["data"]["components"]
        stored = comp["traits"]["persisted_data"] and stores
        data["data"]["components"] = [{**stores[0], "name": name}] if stored else []
    if "performance" in data:
        budgets = data["performance"]["components"][0]["budgets"]
        data["performance"]["components"] = [{"name": name, "budgets": budgets}]
    if "releases" in data:
        data["releases"]["scope"] = "repo"


def override_record(data: dict[str, Any], principle: str, index: int = 0) -> str:
    number = len(data["decisions"]) + index + 1
    return f"docs/decisions/{number:04d}-override-{principle}.md"


def shell_recipe() -> dict[str, Any]:
    return {
        "bootstrap": [],
        "commands": {
            "setup": "true",
            "test": "sh tests/setup.sh",
            "lint": "",
            "format": "",
            "format_check": "",
            "typecheck": "",
            "format_file": "",
            "lint_file": "",
        },
        "lockfiles": [],
        "manifests": ["tool.cfg"],
        "source_globs": ["**/*.sh"],
        "test_globs": ["tests/**"],
        "exclude_globs": ["**/.*/**"],
        "ignores": ["out/"],
        "allow": ["Bash(sh:*)"],
        "why": {},
        "ci": {"steps": [], "env": {}},
        "dependabot": "",
        "templates": {
            "tool.cfg": "name = $slug-$name\n",
            "tests/setup.sh": "test 1 -eq 1\n",
        },
    }


def proven(recipe: dict[str, Any]) -> dict[str, Any]:
    return {**recipe, "proven_hash": recipe_hash(recipe)}


# --- an existing repo to adopt (spec §5b) ---

EXISTING: dict[str, str] = {
    "pyproject.toml": '[project]\nname = "legacy"\nversion = "1.0"\n',
    "src/legacy/__init__.py": "",
    "src/legacy/core.py": "def double(x):\n    return x * 2\n",
    "tests/test_core.py": "from legacy.core import double\n\n\n"
    "def test_double():\n    assert double(2) == 4\n",
    "README.md": "# Legacy\n\nOur service. Run it with `make run`.\n",
    "LICENSE": "Copyright the legacy authors. All rights reserved.\n",
    ".gitignore": "__pycache__/\n.venv/\n*.log\n",
    ".github/workflows/ci.yml": "on: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
    "    steps:\n      - run: make test\n",
    ".claude/settings.json": (
        '{\n  "permissions": {"allow": ["Bash(make test:*)"]}\n}\n'
    ),
    "docs/decisions/0001-use-postgres.md": "# 0001. Use Postgres\n\nStatus: accepted\n",
}


def existing_repo(target: Path, files: dict[str, str] | None = None) -> Path:
    """A committed repo alpha didn't make, on main."""
    target.mkdir(parents=True, exist_ok=True)
    git(target, "init", "-q", "-b", "main")
    for rel, text in (EXISTING if files is None else files).items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(target, "add", "-A")
    git(target, "commit", "-q", "-m", "feat: Start the legacy service")
    return target


def adoption_answers(target: Path, **adoption: Any) -> dict[str, Any]:
    """The ML scenario's answers, fitted to `existing_repo`: its one component
    runs an adopted recipe, and the repo's LICENSE is kept."""
    data: dict[str, Any] = json.loads((SCENARIOS / "python-ml-single.json").read_text())
    data["components"][0]["stack"] = "ml-python"
    data["identity"]["license_file"] = "LICENSE"
    data["recipes"] = {"ml-python": proven({"adopted": True, "extends": "python"})}
    data["adoption"] = {"git_hooks": "alpha", **adoption}
    path = target / ".claude" / "alpha" / "project.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    return data
