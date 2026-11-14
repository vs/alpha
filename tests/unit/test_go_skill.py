import re
import tomllib

import pytest

from alpha.cli import PLUGIN_ROOT

GO = PLUGIN_ROOT / "skills" / "go"
PLAYBOOKS = GO / "playbooks"


def _router() -> str:
    return (GO / "SKILL.md").read_text()


def _table_files() -> list[str]:
    return re.findall(r"^\| [^|]+ \| `([a-z-]+\.md)` \|", _router(), re.M)


def _playbook(name: str) -> str:
    return (PLAYBOOKS / name).read_text()


def _kit_principle_ids() -> set[str]:
    kit = tomllib.loads((PLUGIN_ROOT / "defaults" / "defaults.toml").read_text())
    return {p["id"] for p in kit["principles"]}


def test_the_router_lists_every_playbook_file_and_no_other():
    listed = _table_files()
    assert listed, "list the playbooks as rows of the table in section 2"
    assert sorted(listed) == sorted(p.name for p in PLAYBOOKS.glob("*.md"))


@pytest.mark.parametrize("name", sorted(p.name for p in PLAYBOOKS.glob("*.md")))
def test_each_playbook_has_a_title_and_ends_with_its_reply(name: str):
    lines = _playbook(name).strip().splitlines()
    assert lines[0].startswith("# ")
    assert lines[-1].startswith("**Reply:**")


def test_the_router_stops_outside_an_alpha_project():
    check = _router().split("## 1. Check the project")[1].split("\n## ")[0]
    assert "`manifest` key" in check and "/alpha:adopt" in check
    assert "and stop" in check


def test_the_router_credits_pstack_with_the_full_license():
    credit = re.search(r"<!--(.*?)-->", _router(), re.S)
    assert credit and "pstack" in credit.group(1)
    assert "Copyright (c) 2026 Lauren Tan" in credit.group(1)
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in credit.group(1)


def test_principles_the_skill_names_exist_in_the_kit():
    texts = [_router(), *(_playbook(p.name) for p in PLAYBOOKS.glob("*.md"))]
    named = {
        name
        for text in texts
        for name in re.findall(r"\(`([a-z]+(?:-[a-z]+)+)`\)", text)
    }
    assert named, "name principles as (`id`)"
    assert named <= _kit_principle_ids(), named - _kit_principle_ids()


def test_r8_a_feature_needs_an_approved_spec_before_tests_and_code():
    """R8: the feature spec names a test per check and is approved before any code."""
    text = _playbook("feature.md")
    steps = re.findall(r"^(\d+)\. (.*)$", text, re.M)
    spec = next(int(n) for n, s in steps if "docs/specs/<YYYY-MM-DD>-" in s)
    approval = next(int(n) for n, s in steps if "approval of the spec, every time" in s)
    build = next(int(n) for n, s in steps if s.startswith("Build the tasks"))
    assert spec < approval < build
    assert "Nothing but the spec file is written until they approve" in text
    grill = next(s for _, s in steps if s.startswith("Grill."))
    assert "`decision` skill" not in grill
    after = text.split("approval of the spec, every time")[1]
    assert after.index("git switch -c") < after.index("Commit the spec")


def test_a_feature_offers_native_and_subagent_builds():
    text = _playbook("feature.md")
    assert "**Native**" in text and "**Subagents**" in text
    assert "with your recommendation" in text


def test_tests_fail_first_but_are_committed_with_their_code():
    for name in ("feature.md", "bug-fix.md"):
        text = _playbook(name)
        assert "must fail" in text, name
        assert "`clean-history`" in text, name


def test_the_spec_template_traces_each_check_to_a_test():
    template = _playbook("feature.md").split("```markdown")[1].split("```")[0]
    assert "| ID | Requirement | Acceptance check | Test |" in template
    for heading in ("## Why", "## Requirements", "## Plan", "## Decisions"):
        assert heading in template
    assert "Serves: R<n> in docs/product.md" in template


def test_worktrees_prefer_the_harness_tool_and_an_ignored_folder():
    rules = _router().split("**Worktrees.**")[1].split("\n\n")[0]
    assert rules.index("EnterWorktree") < rules.index("git worktree add")
    assert ".claude/worktrees/" in rules and "git check-ignore" in rules
    assert 'isolation: "worktree"' in rules


def test_pause_and_pickup_share_the_resume_note():
    note = ".claude/alpha/notes/resume-<branch>.md"
    assert note in _playbook("pause.md")
    assert note in _playbook("session-pickup.md")
    assert "git worktree list" in _playbook("session-pickup.md")
