"""The plugin's skills and the area guides they read (spec, R1, R4, R5,
R7 and R11)."""

import argparse
import re
import tomllib
import types
import typing
from dataclasses import is_dataclass
from pathlib import Path
from typing import cast

import pytest

from alpha import answers, areas, core_areas
from alpha.cli import PLUGIN_ROOT, build_parser
from alpha.recipes import RecipeBook
from alpha.status import status

SKILLS = PLUGIN_ROOT / "skills"
CLI = '"${CLAUDE_PLUGIN_ROOT}/bin/alpha"'
ALLOWED_CLI = 'Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)'
ENTRY = ["install", "update", "uninstall", "purge"]
USER_ONLY = ["install", "uninstall", "purge"]
ALL_SKILLS = ["grilling", "stack-recipe", *ENTRY, "do"]
CLI_SKILLS = [s for s in ALL_SKILLS if s != "do"]
INSTALL_PATHS = ["install/new-project.md", "install/adopt.md"]
INSTALL_GUIDES = [f"install/areas/{a}.md" for a in areas.INSTALL_AREAS]
PRODUCT_GUIDES = [f"install/areas/{a}.md" for a in areas.PRODUCT_AREAS]
GUIDES = INSTALL_GUIDES + PRODUCT_GUIDES
DOCS = [f"{s}/SKILL.md" for s in ALL_SKILLS] + INSTALL_PATHS + GUIDES
# The answers each guide owns, beyond its area's own status.
OWNED: dict[str, tuple[str, ...]] = {
    "components": ("layout", "components_talk", "components[]"),
}
AREA_SECTIONS = [
    "Before you start",
    "Purpose",
    "Fields this area settles",
    "Questions",
    "Writing the answers",
    "Check",
]
STATES = [
    "empty",
    "interview",
    "existing",
    "hooks-off",
    "installed",
    "adopting",
    "uncommitted",
    "not-a-repo",
    "missing",
    "old-kit",
]


def _text(rel: str) -> str:
    return (SKILLS / rel).read_text()


def _frontmatter(skill: str) -> dict[str, str]:
    lines = _text(f"{skill}/SKILL.md").splitlines()
    assert lines[0] == "---", f"{skill}: SKILL.md must start with frontmatter"
    end = lines.index("---", 1)
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        assert sep, f"{skill}: frontmatter line {line!r} is not 'key: value'"
        meta[key.strip()] = value.strip()
    return meta


def _section(rel: str, title: str) -> str:
    match = re.search(
        rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", _text(rel), re.M | re.S
    )
    assert match, f"{rel}: missing section '## {title}'"
    return match.group(1)


