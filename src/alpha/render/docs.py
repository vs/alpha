from collections.abc import Mapping
from datetime import date
from pathlib import Path
from string import Template
from typing import Any

from alpha.answers import (
    DESIGN_LANGUAGE_DOC,
    Answers,
    Component,
    Documentation,
    Identity,
)
from alpha.recipes import OPTIONAL_STEPS, check_commands
from alpha.registry import Registry, default_registry
from alpha.render import area_docs
from alpha.render.ci import WORKFLOW
from alpha.render.markdown import row
from alpha.repo_checks import CI_STEPS, RepoCheck, repo_checks

LICENSES_DIR = Path(__file__).resolve().parents[1] / "licenses"
_STEPS = ("setup", "test", "lint", "format", "format_check", "typecheck", "structure")
_DONE = (
    "Tests written and passing.",
    "Types and lint clean.",
    "Docs updated.",
    "Committed per the commit convention.",
    "Reviewed before it reaches main.",
)
_WORKING_RULES = (
    "- Before you change code, docs or config, read the parts of "
    "docs/alpha/specification.md and CONTRIBUTING.md that bear on the change and the "
    "principle's parameters in docs/alpha/principles.toml. Follow them.",
    "- A decision updates the docs, as the decision skill says: what the product "
    "does goes in docs/alpha/specification.md and needs the user's yes; how the work "
    "is done goes in CONTRIBUTING.md, with the reason in the commit; a changed "
    "principle is an override in the answers, which the user agrees to first.",
    "- When a requirement is ambiguous, make the reasonable choice, record it "
    "with the decision skill and say what you chose; don't stop to ask about "
    "reversible work. Ask first only about product direction or what can't be "
    "undone (rewriting main, deploys, deleting data, messages to people).",
    "- Read a file in full before you edit it, and every file a wide change "
    "touches; search snippets aren't enough.",
    "- Look up a dependency's API in its installed source or types instead of "
    "guessing it.",
    "- Remove dead code and replaced internal APIs without asking, but ask "
    "before removing code or behavior that looks intentional.",
    "- Commit only the files you changed for the work, staged by path. Other "
    "changes in the tree may be the user's or another session's, so don't stage, "
    "stash or reset them.",
    "- Subagents work under the same principles, docs and checks.",
    "- Run `/alpha:uninstall` or `/alpha:purge` only when the user asks for it.",
    "- Before you report work as done, re-read every changed file top to bottom "
    "as a stranger would.",
    "- Run the principles-reviewer agent once, before your work reaches main: "
    "the merge guard asks for it, and it reviews only what changed since its "
    "last review.",
)
_TEST_RUN = (
    "The hooks leave the full test suites to one checkpoint: before your "
    "work reaches main (a push to main, or merging a pull request), run "
    "`python3 .claude/alpha/hooks/stop_checks.py tests`. It runs the suite "
    "of each component you changed and remembers a pass until those files "
    "change. While you work, run the tests your change touches."
)
_COMMUNICATION = (
    "- Answer a question before making edits or running commands for it.",
    "- When responding to feedback or a review, say first whether you agree, "
    "then what you changed.",
    "- Be concise and direct: plain technical prose, no filler, no emojis. "
    "Define jargon you can't avoid.",
    "- Explain a non-trivial problem or design as the problem, a concrete example "
    "or short trace, then the solution and why it's needed.",
    "- When you report finished work, end with one or two lines: what you skipped "
    "or didn't check, and any risk the user must know.",
)
_GENERATOR_RULE = (
    "- When you add a code generator, add a `generate` task to `mise.toml` and to "
    "the `ci` task's `depends`; "
)
_GENERATOR_WITH_CI = "CI fails when checks change tracked files."
_GENERATOR_WITHOUT_CI = "commit what it regenerates with the change."
_CHECK_RULES = (
    "- Never disable a lint rule to pass; an exception names one path and one "
    "rule, and a row in CONTRIBUTING.md's Exceptions table names that path, "
    "the rule and the reason.",
    "- A security suppression (osv-scanner, betterleaks) needs a reason and a "
    "review date: in the `osv-scanner.toml` next to the lockfile it applies "
    "to, `ignoreUntil` and `reason`; in "
    "`.betterleaksignore`, a `# <reason> (review YYYY-MM-DD)` line directly "
    "above the entry.",
)
_BRANCHING = {
    "trunk": "Trunk-based: small commits straight to the main branch, "
    "each leaving the checks green.",
    "feature-branches": "Feature branches: short-lived branches merged into main "
    "through pull requests, each leaving the checks green. Before opening a pull "
    "request, rebase the branch on main into small, ordered commits and push it "
    "with --force-with-lease; the hooks block a plain --force and any rewrite "
    "of main.",
}


