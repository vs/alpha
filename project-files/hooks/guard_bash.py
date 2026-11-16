from __future__ import annotations

import glob as globlib
import json
import posixpath
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).parent))
import _common
import review
import stop_checks

NO_VERIFY_MESSAGE = (
    "--no-verify skips the project's commit checks. Fix what the hook reports "
    "instead; if the hook itself is wrong, tell the user."
)
SKIPPING = {"commit", "push", "merge", "rebase", "cherry-pick"}
GLOBAL_OPTIONS_WITH_VALUE = {
    "-C",
    "-c",
    "--config-env",
    "--git-dir",
    "--work-tree",
    "--namespace",
}
COMMIT_VALUE_FLAGS = {"-m", "-F", "-C", "-c", "-t", "--message", "--file", "--template"}
COMMIT_VALUE_LETTERS = "mFCct"
HOOKS_CONFIG_MESSAGE = (
    "Changing core.hooksPath switches off the project's commit checks. Keep it "
    "at .claude/alpha/githooks; only /alpha:uninstall switches alpha's hooks off. "
    "If the hook itself is wrong, tell the user."
)
HOOKS_PATH = ".claude/alpha/githooks"
CONFIG_READS = {"--get", "--get-all", "--get-regexp", "--list", "-l", "get", "list"}
CONFIG_UNSETS = {"--unset", "--unset-all", "unset"}
SHELL_KEYWORDS = {"then", "do", "else", "elif", "!", "time", "if", "while", "until"}
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


def _as_bash_reads(command: str, escaped_quote: str = "") -> str:
    """The command with each unquoted newline made a ";" and, given
    `escaped_quote`, each backslash-escaped quote outside single quotes
    replaced by it: a non-POSIX lexer doesn't know escapes and would take an
    escaped quote for one that opens or closes."""
    out: list[str] = []
    quote = ""
    escaped = False
    for ch in command:
        if escaped:
            escaped = False
            if escaped_quote and ch in "'\"":
                ch = escaped_quote
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
    lexer = shlex.shlex(_as_bash_reads(command), posix=True, punctuation_chars=True)
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


def strip_prefix(segment: list[str]) -> list[str]:
    i = 0
    after_env = False
    while i < len(segment):
        tok = segment[i]
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


def git_invocation(segment: list[str]) -> tuple[str, list[str]] | None:
    if not segment or posixpath.basename(segment[0]) != "git":
        return None
    i = 1
    while i < len(segment) and segment[i].startswith("-"):
        i += 2 if segment[i] in GLOBAL_OPTIONS_WITH_VALUE else 1
    if i >= len(segment):
        return None
    return segment[i], segment[i + 1 :]


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


