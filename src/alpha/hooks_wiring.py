"""Switching alpha's hooks off and back on (rewrite spec, R1.4, R2.1, R2.2).

Neither direction deletes a file or commits. `uninstall` takes alpha's hook
entries out of .claude/settings.json and alpha's commit-msg hook out of git:
it unsets core.hooksPath when that is alpha's, or, where the repo's own hook
manager runs git's hooks, moves alpha's marked call out of that manager's
commit-msg file into local state. `hooks_on` puts each back.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from alpha.generate import GenerateError
from alpha.gitops import set_hooks_path, unset_hooks_path
from alpha.merge import merge_settings, strip_alpha_hooks
from alpha.render.claude_settings import alpha_hooks
from alpha.render.docs import CHAIN_BEGIN, CHAIN_END, CHAINED_COMMIT_MSG
from alpha.status import CHAIN_STATE, HOOKS_PATH, SETTINGS, git_output, read_answers

HOOKS_STATE = ".claude/alpha/state/hooks.json"


@dataclass(frozen=True)
class HookFile:
    """git's commit-msg hook file, where a hook manager calls alpha's check."""

    path: Path
    rel: str


def _installed(target: Path, command: str) -> dict[str, Any]:
    answers = read_answers(target)
    if answers is None or "installed" not in answers:
        raise GenerateError(
            f"alpha isn't installed in {target}, so it has no hooks to switch. "
            f'Run "alpha {command} <project>" on a folder alpha installed.'
        )
    return answers


def _chained(answers: dict[str, Any]) -> bool:
    adoption: object = answers.get("adoption")
    return (
        isinstance(adoption, dict)
        and cast(dict[str, Any], adoption).get("git_hooks") == "chain"
    )


def _commit_msg_hook(target: Path) -> HookFile:
    hooks = Path(git_output(target, "rev-parse", "--git-path", "hooks") or ".git/hooks")
    hook = (hooks if hooks.is_absolute() else target / hooks) / "commit-msg"
    try:
        rel = hook.resolve().relative_to(target.resolve()).as_posix()
    except ValueError:
        rel = str(hook)
    return HookFile(hook, rel)


def _settings(target: Path, command: str) -> dict[str, object]:
    try:
        data: object = json.loads((target / SETTINGS).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise GenerateError(
            f"{target / SETTINGS} isn't a JSON object, so alpha can't find its hook "
            f'entries in it. Fix its JSON, then rerun "alpha {command}".'
        )
    return dict(cast(dict[str, object], data))


def _write_settings(target: Path, settings: dict[str, object]) -> None:
    (target / SETTINGS).parent.mkdir(parents=True, exist_ok=True)
    (target / SETTINGS).write_text(json.dumps(settings, indent=2) + "\n")


def _settings_off(target: Path) -> bool:
    """Take alpha's hook entries out, keeping the hooks table they were in so
    `hooks on` can put it back as it was."""
    settings = _settings(target, f"uninstall {target}")
    if "hooks" not in settings:
        return False
    hooks = strip_alpha_hooks(settings["hooks"])
    if hooks == settings["hooks"]:
        return False
    state = target / HOOKS_STATE
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"before": settings["hooks"], "after": hooks}))
    _write_settings(target, {**settings, "hooks": hooks})
    return True


def _settings_on(target: Path) -> bool:
    """Put alpha's hook entries back: the hooks table uninstall replaced when
    nobody changed the file since, else alpha's entries merged into it."""
    settings = _settings(target, f"hooks on {target}")
    state = target / HOOKS_STATE
    try:
        saved: object = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = None
    record = cast(dict[str, object], saved) if isinstance(saved, dict) else {}
    if "before" in record and settings.get("hooks") == record.get("after"):
        restored = {**settings, "hooks": record["before"]}
    else:
        merged = merge_settings(
            json.dumps(settings), json.dumps({"hooks": alpha_hooks()}), None
        )
        assert merged is not None  # settings is a JSON object
        restored = cast(dict[str, object], json.loads(merged[0]))
    state.unlink(missing_ok=True)
    if restored == settings:
        return False
    _write_settings(target, restored)
    return True


