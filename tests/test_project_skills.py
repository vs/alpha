"""Skills and agents copied into generated projects."""

import re
from datetime import date

from alpha.cli import PLUGIN_ROOT
from alpha.render.docs import _decision

DECISION = PLUGIN_ROOT / "project-files" / "skills" / "decision" / "SKILL.md"


def test_decision_skill_frontmatter():
    text = DECISION.read_text()
    assert text.startswith("---\nname: decision\ndescription: ")
    assert "allowed-tools" not in text.split("\n---\n", 1)[0]


def test_decision_skill_states_the_record_format():
    text = DECISION.read_text()
    for piece in (
        "docs/decisions/NNNN-<slug>.md",
        "# NNNN. ",
        "Date: ",
        "Status: accepted",
        "Supersedes: NNNN",
        "superseded by NNNN",
        "## Context",
        "## Decision",
        "## Consequences",
        "docs/principles.toml",
        "override_decision",
    ):
        assert piece in text, piece
    assert len(text.splitlines()) <= 120


def test_decision_skill_matches_the_interview_format():
    record = _decision(7, "Use OpenAPI", date(2026, 10, 23), "c", "d", "q")
    lines = record.splitlines()
    assert re.fullmatch(r"# \d{4}\. .+", lines[0])
    text = DECISION.read_text()
    for line in lines:
        if line.startswith(("Date: ", "Status: ", "## ")):
            head = line.split(":")[0] + ":" if ":" in line else line
            assert head in text, f"the skill doesn't name {head!r}"
