import re

from alpha.cli import PLUGIN_ROOT
from alpha.render.docs import EXCEPTIONS_SECTION

DECISION = PLUGIN_ROOT / "project-files" / "skills" / "decision" / "SKILL.md"


def test_decision_skill_frontmatter():
    text = DECISION.read_text()
    assert text.startswith("---\nname: decision\ndescription: ")
    assert "allowed-tools" not in text.split("\n---\n", 1)[0]


def test_decision_skill_routes_each_kind_into_the_docs():
    text = DECISION.read_text()
    routes = text.split("## 1. Where it goes")[1].split("\n## ")[0]
    for piece in (
        "`docs/alpha/specification.md`",
        "`CONTRIBUTING.md`",
        "An override in the answers",
        "Exceptions table",
        "An `Accepts:` trailer",
    ):
        assert piece in routes, piece
    assert "docs/decisions" not in text
    assert len(text.splitlines()) <= 60


def test_decision_skill_names_the_exceptions_table_alpha_writes():
    text = DECISION.read_text()
    assert EXCEPTIONS_SECTION[0] in text
    assert re.search(r"Accepts: F-x{6} <", text)


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
        '"checked"',
        '"findings"',
        "`Kind: fix-check`",
        '"principle"',
        '"file"',
        '"line"',
        '"problem"',
        '"fix"',
        "`spec`",
        "```json",
    ):
        assert piece in text, piece
    assert len(text.splitlines()) <= 100


REVIEW_CHANGE = PLUGIN_ROOT / "project-files" / "skills" / "review-change" / "SKILL.md"


def test_review_change_proves_bugs_and_the_safety_fact_by_running_them():
    text = REVIEW_CHANGE.read_text()
    check = text.split("## 3. Check before you report")[1].split("\n## ")[0]
    assert "A bug finding needs a run" in check
    assert "Not checked:" in check
    output = text.split("## 4. Output")[1]
    assert "`Safe because:`" in output and "`unproven`" in output