def _subcommands(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if action.nargs == argparse.PARSER:
            return cast(dict[str, argparse.ArgumentParser], action.choices)
    return {}


def _options(parser: argparse.ArgumentParser) -> set[str]:
    return {flag for action in parser._actions for flag in action.option_strings}


def _calls(rel: str) -> list[str]:
    text = _text(rel)
    body = text.split("\n---\n", 1)[1] if text.startswith("---\n") else text
    return re.findall(rf"{re.escape(CLI)} ([^`\n]*)", body)


def _unwrap(hint: object) -> tuple[object, bool]:
    if isinstance(hint, types.UnionType):
        (hint,) = [a for a in typing.get_args(hint) if a is not type(None)]
    if typing.get_origin(hint) is tuple:
        return typing.get_args(hint)[0], True
    return hint, False


def _resolve(path: str) -> object:
    hint: object = answers.Answers
    parts = path.split(".")
    for i, part in enumerate(parts):
        name = part.removesuffix("[]")
        if typing.get_origin(hint) is dict:
            assert name in areas.AREAS, f"{path}: {name!r} is not an area"
            hint = str
            continue
        assert isinstance(hint, type) and is_dataclass(hint), (
            f"{path}: {name!r} has no fields below it"
        )
        hints = typing.get_type_hints(hint)
        assert name in hints, f"{path}: {hint.__name__} has no field {name!r}"
        hint, is_list = _unwrap(hints[name])
        if part.endswith("[]") or i < len(parts) - 1:
            kind = "a list, write it as" if is_list else "not a list, drop the [] in"
            assert part.endswith("[]") == is_list, f"{path}: {name!r} is {kind} {part}"
    return hint


def _leaves(path: str) -> set[str]:
    hint = _resolve(path)
    if not (isinstance(hint, type) and is_dataclass(hint)):
        return {path}
    out: set[str] = set()
    for name, field_hint in typing.get_type_hints(hint).items():
        element, is_list = _unwrap(field_hint)
        nested = isinstance(element, type) and is_dataclass(element)
        out |= _leaves(f"{path}.{name}" + ("[]" if is_list and nested else ""))
    return out


def _area(guide: str) -> str:
    return Path(guide).stem


def _settled_paths(guide: str) -> list[str]:
    section = _section(guide, "Fields this area settles")
    return re.findall(r"^- `([^`]+)`", section, re.M)


# --- the named acceptance checks ---


def test_R1_2_install_routes_each_state(tmp_path: Path) -> None:
    table = _section("install/SKILL.md", "1. Target and state")
    named = re.findall(r"^\| ([^|]+) \|", table, re.M)
    routed = {s.strip(" `") for cell in named for s in cell.split(",")}
    assert routed - {"State"} == set(STATES)
    source = (PLUGIN_ROOT / "src/alpha/status.py").read_text()
    for state in STATES:
        assert f'Status("{state}"' in source or f'"{state}"' in source, state
    assert status(tmp_path / "nowhere").name == "missing"
    assert f"{CLI} status <target>" in table


def test_R1_4_install_turns_hooks_on_without_asking() -> None:
    row = next(
        line
        for line in _section("install/SKILL.md", "1. Target and state").splitlines()
        if line.startswith("| `hooks-off`")
    )
    assert f"{CLI} hooks on <target>` without asking" in row
    assert "It commits nothing." in row


def test_R1_5_install_works_the_plan() -> None:
    row = next(
        line
        for line in _section("install/SKILL.md", "1. Target and state").splitlines()
        if line.startswith("| `installed`")
    )
    assert "adoption plan's next step" in row and "The plan" in row
    plan = _section("install/adopt.md", "The plan")
    order = ["adopt next", "adopt start", "update <target>", "adopt done"]
    found = [plan.index(f"{CLI} {command}") for command in order]
    assert found == sorted(found)
    assert "Never set a step's status any other way" in plan


def test_R5_2_install_offers_each_product_area_defaulting_to_skip() -> None:
    rules = _section("install/SKILL.md", "Rules for every path")
    listed = re.findall(r"`(\w+)\.md`", rules)
    assert listed == list(areas.INSTALL_AREAS)
    assert "settle one only when the user picks it" in rules
    assert "covers only the install areas" not in rules
    assert "In the install areas, what the project is about may be asked" in rules
    interview = _section("install/new-project.md", "3. Interview, area by area")
    offer = interview.split("Then offer the product areas")[1]
    assert "one question per area" in offer
    assert "settle it right away, before the next question" in offer
    assert "Skip for now (Recommended)" in offer and "Settle now" in offer
    assert "as `/alpha:update` step 3 says" in offer
    assert "`/alpha:update <area>`" in offer
    for unless in ("has a UI", "deployed", "stores data or does ML"):
        assert unless in offer, unless
    summary = _section("install/new-project.md", "4. Summary and confirmation")
    assert "the settled product areas" in summary
    for rel, title in (
        ("install/new-project.md", "1. Start or resume"),
        ("install/adopt.md", "1. Resume"),
    ):
        resume = _section(rel, title)
        assert "finish a product area marked `in_progress`" in resume, rel
        assert "offer the ones after the last product area settled" in resume, rel
    adopt = _section("install/adopt.md", "4. Interview")
    assert "offer the product areas as `new-project.md` step 3 says" in adopt
    assert "recommend Settle now for an area the repo's docs describe" in adopt
    for guide in PRODUCT_GUIDES:
        start = _section(guide, "Before you start")
        assert "and `/alpha:install` when the user picks it" in start, guide
        assert "Their rules win over this guide's" in start, guide


def test_R7_2_only_install_and_update_settle_product_areas() -> None:
    assert sorted(p.name for p in (SKILLS / "install/areas").iterdir()) == sorted(
        f"{a}.md" for a in areas.AREAS
    )
    for gone in ("extend", "specify"):
        assert not (SKILLS / gone).exists(), gone
    playbooks = [
        f"do/playbooks/{p.name}" for p in (SKILLS / "do/playbooks").glob("*.md")
    ]
    readers = [
        rel
        for rel in [*DOCS, *playbooks]
        if "areas/" in _text(rel) and not rel.startswith(("install/", "update/"))
    ]
    assert readers == []
    for guide in PRODUCT_GUIDES:
        start = _section(guide, "Before you start")
        assert "`/alpha:update` reads this guide" in start, guide
        assert "Only `/alpha:install` and `/alpha:update` settle a product area" in (
            start
        ), guide


def test_R4_1_update_changes_a_component_or_an_install_answer() -> None:
    change = _section("update/SKILL.md", "4. Change a component or an install answer")
    for part in (
        "${CLAUDE_PLUGIN_ROOT}/skills/install/areas/<area>.md",
        "send the whole `overrides` array",
        "`git mv`",
        'as "Reading a dry run" says',
    ):
        assert part in change, part
    text = _text("update/SKILL.md")
    assert f"{CLI} bootstrap <target> --component <name>" in text
    assert "offer the git area" in change


def test_R7_1_update_settles_the_named_product_areas() -> None:
    settle = _section("update/SKILL.md", "3. Settle a product area")
    for part in (
        "${CLAUDE_PLUGIN_ROOT}/skills/install/areas/<area>.md",
        "Research first",
        "two or three options",
        "`alpha:grilling`",
        "`done`",
        f"{CLI} defaults show --json",
    ):
        assert part in settle, part


def test_update_reads_every_dry_run_the_same_way() -> None:
    """Each refusal the CLI prints has one instruction, whichever step ran
    the dry run; a no at the preview gives the user a way out."""
    reading = _section("update/SKILL.md", "Reading a dry run")
    for refusal in (
        "an update is waiting to be committed",
        "Revisit the `<area>` area",
        "Fix .claude/alpha/project.json",
        "Any other refusal",
    ):
        assert refusal in reading, refusal
    for title in ("1. Target and checks", "5. Preview and confirm"):
        assert 'as "Reading a dry run" says' in _section("update/SKILL.md", title)
    start = _section("update/SKILL.md", "1. Target and checks")
    assert "applied together with the request" in start
    assert "apply them first" not in start
    assert "an area or a component name is never the target" in start
    preview = _section("update/SKILL.md", "5. Preview and confirm")
    assert "unless step 4 just ran it" not in preview
    assert "On a no" in preview
    assert "git show HEAD:.claude/alpha/project.json" in preview
    assert "check they say what the user settled" in preview
    merge = _section("update/SKILL.md", "6. Apply and merge")
    assert "check they say what the user settled" not in merge
    bootstrap = _section("update/SKILL.md", "7. Bootstrap")
    assert "`path` differs from its `path` in `git show HEAD:" in bootstrap


def test_R11_4_update_routes_each_kind_of_request() -> None:
    route = _section("update/SKILL.md", "2. Route the request")
    rows = re.findall(r"^\| ([^|]+) \| ([^|]+) \|$", route, re.M)
    kinds = [kind.strip() for kind, _ in rows[1:]]
    assert [k.split(":")[0] for k in kinds] == [
        "Empty",
        "A product area",
        "A component or an install answer",
        "Several of these",
        "Unclear",
    ]
    jobs = dict(zip(kinds, (job.strip() for _, job in rows[1:]), strict=True))
    assert jobs["Empty"].startswith("Sync")
    product = next(k for k in kinds if k.startswith("A product area"))
    for area in areas.PRODUCT_AREAS:
        assert area.replace("_", " ") in product.lower(), area
    calls = _calls("update/SKILL.md")
    assert calls.count("update <target>") == 1
    assert [c for c in calls if c.startswith("commit <target>")] == [
        'commit <target> --trailer "<line>"'
    ]
    assert "steps 5 to 9 once" in jobs["Several of these"]


def test_R11_3_update_skill_merges_proposals() -> None:
    text = _text("update/SKILL.md")
    order = ["update <target> --dry-run", "update <target>`.", "commit <target>"]
    found = [text.index(f"{CLI} {command}") for command in order]
    assert found == sorted(found)
    preview = _section("update/SKILL.md", "5. Preview and confirm")
    assert "the project is up to date, and stop" in preview
    assert "wait for a clear yes" in preview
    merge = _section("update/SKILL.md", "6. Apply and merge")
    assert "keeps both sides" in merge and "Never take only alpha's side" in merge
    assert ".claude/alpha/state/update/<path>" in merge


# --- every skill ---


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_frontmatter_names_and_describes_the_skill(skill: str) -> None:
    meta = _frontmatter(skill)
    assert meta.get("name") == skill
    assert len(meta.get("description", "")) > 40


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_only_install_uninstall_and_purge_are_user_invoked_only(skill: str) -> None:
    flag = _frontmatter(skill).get("disable-model-invocation")
    assert flag == ("true" if skill in USER_ONLY else None)
    if skill in ("uninstall", "purge"):
        assert "Run only when the user asks" in _frontmatter(skill)["description"]


@pytest.mark.parametrize("skill", CLI_SKILLS)
def test_cli_calls_are_pre_approved(skill: str) -> None:
    assert _frontmatter(skill).get("allowed-tools") == ALLOWED_CLI


@pytest.mark.parametrize("rel", DOCS)
def test_docs_stay_short(rel: str) -> None:
    assert len(_text(rel).splitlines()) <= 150


@pytest.mark.parametrize("rel", DOCS)
def test_cli_is_always_called_through_the_plugin_root(rel: str) -> None:
    text = _text(rel)
    names = "|".join(map(re.escape, _subcommands(build_parser())))
    bare = re.findall(rf"(?<![/\w])alpha ({names})\b", text)
    assert not bare, f'{rel}: write "alpha {bare[0]}" as {CLI} {bare[0]}'
    for match in re.finditer(r"bin/alpha", text):
        start = match.start() - len('"${CLAUDE_PLUGIN_ROOT}/')
        assert text[start : match.end() + 1] == CLI, (
            f"{rel}: call the CLI as {CLI}, not {text[start : match.end() + 1]!r}"
        )


@pytest.mark.parametrize("rel", DOCS)
def test_cli_calls_name_real_subcommands_and_options(rel: str) -> None:
    top = _subcommands(build_parser())
    for call in _calls(rel):
        words = call.split()
        assert words[0] in top, f"{rel}: no subcommand {words[0]!r} in: {call}"
        parser = top[words[0]]
        nested = _subcommands(parser)
        if nested:
            assert len(words) > 1 and words[1] in nested, (
                f"{rel}: {words[0]} needs one of {sorted(nested)}: {call}"
            )
            parser = nested[words[1]]
        for flag in re.findall(r"(?<!\S)(--[a-z][a-z-]*)", call):
            assert flag in _options(parser), f"{rel}: unknown {flag} in: {call}"
        for area in re.findall(r"--area (\S+)", call):
            assert area in areas.AREAS, f"{rel}: unknown area {area} in: {call}"


def test_skills_use_every_cli_command_alpha_needs() -> None:
    calls = [" ".join(c.split()[:2]) for rel in DOCS for c in _calls(rel)]
    needed = ["status <target>", "hooks on", "uninstall <target>", "purge <target>"]
    needed += ["defaults show", "defaults set", "answers check", "answers write"]
    needed += ["apply <target>", "update <target>", "bootstrap <target>"]
    needed += ["commit <target>", "recipe list", "recipe check", "recipe try"]
    needed += ["recipe save", "adopt survey", "adopt gaps", "baseline show"]
    for command in needed:
        assert any(c == command or c.startswith(command) for c in calls), command


@pytest.mark.parametrize("rel", DOCS)
def test_docs_never_save_answers_with_the_file_tools(rel: str) -> None:
    text = _text(rel)
    assert "Write or Edit tool" not in text
    assert "Write tool" not in text.replace("never with the Write tool", "")


@pytest.mark.parametrize("rel", ["install/SKILL.md", "update/SKILL.md"])
def test_entry_skills_ask_one_question_at_a_time(rel: str) -> None:
    text = _text(rel)
    assert (
        'Ask one question at a time, as the `alpha:grilling` skill\'s "Rounds" says:'
        " a choice, a yes or no or "
    ) in text
    assert (
        " in the `AskUserQuestion` dialog when that tool is in your tool list,"
        " a draft for the user to edit in plain text."
    ) in text


@pytest.mark.parametrize("rel", ["install/SKILL.md", "update/SKILL.md"])
def test_answers_are_saved_with_one_line_answers_write(rel: str) -> None:
    text = _text(rel)
    assert f"{CLI} answers write <target> --json '<object>'" in text
    assert "never a heredoc" in text and "<<" not in text


REMOVED = re.compile(
    r"docs/(product|architecture|build|security|releases|ui|data|performance"
    r"|observability)\.md|/alpha:new-project|/alpha:adopt\b|alpha:adopt\b|/alpha:go\b"
    r"|/alpha:extend\b|/alpha:specify\b"
)
REMOVED_COMMANDS = re.compile(r"/alpha:(extend|specify)\b")


def test_no_kit_file_names_a_removed_doc_or_skill() -> None:
    shipped = [
        p
        for folder in ("skills", "project-files", "recipes", "src", "defaults")
        for p in (PLUGIN_ROOT / folder).rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    ]
    assert len(shipped) > 50
    named = [str(p) for p in shipped if REMOVED.search(p.read_text())]
    assert not named, named
    for doc in ("README.md", "docs/specification.md"):
        assert not REMOVED_COMMANDS.search((PLUGIN_ROOT / doc).read_text()), doc


# --- install, update, uninstall, purge ---


def test_new_project_creates_install_areas_pending_and_product_areas_open() -> None:
    start = _section("install/new-project.md", "1. Start or resume")
    for area in areas.INSTALL_AREAS:
        assert f'"{area}": "pending"' in start
    for area in areas.PRODUCT_AREAS:
        assert f'"{area}": "open"' in start


def test_new_project_runs_apply_bootstrap_commit_in_order() -> None:
    text = _text("install/new-project.md")
    order = ["answers check", "apply <target>", "bootstrap <target>", "commit <target>"]
    found = [text.index(f"{CLI} {command}") for command in order]
    assert found == sorted(found)
    assert "Save the <stack> recipe for your future projects?" in text
    assert f"{CLI} recipe save <target> <stack>" in text


def test_the_final_report_names_the_review_at_merge_and_uninstall() -> None:
    report = _section("install/new-project.md", "6. Final report")
    assert "Before its work reaches main" in report
    assert 'a finding on a risk path needs your "accept"' in report
    assert "batched" not in report
    assert "Only `/alpha:uninstall` switches these hooks off" in report
    assert "`/alpha:update <area>` request" in report


def test_adopt_installs_in_order() -> None:
    calls = [" ".join(c.split()[:2]) for c in _calls("install/adopt.md")]
    order = ["adopt survey", "adopt gaps", "apply <target>", "bootstrap <target>"]
    order += ["commit <target>"]
    found = [next(i for i, c in enumerate(calls) if c == step) for step in order]
    assert found == sorted(found), calls
    text = _text("install/adopt.md")
    assert text.index("apply <target> --dry-run") < text.index("apply <target>`.")
    assert "--capture-baselines" in text


def test_adopt_records_the_chain_markers_and_existing_docs() -> None:
    interview = _section("install/adopt.md", "4. Interview")
    assert "`# alpha:begin` and `# alpha:end`" in interview
    assert "`documentation.existing`" in interview
    assert "It gets no adopted recipe and no baselines" in interview


def test_uninstall_and_purge_say_what_they_keep() -> None:
    uninstall = _text("uninstall/SKILL.md")
    assert f"{CLI} uninstall <target>" in uninstall
    assert "deletes no file and commits nothing" in uninstall
    purge = _text("purge/SKILL.md")
    assert f"{CLI} purge <target> --trailer" in purge
    assert "wait for a clear yes" in purge


# --- area guides ---


@pytest.mark.parametrize("guide", GUIDES)
def test_guide_has_every_section_in_order(guide: str) -> None:
    for title in AREA_SECTIONS:
        assert _section(guide, title).strip(), f"{guide}: '## {title}' is empty"
    assert re.findall(r"^## (.+)$", _text(guide), re.M) == AREA_SECTIONS
    assert not _text(guide).startswith("---"), "a guide isn't a skill"


@pytest.mark.parametrize("guide", GUIDES)
def test_guide_fields_exist_in_the_answers_contract(guide: str) -> None:
    paths = _settled_paths(guide)
    assert paths, f"{guide}: list the fields as '- `path` ...' bullets"
    for path in paths:
        _resolve(path)


@pytest.mark.parametrize("guide", GUIDES)
def test_guide_lists_every_field_it_owns(guide: str) -> None:
    area = _area(guide)
    expected = {f"areas.{area}"}
    for root in OWNED.get(area, (area,)):
        expected |= _leaves(root)
    assert expected <= set(_settled_paths(guide))


@pytest.mark.parametrize("guide", GUIDES)
def test_guide_saves_and_checks_its_own_area(guide: str) -> None:
    area = _area(guide)
    writing = _section(guide, "Writing the answers")
    assert f"{CLI} answers write <target> --json '" in writing
    assert "<<" not in writing
    check = f"{CLI} answers check <target>/.claude/alpha/project.json --area {area}"
    assert check in _text(guide)


@pytest.mark.parametrize("guide", INSTALL_GUIDES)
def test_install_guides_hand_control_to_install_and_update(guide: str) -> None:
    start = _section(guide, "Before you start")
    assert "`/alpha:install` reads this guide" in start
    assert "`/alpha:update`" in start


@pytest.mark.parametrize(
    "guide",
    [
        "install/areas/design_language.md",
        "install/areas/ui.md",
        "install/areas/accessibility.md",
        "install/areas/data.md",
    ],
)
def test_areas_that_may_not_apply_ask_nothing(guide: str) -> None:
    assert "ask nothing" in _section(guide, "Questions")


def test_data_guide_explains_the_append_only_rule() -> None:
    text = _text("install/areas/data.md")
    assert "append-only" in text and "Stop hook" in text


def test_components_offers_any_stack() -> None:
    text = _text("install/areas/components.md")
    assert f"{CLI} recipe list" in text and "`alpha:stack-recipe`" in text


def test_agent_workflow_says_the_reviewer_runs_before_main() -> None:
    purpose = _section("install/areas/agent_workflow.md", "Purpose")
    assert "principles-reviewer" in purpose and "before work reaches main" in purpose


def test_design_language_is_the_users_to_skip() -> None:
    questions = _section("install/areas/design_language.md", "Questions")
    assert "Either answer is fine; never argue for one." in questions
    assert 'save `{"defined": false}`' in questions
    assert "Don't suggest colors, typefaces or diagram styles anywhere later" in (
        questions
    )
    purpose = _section("install/areas/design_language.md", "Purpose")
    assert "enforces and recommends nothing" in purpose
    assert "When `design_language.defined` is true" in _section(
        "install/areas/ui.md", "Questions"
    )
    assert "In an adoption, never recommend `enforce`" in questions
    assert "key `design_language.palette_check`" in questions


# --- grilling and stack-recipe ---


EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿⬀-⯿️]")


