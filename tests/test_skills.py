"""The interview skills under skills/: frontmatter, CLI calls, answers fields."""

import argparse
import re
import tomllib
import types
import typing
from dataclasses import is_dataclass

import pytest

from alpha import answers, core_areas
from alpha.cli import PLUGIN_ROOT, build_parser
from alpha.recipes import RecipeBook

SKILLS = PLUGIN_ROOT / "skills"
CLI = '"${CLAUDE_PLUGIN_ROOT}/bin/alpha"'
# skill folder -> (area key in project.json, root field paths the area settles)
AREA_SKILLS: dict[str, tuple[str, tuple[str, ...]]] = {
    "identity": ("identity", ("identity",)),
    "components": ("components", ("layout", "components_talk", "components[]")),
    "architecture": ("architecture", ("architecture",)),
    "errors": ("errors", ("errors",)),
    "testing": ("testing", ("testing",)),
    "documentation": ("documentation", ("documentation",)),
    "build-and-hosting": ("build", ("build",)),
    "security": ("security", ("security",)),
    "dependencies": ("dependencies", ("dependencies",)),
    "observability": ("observability", ("observability",)),
    "git-history": ("git", ("git",)),
    "agent-workflow": ("agent_workflow", ("agent_workflow",)),
}
ALL_SKILLS = ["grilling", *AREA_SKILLS, "stack-recipe", "new-project"]
CLI_SKILLS = ALL_SKILLS  # every skill calls the CLI
ALLOWED_CLI = 'Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)'
AREA_SECTIONS = [
    "Before you start",
    "Purpose",
    "Fields this area settles",
    "Questions",
    "Writing the answers",
    "Check",
]


def _text(skill: str) -> str:
    return (SKILLS / skill / "SKILL.md").read_text()


def _frontmatter(skill: str) -> dict[str, str]:
    lines = _text(skill).splitlines()
    assert lines[0] == "---", f"{skill}: SKILL.md must start with frontmatter"
    end = lines.index("---", 1)
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        assert sep, f"{skill}: frontmatter line {line!r} is not 'key: value'"
        meta[key.strip()] = value.strip()
    return meta


def _section(skill: str, title: str) -> str:
    match = re.search(
        rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", _text(skill), re.M | re.S
    )
    assert match, f"{skill}: missing section '## {title}'"
    return match.group(1)


def _subcommands(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)  # pyright: ignore[reportUnknownArgumentType]
    return {}


def _options(parser: argparse.ArgumentParser) -> set[str]:
    return {flag for action in parser._actions for flag in action.option_strings}


def _calls(skill: str) -> list[str]:
    """Every CLI invocation in a skill's body: the text after the binary up to `."""
    body = _text(skill).split("\n---\n", 1)[1]  # skip allowed-tools
    return re.findall(rf"{re.escape(CLI)} ([^`\n]*)", body)


def _unwrap(hint: object) -> tuple[object, bool]:
    """(element type, is it a list) for X, X | None and tuple[X, ...]."""
    if isinstance(hint, types.UnionType):
        (hint,) = [a for a in typing.get_args(hint) if a is not type(None)]
    if typing.get_origin(hint) is tuple:
        return typing.get_args(hint)[0], True
    return hint, False


def _resolve(path: str) -> object:
    """The type at a project.json path like components[].traits.ml, or fail."""
    hint: object = answers.Answers
    parts = path.split(".")
    for i, part in enumerate(parts):
        name = part.removesuffix("[]")
        if typing.get_origin(hint) is dict:
            assert name in answers.AREAS, f"{path}: {name!r} is not an area"
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
    """Every leaf field path under path; lists of objects written as name[]."""
    hint = _resolve(path)
    if not (isinstance(hint, type) and is_dataclass(hint)):
        return {path}
    out: set[str] = set()
    for name, field_hint in typing.get_type_hints(hint).items():
        element, is_list = _unwrap(field_hint)
        nested = isinstance(element, type) and is_dataclass(element)
        out |= _leaves(f"{path}.{name}" + ("[]" if is_list and nested else ""))
    return out


