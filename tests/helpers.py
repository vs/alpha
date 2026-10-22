"""Plain helpers shared by the generator tests (fixtures live in conftest.py)."""

import ast
import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

from alpha.cli import PLUGIN_ROOT

SCENARIOS = PLUGIN_ROOT / "evals" / "scenarios"
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


def old_python() -> str | None:
    """A python3 older than 3.11 on this machine (e.g. stock macOS), if any."""
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
    """Reduce answers to one component, with every per-component area in step."""
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


def override_record(data: dict[str, Any], principle: str, index: int = 0) -> str:
    """The decision record path of the index-th override, numbered after the areas'."""
    number = len(data["decisions"]) + index + 1
    return f"docs/decisions/{number:04d}-override-{principle}.md"
