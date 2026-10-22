"""Render the project's prose files: README, LICENSE, CONTRIBUTING, CLAUDE.md, docs."""

import re
from datetime import date
from pathlib import Path
from string import Template
from typing import Any

from alpha.answers import Answers, Component, Documentation, Identity
from alpha.principles import override_decision_paths
from alpha.recipes import check_commands, load_recipe
from alpha.render import area_docs
from alpha.render.ci import WORKFLOW

LICENSES_DIR = Path(__file__).resolve().parents[1] / "licenses"
_STEPS = ("setup", "test", "lint", "format", "format_check", "typecheck")
_DONE = (
    "Tests written and passing.",
    "Types and lint clean.",
    "Docs updated.",
    "Committed per the commit convention.",
    "Reviewer passed.",
)
_BRANCHING = {
    "trunk": "Trunk-based: small commits straight to the main branch, "
    "each leaving the checks green.",
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "decision"


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
            f"| {_ticked(list(m.paths))} | {_ticked(list(m.docs))} |"
            for m in docs.mappings
        ]
        lines += [
            "",
            "The Stop hook blocks a change to these paths that leaves the docs "
            "untouched.",
            "",
        ]
    return lines


def _build(a: Answers, principles: dict[str, Any]) -> str:
    assert a.build is not None
    lines = ["# Build, CI and hosting", "", "## CI", ""]
    if a.build.ci == "none":
        first = len(a.decisions) + 1
        record = next(
            path
            for i, path in override_decision_paths(a, first).items()
            if a.overrides[i].principle == "build-hosting-upfront"
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
            f"| {c['name']} | "
            + ", ".join(f"`{cmd}`" for _, cmd in check_commands(c["commands"]))
            + " |"
            for c in principles["components"]
        ]
    lines += ["", "## Components", "", "| Component | Artifact | Hosting |"]
    lines.append("|---|---|---|")
    lines += [
        f"| {t.name} | {t.artifact} | {t.hosting or '-'} |" for t in a.build.components
    ]
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
    rows += [f"| {s} | `{commands[s]}` |" for s in _STEPS]
    rows.append("| run | add when the entry point exists |")
    return rows


def _claude_md(a: Answers, principles: dict[str, Any]) -> str:
    ident = _identity(a)
    assert a.git is not None
    lines = [f"# {ident.name}", "", ident.value_proposition, "", "## Principles", ""]
    lines += [
        f"- **{p['title']}**: {p['statement']}"
        for p in principles["principles"]
        if p["active"]
    ]
    lines += [
        "",
        "`docs/principles.toml` is the source of truth, with each principle's "
        "parameters, rationale and overrides.",
        "",
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
    lines += [f"| {r.id} | {r.text} | {r.acceptance} |" for r in ident.requirements]
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
    lines += [
        f"| {c.name} | {c.path} | {c.kind} | {c.stack} | {_traits(c)} |"
        for c in a.components
    ]
    talk = (
        "Components communicate with each other; keep their contract explicit."
        if a.components_talk
        else "Components do not communicate with each other."
    )
    lines += ["", talk, "", "## Tool choices", ""]
    for stack in dict.fromkeys(c.stack for c in a.components):
        recipe = load_recipe(stack)
        tools = ", ".join(recipe.why)
        lines += [
            f"- {stack}: {tools}. Commands: "
            + ", ".join(f"`{recipe.commands[s]}`" for s in _STEPS)
        ]
    lines += ["", *area_docs.architecture_sections(a)]
    return "\n".join(lines) + "\n"


def _dependencies(a: Answers, today: date) -> str:
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
            f"| {tool} | {c.name} | {why} | {today.isoformat()} |"
            for tool, why in load_recipe(c.stack).why.items()
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
) -> dict[str, str]:
    out = {
        "README.md": _readme(a, principles),
        "LICENSE": _license(a, year, root),
        "CONTRIBUTING.md": _contributing(a, principles),
        "CLAUDE.md": _claude_md(a, principles),
        "docs/product.md": _product(a),
        "docs/architecture.md": _architecture(a),
        "docs/dependencies.md": _dependencies(a, today),
        "docs/build.md": _build(a, principles),
        "docs/security.md": area_docs.security_doc(a, principles),
    }
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
    for i, d in enumerate(a.decisions, 1):
        out[f"docs/decisions/{i:04d}-{_slug(d.title)}.md"] = _decision(
            i, d.title, today, d.context, d.decision, d.consequences
        )
    first = len(a.decisions) + 1
    for i, path in override_decision_paths(a, first).items():
        o = a.overrides[i]
        out[path] = _decision(
            first + i,
            f"Override {o.principle}",
            today,
            o.reason,
            f"{o.change.capitalize()} {o.principle} for {o.scope}.",
            "See docs/principles.toml for the resulting parameters.",
            f"Principle: {o.principle} ({o.change}, scope {o.scope})",
        )
    return out
