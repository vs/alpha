import fnmatch
import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from alpha.generate import PRINCIPLES_TOML, GenerateError, load_project_principles
from alpha.recipes import check_commands as ci_steps
from alpha_evals.checks import SETTINGS, Check

EDIT_MATCHER = "Edit|Write|MultiEdit"
HOOK_TIMEOUT = 1200.0
COMMAND_TIMEOUT = 900.0
_TAIL = 5


def _parts_match(path: list[str], pat: list[str]) -> bool:
    if not pat:
        return not path
    if pat[0] == "**":
        return any(_parts_match(path[k:], pat[1:]) for k in range(len(path) + 1))
    if not path:
        return False
    return fnmatch.fnmatchcase(path[0], pat[0]) and _parts_match(path[1:], pat[1:])


def _matches(rel: str, globs: list[str]) -> bool:
    return any(_parts_match(rel.split("/"), g.split("/")) for g in globs)


def seed_source_path(component: Mapping[str, Any]) -> str:
    sources = [str(g) for g in component.get("source_globs", [])]
    tests = [str(g) for g in component.get("test_globs", [])]
    for glob in sources:
        rel = glob.replace("**/", "").replace("*", "eval_seed")
        if _matches(rel, sources) and not _matches(rel, tests):
            return rel
    raise ValueError(f"no source path for component {component.get('name')}")


def _in(component: Mapping[str, Any], name: str) -> str:
    path = str(component["path"])
    return name if path == "." else f"{path}/{name}"


def _keeps(principles: dict[str, Any], principle: str, component: str) -> bool:
    for p in cast(list[dict[str, Any]], principles.get("principles", [])):
        if p.get("id") == principle:
            return bool(p.get("active")) and component in p.get("components", [])
    return False


class _Hooks:
    def __init__(self, root: Path) -> None:
        self.root = root
        settings = json.loads((root / SETTINGS).read_text(encoding="utf-8"))
        self.hooks = cast(dict[str, list[dict[str, Any]]], settings.get("hooks", {}))

    def run(
        self, event: str, matcher: str | None, payload: dict[str, Any]
    ) -> list[subprocess.CompletedProcess[str]]:
        done: list[subprocess.CompletedProcess[str]] = []
        for entry in self.hooks.get(event, []):
            if entry.get("matcher") != matcher:
                continue
            for hook in cast(list[dict[str, Any]], entry.get("hooks", [])):
                command = str(hook["command"])
                try:
                    done.append(
                        subprocess.run(
                            command,
                            shell=True,
                            cwd=self.root,
                            env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)},
                            input=json.dumps(payload),
                            capture_output=True,
                            text=True,
                            timeout=HOOK_TIMEOUT,
                        )
                    )
                except subprocess.TimeoutExpired:
                    done.append(
                        subprocess.CompletedProcess(
                            command, -1, "", f"timed out after {HOOK_TIMEOUT:g}s"
                        )
                    )
        return done


def _got(runs: list[subprocess.CompletedProcess[str]]) -> str:
    if not runs:
        return "no hook wired"
    last = runs[-1]
    lines = (last.stderr or last.stdout).strip().splitlines()
    if last.returncode == -1:
        return lines[0]
    return f"exit {last.returncode}: {lines[0] if lines else '(no output)'}"


def _blocked(runs: list[subprocess.CompletedProcess[str]]) -> bool:
    return any(r.returncode == 2 for r in runs)


def _asked(runs: list[subprocess.CompletedProcess[str]]) -> bool:
    for r in runs:
        try:
            out = json.loads(r.stdout)
            if out["hookSpecificOutput"]["permissionDecision"] == "ask":
                return True
        except (ValueError, KeyError, TypeError):
            continue
    return False


def _stop_reason(runs: list[subprocess.CompletedProcess[str]]) -> str | None:
    for r in runs:
        try:
            out: object = json.loads(r.stdout)
        except ValueError:
            continue
        if isinstance(out, dict):
            fields = cast(dict[str, Any], out)
            if fields.get("decision") == "block":
                return str(fields.get("reason", ""))
    return None


