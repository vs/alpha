import re
import tomllib

import pytest

from alpha.cli import PLUGIN_ROOT

DO = PLUGIN_ROOT / "skills" / "do"
PLAYBOOKS = DO / "playbooks"


def _router() -> str:
    return (DO / "SKILL.md").read_text()


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
    assert "`installed` key" in check and "/alpha:install" in check
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


def test_R8_1_a_feature_gets_research_spec_and_plan():
    text = _playbook("feature.md")
    steps = re.findall(r"^(\d+)\. (.*)$", text, re.M)

    def step(start: str) -> int:
        return next(int(n) for n, s in steps if s.startswith(start))

    folder = "docs/alpha/features/<YYYY-MM-DD>-<feature-slug>/research.md"
    deep = next(s for _, s in steps if s.startswith("Deep research."))
    assert "subagents" in deep and folder in deep and "sources" in deep
    brainstorm = next(s for _, s in steps if s.startswith("Brainstorm"))
    assert "one question at a time" in brainstorm
    assert "two or three approaches with their trade-offs" in brainstorm
    assert "show the design in sections" in brainstorm
    writing = next(s for _, s in steps if s.startswith("Write `specification.md`"))
    assert "`plan.md`" in writing and "the test that proves it" in writing
    order = [
        "Research the code",
        "Deep research",
        "Brainstorm",
        "Write `specification.md`",
    ]
    order += ["Get the user's approval", "Build the tasks"]
    assert [step(s) for s in order] == sorted(step(s) for s in order)
    assert "Nothing but the feature folder is written until they approve" in text


def test_R8_2_do_runs_no_whole_branch_review():
    texts = {"SKILL.md": _router()}
    texts |= {p.name: p.read_text() for p in PLAYBOOKS.glob("*.md")}
    for name, text in texts.items():
        assert "whole branch is reviewed" not in text, name
        assert "review-change` of the whole branch" not in text, name
        assert "reviews the whole branch" not in text, name
    done = _router().split("**Done.**")[1].split("\n\n**")[0]
    assert "Don't run the principles reviewer or review the whole branch" in done
    assert "when the work reaches main" in done


def test_open_product_areas_are_named_not_settled():
    assert not (PLAYBOOKS / "specify.md").exists()
    feature = _playbook("feature.md")
    areas = next(
        line for line in feature.splitlines() if line.startswith("3. Find the product")
    )
    assert "`/alpha:specify` request; don't settle it here" in areas
    assert "Only `/alpha:specify` settles one" in _router()


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
    for heading in ("## Why", "## Requirements", "## Design", "## Decisions"):
        assert heading in template
    assert "Serves: R<n> in docs/alpha/specification.md" in template
    assert "Research: research.md · Plan: plan.md" in template


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
