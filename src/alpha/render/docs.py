"""Render the project's prose files: README, LICENSE, CONTRIBUTING, CLAUDE.md, docs."""

import re
from datetime import date
from pathlib import Path
from string import Template
from typing import Any

from alpha.answers import Answers, Component, Identity
from alpha.principles import override_decision_paths
from alpha.recipes import load_recipe

LICENSES_DIR = Path(__file__).resolve().parents[1] / "licenses"
_STEPS = ("setup", "test", "lint", "format", "typecheck")
_DONE = (
    "Tests written and passing.",
    "Types and lint clean.",
    "Docs updated.",
    "Committed per the commit convention.",
    "Reviewer passed.",
)
_WHY = {
    "pytest": "Test runner",
    "ruff": "Linting and formatting",
    "pyright": "Strict type checking",
    "typescript": "Type checking and compilation",
    "vitest": "Test runner",
    "@biomejs/biome": "Linting and formatting",
    "@types/node": "Node.js type definitions",
}
_BRANCHING = {
    "trunk": "Trunk-based: small commits straight to the main branch, "
    "each leaving the checks green.",
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _bootstrap_tools(stack: str) -> list[str]:
    tools: list[str] = []
    for line in load_recipe(stack).bootstrap:
        tools += [t for t in line.split() if not t.startswith("-")][2:]
    return tools


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
        f"scopes = component names ({', '.join(a.git.scopes)}), "
        "enforced by the commit-msg hook.",
        "",
        "## Docs",
        "",
        "- [Principles](docs/principles.toml)",
        "- [Product](docs/product.md)",
        "- [Architecture](docs/architecture.md)",
        "- [Dependencies](docs/dependencies.md)",
        "- [Decisions](docs/decisions/)",
        "- [Contributing](CONTRIBUTING.md)",
    ]
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
        tools = ", ".join(_bootstrap_tools(stack))
        lines += [
            f"- {stack}: {tools}. Commands: "
            + ", ".join(f"`{recipe.commands[s]}`" for s in _STEPS)
        ]
    return "\n".join(lines) + "\n"


def _dependencies(a: Answers, year: int) -> str:
    lines = [
        "# Dependencies",
        "",
        "Log every dependency added, with the reason.",
        "",
        "| Dependency | Component | Why | Added |",
        "|---|---|---|---|",
    ]
    for c in a.components:
        lines += [
            f"| {t} | {c.name} | {_WHY.get(t, 'Tooling')} | {year} |"
            for t in _bootstrap_tools(c.stack)
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
        "docs/dependencies.md": _dependencies(a, year),
    }
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