def _identity(a: Answers) -> Identity:
    assert a.identity is not None
    return a.identity


def _traits(c: Component) -> str:
    names = [k for k, v in vars(c.traits).items() if v]
    return ", ".join(names) or "none"


def _license(a: Answers, year: int, root: Path) -> str:
    ident = _identity(a)
    if ident.license_file is not None:
        return (root / ident.license_file).read_text()
    if ident.license == "Proprietary":
        return f"Copyright (c) {year} {ident.copyright_holder}. All rights reserved.\n"
    text = (LICENSES_DIR / f"{ident.license}.txt").read_text()
    return Template(text).safe_substitute(year=year, holder=ident.copyright_holder)


def _documentation(a: Answers) -> Documentation:
    assert a.documentation is not None
    return a.documentation


def _external(docs: Documentation) -> str:
    if docs.external == "readme":
        return "User-facing documentation lives in README.md."
    if docs.external == "folder":
        return f"User-facing documentation lives in `{docs.external_path}/`."
    if docs.external == "elsewhere":
        return (
            "User-facing documentation lives outside this repository: "
            f"{docs.external_location}."
        )
    return "There is no user-facing documentation."


def _docs_section(docs: Documentation) -> list[str]:
    lines = [
        "## Documentation",
        "",
        "alpha's docs (the specification, the principles, the dependency log) "
        "live in `docs/alpha/`. " + _external(docs),
        "",
    ]
    if docs.mappings:
        lines += ["| When these change | Update |", "|---|---|"]
        lines += [
            row(_ticked(list(m.paths)), _ticked(list(m.docs))) for m in docs.mappings
        ]
        lines += [
            "",
            "The Stop hook blocks a change to these paths that leaves the docs "
            "untouched.",
            "",
        ]
    return lines


def _build_section(a: Answers, principles: dict[str, Any]) -> list[str]:
    assert a.build is not None
    lines = ["## Build, CI and hosting", "", "### CI", ""]
    if a.build.ci == "none":
        lines.append("No CI: see build-hosting-upfront under Overrides below.")
    else:
        lines += [
            f"GitHub Actions runs `{WORKFLOW}` on every push to main and every "
            "pull request: one job per component, running its checks in order.",
            "",
            "| Component | Checks |",
            "|---|---|",
        ]
        lines += [
            row(
                c["name"],
                ", ".join(f"`{cmd}`" for _, cmd in check_commands(c["commands"])),
            )
            for c in principles["components"]
        ]
    lines += ["", "### Artifacts and hosting", "", "| Component | Artifact | Hosting |"]
    lines.append("|---|---|---|")
    lines += [row(t.name, t.artifact, t.hosting or "-") for t in a.build.components]
    lines += ["", "### Environments", ""]
    if a.build.environments:
        lines += [f"- {env}" for env in a.build.environments]
    else:
        lines.append("None: nothing is deployed.")
    lines += [
        "",
        "Hosting is decided and documented here; alpha creates no cloud resources "
        "and no deploy jobs.",
    ]
    return lines


def _ticked(globs: list[str]) -> str:
    return ", ".join(f"`{g}`" for g in globs)


def _not_code(a: Answers) -> list[str]:
    if not a.not_code:
        return []
    folders = ", ".join(f"`{f}/`" for f in a.not_code)
    return [
        f"Not code: {folders}: examples, fixtures and reference data. No format, "
        "lint, test or docs rule and no principles review applies there; the "
        "secrets scan and the repository's text checks (spelling, Markdown, links) "
        "still do.",
        "",
    ]


