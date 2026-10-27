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


def test_decision_skill_keeps_claude_md_in_step_with_overrides():
    text = DECISION.read_text()
    change = text.split("## 4. Changing a principle")[1].split("\n## ")[0]
    assert "CLAUDE.md" in change and "(overridden: see " in change


def test_decision_skill_matches_the_interview_format():
    record = _decision(7, "Use OpenAPI", date(2026, 10, 23), "c", "d", "q")
    lines = record.splitlines()
    assert re.fullmatch(r"# \d{4}\. .+", lines[0])
    text = DECISION.read_text()
    for line in lines:
        if line.startswith(("Date: ", "Status: ", "## ")):
            head = line.split(":")[0] + ":" if ":" in line else line
            assert head in text, f"the skill doesn't name {head!r}"


REVIEWER = PLUGIN_ROOT / "project-files" / "agents" / "principles-reviewer.md"


def frontmatter(text: str) -> dict[str, str]:
    head = text.split("\n---\n", 1)[0].removeprefix("---\n")
    return {
        k.strip(): v.strip()
        for k, _, v in (line.partition(":") for line in head.splitlines())
    }


def test_reviewer_agent_frontmatter():
    meta = frontmatter(REVIEWER.read_text())
    assert meta["name"] == "principles-reviewer"
    assert len(meta["description"]) > 60
    tools = {t.strip() for t in meta["tools"].split(",")}
    assert tools == {"Read", "Grep", "Glob", "Bash"}
    assert "model" not in meta


def test_reviewer_agent_contract():
    text = REVIEWER.read_text()
    for piece in (
        "python3 .claude/alpha/hooks/review.py brief",
        '"tree"',
        '"findings"',
        '"principle"',
        '"file"',
        '"line"',
        '"problem"',
        '"fix"',
        "decision:NNNN",
        "```json",
    ):
        assert piece in text, piece
    assert len(text.splitlines()) <= 100
