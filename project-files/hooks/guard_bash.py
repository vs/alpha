from __future__ import annotations

import glob as globlib
import posixpath
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
import _common  # noqa: E402
import review  # noqa: E402

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


# A heredoc operator (<<WORD, <<-'WORD', <<"WORD"), but not a <<< here-string.
_HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")


def strip_heredocs(command: str) -> str:
    out: list[str] = []
    pending: list[tuple[str, bool]] = []
    for line in command.split("\n"):
        if pending:
            delimiter, tabs = pending[0]
            if (line.lstrip("\t") if tabs else line) == delimiter:
                pending.pop(0)
            continue
        out.append(line)
        pending = [(m.group(3), m.group(1) == "-") for m in _HEREDOC.finditer(line)]
    return "\n".join(out)


def _newlines_to_semicolons(command: str) -> str:
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
    command = strip_heredocs(command).replace("\\\n", "")  # line continuations
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
        if (token and set(token) <= set("&|;()")) or token in ("{", "}"):
            segments.append([])
        else:
            segments[-1].append(token)
    return [s for s in segments if s]


def skip_wrapper(segment: list[str], i: int) -> int:
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


REDIRECTS = (">>", ">|", ">")  # longest first; "&>" is "&" glued to ">"
SEPARATOR_CHARS = set("&|;()")
WRITES_LAST = {"cp", "install", "ln"}  # the last argument is written
WRITES_ALL = {"rm", "truncate", "tee", "mv"}  # mv removes its sources, too
NOT_FILES = {"", "-", "/dev/null", "/dev/stdout", "/dev/stderr"}
GLOB_CHARS = set("*?[")


def _redirect(token: str) -> str | None:
    for op in REDIRECTS:
        if token.endswith(op) and set(token[: -len(op)]) <= SEPARATOR_CHARS:
            return token[: -len(op)]
    return None