def _command_table(c: Component, comp: dict[str, Any]) -> list[str]:
    commands: dict[str, str] = comp["commands"]
    rows = [
        f"### {c.name} ({c.stack}, `{c.path}/`)",
        "",
        f"Code: {_ticked(comp['source_globs'])}. "
        f"Tests: {_ticked(comp['test_globs'])}. "
        f"Not checked: {_ticked(comp['exclude_globs'])}.",
        "",
        "| Step | Command |",
        "|---|---|",
    ]
    rows += [
        row(s, f"`{commands[s]}`")
        for s in _STEPS
        if commands.get(s) or s not in OPTIONAL_STEPS
    ]
    run = commands["run"]
    rows.append(
        row("run", f"`{run}`") if run else "| run | add when the entry point exists |"
    )
    return rows


def _stack_rules(principles: dict[str, Any]) -> list[str]:
    by_stack: dict[str, list[dict[str, Any]]] = {}
    for comp in principles["components"]:
        by_stack.setdefault(comp["stack"], []).append(comp)
    lines: list[str] = []
    for stack, comps in by_stack.items():
        rules: list[dict[str, str]] = comps[0]["rules"]
        if rules:
            names = ", ".join(c["name"] for c in comps)
            lines += [f"### {stack} ({names})", ""]
            lines += [f"- **{r['id']}**: {r['rule']}" for r in rules] + [""]
    if not lines:
        return []
    return ["## Stack rules", "", *lines]


def _claude_md(a: Answers, principles: dict[str, Any]) -> str:
    ident = _identity(a)
    assert a.git is not None
    has_ci = a.build is not None and a.build.ci != "none"
    lines = [f"# {ident.name}", "", ident.value_proposition, "", "## Principles", ""]
    lines += [
        f"- **{p['title']}**: {p['statement']}"
        + (" (overridden: see CONTRIBUTING.md, Overrides)" if p["override"] else "")
        for p in principles["principles"]
        if p["active"]
    ]
    lines += [
        "",
        "`docs/alpha/principles.toml` is the source of truth, with each principle's "
        "parameters, rationale and overrides.",
        "",
        "## Working rules",
        "",
        *_WORKING_RULES,
        _GENERATOR_RULE + (_GENERATOR_WITH_CI if has_ci else _GENERATOR_WITHOUT_CI),
        *_CHECK_RULES,
        "",
        "## Communication",
        "",
        *_COMMUNICATION,
        "",
        *_stack_rules(principles),
        "## Commands",
        "",
    ]
    for comp in principles["components"]:
        c = next(x for x in a.components if x.name == comp["name"])
        lines += _command_table(c, comp) + [""]
    lines += _not_code(a)
    lines += [
        "Run every check: `mise run check`"
        + (" (CI runs the same checks)." if has_ci else "."),
        "",
        _TEST_RUN,
        "",
    ]
    scopes = ", ".join([*a.git.scopes, "or another area it touches"])
    lines += ["## Definition of done", ""]
    lines += [f"{i}. {item}" for i, item in enumerate(_DONE, 1)]
    lines += [
        "",
        "## Commits",
        "",
        "Follow the commit skill (`.claude/skills/commit/SKILL.md`, which "
        "the user runs as /commit). "
        f"Convention: {a.git.convention} commits, "
        f"scopes: {scopes if a.git.scopes else 'any'}, "
        "enforced by the commit-msg hook."
        + (
            " Work on a short-lived branch and open a pull request into main; "
            "don't commit to main directly."
            if a.git.branching == "feature-branches"
            else ""
        ),
        "",
        "## Docs",
        "",
        "- [Principles](docs/alpha/principles.toml)",
        "- [Specification](docs/alpha/specification.md): what the product does; "
        "`/alpha:update <area>` settles each open part, and each full-track task gets "
        "a folder in `docs/alpha/features/`, `docs/alpha/bug-fixes/`, "
        "`docs/alpha/refactorings/` or `docs/alpha/perf/`",
        "- [Contributing](CONTRIBUTING.md): how the project is built, checked, "
        "released and kept secure",
        "- [Dependencies](docs/alpha/dependencies.md)",
    ]
    docs = _documentation(a)
    if docs.external == "folder":
        lines.append(f"- User guide: `{docs.external_path}/`")
    if area_docs.glossary(a, principles) is not None:
        lines.append("- [Glossary](docs/alpha/glossary.md)")
    if area_docs.changelog(a) is not None:
        lines.append("- [Changelog](CHANGELOG.md)")
    if area_docs.adoption_doc(a) is not None:
        lines.append(
            "- [Adoption plan](docs/alpha/adoption.md): the steps that bring this "
            "repo's code up to the principles; `/alpha:install` resumes it"
        )
    return "\n".join(lines) + "\n"


