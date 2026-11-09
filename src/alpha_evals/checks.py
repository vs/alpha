import hashlib
import json
import os
import re
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from alpha.answers import PROJECT_JSON
from alpha.generate import PRINCIPLES_TOML
from alpha_evals.scenario import Brief, compare

Status = Literal["pass", "warn", "fail", "skip"]
SETTINGS = ".claude/settings.json"
COMMIT_MSG = ".claude/alpha/githooks/commit-msg"
HOOKS_PATH = ".claude/alpha/githooks"
REQUIRED = (
    "CLAUDE.md",
    PRINCIPLES_TOML,
    SETTINGS,
    PROJECT_JSON,
    COMMIT_MSG,
    ".claude/skills/commit/SKILL.md",
    ".claude/agents/committer.md",
    ".claude/agents/principles-reviewer.md",
)
HOOK_SCRIPT = re.compile(r'"\$CLAUDE_PROJECT_DIR"/(\S+\.py)')


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    detail: str = ""

    def to_json(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


class _Unreadable(Exception):
    pass


def _verdict(name: str, problems: list[str]) -> Check:
    return Check(name, "fail", "\n".join(problems)) if problems else Check(name, "pass")


def _json(project: Path, rel: str) -> dict[str, Any]:
    try:
        data = json.loads((project / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise _Unreadable(f"{rel}: can't be read ({e})") from None
    if not isinstance(data, dict):
        raise _Unreadable(f"{rel}: not a JSON object")
    return cast(dict[str, Any], data)


def _toml(project: Path, rel: str) -> dict[str, Any]:
    try:
        return tomllib.loads((project / rel).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise _Unreadable(f"{rel}: can't be read ({e})") from None


def _git(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=project, capture_output=True, text=True)


def check_answers(project: Path, brief: Brief) -> Check:
    try:
        actual = _json(project, PROJECT_JSON)
    except _Unreadable as e:
        return Check("answers", "fail", str(e))
    problems: list[str] = []
    areas: object = actual.get("areas")
    if not isinstance(areas, dict) or not areas:
        problems.append("no areas recorded")
    else:
        for area, state in cast(dict[str, Any], areas).items():
            if state != "done":
                problems.append(f"area {area} is {state}")
    for m in compare(brief.answers, actual, brief.expect):
        got = "nothing" if m.missing else json.dumps(m.actual)
        problems.append(f"{m.pointer}: expected {json.dumps(m.expected)}, got {got}")
    return _verdict("answers", problems)


def hook_scripts(settings: dict[str, Any]) -> list[str]:
    found: list[str] = []
    hooks: object = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        return found
    for entries in cast(dict[str, Any], hooks).values():
        for entry in cast(list[dict[str, Any]], entries):
            for hook in cast(list[dict[str, Any]], entry.get("hooks", [])):
                found += HOOK_SCRIPT.findall(str(hook.get("command", "")))
    return found


def check_files(project: Path) -> Check:
    problems = [f"{rel}: missing" for rel in REQUIRED if not (project / rel).is_file()]
    try:
        settings = _json(project, SETTINGS)
        problems += [
            f"{rel}: missing (a hook runs it)"
            for rel in hook_scripts(settings)
            if not (project / rel).is_file()
        ]
    except _Unreadable as e:
        problems.append(str(e))
    try:
        files = cast(dict[str, str], _json(project, PROJECT_JSON)["manifest"]["files"])
        for rel, digest in files.items():
            path = project / rel
            if not path.is_file():
                problems.append(f"{rel}: missing (generated)")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                problems.append(f"{rel}: changed since generation")
    except _Unreadable as e:
        problems.append(str(e))
    except (KeyError, TypeError):
        problems.append(f"{PROJECT_JSON}: no manifest (was the project generated?)")
    tracked = _git(project, "ls-files").stdout.splitlines()
    problems += [
        f"{rel}: app code in the skeleton"
        for rel in tracked
        if rel.startswith("src/") or "/src/" in rel
    ]
    return _verdict("files", problems)


def check_settings(project: Path) -> Check:
    problems: list[str] = []
    try:
        if not isinstance(_json(project, SETTINGS).get("hooks"), dict):
            problems.append(f"{SETTINGS}: no hooks object")
    except _Unreadable as e:
        problems.append(str(e))
    try:
        components: object = _toml(project, PRINCIPLES_TOML).get("components")
        if not isinstance(components, list) or not components:
            problems.append(f"{PRINCIPLES_TOML}: no [[components]]")
        else:
            for c in cast(list[dict[str, Any]], components):
                commands = cast(dict[str, Any], c.get("commands", {}))
                for step in ("setup", "test"):
                    if not commands.get(step):
                        problems.append(f"{c.get('name')}: no {step} command")
    except _Unreadable as e:
        problems.append(str(e))
    return _verdict("settings", problems)


def _rejection(project: Path, message: str) -> str | None:
    with tempfile.NamedTemporaryFile("w", suffix=".msg", delete=False) as f:
        f.write(message)
    try:
        done = subprocess.run(
            [str(project / COMMIT_MSG), f.name],
            cwd=project,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
            capture_output=True,
            text=True,
        )
    finally:
        os.unlink(f.name)
    if done.returncode == 0:
        return None
    lines = (done.stderr or done.stdout).strip().splitlines()
    return lines[0] if lines else f"exit {done.returncode}"


def check_commits(project: Path) -> Check:
    log = _git(project, "log", "--format=%h%x1f%B%x00")
    if log.returncode != 0 or not log.stdout.strip():
        return Check("commits", "fail", "no commits")
    problems: list[str] = []
    if not (project / COMMIT_MSG).is_file():
        problems.append(f"{COMMIT_MSG}: missing, so messages can't be checked")
    else:
        for record in log.stdout.split("\x00"):
            if not record.strip():
                continue
            sha, message = record.strip("\n").split("\x1f", 1)
            why = _rejection(project, message)
            if why is not None:
                subject = message.strip().splitlines()[0]
                problems.append(f"{sha} {subject}: {why}")
    porcelain = _git(project, "status", "--porcelain").stdout.strip()
    if porcelain:
        problems.append(f"uncommitted changes: {porcelain}")
    branch = _git(project, "branch", "--show-current").stdout.strip()
    if branch != "main":
        problems.append(f"branch is {branch or 'detached'}, not main")
    hooks_path = _git(project, "config", "core.hooksPath").stdout.strip()
    if hooks_path != HOOKS_PATH:
        problems.append(f"core.hooksPath is {hooks_path or 'unset'}, not {HOOKS_PATH}")
    return _verdict("commits", problems)