def _settled_paths(skill: str) -> list[str]:
    """The first `code` span of each bullet in 'Fields this area settles'."""
    section = _section(skill, "Fields this area settles")
    return re.findall(r"^- `([^`]+)`", section, re.M)


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_frontmatter_names_and_describes_the_skill(skill: str):
    meta = _frontmatter(skill)
    assert meta.get("name") == skill
    assert len(meta.get("description", "")) > 40


def test_only_the_entry_point_is_user_invoked_only():
    assert _frontmatter("new-project").get("disable-model-invocation") == "true"


@pytest.mark.parametrize("skill", ["grilling", *AREA_SKILLS])
def test_skills_new_project_calls_stay_model_invocable(skill: str):
    assert "disable-model-invocation" not in _frontmatter(skill)


@pytest.mark.parametrize("skill", AREA_SKILLS)
def test_area_descriptions_only_trigger_inside_an_interview(skill: str):
    description = _frontmatter(skill)["description"]
    assert "Use only inside an alpha project interview (/alpha:new-project)" in (
        description
    )


@pytest.mark.parametrize("skill", CLI_SKILLS)
def test_cli_calls_are_pre_approved(skill: str):
    assert _frontmatter(skill).get("allowed-tools") == ALLOWED_CLI


def test_grilling_credits_its_source_with_the_full_license():
    text = _text("grilling")
    credit = re.search(r"<!--(.*?)-->", text, re.S)
    assert credit and "mattpocock/skills" in credit.group(1)
    assert "Permission is hereby granted, free of charge" in credit.group(1)
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in credit.group(1)


def test_grilling_override_protocol_reads_the_exit_codes():
    text = _text("grilling")
    assert "Make this the default for future projects too?" in text
    for code in ("exits 0", "exits 4", "exits 3"):
        assert code in text
    assert "<target>/.claude/alpha/project.json" in text


def test_every_kind_has_a_recommended_stack():
    kit = tomllib.loads((PLUGIN_ROOT / "defaults" / "defaults.toml").read_text())
    stacks: dict[str, str] = kit["stacks"]
    assert answers.KINDS <= set(stacks)
    assert {stacks[kind] for kind in answers.KINDS} <= set(RecipeBook().kit_stacks())


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_skills_stay_short(skill: str):
    assert len(_text(skill).splitlines()) <= 150


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_cli_is_always_called_through_the_plugin_root(skill: str):
    text = _text(skill)
    names = "|".join(map(re.escape, _subcommands(build_parser())))
    bare = re.findall(rf"(?<![/\w])alpha ({names})\b", text)
    assert not bare, f'{skill}: write "alpha {bare[0]}" as {CLI} {bare[0]}'
    for match in re.finditer(r"bin/alpha", text):
        start = match.start() - len('"${CLAUDE_PLUGIN_ROOT}/')
        assert text[start : match.end() + 1] == CLI, (
            f"{skill}: call the CLI as {CLI}, not {text[start : match.end() + 1]!r}"
        )


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_cli_calls_name_real_subcommands_and_options(skill: str):
    top = _subcommands(build_parser())
    for call in _calls(skill):
        words = call.split()
        assert words[0] in top, f"{skill}: no subcommand {words[0]!r} in: {call}"
        parser = top[words[0]]
        nested = _subcommands(parser)
        if nested:
            assert len(words) > 1 and words[1] in nested, (
                f"{skill}: {words[0]} needs one of {sorted(nested)}: {call}"
            )
            parser = nested[words[1]]
        for flag in re.findall(r"(?<!\S)(--[a-z][a-z-]*)", call):
            assert flag in _options(parser), f"{skill}: unknown {flag} in: {call}"
        for area in re.findall(r"--area (\S+)", call):
            assert area in answers.AREAS, f"{skill}: unknown area {area} in: {call}"