def redirect_segments(command: str) -> list[tuple[list[str], list[str]]]:
    """(words, redirect targets) per segment. Lexed without POSIX quote
    removal, so a quoted ">" (as in grep '>' f) stays a word, not a redirect;
    an escaped \\> and a comparison inside [[ ]] aren't redirects either."""
    command = _newlines_to_semicolons(strip_heredocs(command).replace("\\\n", ""))
    lexer = shlex.shlex(command, posix=False, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return []
    segments: list[tuple[list[str], list[str]]] = [([], [])]
    in_test = False
    for i, token in enumerate(tokens):
        glued = _redirect(token)
        if glued is None and token and set(token) <= SEPARATOR_CHARS:
            segments.append(([], []))
            continue
        if glued is None:
            in_test = (in_test or token == "[[") and token != "]]"
            segments[-1][0].append(token)
            continue
        if glued:
            segments.append(([], []))
        before = tokens[i - 1] if i > 0 else ""
        backslashes = len(before) - len(before.rstrip("\\"))
        escaped = not glued and backslashes % 2 == 1
        if in_test or escaped or i + 1 >= len(tokens):
            continue
        try:
            segments[-1][1].extend(shlex.split(tokens[i + 1]))
        except ValueError:
            continue
    return segments


def command_targets(segment: list[str]) -> list[str]:
    if not segment:
        return []
    name = posixpath.basename(segment[0])
    args = segment[1:]
    plain = [a for a in args if not a.startswith("-")]
    if name in WRITES_ALL:
        return plain
    if name in WRITES_LAST:
        return plain[-1:]
    short = [a[1:] for a in args if a.startswith("-") and not a.startswith("--")]
    in_place = (
        name == "sed"
        and (
            any("i" in a for a in short)
            or any(a.startswith("--in-place") for a in args)
        )
    ) or (name == "perl" and any("i" in a for a in short))
    if in_place:
        return plain[1:]  # the first plain argument is the script
    return []


def _cd(here: Path, words: list[str]) -> Path:
    args = words[1:]
    while args and args[0] in ("-P", "-L", "-e", "-@"):
        args = args[1:]
    if args and args[0] == "--":
        args = args[1:]
    if not args:
        return Path.home()
    if args[0].startswith("-"):
        return here
    return here / Path(args[0]).expanduser()


def _unquoted(words: list[str]) -> list[str]:
    out: list[str] = []
    for word in words:
        try:
            out += shlex.split(word) or [""]
        except ValueError:
            out.append(word)
    return out


def _files(here: Path, word: str) -> list[Path]:
    if GLOB_CHARS & set(word):
        base = Path(word).expanduser()
        pattern = str(base if base.is_absolute() else here / base)
        found = [Path(p) for p in globlib.glob(pattern)]
        if found:
            return found
    path = Path(word).expanduser()
    return [path if path.is_absolute() else here / path]


def write_targets(command: str, cwd: Path, depth: int = 0) -> list[Path]:
    segments = split_segments(command)
    if segments is None:
        return []
    targets: list[Path] = []
    here = cwd
    for segment in segments:
        segment = strip_prefix(segment)
        if segment and segment[0] == "cd":
            here = _cd(here, segment)
            continue
        script = shell_script(segment)
        if script is not None and depth < MAX_DEPTH:
            targets += write_targets(script, here, depth + 1)
        for word in command_targets(segment):
            if word not in NOT_FILES:
                targets += _files(here, word)
    here = cwd
    for words, redirected in redirect_segments(command):
        if words and words[0] == "cd":
            here = _cd(here, _unquoted(words))
            continue
        for word in redirected:
            if word not in NOT_FILES:
                targets += _files(here, word)
    return targets


def check_writes(
    command: str, root: Path, cwd: Path, principles: dict[str, Any]
) -> None:
    for target in write_targets(command, cwd):
        rel = _common.rel_to_root(root, str(target))
        if rel is None:
            continue
        glob = _common.protected_glob(rel, principles)
        if glob is not None:
            _common.block(_common.protected_message(rel, glob, principles))


def changes_hooks_path(args: list[str]) -> bool:
    keys = [k for k, arg in enumerate(args) if arg.lower() == "core.hookspath"]
    if not keys:
        return False
    before = set(args[: keys[0]])
    # git accepts options on either side of the key.
    if set(args) & CONFIG_UNSETS:
        return True
    values = [a for a in args[keys[0] + 1 :] if not a.startswith("-")]
    if before & CONFIG_READS or not values:
        return False
    return values[0].rstrip("/").removeprefix("./") != HOOKS_PATH


def check_review(root: Path) -> None:
    principles = _common.load_principles(root)
    if principles is None:
        return
    reason = review.push_blocker(root, principles)
    if reason:
        _common.block(reason)


def gh_command(segment: list[str]) -> list[str] | None:
    if not segment or posixpath.basename(segment[0]) != "gh":
        return None
    words = segment[1:]
    while words and words[0].startswith("-"):
        words = words[2:] if words[0] in ("-R", "--repo") else words[1:]
    return words


SHARED = "some may be the user's or another session's"
WHOLE_TREE = {".", "./", ":", ":/", "*"}
STAGE_ALL = {"-A", "--all", "-u", "--update", "--no-ignore-removal"}
STASH_READS = {"list", "show"}


def pathspecs(raw_args: list[str]) -> list[str]:
    cut = raw_args.index("--") if "--" in raw_args else len(raw_args)
    words = [a for a in raw_args[:cut] if not a.startswith("-")]
    return words + raw_args[cut + 1 :]


def check_shared_work(sub: str, raw_args: list[str], args: list[str]) -> None:
    whole = next((p for p in pathspecs(raw_args) if p in WHOLE_TREE), None)
    if sub == "add":
        flag = next(
            (a for a in args if a in STAGE_ALL or set("Au") & set(short_flags(a, sub))),
            None,
        )
        if flag or whole:
            _common.block(
                f"git add {flag or whole} stages every change in the tree, and "
                f"{SHARED}. Stage the files you changed by path: git add <path> …"
            )
    if sub == "commit":
        flag = next(
            (a for a in args if a == "--all" or "a" in short_flags(a, sub)), None
        )
        if flag:
            _common.block(
                f"git commit {flag} commits every tracked change, and {SHARED}. "
                "Stage the files you changed by path (git add <path> …), then "
                "commit without -a."
            )
    if sub == "reset" and "--hard" in args:
        _common.block(
            f"git reset --hard discards every uncommitted change, and {SHARED}. "
            "Put back your own files by path (git restore <path>), or ask the "
            "user to run it."
        )
    # restore --staged alone only unstages; the files themselves stay.
    staged_only = bool({"--staged", "-S"} & set(args)) and not (
        {"--worktree", "-W"} & set(args)
    )
    if sub in ("checkout", "restore") and whole and not staged_only:
        _common.block(
            f"git {sub} {whole} discards every uncommitted change under it, and "
            f"{SHARED}. Put back your own files by path (git restore <path>), or "
            "ask the user to run it."
        )
    if sub == "stash" and not (raw_args and raw_args[0] in STASH_READS):
        _common.block(
            f"git stash takes uncommitted changes out of the tree, and {SHARED}; "
            "a forgotten stash loses them. Commit or put back your own files by "
            "path instead, or ask the user to run it."
        )


def check_segment(segment: list[str], root: Path) -> None:
    gh = gh_command(segment)
    if gh is not None and gh[:1] == ["pr"] and gh[1:2] in (["create"], ["new"]):
        check_review(root)
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
    if sub == "push":
        check_review(root)
    if sub == "clean" and any(
        a in ("-x", "-X") or ("x" in short_flags(a, sub) or "X" in short_flags(a, sub))
        for a in args
    ):
        _common.block(
            f"git clean -x/-X deletes ignored files, including alpha's review state "
            f"in {_common.STATE_DIR}/. Delete the files you mean by name, or ask the "
            "user to run it."
        )
    check_shared_work(sub, raw_args, args)
    if sub == "commit" and "--amend" in args:
        branches = pushed_branches(root)
        if branches:
            _common.block(
                f"HEAD is already pushed ({branches}); amending rewrites shared "
                "history. Make a new commit instead."
            )


REVIEWER = "principles-reviewer"
READ_ONLY_GIT = {
    "diff",
    "log",
    "show",
    "status",
    "rev-parse",
    "ls-files",
    "ls-tree",
    "cat-file",
    "blame",
    "grep",
    "merge-base",
    "describe",
    "shortlog",
}
REVIEWER_MESSAGE = (
    "The principles-reviewer only reads: it may run the brief, git diff, log, "
    "show and status, and read files, but not write, delete or commit. Report "
    "the problem as a finding instead."
)


def check_read_only(command: str, cwd: Path, depth: int = 0) -> None:
    if write_targets(command, cwd):
        _common.block(REVIEWER_MESSAGE)
    for segment in split_segments(command) or []:
        segment = strip_prefix(segment)
        script = shell_script(segment)
        if script is not None and depth < MAX_DEPTH:
            check_read_only(script, cwd, depth + 1)
        invocation = git_invocation(segment)
        if invocation is not None and invocation[0] not in READ_ONLY_GIT:
            _common.block(REVIEWER_MESSAGE)


def main() -> None:
    _common.check_python()
    inp = _common.read_input()
    root = _common.project_root(inp)
    principles = _common.load_principles(root)
    if principles is None:
        sys.exit(0)
    if inp.get("tool_name") != "Bash":
        sys.exit(0)
    tool_input: object = inp.get("tool_input")
    command: object = None
    if isinstance(tool_input, dict):
        command = tool_input.get("command")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if not isinstance(command, str):
        sys.exit(0)
    cwd_value = inp.get("cwd")
    cwd = Path(cwd_value) if isinstance(cwd_value, str) and cwd_value else root
    if inp.get("agent_type") == REVIEWER:
        check_read_only(command, cwd)
    check_command(command, root)
    check_writes(command, root, cwd, principles)
    sys.exit(0)


if __name__ == "__main__":
    main()