def check_hooks(project: Path, scratch: Path) -> Check:
    copy = scratch / "hooks-copy"
    if copy.exists():
        shutil.rmtree(copy)
    shutil.copytree(project, copy, symlinks=True)
    try:
        hooks = _Hooks(copy)
        principles = load_project_principles(copy)
    except (OSError, ValueError, KeyError, GenerateError) as e:
        return Check("hooks", "fail", f"can't read the hook wiring: {e}")
    components = cast(list[dict[str, Any]], principles["components"])
    first = components[0]
    problems: list[str] = []
    hooks.run("SessionStart", None, {"source": "startup"})

    def write(rel: str, content: str = "") -> dict[str, Any]:
        return {
            "tool_name": "Write",
            "tool_input": {"file_path": str(copy / rel), "content": content},
        }

    no_verify = {
        "tool_name": "Bash",
        "tool_input": {"command": "git commit --no-verify -m x"},
    }
    runs = hooks.run("PreToolUse", "Bash", no_verify)
    if not _blocked(runs):
        problems.append(
            f"1. git commit --no-verify: expected a block, got {_got(runs)}"
        )

    env_file = _in(first, ".env")
    runs = hooks.run("PreToolUse", EDIT_MATCHER, write(env_file, "KEY=1\n"))
    if not _blocked(runs):
        problems.append(f"2. write {env_file}: expected a block, got {_got(runs)}")

    seeds = {c["name"]: seed_source_path(c) for c in components}
    weak = seeds[first["name"]]
    runs = hooks.run("PreToolUse", EDIT_MATCHER, write(weak, "x = 1  # type: ignore\n"))
    if not _asked(runs):
        problems.append(
            f"3. # type: ignore in {weak}: expected an ask, got {_got(runs)}"
        )

    for rel in seeds.values():
        path = copy / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n", encoding="utf-8")
        hooks.run("PostToolUse", EDIT_MATCHER, write(rel, "x = 1\n"))
    runs = hooks.run("Stop", None, {"stop_hook_active": False})
    reason = _stop_reason(runs)
    expected = [n for n in seeds if _keeps(principles, "tests-first-class", n)]
    if expected and reason is None:
        problems.append(f"4. untested source files: expected a block, got {_got(runs)}")
    for name in expected:
        if reason is not None and f"{name}: source changed" not in reason:
            problems.append(
                f"4. untested {seeds[name]}: expected the Stop reason to name it, "
                f"got: {reason.splitlines()[0] if reason else '(empty)'}"
            )
    return (
        Check("hooks", "fail", "\n".join(problems))
        if problems
        else Check("hooks", "pass")
    )


def check_commands(project: Path) -> Check:
    try:
        principles = load_project_principles(project)
    except GenerateError as e:
        return Check("commands", "fail", f"{PRINCIPLES_TOML}: {e}")
    problems: list[str] = []
    for c in cast(list[dict[str, Any]], principles["components"]):
        for _, command in ci_steps(cast(dict[str, str], c.get("commands", {}))):
            try:
                done = subprocess.run(
                    command,
                    shell=True,
                    cwd=project / str(c["path"]),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=COMMAND_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                problems.append(
                    f'{c["name"]}: "{command}" timed out after {COMMAND_TIMEOUT:g}s'
                )
                break
            if done.returncode != 0:
                tail = " | ".join(done.stdout.strip().splitlines()[-_TAIL:])
                problems.append(
                    f'{c["name"]}: "{command}" failed (exit {done.returncode}): {tail}'
                )
                break
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"], cwd=project, capture_output=True, text=True
    ).stdout.strip()
    if porcelain:
        problems.append(f"checks left changes: {porcelain}")
    return (
        Check("commands", "fail", "\n".join(problems))
        if problems
        else Check("commands", "pass")
    )
