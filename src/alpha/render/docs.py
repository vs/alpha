"""Render the project's prose files: README, LICENSE, CONTRIBUTING, CLAUDE.md, docs."""

from collections.abc import Mapping
from datetime import date
from pathlib import Path
from string import Template
from typing import Any

from alpha.answers import Answers, Component, Documentation, Identity
from alpha.recipes import check_commands
from alpha.records import Records, record_number, record_paths
from alpha.render import area_docs
from alpha.render.ci import WORKFLOW
from alpha.render.markdown import row

LICENSES_DIR = Path(__file__).resolve().parents[1] / "licenses"
_STEPS = ("setup", "test", "lint", "format", "format_check", "typecheck")
_DONE = (
    "Tests written and passing.",
    "Types and lint clean.",
    "Docs updated.",
    "Committed per the commit convention.",
    "Reviewer passed.",
)
_WORKING_RULES = (
    "- Before you change code, docs or config, read the decision records in "
    "docs/decisions/ that bear on the change (an index is added to your context "
    "at the start of each session) and the principle's parameters in "
    "docs/principles.toml. Follow them.",
    "- A change that contradicts an accepted decision needs a new decision that "
    "supersedes it. Ask the user first, then record it with the decision skill.",
    "- When a requirement is ambiguous, ask the user, then record the answer with "
    "the decision skill.",
    "- Read a file in full before you edit it, and every file a wide change "
    "touches; search snippets aren't enough.",
    "- Look up a dependency's API in its installed source or types instead of "
    "guessing it.",
    "- Ask before removing code or behavior that looks intentional.",
    "- Commit only the files you changed for the work, staged by path. Other "
    "changes in the tree may be the user's or another session's, so don't stage, "
    "stash or reset them; the hooks block the commands that would.",
    "- Subagents work under the same principles, decisions and checks.",
    "- Before you report work as done, re-read every changed file top to bottom "
    "as a stranger would.",
    "- At the end of a planned piece of work, run the principles-reviewer agent.",
)
_COMMUNICATION = (
    "- Answer a question before making edits or running commands for it.",
    "- When responding to feedback or a review, say first whether you agree, "
    "then what you changed.",
    "- Be concise and direct: plain technical prose, no filler, no emojis. "
    "Define jargon you can't avoid.",
    "- Explain a non-trivial problem or design as the problem, a concrete example "
    "or short trace, then the solution and why it's needed.",
)
_BRANCHING = {
    "trunk": "Trunk-based: small commits straight to the main branch, "
    "each leaving the checks green.",
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
    """CONTRIBUTING's Documentation section, ending with a blank line."""
    lines = [
        "## Documentation",
        "",
        "Internal docs (design, decisions, how we work) live in `docs/`. "
        + _external(docs),
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


def _build(a: Answers, principles: dict[str, Any], records: Records) -> str:
    assert a.build is not None
    lines = ["# Build, CI and hosting", "", "## CI", ""]
    if a.build.ci == "none":
        record = next(
            path
            for o, path in zip(a.overrides, records.overrides, strict=True)
            if o.principle == "build-hosting-upfront"
        )
        lines.append(f"No CI. Why: see [the decision]({record.removeprefix('docs/')}).")
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
    lines += ["", "## Components", "", "| Component | Artifact | Hosting |"]
    lines.append("|---|---|---|")
    lines += [row(t.name, t.artifact, t.hosting or "-") for t in a.build.components]
    lines += ["", "## Environments", ""]
    if a.build.environments:
        lines += [f"- {env}" for env in a.build.environments]
    else:
        lines.append("None: nothing is deployed.")
    lines += [
        "",
        "Hosting is decided and documented here; alpha creates no cloud resources "
        "and no deploy jobs.",
    ]
    return "\n".join(lines) + "\n"


def _ticked(globs: list[str]) -> str:
    return ", ".join(f"`{g}`" for g in globs)


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
    rows += [row(s, f"`{commands[s]}`") for s in _STEPS]
    rows.append("| run | add when the entry point exists |")
    return rows


def _stack_rules(principles: dict[str, Any]) -> list[str]:
    """Each stack's rules once, under the components that use the stack."""
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
    lines = [f"# {ident.name}", "", ident.value_proposition, "", "## Principles", ""]
    lines += [
        f"- **{p['title']}**: {p['statement']}"
        + (
            f" (overridden: see {p['override_decision']})"
            if p["override_decision"]
            else ""
        )
        for p in principles["principles"]
        if p["active"]
    ]
    lines += [
        "",
        "`docs/principles.toml` is the source of truth, with each principle's "
        "parameters, rationale and overrides.",
        "",
        "## Working rules",
        "",
        *_WORKING_RULES,
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
    lines += ["## Definition of done", ""]
    lines += [f"{i}. {item}" for i, item in enumerate(_DONE, 1)]
    lines += [
        "",
        "## Commits",
        "",
        "Use the commit skill (`.claude/skills/commit/SKILL.md`). "
        f"Convention: {a.git.convention} commits, "
        f"scopes: {', '.join(a.git.scopes) or 'any'}, "
        "enforced by the commit-msg hook.",
        "",
        "## Docs",
        "",
        "- [Principles](docs/principles.toml)",
        "- [Product](docs/product.md)",
        "- [Architecture](docs/architecture.md)",
        "- [Build, CI and hosting](docs/build.md)",
        "- [Security](docs/security.md)",
        "- [Dependencies](docs/dependencies.md)",
        "- [Decisions](docs/decisions/)",
        "- [Contributing](CONTRIBUTING.md)",
    ]
    docs = _documentation(a)
    if docs.external == "folder":
        lines.append(f"- [User guide]({docs.external_path}/)")
    if area_docs.glossary(a, principles) is not None:
        lines.append("- [Glossary](docs/glossary.md)")
    if area_docs.observability_doc(a) is not None:
        lines.append("- [Observability](docs/observability.md)")
    if area_docs.ui_doc(a) is not None:
        lines.append("- [UI](docs/ui.md)")
    if area_docs.data_doc(a, principles) is not None:
        lines.append("- [Data](docs/data.md)")
    if area_docs.performance_doc(a) is not None:
        lines.append("- [Performance](docs/performance.md)")
    lines.append("- [Releases](docs/releases.md)")
    if area_docs.changelog(a) is not None:
        lines.append("- [Changelog](CHANGELOG.md)")
    return "\n".join(lines) + "\n"


def _readme(a: Answers, principles: dict[str, Any]) -> str:
    ident = _identity(a)
    lines = [
        f"# {ident.name}",
        "",
        ident.value_proposition,
        "",
        "## Setup and test",
        "",
    ]
    for comp in principles["components"]:
        cmds = comp["commands"]
        lines += [
            f"### {comp['name']} (`{comp['path']}/`)",
            "",
            "```sh",
            f"cd {comp['path']}",
            cmds["setup"],
            cmds["test"],
            "```",
            "",
        ]
    lines += ["See [CONTRIBUTING.md](CONTRIBUTING.md) before your first commit."]
    return "\n".join(lines) + "\n"


def _contributing(a: Answers, principles: dict[str, Any]) -> str:
    assert a.git is not None
    git = principles["git"]
    branching = _BRANCHING.get(a.git.branching, f"Branching model: {a.git.branching}.")
    lines = [
        "# Contributing",
        "",
        "## One-time setup",
        "",
        "```sh",
        "git config core.hooksPath .claude/alpha/githooks",
        "```",
        "",
        "Then set up each component:",
        "",
    ]
    lines += [
        f"- `{c['name']}`: `cd {c['path']} && {c['commands']['setup']}`"
        for c in principles["components"]
    ]
    lines += [
        "",
        "## Commit convention",
        "",
        f"{a.git.convention.capitalize()} commits: `type(scope): Description`.",
        "",
        "- Types: " + ", ".join(f"`{t}`" for t in git["types"]),
        "- Scopes: " + ", ".join(f"`{s}`" for s in git["scopes"]),
        "- The description is at most 50 characters, imperative, capitalized, "
        "with no trailing period.",
        "- Body lines wrap at 72 characters.",
        "",
        *area_docs.testing_section(a),
        *_docs_section(_documentation(a)),
        "## Branching",
        "",
        branching,
        "",
        "Claude runs the principles reviewer before it pushes or opens a pull "
        "request; people can push by hand.",
    ]
    return "\n".join(lines) + "\n"


def _product(a: Answers) -> str:
    ident = _identity(a)
    lines = [
        f"# {ident.name}: product",
        "",
        "## Value proposition",
        "",
        ident.value_proposition,
        "",
        "## Target users",
        "",
        ident.target_users,
        "",
        "## Requirements",
        "",
        "| ID | Requirement | Acceptance check |",
        "|---|---|---|",
    ]
    lines += [row(r.id, r.text, r.acceptance) for r in ident.requirements]
    return "\n".join(lines) + "\n"


def _architecture(a: Answers) -> str:
    lines = [
        "# Architecture",
        "",
        "## Layout",
        "",
        f"Layout: {a.layout}.",
        "",
        "## Components",
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
    lines += ["", talk, "", "## Tool choices", ""]
    book = a.book()
    for stack in dict.fromkeys(c.stack for c in a.components):
        recipe = book.get(stack)
        tools = ", ".join(recipe.why) or "the stack's own toolchain"
        commands = [recipe.commands[s] for s in _STEPS if recipe.commands[s]]
        line = f"- {stack}: {tools}. Commands: " + ", ".join(f"`{c}`" for c in commands)
        if not recipe.proven:
            line += " (less proven: recipe drafted for this project)"
        lines.append(line)
    lines += ["", *area_docs.architecture_sections(a)]
    return "\n".join(lines) + "\n"


def _dependencies(a: Answers, today: date, added: Mapping[str, date]) -> str:
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


def _decision(
    number: int,
    title: str,
    day: date,
    context: str,
    decision: str,
    cons: str,
    extra: str = "",
) -> str:
    head = f"# {number:04d}. {title}\n\nDate: {day.isoformat()}\nStatus: accepted\n"
    if extra:
        head += extra + "\n"
    return (
        f"{head}\n## Context\n\n{context}\n\n## Decision\n\n{decision}\n\n"
        f"## Consequences\n\n{cons}\n"
    )


def render_docs(
    a: Answers,
    principles: dict[str, Any],
    year: int,
    today: date,
    root: Path = Path(),
    records: Records | None = None,
    added: Mapping[str, date] | None = None,
) -> dict[str, str]:
    records = records or record_paths(a)
    out = {
        "README.md": _readme(a, principles),
        "LICENSE": _license(a, year, root),
        "CONTRIBUTING.md": _contributing(a, principles),
        "CLAUDE.md": _claude_md(a, principles),
        "docs/product.md": _product(a),
        "docs/architecture.md": _architecture(a),
        "docs/dependencies.md": _dependencies(a, today, added or {}),
        "docs/build.md": _build(a, principles, records),
        "docs/security.md": area_docs.security_doc(a, principles),
        "docs/releases.md": area_docs.releases_doc(a),
    }
    optional = {
        "docs/ui.md": area_docs.ui_doc(a),
        "docs/data.md": area_docs.data_doc(a, principles),
        "docs/performance.md": area_docs.performance_doc(a),
        "CHANGELOG.md": area_docs.changelog(a),
    }
    out.update({path: text for path, text in optional.items() if text is not None})
    observability = area_docs.observability_doc(a)
    if observability is not None:
        out["docs/observability.md"] = observability
    glossary = area_docs.glossary(a, principles)
    if glossary is not None:
        out["docs/glossary.md"] = glossary
    docs = _documentation(a)
    if docs.external == "folder":
        out[f"{docs.external_path}/README.md"] = (
            f"# {_identity(a).name} guide\n\n"
            f"User-facing documentation for {_identity(a).name} lives here.\n"
        )
    for d, path in zip(a.decisions, records.decisions, strict=True):
        out[path] = _decision(
            record_number(path), d.title, today, d.context, d.decision, d.consequences
        )
    for o, path in zip(a.overrides, records.overrides, strict=True):
        out[path] = _decision(
            record_number(path),
            f"Override {o.principle}",
            today,
            o.reason,
            f"{o.change.capitalize()} {o.principle} for {o.scope}.",
            "See docs/principles.toml for the resulting parameters.",
            f"Principle: {o.principle} ({o.change}, scope {o.scope})",
        )
    return out