def test_grilling_credits_its_source_with_the_full_license() -> None:
    text = _text("grilling/SKILL.md")
    credit = re.search(r"<!--(.*?)-->", text, re.S)
    assert credit and "mattpocock/skills" in credit.group(1)
    assert "Permission is hereby granted, free of charge" in credit.group(1)
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in credit.group(1)


def test_grilling_asks_one_question_at_a_time() -> None:
    rounds = _section("grilling/SKILL.md", "Rounds")
    assert "asked **one question at a time**" in rounds
    assert (
        "headless, and no person is waiting), ask the whole round in one message"
        in (rounds)
    )
    dialog, plain = rounds.split("### A choice: in the dialog")[1].split(
        "### A draft: in plain text"
    )
    assert "the `AskUserQuestion` tool is in your tool list" in dialog
    for limit in ("One question per call.", "2 to 4 options", "at most 12 characters"):
        assert limit in dialog
    assert '" (Recommended)"' in dialog and 'Never add an "Other" option' in dialog
    assert "when the tool isn't in your tool list" in plain


def test_grilling_plain_text_question_ends_with_the_recommendation() -> None:
    rounds = _section("grilling/SKILL.md", "Rounds")
    template = re.search(r"```text\n(.*?)```", rounds, re.S)
    assert template
    lines = template.group(1).strip().splitlines()
    assert len(re.findall(r"\*\*Q\d+\.", template.group(1))) == 1
    assert lines[-1].startswith("Recommended: ")
    assert not EMOJI.search(rounds)
    assert "End the question with the `Recommended:` line" in rounds