def _chain_off(target: Path) -> list[str]:
    """Move alpha's marked call out of the hook manager's file into state."""
    if (target / CHAIN_STATE).is_file():
        return []
    hook = _commit_msg_hook(target)
    try:
        lines = hook.path.read_text(encoding="utf-8").splitlines(keepends=True)
    except FileNotFoundError:
        return []
    stripped = [line.strip() for line in lines]
    if CHAIN_BEGIN in stripped and CHAIN_END in stripped[stripped.index(CHAIN_BEGIN) :]:
        start = stripped.index(CHAIN_BEGIN)
        end = stripped.index(CHAIN_END, start)
        block = lines[start : end + 1]
        state = target / CHAIN_STATE
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(
            json.dumps({"path": hook.rel, "line": start, "lines": block}, indent=2)
        )
        hook.path.write_text("".join(lines[:start] + lines[end + 1 :]))
        return [f"took alpha's call out of {hook.rel}"]
    unmarked = [n for n, line in enumerate(stripped, 1) if CHAINED_COMMIT_MSG in line]
    if unmarked:
        return [
            f"left alpha's commit check in {hook.rel}: line {unmarked[0]} calls "
            f"it without the {CHAIN_BEGIN} and {CHAIN_END} lines around it. Remove "
            "that line by hand to switch it off."
        ]
    return []


def uninstall(target: Path) -> list[str]:
    """Switch alpha's hooks off; returns what was switched off."""
    answers = _installed(target, "uninstall")
    done: list[str] = []
    if _settings_off(target):
        done.append(f"removed alpha's hook entries from {SETTINGS}")
    if _chained(answers):
        done += _chain_off(target)
    elif git_output(target, "config", "--get", "core.hooksPath") == HOOKS_PATH:
        unset_hooks_path(target, "uninstall")
        done.append(f"unset core.hooksPath ({HOOKS_PATH})")
    return done


def _chain_on(target: Path) -> list[str]:
    state = target / CHAIN_STATE
    try:
        saved: object = json.loads(state.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except ValueError:
        saved = None
    record = cast(dict[str, Any], saved) if isinstance(saved, dict) else {}
    block, at, rel = record.get("lines"), record.get("line"), record.get("path")
    if not (isinstance(block, list) and isinstance(at, int) and isinstance(rel, str)):
        raise GenerateError(
            f"{state} doesn't hold alpha's chained call as uninstall saved it. Add "
            f"{CHAIN_BEGIN}, {CHAINED_COMMIT_MSG} and {CHAIN_END} as three lines to "
            "your hook manager's commit-msg hook, delete that file, then rerun "
            f'"alpha hooks on {target}".'
        )
    path = target / rel
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except FileNotFoundError:
        raise GenerateError(
            f"{path} is gone, so alpha can't put its commit check back into it. "
            "Set your hook manager's commit-msg hook up again, then rerun "
            f'"alpha hooks on {target}".'
        ) from None
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    at = min(at, len(lines))
    saved_lines = [str(line) for line in cast(list[object], block)]
    path.write_text("".join(lines[:at] + saved_lines + lines[at:]))
    state.unlink()
    return [f"put alpha's call back into {rel}"]


def hooks_on(target: Path) -> list[str]:
    """Switch alpha's hooks back on; returns what was switched on."""
    answers = _installed(target, "hooks on")
    done: list[str] = []
    if _settings_on(target):
        done.append(f"put alpha's hook entries back into {SETTINGS}")
    if _chained(answers):
        done += _chain_on(target)
    elif git_output(target, "config", "--get", "core.hooksPath") != HOOKS_PATH:
        set_hooks_path(target, "hooks on")
        done.append(f"set core.hooksPath to {HOOKS_PATH}")
    return done
