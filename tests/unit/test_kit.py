"""What the kit ships, as a whole: features the rewrite dropped stay gone."""

import re
from pathlib import Path

import pytest

from alpha.answers import AnswersError, parse_answers
from alpha.cli import PLUGIN_ROOT

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
    r"`decisions\[\]`|`Kind: (product|technical)`|--decision|fold-decisions"
)


def test_R15_1_no_decision_records(tmp_path: Path):
    """Decisions live in the docs. Only the survey, which finds a repo's own
    records, may name them."""
    allowed = {"defaults/survey.toml"}
    named = sorted(
        rel
        for rel, text in _texts().items()
        if rel not in allowed and RECORD_USE.search(text)
    )
    assert named == []
    with pytest.raises(AnswersError, match=r"decisions: isn't part of the answers"):
        parse_answers({"schema": 1, "areas": {}, "decisions": []}, tmp_path, ())