def test_grilling_override_protocol_reads_the_exit_codes() -> None:
    text = _text("grilling/SKILL.md")
    assert "Make this the default for future projects too?" in text
    for code in ("exits 0", "exits 3"):
        assert code in text
    protocol = _section("grilling/SKILL.md", "When the user overrides a default")
    assert f"{CLI} answers write <target> --json" in protocol


def test_stack_recipe_drafts_checks_tries_and_adopts() -> None:
    text = _text("stack-recipe/SKILL.md")
    assert "/alpha:install" in _frontmatter("stack-recipe")["description"]
    for call in ("recipe check <target> <stack>", "recipe try <target> <stack>"):
        assert f"{CLI} {call}" in text
    for field in ("bootstrap", "commands", "templates", "test_globs", "ci"):
        assert f"`{field}`" in text
    assert "less proven" in text
    adopting = _section("stack-recipe/SKILL.md", "Adopting a repo's tools")
    for needed in ('"adopted": true', '"extends"', "[baseline.<step>]", "recipe try"):
        assert needed in adopting, needed
    steps = _section("stack-recipe/SKILL.md", "Steps")
    assert f"{CLI} registry list --stack <stack>" in steps


# --- the kit defaults the guides recommend from ---


def test_every_kind_has_its_defaults() -> None:
    kit = tomllib.loads((PLUGIN_ROOT / "defaults" / "defaults.toml").read_text())
    stacks: dict[str, str] = kit["stacks"]
    assert answers.KINDS <= set(stacks)
    assert {stacks[kind] for kind in answers.KINDS} <= set(RecipeBook().kit_stacks())
    assert answers.KINDS <= set(kit["documentation"]["public_paths"])
    artifacts = kit["build"]["artifacts"]
    assert {artifacts[kind] for kind in answers.KINDS} <= set(answers.ARTIFACTS)
    formats, levels = kit["errors"]["formats"], kit["testing"]["levels"]
    assert {formats[k] for k in answers.KINDS} <= set(core_areas.ERROR_FORMATS)
    for kind in answers.KINDS:
        assert "unit" in levels[kind]
        assert set(levels[kind]) <= set(core_areas.TEST_LEVELS)
        for budget in kit["performance"]["budgets"][kind]:
            assert " < " in budget, f"{kind}: write budgets as '<metric> < <limit>'"