def git_output(root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    return proc.stdout if proc.returncode == 0 else None


def main_branches(root: Path) -> set[str]:
    names = {"main", "master"}
    head = git_output(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head and "/" in head:
        names.add(head.strip().split("/", 1)[1])
    return names


def current_branch(root: Path) -> str:
    return (git_output(root, "branch", "--show-current") or "").strip()


PUSH_VALUE_FLAGS = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
PUSH_EVERY_BRANCH = {"--all", "--mirror", "--branches"}


def pushed_to(root: Path, raw_args: list[str]) -> set[str] | None:
    words: list[str] = []
    skip = False
    for arg in raw_args:
        if skip:
            skip = False
        elif arg in PUSH_EVERY_BRANCH:
            return None
        elif arg in PUSH_VALUE_FLAGS:
            skip = True
        elif not arg.startswith("-"):
            words.append(arg)
    refspecs = words[1:]
    if not refspecs:
        return {current_branch(root)}
    targets: set[str] = set()
    for spec in refspecs:
        dst = spec.lstrip("+").rsplit(":", 1)[-1]
        if dst in ("", "HEAD"):
            dst = current_branch(root)
        targets.add(dst.removeprefix("refs/heads/"))
    return targets


def touches_main(root: Path, raw_args: list[str]) -> bool:
    targets = pushed_to(root, raw_args)
    return targets is None or bool(targets & main_branches(root))


def on_main_remote(root: Path) -> list[str]:
    out = git_output(root, "branch", "-r", "--contains", "HEAD") or ""
    remotes = [line.strip() for line in out.splitlines() if "->" not in line]
    main = main_branches(root)
    return [r for r in remotes if r and r.split("/", 1)[-1] in main]


def git_folder(segment: list[str]) -> str | None:
    for i, arg in enumerate(segment[1:-1], start=1):
        if not arg.startswith("-"):
            return None
        if arg == "-C":
            return segment[i + 1]
    return None


NOTES_MESSAGE = (
    "alpha's review notes are written only by its review hooks (the reviewer's "
    "record, the user's accept) and stay in this clone. Run the "
    "principles-reviewer instead."
)
NOTES_WRITES = {"add", "append", "copy", "edit", "merge", "remove", "prune"}


def review_notes_written(raw: list[str], sub: str, args: list[str]) -> bool:
    """Whether a git command writes alpha's review notes or moves them between
    clones."""
    named = " ".join(raw).count(review.NOTES_REF) > 0
    if sub == "notes":
        words = [a for a in args if not a.startswith("-")]
        return named and bool(set(words) & NOTES_WRITES)
    if sub == "update-ref":
        return named
    if sub == "push":
        notes = [a for a in args if "refs/notes/" in a]
        return "--mirror" in args or named or any("*" in a for a in notes)
    if sub == "fetch":
        return named or any("refs/notes/" in a and "*" in a for a in args)
    return False


def check_command(command: str, root: Path, here: Path) -> None:
    for raw in split_segments(command) or []:
        segment = strip_prefix(raw)
        invocation = git_invocation(segment)
        if invocation is not None and review_notes_written(
            raw, invocation[0], invocation[1]
        ):
            _common.block(NOTES_MESSAGE)
        if segment[:1] == ["cd"] and len(segment) > 1 and segment[1] != "-":
            here = here / Path(segment[1]).expanduser()
        folder = git_folder(segment) if segment[:1] == ["git"] else None
        target = here / folder if folder else here
        check_segment(segment, _common.checkout_of(target.resolve()) or root)


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


def redirect_segments(command: str) -> list[tuple[list[str], list[str]]] | None:
    """(words, redirect targets) per segment. Lexed without POSIX quote
    removal, so a quoted ">" (as in grep '>' f) stays a word, not a redirect;
    an escaped \\> and a comparison inside [[ ]] aren't redirects either."""
    command = strip_heredocs(command).replace("\\\n", "")
    lexer = shlex.shlex(
        _as_bash_reads(command, escaped_quote="_"), posix=False, punctuation_chars=True
    )
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return None
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


def write_targets(command: str, cwd: Path) -> list[Path]:
    targets: list[Path] = []
    here = cwd
    for segment in split_segments(command) or []:
        segment = strip_prefix(segment)
        if segment and segment[0] == "cd":
            here = _cd(here, segment)
            continue
        for word in command_targets(segment):
            if word not in NOT_FILES:
                targets += _files(here, word)
    here = cwd
    for words, redirected in redirect_segments(command) or []:
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
        glob = _common.protected_glob(rel, principles, shell=True)
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
    reason = review.gate(root, principles) or stop_checks.untested_blocker(
        root, principles
    )
    if reason:
        _common.block(reason)


MERGE_VALUE_FLAGS = {
    "-R",
    "--repo",
    "-t",
    "--subject",
    "-b",
    "--body",
    "-F",
    "--body-file",
    "--match-head-commit",
    "-A",
    "--author-email",
}


def merge_target(words: list[str]) -> str | None:
    skip = False
    for word in words:
        if skip:
            skip = False
        elif word in MERGE_VALUE_FLAGS:
            skip = True
        elif not word.startswith("-"):
            return word
    return None


def pr_branch(root: Path, target: str | None) -> str | None:
    if target is None:
        return current_branch(root) or None
    if not (target.lstrip("#").isdigit() or "://" in target):
        return target
    try:
        proc = subprocess.run(
            ["gh", "pr", "view", target.lstrip("#"), "--json", "headRefName"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        branch = json.loads(proc.stdout).get("headRefName")
    except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError):
        return None
    return branch if proc.returncode == 0 and isinstance(branch, str) else None


def checkout_with(root: Path, branch: str) -> Path | None:
    path: Path | None = None
    for line in (
        git_output(root, "worktree", "list", "--porcelain") or ""
    ).splitlines():
        if line.startswith("worktree "):
            path = Path(line.removeprefix("worktree "))
        elif line == f"branch refs/heads/{branch}" and path is not None:
            return path
    return None


def pr_head(root: Path, target: str) -> str | None:
    """The commit a pull request's head is at on GitHub, or None."""
    try:
        proc = subprocess.run(
            ["gh", "pr", "view", target.lstrip("#"), "--json", "headRefOid"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        oid = json.loads(proc.stdout).get("headRefOid")
    except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError):
        return None
    return oid if proc.returncode == 0 and isinstance(oid, str) else None


def check_merge(root: Path, words: list[str]) -> None:
    target = merge_target(words)
    branch = pr_branch(root, target)
    if branch is None:
        _common.block(
            f"alpha can't tell which branch pull request {target} merges (gh pr "
            "view failed), so it can't check its review and tests. Check the "
            "branch out (gh pr checkout), then merge from there."
        )
    checkout = checkout_with(root, branch)
    if checkout is None:
        _common.block(
            f"{branch} isn't checked out here, so alpha can't check what merges "
            f"was reviewed and tested. Run git switch {branch} (or gh pr "
            "checkout), then merge from there."
        )
    check_review(checkout)
    pull_request = target or branch
    remote = pr_head(checkout, pull_request)
    if remote is None:
        _common.block(
            f"alpha can't ask GitHub where pull request {pull_request}'s head is "
            "(gh pr view failed or timed out), so it can't check that what merges "
            "is what was reviewed and tested. Check gh auth status and the "
            "network, then merge again."
        )
    local = (git_output(checkout, "rev-parse", "HEAD") or "").strip()
    if remote != local:
        _common.block(
            f"The pull request's head on GitHub ({remote[:12]}) isn't this "
            f"checkout's HEAD ({local[:12]}): push the branch first, so what merges "
            "is what was reviewed and tested."
        )


def gh_command(segment: list[str]) -> list[str] | None:
    if not segment or posixpath.basename(segment[0]) != "gh":
        return None
    words = segment[1:]
    while words and words[0].startswith("-"):
        words = words[2:] if words[0] in ("-R", "--repo") else words[1:]
    return words


def pathspecs(raw_args: list[str]) -> list[str]:
    cut = raw_args.index("--") if "--" in raw_args else len(raw_args)
    words = [a for a in raw_args[:cut] if not a.startswith("-")]
    return words + raw_args[cut + 1 :]


def git_wiring_paths(sub: str, raw_args: list[str], args: list[str]) -> list[str]:
    """The paths a git command removes, moves or brings back from another
    revision: `git rm`, `git mv`, `git checkout <rev> -- <path>`,
    `git restore --source`."""
    if sub in ("rm", "mv"):
        return pathspecs(raw_args)
    if sub == "checkout" and "--" in raw_args:
        before = [a for a in raw_args[: raw_args.index("--")] if not a.startswith("-")]
        return raw_args[raw_args.index("--") + 1 :] if before else []
    if sub == "restore" and any(a.startswith(("--source", "-s")) for a in args):
        return [p for p in pathspecs(raw_args) if not p.startswith("--source")]
    return []


def check_git_wiring(
    sub: str, raw_args: list[str], args: list[str], root: Path
) -> None:
    principles = _common.load_principles(root) or {}
    for path in git_wiring_paths(sub, raw_args, args):
        rel = _common.rel_to_root(root, str(root / path))
        if rel is None:
            continue
        glob = _common.protected_glob(rel, principles, shell=True)
        if (
            glob in (_common.ALPHA_GLOB, _common.STATE_GLOB)
            or rel in _common.SHELL_WIRING
        ):
            _common.block(_common.protected_message(rel, glob or rel, principles))


def check_segment(segment: list[str], root: Path) -> None:
    gh = gh_command(segment)
    if gh is not None and gh[:2] == ["pr", "merge"]:
        check_merge(root, gh[2:])
    invocation = git_invocation(segment)
    if invocation is None:
        return
    sub, raw_args = invocation
    if sub == "config" and changes_hooks_path(raw_args):
        _common.block(HOOKS_CONFIG_MESSAGE)
    args = option_args(sub, raw_args)
    if sub in SKIPPING:
        if "--no-verify" in args:
            _common.block(NO_VERIFY_MESSAGE)
        if sub == "commit" and any("n" in short_flags(a, sub) for a in args):
            _common.block(NO_VERIFY_MESSAGE)
    if sub == "push":
        check_push(root, raw_args, args)
    check_git_wiring(sub, raw_args, args, root)
    if sub == "commit" and "--amend" in args:
        branches = on_main_remote(root)
        if branches:
            _common.block(
                f"HEAD is already on {', '.join(branches)}; amending rewrites the "
                "main branch's history. Make a new commit instead."
            )


def check_push(root: Path, raw_args: list[str], args: list[str]) -> None:
    lease = [a for a in args if a.startswith(("--force-with-lease", "--force-if-"))]
    blind = [
        a
        for a in args
        if a == "--force"
        or (len(a) > 1 and a.startswith("+"))
        or "f" in short_flags(a, "push")
    ]
    if blind:
        _common.block(
            f"git push {blind[0]} overwrites the remote branch without checking "
            "what's on it. To publish a rebased or amended branch, push it with "
            "--force-with-lease instead."
        )
    to_main = touches_main(root, raw_args)
    if lease and to_main:
        _common.block(
            f"git push {lease[0]} would rewrite the main branch, which others "
            "build on. Merge or revert with a new commit instead; only the user "
            "rewrites main."
        )
    if to_main:
        foreign = [s for s in main_sources(root, raw_args) if not is_head(root, s)]
        if foreign:
            _common.block(
                f"git push sends {foreign[0]} to main, but the review and test "
                "gates judge this checkout's HEAD. Push main from the checkout "
                "where it is checked out."
            )
        check_review(root)


def main_sources(root: Path, raw_args: list[str]) -> list[str]:
    """What a push sends to a main branch: each refspec's source, or the main
    branches themselves when it pushes every branch."""
    words: list[str] = []
    skip = False
    for arg in raw_args:
        if skip:
            skip = False
        elif arg in PUSH_EVERY_BRANCH:
            return sorted(
                name
                for name in main_branches(root)
                if git_output(root, "rev-parse", "--verify", "-q", f"refs/heads/{name}")
            )
        elif arg in PUSH_VALUE_FLAGS:
            skip = True
        elif not arg.startswith("-"):
            words.append(arg)
    main = main_branches(root)
    sources: list[str] = []
    for spec in words[1:] or ["HEAD"]:
        src, _, dst = (
            spec.lstrip("+").rpartition(":") if ":" in spec else ("", "", spec)
        )
        src = src or dst
        target = dst if dst not in ("", "HEAD") else current_branch(root)
        if target.removeprefix("refs/heads/") in main:
            sources.append(src)
    return sources


def is_head(root: Path, ref: str) -> bool:
    here = (git_output(root, "rev-parse", "HEAD") or "").strip()
    there = (git_output(root, "rev-parse", "--verify", "-q", ref) or "").strip()
    return ref == "HEAD" or (bool(there) and there == here)


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
UNPARSED_MESSAGE = (
    "alpha's command guard can't parse this command (a quote it can't pair up, "
    "or $'...' quoting with an escaped quote), so it can't check what it runs. "
    "Simplify the quoting, or put the text in a heredoc or a file (e.g. git "
    "commit -F <file>), then run it again."
)

REVIEWER_MESSAGE = (
    "The principles-reviewer only reads: it may run the brief, git diff, log, "
    "show and status, and read files, but not write, delete or commit. Report "
    "the problem as a finding instead."
)


def check_read_only(command: str, cwd: Path) -> None:
    if write_targets(command, cwd):
        _common.block(REVIEWER_MESSAGE)
    for segment in split_segments(command) or []:
        invocation = git_invocation(strip_prefix(segment))
        if invocation is not None and invocation[0] not in READ_ONLY_GIT:
            _common.block(REVIEWER_MESSAGE)


def main() -> None:
    _common.check_python()
    inp = _common.read_input()
    root = _common.project_root(inp)
    if _common.checkout_of(root.resolve()) is None:
        sys.exit(0)
    principles = _common.load_principles(root) or {}
    if inp.get("tool_name") != "Bash":
        sys.exit(0)
    tool_input: object = inp.get("tool_input")
    command: object = None
    if isinstance(tool_input, dict):
        command = cast("dict[str, object]", tool_input).get("command")
    if not isinstance(command, str):
        sys.exit(0)
    cwd_value = inp.get("cwd")
    cwd = Path(cwd_value) if isinstance(cwd_value, str) and cwd_value else root
    if split_segments(command) is None or redirect_segments(command) is None:
        _common.block(UNPARSED_MESSAGE)
    if inp.get("agent_type") == REVIEWER:
        check_read_only(command, cwd)
    check_command(command, root, here=cwd)
    check_writes(command, root, cwd, principles)
    sys.exit(0)


if __name__ == "__main__":
    main()
