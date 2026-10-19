from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "project-files"
SKILL = ROOT / "skills" / "commit" / "SKILL.md"
AGENT = ROOT / "agents" / "committer.md"


@pytest.mark.parametrize("path", [SKILL, AGENT])
def test_no_hardcoded_coauthor_and_uses_session_attribution(path: Path):
    text = path.read_text()
    assert "Co-Authored-By" not in text
    assert "Generated with" not in text
    assert "attribution lines Claude Code provides" in text
    assert "Never invent or hard-code co-author lines." in text


@pytest.mark.parametrize("path", [SKILL, AGENT])
def test_points_at_contributing_convention(path: Path):
    assert "This project's convention is in CONTRIBUTING.md" in path.read_text()
    assert "enforced by the commit-msg hook." in path.read_text()


def test_skill_frontmatter():
    lines = SKILL.read_text().splitlines()
    assert lines[0] == "---"
    end = lines.index("---", 1)
    assert "name: commit" in lines[1:end]
    assert any(line.startswith("description: ") for line in lines[1:end])


def test_agent_keeps_frontmatter():
    text = AGENT.read_text()
    assert text.startswith("---\nname: committer\n")