def _readme(a: Answers, principles: dict[str, Any]) -> str:
    ident = _identity(a)
    lines = [
        f"# {ident.name}",
        "",
        ident.value_proposition,
        "",
        "## Setup, test and run",
        "",
    ]
    for comp in principles["components"]:
        cmds = comp["commands"]
        run = cmds["run"] or "# run: add the command once the entry point exists"
        lines += [
            f"### {comp['name']} (`{comp['path']}/`)",
            "",
            "```sh",
            f"cd {comp['path']}",
            cmds["setup"],
            cmds["test"],
            run,
            "```",
            "",
        ]
    lines += ["See [CONTRIBUTING.md](CONTRIBUTING.md) before your first commit."]
    return "\n".join(lines) + "\n"


_WHEN = {"pr": "pull request", "both": "pull request, weekly", "schedule": "weekly"}


def _check_row(c: RepoCheck) -> str:
    what = c.description + (f" ({c.tool})" if c.tool else "")
    runs = _WHEN[c.when] + (", at Stop" if c.stop else "")
    return row(c.id, what, runs)


CHAINED_COMMIT_MSG = 'sh .claude/alpha/githooks/commit-msg "$1"'
CHAIN_BEGIN = "# alpha:begin"
CHAIN_END = "# alpha:end"


def _workflow_section(a: Answers) -> list[str]:
    """How alpha runs the project. Every line names an /alpha: command, so
    purge's line remover takes the whole section out."""
    install = (
        "- `/alpha:install` adopted this repo on `alpha/adopt`; run again, it "
        "carries out the next step of `docs/alpha/adoption.md` while one is left."
        if a.steps
        else "- `/alpha:install` set up this process once."
    )
    return [
        "## Working with alpha",
        "",
        install,
        "- `/alpha:update [request]` keeps it current: with no request it brings "
        "alpha's files to the installed kit; with one it adds or changes a "
        "component or a setup answer, or settles a product area "
        "(`/alpha:update performance`).",
        "- `/alpha:do <task>` works a task on the light track: by a playbook, straight "
        "into the work, with no spec files.",
        "- `/alpha:brainstorm <task>` starts the full track: research and a design "
        "spec the user approves, then `/alpha:plan` writes the plan and "
        "`/alpha:execute` builds it and runs the principles review.",
        "- `/alpha:uninstall` switches alpha's hooks off and `/alpha:install` "
        "switches them back on; `/alpha:purge` removes alpha in one commit.",
    ]


