"""PreToolUse hook for Bash: blocks --no-verify, hooksPath changes, force-push and
pushed amends."""

from __future__ import annotations

import posixpath
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _common  # noqa: E402

NO_VERIFY_MESSAGE = (
    "--no-verify skips the project's commit checks. Fix what the hook reports "
    "instead; if the hook itself is wrong, tell the user."
)
SKIPPING = {"commit", "push", "merge", "rebase", "cherry-pick"}
GLOBAL_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
COMMIT_VALUE_FLAGS = {"-m", "-F", "-C", "-c", "-t", "--message", "--file", "--template"}
COMMIT_VALUE_LETTERS = "mFCct"
HOOKS_PATH_MESSAGE = (
    "Overriding core.hooksPath skips the project's commit checks. Fix what the "
    "hook reports instead; if the hook itself is wrong, tell the user."
)
HOOKS_CONFIG_MESSAGE = (
    "Changing core.hooksPath switches off the project's commit checks. Keep it "
    "at .claude/alpha/githooks; if the hook itself is wrong, tell the user."
)
HOOKS_PATH = ".claude/alpha/githooks"
CONFIG_READS = {"--get", "--get-all", "--get-regexp", "--list", "-l", "get", "list"}
CONFIG_UNSETS = {"--unset", "--unset-all", "unset"}
# Commands that run another command, with their options that take a value.
WRAPPERS: dict[tuple[str, ...], set[str]] = {
    ("uv", "run"): {
        "--with",
        "--with-editable",
        "--with-requirements",
        "--project",
        "--directory",
        "--python",
        "-p",
        "--package",
        "--group",
        "--extra",
        "--env-file",
        "--index",
    },
    ("pnpm", "exec"): {"--filter", "-F", "--dir", "-C"},
    ("npx",): {"--package", "-p"},
    ("nohup",): set(),
    ("xargs",): {"-I", "-n", "-L", "-P", "-d", "-E", "-s", "-a"},
}
SHELLS = {"sh", "bash", "zsh"}
SHELL_KEYWORDS = {"then", "do", "else", "elif", "!", "time", "if", "while", "until"}
MAX_DEPTH = 2
ENV_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


def _newlines_to_semicolons(command: str) -> str:
    """Replace newlines outside quotes with `;` so they split segments."""
    out: list[str] = []
    quote = ""
    escaped = False
    for ch in command:
        if escaped:
            escaped = False
        elif ch == "\\" and quote != "'":
            escaped = True
        elif quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "\n":
            ch = ";"
        out.append(ch)
    return "".join(out)


def split_segments(command: str) -> list[list[str]] | None:
    """Token lists per `&&`/`||`/`;`/`|`/newline segment; None if unparseable."""
    command = command.replace("\\\n", "")  # line continuations
    lexer = shlex.shlex(
        _newlines_to_semicolons(command), posix=True, punctuation_chars=True
    )
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    segments: list[list[str]] = [[]]
    for token in tokens:
        if set(token) <= set("&|;()") or token in ("{", "}"):
            segments.append([])
        else:
            segments[-1].append(token)
    return [s for s in segments if s]


def skip_wrapper(segment: list[str], i: int) -> int:
    """Index of the wrapped command if segment[i:] starts with a wrapper, else i."""
    for words, valued in WRAPPERS.items():
        head = segment[i : i + len(words)]
        if not head or posixpath.basename(head[0]) != words[0]:
            continue
        if head[1:] != list(words[1:]):
            continue
        j = i + len(words)
        while j < len(segment) and segment[j].startswith("-"):
            if segment[j] == "--":
                return j + 1
            j += 2 if segment[j] in valued else 1
        return j
    return i


def strip_prefix(segment: list[str]) -> list[str]:
    """Drop leading keywords, env assignments and wrappers (env, uv run, xargs…)."""
    i = 0
    after_env = False
    while i < len(segment):
        tok = segment[i]
        wrapped = skip_wrapper(segment, i)
        if wrapped != i:
            i, after_env = wrapped, False
            continue
        if tok == "env":
            after_env = True
        elif tok in SHELL_KEYWORDS or tok in ("command", "exec"):
            after_env = False
        elif ENV_ASSIGNMENT.match(tok) or (after_env and tok.startswith("-")):
            pass
        else:
            break
        i += 1
    return segment[i:]


def git_invocation(segment: list[str]) -> tuple[str, list[str], bool] | None:
    """(subcommand, args after it, core.hooksPath overridden) for a git segment."""
    if not segment or posixpath.basename(segment[0]) != "git":
        return None
    hooks_override = False
    i = 1
    while i < len(segment) and segment[i].startswith("-"):
        arg = segment[i]
        if arg == "-c" and i + 1 < len(segment):
            config = segment[i + 1]
        elif arg.startswith("-c") and not arg.startswith("--"):
            config = arg[2:]
        else:
            config = ""
        if config.lower().startswith("core.hookspath"):
            hooks_override = True
        i += 2 if arg in GLOBAL_OPTIONS_WITH_VALUE else 1
    if i >= len(segment):
        return None
    return segment[i], segment[i + 1 :], hooks_override


