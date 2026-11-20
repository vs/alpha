"""The full track: brainstorm, plan and execute (spec, R8.3 to R8.6)."""

import re

import pytest

from alpha.cli import PLUGIN_ROOT

SKILLS = PLUGIN_ROOT / "skills"
FULL_TRACK = ["brainstorm"]


def _skill(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text()


def _steps(text: str) -> list[str]:
    return re.findall(r"^\d+\. (.*)$", text, re.M)


def _in_order(steps: list[str], starts: list[str]) -> list[int]:
    return [next(i for i, s in enumerate(steps) if s.startswith(x)) for x in starts]


def test_R8_3_brainstorm_designs_before_anything_is_built():
    text = _skill("brainstorm")
    steps = _steps(text)
    order = [
        "Research the code.",
        "Run the playbook's research steps.",
        "Deep research.",
        "Ask what the user wants",
        "Lay out the approaches",
        "Play the design back in sections",
        "Write `specification.md`",
        "Builder check.",
        "Get the user's approval",
        "Hand off to `/alpha:plan`",
    ]
    found = _in_order(steps, order)
    assert found == sorted(found)
    playbook = next(s for s in steps if s.startswith("Run the playbook's research"))
    for step in ("reproduce", "root cause", "baseline", "pin"):
        assert step in playbook, step
    deep = next(s for s in steps if s.startswith("Deep research."))
    assert "subagents" in deep and "`research.md`" in deep and "sources" in deep
    ask = next(s for s in steps if s.startswith("Ask what the user wants"))
    assert "before how" in ask and "one question at a time" in ask
    assert "in a message of their own" in text
    assert "Nothing but the folder is written until the user approves" in text
    template = text.split("```markdown")[1].split("```")[0]
    assert "| ID | Requirement | Acceptance check | Test |" in template
    for heading in ("Why", "Requirements", "Design", "Decisions", "Out of scope"):
        assert f"## {heading}" in template, heading


def test_R8_3_the_folder_is_named_by_the_playbook():
    text = _skill("brainstorm")
    rows = dict(re.findall(r"^\| (\w[\w ]*) \| `docs/alpha/([a-z-]+)/` \|", text, re.M))
    assert rows == {
        "Feature": "features",
        "Bug fix": "bug-fixes",
        "Refactoring": "refactorings",
        "Perf": "perf",
    }
    assert "`docs/alpha/<folder>/<YYYY-MM-DD>-<slug>/`" in text
    back = next(line for line in text.splitlines() if "no full track" in line)
    assert "`/alpha:do <task>`" in back
    for mode in ("investigation", "prototype", "pause", "session pickup"):
        assert mode in back.lower(), mode


@pytest.mark.parametrize("name", FULL_TRACK)
def test_full_track_credits_superpowers_with_the_full_license(name: str):
    credit = re.search(r"<!--(.*?)-->", _skill(name), re.S)
    assert credit and "superpowers" in credit.group(1)
    assert "Copyright (c) 2025 Jesse Vincent" in credit.group(1)
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in credit.group(1)
