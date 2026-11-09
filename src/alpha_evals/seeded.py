"""Seeded violations for the generated hooks, and the components' own checks."""

import fnmatch
import json
import os
import re
import secrets
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.generate import PRINCIPLES_TOML, GenerateError, load_project_principles
from alpha.recipes import check_commands as ci_steps
from alpha.registry import RegistryError, load_registry
from alpha_evals.checks import SETTINGS, Check

EDIT_MATCHER = "Edit|Write|MultiEdit"
HOOK_TIMEOUT = 1200.0  # the generated settings' longest hook timeout
COMMAND_TIMEOUT = 900.0  # per CI step
_TAIL = 5


def _parts_match(path: list[str], pat: list[str]) -> bool:
    # The hooks' own glob semantics (_common.matches): ** spans folders.
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
    """A source file of the component that no test glob matches."""
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
        """Run every hook wired to the event and matcher; [] if none is."""
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
        return lines[0]  # timed out
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
    """Feed the project's hooks seeded violations, in a copy of the project."""
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
    """Every component's CI checks, in CI order, in the project itself."""
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


def _seed_problem(project: Path, check: str, fails_with: int) -> str | None:
    _, rel, change, says = REPO_SEEDS[check]
    path = project / rel
    before = path.read_bytes() if path.exists() else None
    after = change(before.decode("utf-8") if before is not None else None)
    if before is not None and after.encode("utf-8") == before:
        return f"{check}: the seed changed nothing in {rel}"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(after, encoding="utf-8")
        done = subprocess.run(
            ["mise", "run", f"check:{check}"],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return f"{check}: timed out after {COMMAND_TIMEOUT:g}s"
    finally:
        if before is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(before)
    output = done.stdout + done.stderr
    if done.returncode != fails_with:
        tail = " | ".join(output.strip().splitlines()[-_TAIL:])
        return (
            f"{check}: expected exit {fails_with} on the seed, "
            f"got {done.returncode}: {tail}"
        )
    if says not in output:
        return f"{check}: exit {fails_with}, but the output doesn't say {says!r}"
    return None


def check_repo_seeds(project: Path) -> Check:
    """Each repository check fails, readably, on its seeded violation."""
    if shutil.which("mise") is None:
        return Check("repo-seeds", "fail", "mise is not installed")
    try:
        registry = load_registry(Source(PLUGIN_ROOT, True, ""))
        codes = {c: registry.tool(t[0]).pin for c, t in REPO_SEEDS.items()}
    except RegistryError as e:
        return Check("repo-seeds", "fail", str(e))
    problems: list[str] = []
    for check, pin in codes.items():
        if pin is None:
            problems.append(f"{check}: its registry tool has no pin")
            continue
        found = _seed_problem(project, check, pin.fails_with)
        if found:
            problems.append(found)
    return (
        Check("repo-seeds", "fail", "\n".join(problems))
        if problems
        else Check("repo-seeds", "pass")
    )