def test_skills_use_every_cli_command_the_interview_needs():
    calls = [" ".join(c.split()[:2]) for s in ALL_SKILLS for c in _calls(s)]
    needed = ["defaults show", "defaults set", "answers check", "answers write"]
    needed += ["generate"]
    needed += ["bootstrap", "commit-skeleton"]
    needed += ["recipe list", "recipe check", "recipe try", "recipe save"]
    for command in needed:
        assert any(c == command or c.startswith(command) for c in calls), command


@pytest.mark.parametrize("skill", AREA_SKILLS)
def test_area_skill_has_every_section_in_order(skill: str):
    for title in AREA_SECTIONS:
        assert _section(skill, title).strip(), f"{skill}: '## {title}' is empty"
    titles = re.findall(r"^## (.+)$", _text(skill), re.M)
    assert titles == AREA_SECTIONS


@pytest.mark.parametrize("skill", AREA_SKILLS)
def test_area_fields_exist_in_the_answers_contract(skill: str):
    paths = _settled_paths(skill)
    assert paths, f"{skill}: list the fields as '- `path` ...' bullets"
    for path in paths:
        _resolve(path)


@pytest.mark.parametrize("skill", AREA_SKILLS)
def test_area_lists_every_field_it_owns(skill: str):
    area, roots = AREA_SKILLS[skill]
    expected = {f"areas.{area}", "decisions[]"}
    for root in roots:
        expected |= _leaves(root)
    assert expected <= set(_settled_paths(skill))


@pytest.mark.parametrize("skill", AREA_SKILLS)
def test_area_checks_its_own_area(skill: str):
    area = AREA_SKILLS[skill][0]
    check = f"{CLI} answers check <target>/.claude/alpha/project.json --area {area}"
    assert check in _text(skill)


def test_new_project_invokes_the_area_skills_in_order():
    text = _text("new-project")
    order = [text.index(f"`alpha:{skill}`") for skill in AREA_SKILLS]
    assert order == sorted(order)
    assert "SKILL.md" not in text, "invoke area skills, don't read their files"
    assert "$ARGUMENTS" in text


def test_new_project_saves_through_the_cli_and_says_what_to_approve():
    # Claude Code asks before every Write/Edit under .claude/ (allow rules
    # can't pre-approve those), so answers are saved with one Bash command
    # the user can allow once.
    start = _section("new-project", "2. Start or resume")
    assert f"{CLI} answers write <target> --json '" in start
    assert "<<" not in start
    assert "don't ask again" in start


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_skills_never_save_answers_with_the_file_tools(skill: str):
    text = _text(skill)
    assert "Write or Edit tool" not in text
    assert "Write tool" not in text.replace("never with the Write tool", "")


@pytest.mark.parametrize("skill", AREA_SKILLS)
def test_area_saves_its_answers_with_answers_write(skill: str):
    section = _section(skill, "Writing the answers")
    # One line: a multi-line (heredoc) command isn't covered by allowed-tools.
    assert f"{CLI} answers write <target> --json '" in section
    assert "<<" not in section


def test_grilling_saves_overrides_with_answers_write():
    protocol = _section("grilling", "When the user overrides a default")
    assert f"{CLI} answers write <target> --json" in protocol
    assert "<<" not in protocol


def test_new_project_saves_summary_changes_with_one_line_json():
    summary = _section("new-project", "5. Summary and confirmation")
    assert f"{CLI} answers write <target> --json '" in summary
    assert "<<" not in summary


def test_every_kind_has_public_paths_and_an_artifact():
    kit = tomllib.loads((PLUGIN_ROOT / "defaults" / "defaults.toml").read_text())
    assert answers.KINDS <= set(kit["documentation"]["public_paths"])
    artifacts = kit["build"]["artifacts"]
    assert answers.KINDS <= set(artifacts)
    assert {artifacts[kind] for kind in answers.KINDS} <= set(answers.ARTIFACTS)
    assert kit["build"]["ci"] in answers.CI_PROVIDERS
    assert kit["documentation"]["external"] in answers.EXTERNAL_DOCS


def test_new_project_creates_every_area_as_pending():
    start = _section("new-project", "2. Start or resume")
    for area in answers.AREAS:
        assert f'"{area}": "pending"' in start
    assert "missing from" in start  # an older interview's new areas