def test_every_default_is_a_choice_the_guides_offer() -> None:
    kit = tomllib.loads((PLUGIN_ROOT / "defaults" / "defaults.toml").read_text())
    assert kit["build"]["ci"] in answers.CI_PROVIDERS
    assert kit["documentation"]["external"] in answers.EXTERNAL_DOCS
    assert kit["architecture"]["contract_format"] in core_areas.CONTRACT_FORMATS
    assert kit["dependencies"]["updates"] in core_areas.UPDATE_TOOLS
    assert kit["dependencies"]["schedule"] in core_areas.SCHEDULES
    obs = kit["observability"]
    assert obs["log_format"] in core_areas.LOG_FORMATS
    assert obs["correlation"] in core_areas.CORRELATION
    assert obs["telemetry"] in core_areas.TELEMETRY
    assert kit["ui"]["theming"] in core_areas.THEMING
    assert kit["accessibility"]["level"] in core_areas.A11Y_LEVELS
    releases = kit["releases"]
    assert releases["scheme"] in core_areas.SCHEMES
    assert releases["changelog"] in core_areas.CHANGELOGS
    assert releases["scope"] in core_areas.RELEASE_SCOPES
    assert kit["design_language"]["palette_check"] in core_areas.PALETTE_CHECKS


# --- the copied reviewer ---


@pytest.mark.parametrize(
    ("path", "source"),
    [
        ("project-files/skills/review-change/SKILL.md", "ponytail-review"),
        ("project-files/skills/audit/SKILL.md", "ponytail-audit"),
        ("project-files/agents/principles-reviewer.md", "ponytail-review"),
    ],
)
def test_ponytail_adaptations_credit_it_with_the_full_license(
    path: str, source: str
) -> None:
    text = (PLUGIN_ROOT / path).read_text()
    credit = re.search(r"<!--(.*?)-->", text, re.S)
    assert credit and f"`{source}` skill" in credit.group(1)
    assert "Copyright (c) 2026 DietrichGebert" in credit.group(1)
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in credit.group(1)


def test_the_reviewer_needs_a_concrete_case_and_checks_visuals() -> None:
    text = (PLUGIN_ROOT / "project-files/agents/principles-reviewer.md").read_text()
    assert "No case, no finding." in text
    for lens in ("lens:bug", "lens:risk", "lens:scale", "lens:speed", "lens:lean"):
        assert lens in text
    assert "When the brief lists `design-language`" in text
    assert "The design language guides, it isn't a wall" in text
