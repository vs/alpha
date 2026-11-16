"""What the kit ships, as a whole: features the rewrite dropped stay gone."""

import ast
import contextlib
import functools
import io
import re
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