def _contributing(
    a: Answers,
    principles: dict[str, Any],
    checks: list[RepoCheck],
) -> str:
    assert a.git is not None
    git = principles["git"]
    branching = _BRANCHING.get(a.git.branching, f"Branching model: {a.git.branching}.")
    lines = ["# Contributing", "", *_workflow_section(a), "", "## One-time setup", ""]
    if git.get("hooks") == "chain":
        lines += [
            "The project's own git hook manager runs alpha's commit check "
            "(`.claude/alpha/githooks/commit-msg`): its commit-msg hook must call it, "
            "between the lines that mark it as alpha's:",
            "",
            "```sh",
            CHAIN_BEGIN,
            CHAINED_COMMIT_MSG,
            CHAIN_END,
            "```",
        ]
    else:
        lines += ["```sh", "git config core.hooksPath .claude/alpha/githooks", "```"]
    lines += ["", "Then set up each component:", ""]
    lines += [
        f"- `{c['name']}`: `cd {c['path']} && {c['commands']['setup']}`"
        for c in principles["components"]
    ]
    lines += ["", *_components_section(a, principles)]
    lines += [
        "",
        "## Checks",
        "",
        "```sh",
        "mise install",
        "mise run check",
        "```",
        "",
        "`mise install` installs the pinned tools; `mise run check` runs every "
        "component's checks and the repository checks below, the same as CI.",
        "",
        "The principles in `docs/alpha/principles.toml` name them in `checked_by` as "
        "`ci:<name>`: a name in the table is that check, and "
        + "; ".join(f"`ci:{k}` is when {v}" for k, v in CI_STEPS.items())
        + ".",
        "",
        "| Check | What it checks | Runs |",
        "|---|---|---|",
        *(_check_row(c) for c in checks),
        "",
        "## Commit convention",
        "",
        f"{a.git.convention.capitalize()} commits: `type(scope): description`.",
        "",
        "- Types: " + ", ".join(f"`{t}`" for t in git["types"]),
        "- Scopes: "
        + ", ".join(
            [*(f"`{s}`" for s in git["scopes"]), "or another area the commit touches"]
        ),
        "- The description is at most 50 characters, imperative, with no trailing "
        "period; it may start lowercase, e.g. with the symbol it changes.",
        "- Body lines wrap at 72 characters.",
        "",
        *area_docs.testing_section(a, principles),
        *_docs_section(_documentation(a)),
        "## Branching",
        "",
        branching,
        "",
        "Claude runs the principles reviewer and each changed component's full "
        "test suite before its work reaches main: a push to main, or merging a "
        "pull request. People can push by hand.",
        "",
        *_build_section(a, principles),
        "",
        *area_docs.releases_section(a),
        "",
        *area_docs.security_section(a, principles),
        "",
        *area_docs.data_rules_sections(a, principles),
        *_overrides_section(a),
        *EXCEPTIONS_SECTION,
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def _specification(a: Answers) -> str:
    """What the product does, in one file; full-track tasks add their own specs
    in docs/alpha/<features|bug-fixes|refactorings|perf>/."""
    ident = _identity(a)
    req = a.requirements
    linked = (
        {
            area: path
            for area, path in a.documentation.existing.items()
            if area in a.areas and a.areas[area] == "done"
        }
        if a.documentation
        else {}
    )
    lines = [
        f"# {ident.name}: specification",
        "",
        "## Value proposition",
        "",
        ident.value_proposition,
        "",
        "## Target users",
        "",
        req.target_users if req else area_docs.not_settled("requirements"),
        "",
        "## Requirements",
        "",
    ]
    if req and req.items:
        lines += ["| ID | Requirement | Acceptance check |", "|---|---|---|"]
        lines += [row(r.id, r.text, r.acceptance) for r in req.items]
    elif req:
        lines.append(
            "None yet: `/alpha:update requirements` adds them, with their "
            "acceptance checks."
        )
    else:
        lines.append(area_docs.not_settled("requirements"))
    open_areas = [
        (title, request)
        for area, (title, request) in area_docs.SETTLE_REQUESTS.items()
        if a.areas[area] == "open" and area_docs.could_apply(area, a)
    ]
    if open_areas:
        lines += [
            "",
            "## Not settled yet",
            "",
            "These parts of the specification stay open until you settle them. "
            "Until then their principles are off.",
            "",
        ]
        for area, (title, request) in area_docs.SETTLE_REQUESTS.items():
            if (title, request) not in open_areas:
                continue
            theirs = area_docs.existing_doc(a, area)
            documented = (
                f" (the project documents it so far in [{theirs}](../../{theirs}))"
                if theirs
                else ""
            )
            lines.append(f"- {title}: `{request}`{documented}")
    sections = [
        ("architecture", area_docs.architecture_section(a)),
        ("errors", area_docs.errors_section(a)),
        ("auth", area_docs.auth_section(a)),
        ("ui", area_docs.ui_section(a)),
        ("data", area_docs.data_section(a)),
        ("performance", area_docs.performance_section(a)),
        ("observability", area_docs.observability_section(a)),
    ]
    for area, section in sections:
        if section is None:
            continue
        if area in linked:
            section = [section[0], "", area_docs.see(linked[area])]
        lines += ["", *section]
    return "\n".join(lines) + "\n"


def _components_section(a: Answers, principles: dict[str, Any]) -> list[str]:
    members = [c for c in principles["components"] if c.get("workspace")]
    lines = [
        "## Components",
        "",
        f"Layout: {a.layout}.",
        "",
        "| Name | Path | Kind | Stack | Traits |",
        "|---|---|---|---|---|",
    ]
    lines += [row(c.name, c.path, c.kind, c.stack, _traits(c)) for c in a.components]
    talk = (
        "Components communicate with each other; keep their contract explicit."
        if a.components_talk
        else "Components do not communicate with each other."
    )
    lines += ["", talk, "", *_not_code(a), "### Tool choices", ""]
    book = a.book()
    for stack in dict.fromkeys(c.stack for c in a.components):
        recipe = book.get(stack)
        tools = ", ".join(recipe.why) or "the stack's own toolchain"
        commands = [recipe.commands[s] for s in _STEPS if recipe.commands.get(s)]
        line = f"- {stack}: {tools}. Commands: " + ", ".join(f"`{c}`" for c in commands)
        shared = [
            f"`{f}`" for c in members if c["stack"] == stack for f in c["workspace"]
        ]
        if shared:
            line += (
                ". Its components form one workspace at the repository root "
                f"({', '.join(dict.fromkeys(shared))}, one lockfile); each "
                "command covers the component it runs in"
            )
        if not recipe.proven:
            line += " (less proven: recipe drafted for this project)"
        lines.append(line)
    return lines


def _dependencies(a: Answers, today: date, added: Mapping[str, date]) -> str:
    theirs = area_docs.existing_doc(a, "dependencies")
    if theirs is not None:
        return (
            "# Dependencies\n\nThis project logs each dependency it adds, with the "
            f"reason, in [{theirs}](../../{theirs}).\n"
        )
    lines = [
        "# Dependencies",
        "",
        *area_docs.dependency_policy(a),
        "## Log",
        "",
        "Log every dependency added, with the reason.",
        "",
        "| Dependency | Component | Why | Added |",
        "|---|---|---|---|",
    ]
    for c in a.components:
        lines += [
            row(tool, c.name, why, added.get(c.name, today).isoformat())
            for tool, why in a.book().get(c.stack).why.items()
        ]
    return "\n".join(lines) + "\n"


def _overrides_section(a: Answers) -> list[str]:
    """Each principle the project tightened, loosened or dropped, with the
    reason the principles require."""
    if not a.overrides:
        return []
    lines = [
        "## Overrides",
        "",
        "| Principle | Change | Scope | Reason |",
        "|---|---|---|---|",
    ]
    lines += [row(o.principle, o.change, o.scope, o.reason or "-") for o in a.overrides]
    return [*lines, ""]


# Agents add rows under the header by hand; alpha update keeps them.
EXCEPTIONS_SECTION = (
    "## Exceptions",
    "",
    "A check skipped or loosened in one place, or a baseline loosened, needs a row "
    "here naming the path and the check, with the reason; the checks look for it.",
    "",
    "| Path | Check | Reason |",
    "|---|---|---|",
)


def render_docs(
    a: Answers,
    principles: dict[str, Any],
    year: int,
    today: date,
    root: Path = Path(),
    added: Mapping[str, date] | None = None,
    registry: Registry | None = None,
) -> dict[str, str]:
    checks = repo_checks(a, principles, registry or default_registry())
    out = {
        "README.md": _readme(a, principles),
        "LICENSE": _license(a, year, root),
        "CONTRIBUTING.md": _contributing(a, principles, checks),
        "CLAUDE.md": _claude_md(a, principles),
        "docs/alpha/specification.md": _specification(a),
        "docs/alpha/dependencies.md": _dependencies(a, today, added or {}),
    }
    optional = {
        DESIGN_LANGUAGE_DOC: area_docs.design_language_doc(a),
        "CHANGELOG.md": area_docs.changelog(a),
        "docs/alpha/adoption.md": area_docs.adoption_doc(a),
    }
    out.update({path: text for path, text in optional.items() if text is not None})
    glossary = area_docs.glossary(a, principles)
    if glossary is not None:
        out["docs/alpha/glossary.md"] = glossary
    return out
