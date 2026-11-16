import ast
import copy
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, cast

from alpha.answers import PROJECT_JSON
from alpha.apply import plan, write
from alpha.areas import PRODUCT_AREAS
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.generate import load_project_principles
from alpha.gitops import commit
from alpha.recipes import record_proof

GenerateScenario = Callable[[Path, str], list[str]]

SCENARIOS = PLUGIN_ROOT / "tests" / "fixtures" / "scenarios"
SHIM = PLUGIN_ROOT / "bin" / "alpha"
TODAY = date(2026, 10, 19)


def install(target: Path, today: date = TODAY) -> list[str]:
    """`alpha apply` on a folder that holds finished answers: what it wrote."""
    p = plan(target, PLUGIN_ROOT, Source(PLUGIN_ROOT, True), today)
    write(target, p)
    return sorted({*(c.path for c in p.changes), PROJECT_JSON})


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


def setup_only(data: dict[str, Any]) -> None:
    """Answers as install leaves them: every product area open."""
    for area in PRODUCT_AREAS:
        data["areas"][area] = "open"
        data.pop(area, None)
    data["overrides"] = []


def generated_repo(
    tmp_path: Path,
    scenario: str,
    edit: Callable[[dict[str, Any]], None] | None = None,
) -> Path:
    path = place_answers(tmp_path, scenario)
    if edit is not None:
        data = json.loads(path.read_text())
        edit(data)
        path.write_text(json.dumps(data))
    install(tmp_path)
    commit(tmp_path, load_project_principles(tmp_path), [])
    return tmp_path


def clone_component(data: dict[str, Any], source: str, name: str, path: str) -> None:
    comp = next(c for c in data["components"] if c["name"] == source)
    data["components"].append({**copy.deepcopy(comp), "name": name, "path": path})
    for section in data.values():
        if not isinstance(section, dict):
            continue
        entries: object = cast(dict[str, Any], section).get("components")
        if not isinstance(entries, list):
            continue
        listed = cast(list[dict[str, Any]], entries)
        for entry in list(listed):
            if entry.get("name") == source:
                listed.append({**copy.deepcopy(entry), "name": name})
    if name not in data["git"]["scopes"]:
        data["git"]["scopes"].append(name)
    data["layout"] = "monorepo"


def place_rust_monorepo(
    target: Path, workspace: bool | None = None, **testing: object
) -> Path:
    """The rust-cli scenario as a monorepo: the Rust components `cli` and
    `core`, and the Python component `api`. `workspace` sets the components
    answer of that name; `testing` sets answers of the testing area."""
    answers = place_answers(target, "rust-cli")
    data = json.loads(answers.read_text())
    data["components"][0]["path"] = "cli"
    clone_component(data, "cli", "core", "core")
    clone_component(data, "cli", "api", "api")
    data["components"][2]["stack"] = "python"
    data["testing"].update(testing)
    if workspace is not None:
        data["workspace"] = workspace
    answers.write_text(json.dumps(data))
    return answers


def uv_python(version: str) -> str:
    """An interpreter of `version`: uv finds an installed one or downloads it
    once."""
    done = subprocess.run(
        [
            "uv",
            "run",
            "--python",
            version,
            "--no-project",
            "python",
            "-c",
            "import sys; print(sys.executable)",
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def old_python() -> str:
    """Python 3.9, older than alpha supports: the shim and the hooks still
    parse on it, so they can say which Python alpha needs."""
    return uv_python("3.9")


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


def prove(target: Path) -> None:
    """What `alpha recipe try` records for each drafted recipe in the
    project's answers once it passes: its proof, in local state."""
    data = json.loads((target / PROJECT_JSON).read_text())
    for stack, fields in data.get("recipes", {}).items():
        record_proof(target, stack, fields)


# --- an existing repo to adopt ---

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
    data["recipes"] = {"ml-python": {"adopted": True, "extends": "python"}}
    data["adoption"] = {"git_hooks": "alpha", **adoption}
    path = target / ".claude" / "alpha" / "project.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    prove(target)
    return data


# --- a seeded violation per repository check ---


def _aws_key_pair(_: str | None) -> str:
    # Random, so the scanner can't skip it as a well-known example key.
    key_id = "AKIA" + "".join(
        secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(16)
    )
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789/+"
    secret = "".join(secrets.choice(alphabet) for _ in range(40))
    return f"# Deploy\n\nAWS_ACCESS_KEY_ID={key_id}\nAWS_SECRET_ACCESS_KEY={secret}\n"


def _append(extra: str) -> Callable[[str | None], str]:
    return lambda text: (text or "") + extra


# check id -> (registry tool, the file it changes, how it changes it, what the
# failing output says: proof that the tool found the seed rather than crashed)
REPO_SEEDS: dict[str, tuple[str, str, Callable[[str | None], str], str]] = {
    "actions": (
        "jactionlint",
        ".github/workflows/ci.yml",
        lambda text: re.sub(r"@[0-9a-f]{40}", "@v7", text or "", count=1),
        'action "actions/checkout@v7" must be pinned',
    ),
    # betterleaks names no file without --verbose, only the count.
    "secrets": ("betterleaks", "docs/x.md", _aws_key_pair, "leaks found: 1"),
    "typos": ("typos", "README.md", _append("\nteh\n"), "`teh` should be `the`"),
    "markdown": (
        "rumdl",
        "docs/x.md",
        lambda _: "# Notes\n\n### Skips a level\n\nText.\n",
        "docs/x.md:3:1: [MD001]",
    ),
    "links": (
        "lychee",
        "README.md",
        _append("\nSee [notes](docs/missing.md).\n"),
        "docs/missing.md (at ",
    ),
    "agent-config": (
        "agnix",
        ".claude/agents/committer.md",
        lambda text: (text or "").replace("model: inherit\n", "model: [inherit\n", 1),
        "committer.md:5:8 error: Failed to parse agent frontmatter",
    ),
}
