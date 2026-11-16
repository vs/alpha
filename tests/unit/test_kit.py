"""What the kit ships, as a whole: features the rewrite dropped stay gone."""

import ast
import contextlib
import functools
import io
import re
import tokenize
import tomllib
from pathlib import Path

import pytest

from alpha.answers import AnswersError, parse_answers
from alpha.cli import PLUGIN_ROOT, build_parser

# The kit's shipped files.
SHIPPED = ("src", "project-files", "skills", "recipes", "defaults", "registry", "bin")
SHIPPED_FILES = ("pyproject.toml",)


def _texts() -> dict[str, str]:
    paths: list[Path] = []
    for folder in SHIPPED:
        paths += [p for p in (PLUGIN_ROOT / folder).rglob("*") if p.is_file()]
    paths += [PLUGIN_ROOT / f for f in SHIPPED_FILES]
    texts: dict[str, str] = {}
    for path in paths:
        if "__pycache__" in path.parts or "state" in path.parts:
            continue
        try:
            texts[path.relative_to(PLUGIN_ROOT).as_posix()] = path.read_text("utf-8")
        except UnicodeDecodeError:
            continue
    return texts


def _naming(*words: str) -> list[str]:
    """Each file that names one of `words`; a word may be a regex."""
    return sorted(
        f"{rel}: {word}"
        for rel, text in _texts().items()
        for word in words
        if re.search(word, text)
    )


def test_R14_1_dropped_features_are_gone():
    for gone in ("src/alpha_evals", "bin/alpha-evals", "evals"):
        assert not (PLUGIN_ROOT / gone).exists(), gone
    assert _naming("alpha-evals", "alpha_evals") == []
    assert _naming("cargo-mutants", "ci:mutants", "mutants::skip") == []
    for gone in ("project-files/skills/debt", "project-files/checks/shortcuts.py"):
        assert not (PLUGIN_ROOT / gone).exists(), gone
    # apply.py lists the debt skill among the retired files it deletes.
    assert (
        _naming("check:shortcuts", "checks/shortcuts\\.py", r"(?<!skills)/debt") == []
    )


RECORD_USE = re.compile(
    r"docs/decisions|decision records? (in|under|that)|decision log|"
    r"`decisions\[\]`|`Kind: (product|technical)`|--decision|fold-decisions|"
    r"accepted record|supersedes? (it|the record)|decisions = \["
)


def test_R15_1_no_decision_records(tmp_path: Path):
    """Decisions live in the docs; no shipped file names a record."""
    named = sorted(rel for rel, text in _texts().items() if RECORD_USE.search(text))
    assert named == []
    with pytest.raises(AnswersError, match=r"decisions: isn't part of the answers"):
        parse_answers({"schema": 1, "areas": {}, "decisions": []}, tmp_path, ())


# `alpha <word> [<word>]` meant as a command: the first word is a subcommand
# or hyphenated, or a cue (run, rerun, then, a quote or backtick) comes first.
MENTION = re.compile(
    r"(?P<cue>(?:\b(?:run|rerun|then) |[\"'`])?)"
    r"\balpha (?P<first>[a-z][a-z-]*)(?: (?P<second>[a-z][a-z-]*))?"
)


def _string_literals(path: Path) -> list[str]:
    """Each string in the module, an f-string's parts joined around {}."""
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text("utf-8"))):
        if isinstance(node, ast.JoinedStr):
            found.append(
                "".join(
                    v.value
                    if isinstance(v, ast.Constant) and isinstance(v.value, str)
                    else "{}"
                    for v in node.values
                )
            )
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append(node.value)
    return found


@functools.cache
def _invalid(*words: str) -> bool:
    """Whether the CLI rejects `words` as an unknown (sub)command."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.suppress(SystemExit):
        build_parser().parse_args(list(words))
    return "invalid choice" in err.getvalue()


def test_every_alpha_command_named_in_a_message_exists():
    sources = [
        p
        for folder in ("src/alpha", "project-files")
        for p in (PLUGIN_ROOT / folder).rglob("*.py")
    ]
    wrong: list[str] = []
    for path in sources:
        for text in _string_literals(path):
            for m in MENTION.finditer(text):
                first, second = m["first"], m["second"]
                if _invalid(first):
                    if m["cue"] or "-" in first:
                        wrong.append(f"{path.name}: alpha {first}")
                elif second and _invalid(first, second):
                    wrong.append(f"{path.name}: alpha {first} {second}")
    assert wrong == []


def test_dev_python_is_pinned_once_for_mise_and_uv():
    """mise installs the Python in mise.toml; uv, locally and in CI, runs on
    the one in .python-version. They must be the same."""
    tools = tomllib.loads((PLUGIN_ROOT / "mise.toml").read_text("utf-8"))["tools"]
    pinned = (PLUGIN_ROOT / ".python-version").read_text("utf-8").strip()
    assert tools["python"] == pinned
    assert "uv" in tools


def _comments(path: Path) -> list[tuple[int, str]]:
    """(line, text) of each comment, read as Python reads the file: by
    readline, since str.splitlines also breaks at U+2028 inside strings."""
    with tokenize.open(path) as source:
        return [
            (token.start[0], token.string)
            for token in tokenize.generate_tokens(source.readline)
            if token.type == tokenize.COMMENT
        ]


def test_no_type_check_is_silenced_in_python():
    """never-weaken-checks: narrow an Optional or fix the type instead. Only
    real comments count, not the strings tests use to prove the guard
    blocks such comments."""
    silenced = [
        f"{path.relative_to(PLUGIN_ROOT)}:{line}"
        for folder in ("src", "project-files", "tests")
        for path in (PLUGIN_ROOT / folder).rglob("*.py")
        for line, text in _comments(path)
        if "type: ignore" in text or "pyright: ignore" in text
    ]
    assert silenced == []


GIT_ARGV = re.compile(r'\[\s*"git"\s*,')


def test_every_git_call_in_src_goes_through_the_runner():
    """shell.git runs git under GIT_TIMEOUT and reports a stuck or missing git
    the same way; a direct call can hang a command or end in a traceback. The
    whole text is searched, since the formatter puts a long argv's "git" on
    the line after its bracket."""
    direct = sorted(
        f"{path.relative_to(PLUGIN_ROOT)}:{text.count(chr(10), 0, m.start()) + 1}"
        for path in (PLUGIN_ROOT / "src" / "alpha").rglob("*.py")
        if path.name != "shell.py"
        for text in [path.read_text("utf-8")]
        for m in GIT_ARGV.finditer(text)
    )
    assert direct == []