def shell_script(segment: list[str]) -> str | None:
    """The script string of `sh -c "…"` / `eval "…"`, if the segment is one."""
    if not segment:
        return None
    name = posixpath.basename(segment[0])
    if name == "eval":
        return " ".join(segment[1:]) or None
    if name in SHELLS:
        for k, arg in enumerate(segment[1:], start=1):
            is_flag = arg.startswith("-") and not arg.startswith("--")
            if is_flag and arg.endswith("c") and k + 1 < len(segment):
                return segment[k + 1]
    return None


def option_args(sub: str, args: list[str]) -> list[str]:
    """Args before `--`, minus the values of commit's value-taking flags."""
    kept: list[str] = []
    skip = False
    for arg in args:
        if skip:
            skip = False
        elif arg == "--":
            break
        else:
            kept.append(arg)
            skip = sub == "commit" and arg in COMMIT_VALUE_FLAGS
    return kept


def short_flags(arg: str, sub: str) -> str:
    """Letters of a short-flag cluster, up to a flag that takes a value."""
    if not arg.startswith("-") or arg.startswith("--") or len(arg) < 2:
        return ""
    letters = arg[1:]
    if sub == "commit":
        for k, ch in enumerate(letters):
            if ch in COMMIT_VALUE_LETTERS:
                return letters[: k + 1]
    return letters


def pushed_branches(root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "branch", "-r", "--contains", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    if proc.returncode != 0:
        return ""
    return ", ".join(line.strip() for line in proc.stdout.splitlines() if line.strip())


def check_command(command: str, root: Path, depth: int = 0) -> None:
    segments = split_segments(command)
    if segments is None:
        return
    for segment in segments:
        segment = strip_prefix(segment)
        script = shell_script(segment)
        if script is not None and depth < MAX_DEPTH:
            check_command(script, root, depth + 1)
        check_segment(segment, root)


def changes_hooks_path(args: list[str]) -> bool:
    """Whether `git config <args>` sets or unsets core.hooksPath elsewhere."""
    keys = [k for k, arg in enumerate(args) if arg.lower() == "core.hookspath"]
    if not keys:
        return False
    before = set(args[: keys[0]])
    if before & CONFIG_UNSETS:
        return True
    values = [a for a in args[keys[0] + 1 :] if not a.startswith("-")]
    if before & CONFIG_READS or not values:
        return False
    return values[0].rstrip("/").removeprefix("./") != HOOKS_PATH


def check_segment(segment: list[str], root: Path) -> None:
    invocation = git_invocation(segment)
    if invocation is None:
        return
    sub, raw_args, hooks_override = invocation
    if sub == "config" and changes_hooks_path(raw_args):
        _common.block(HOOKS_CONFIG_MESSAGE)
    args = option_args(sub, raw_args)
    if hooks_override and sub in SKIPPING:
        _common.block(HOOKS_PATH_MESSAGE)
    if sub in SKIPPING:
        if "--no-verify" in args:
            _common.block(NO_VERIFY_MESSAGE)
        if sub == "commit" and any("n" in short_flags(a, sub) for a in args):
            _common.block(NO_VERIFY_MESSAGE)
    if sub == "push":
        for arg in args:
            forced = (
                arg in ("--force", "--force-if-includes")
                or arg.startswith("--force-with-lease")
                or (len(arg) > 1 and arg.startswith("+"))
                or "f" in short_flags(arg, sub)
            )
            if forced:
                _common.block(
                    f"git push {arg} can overwrite history on the remote. Push "
                    "normally after making a new commit instead, or ask the user "
                    "to run the forced push themselves."
                )
    if sub == "commit" and "--amend" in args:
        branches = pushed_branches(root)
        if branches:
            _common.block(
                f"HEAD is already pushed ({branches}); amending rewrites shared "
                "history. Make a new commit instead."
            )


def main() -> None:
    _common.check_python()
    inp = _common.read_input()
    root = _common.project_root(inp)
    if _common.load_principles(root) is None:
        sys.exit(0)
    if inp.get("tool_name") != "Bash":
        sys.exit(0)
    tool_input: object = inp.get("tool_input")
    command: object = None
    if isinstance(tool_input, dict):
        command = tool_input.get("command")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if not isinstance(command, str):
        sys.exit(0)
    check_command(command, root)
    sys.exit(0)


if __name__ == "__main__":
    main()