def test_new_project_reports_ci_and_no_longer_lists_these_areas_as_missing():
    report = _section("new-project", "7. Final report")
    assert "CI runs" in report
    not_covered = report.split("**Not covered yet:**")[1].split("\n- **")[0]
    assert "documentation" not in not_covered
    assert "build/CI/hosting" not in not_covered


def test_every_kind_has_an_error_format_and_test_levels():
    kit = tomllib.loads((PLUGIN_ROOT / "defaults" / "defaults.toml").read_text())
    formats = kit["errors"]["formats"]
    levels = kit["testing"]["levels"]
    assert answers.KINDS <= set(formats) and answers.KINDS <= set(levels)
    assert {formats[k] for k in answers.KINDS} <= set(core_areas.ERROR_FORMATS)
    for kind in answers.KINDS:
        assert "unit" in levels[kind]
        assert set(levels[kind]) <= set(core_areas.TEST_LEVELS)
    assert kit["errors"]["categories"]
    assert kit["architecture"]["contract_format"] in core_areas.CONTRACT_FORMATS


def test_every_update_and_observability_default_is_a_choice():
    kit = tomllib.loads((PLUGIN_ROOT / "defaults" / "defaults.toml").read_text())
    assert kit["dependencies"]["updates"] in core_areas.UPDATE_TOOLS
    assert kit["dependencies"]["schedule"] in core_areas.SCHEDULES
    obs = kit["observability"]
    assert obs["log_format"] in core_areas.LOG_FORMATS
    assert obs["correlation"] in core_areas.CORRELATION
    assert obs["telemetry"] in core_areas.TELEMETRY


@pytest.mark.parametrize("skill", AREA_SKILLS)
def test_area_waits_for_the_area_before_it(skill: str):
    area = AREA_SKILLS[skill][0]
    index = answers.AREAS.index(area)
    found = re.findall(
        r"`areas\.(\w+)` isn't `\"done\"`", _section(skill, "Before you start")
    )
    assert found == ([answers.AREAS[index - 1]] if index else [])


def test_new_project_no_longer_lists_the_core_areas_as_missing():
    report = _section("new-project", "7. Final report")
    not_covered = report.split("**Not covered yet:**")[1].split("\n- **")[0]
    for area in ("architecture", "errors", "testing", "security", "dependencies"):
        assert area not in not_covered
    assert "observability" not in not_covered
    assert "Dependabot" in report


def test_agent_workflow_says_the_reviewer_is_real():
    purpose = _section("agent-workflow", "Purpose")
    assert "arrives in a later version" not in purpose
    assert "principles-reviewer" in purpose and "before any push" in purpose


def test_new_project_reports_the_reviewer():
    report = _section("new-project", "7. Final report")
    assert (
        "Claude can't finish, or push, with unreviewed changes past the thresholds "
        "or open review findings; findings you accept are recorded in the decision "
        "log." in report
    )
    not_covered = report.split("**Not covered yet:**")[1].split("\n- **")[0]
    assert "reviewer" not in not_covered


def test_stack_recipe_skill_drafts_checks_and_tries():
    text = _text("stack-recipe")
    assert (
        "Use only inside an alpha project interview"
        in _frontmatter("stack-recipe")["description"]
    )
    for call in ("recipe check <target> <stack>", "recipe try <target> <stack>"):
        assert f"{CLI} {call}" in text
    for field in (
        "bootstrap",
        "commands",
        "templates",
        "test_globs",
        "ci",
        "dependabot",
    ):
        assert f"`{field}`" in text
    assert "less proven" in text


def test_components_offers_any_stack():
    text = _text("components")
    assert "Python** and **TypeScript** only" not in text
    assert f"{CLI} recipe list" in text and "`alpha:stack-recipe`" in text


def test_new_project_offers_to_save_drafted_recipes():
    text = _text("new-project")
    assert f"{CLI} recipe save <target> <stack>" in text
    assert "Save the <stack> recipe to the kit for future projects?" in text
    assert "less proven" in _section("new-project", "7. Final report")
