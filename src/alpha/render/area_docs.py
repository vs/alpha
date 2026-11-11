from typing import Any

from alpha.answers import Answers, describe_condition
from alpha.render.markdown import row

_ERROR_FORMATS = {
    "problem-json": "HTTP errors as problem details (RFC 9457): type, title, detail.",
    "message-and-exit-code": "A message on stderr and a non-zero exit code.",
    "user-message": "A message next to the problem, saying how to fix it.",
    "exceptions": "Typed exceptions whose message says how to fix the problem.",
    "structured-log": "A structured log entry with the category and the fix.",
    "other": "As described in the errors decision record.",
}


def _active(principles: dict[str, Any], principle_id: str) -> bool:
    return any(
        p["id"] == principle_id and p["active"] for p in principles["principles"]
    )


def architecture_sections(a: Answers) -> list[str]:
    assert a.architecture is not None and a.errors is not None
    lines = [
        "## Responsibilities",
        "",
        "| Component | Responsibility | Calls |",
        "|---|---|---|",
    ]
    lines += [
        row(c.name, c.responsibility, ", ".join(c.calls) or "-")
        for c in a.architecture.components
    ]
    lines += ["", "## Contracts", ""]
    contracts = a.architecture.contracts
    if contracts.format == "none":
        lines.append("No contracts: components don't call each other.")
    else:
        lines.append(
            f"Interfaces between components are defined once, as {contracts.format}, "
            f"in {', '.join(f'`{p}`' for p in contracts.paths)}. Changes there are "
            "reviewed as risky."
        )
    lines += [
        "",
        "## Errors",
        "",
        "Every error a user sees says what went wrong and how to fix it.",
        "",
        "| Component | Format | Meaning |",
        "|---|---|---|",
    ]
    lines += [
        row(c.name, c.format, _ERROR_FORMATS[c.format]) for c in a.errors.components
    ]
    lines += ["", "Categories:", ""]
    lines += [f"- {category}" for category in a.errors.categories]
    return lines


def glossary(a: Answers, principles: dict[str, Any]) -> str | None:
    assert a.architecture is not None
    terms = sorted(a.architecture.glossary, key=lambda t: t.term.casefold())
    if not terms and not _active(principles, "one-vocabulary"):
        return None
    lines = [
        "# Glossary",
        "",
        "Use these names in code, docs and UI alike.",
        "",
    ]
    if terms:
        lines += ["| Term | Meaning |", "|---|---|"]
        lines += [row(t.term, t.meaning) for t in terms]
    else:
        lines.append("Add terms as they come up.")
    return "\n".join(lines) + "\n"


def testing_section(a: Answers) -> list[str]:
    assert a.testing is not None
    lines = ["## Testing", "", "| Component | Levels |", "|---|---|"]
    lines += [row(c.name, ", ".join(c.levels)) for c in a.testing.components]
    lines += [
        "",
        "Put each level's tests under `tests/<level>/` in the component.",
        "",
        "A test that covers an acceptance check names its requirement id (e.g. "
        "`R1`) in its name, so each check in docs/product.md traces to a test.",
        "",
    ]
    return lines


def security_doc(a: Answers, principles: dict[str, Any]) -> str:
    assert a.security is not None
    store = a.security.secret_store
    lines = [
        "# Security",
        "",
        "## Secrets",
        "",
        f"Production secrets live in: {store}." if store else "Nothing is deployed.",
        "",
        "Locally, secrets live in `.env` files, which git ignores; never commit "
        "them. Claude can't edit them, and the Stop hook blocks a change that adds "
        "a secret to the repository.",
        "",
        "## Auth",
        "",
        a.security.auth,
        "",
        "## Protected paths",
        "",
        "Claude can't edit these. Lockfiles change only through the package "
        "manager; change the others by hand.",
        "",
    ]
    lines += [f"- `{glob}`" for glob in principles["protected"]["paths"]]
    return "\n".join(lines) + "\n"


def dependency_policy(a: Answers) -> list[str]:
    assert a.dependencies is not None
    deps = a.dependencies
    if deps.updates == "dependabot":
        actions = (
            " and for the CI actions"
            if a.build is not None and a.build.ci != "none"
            else ""
        )
        upgrading = (
            f"Dependabot opens {deps.schedule} update pull requests, per "
            f"component{actions}."
        )
    else:
        upgrading = f"Upgrades are manual: check for updates {deps.schedule}."
    return [
        "## Policy",
        "",
        "- Adding: every new dependency gets a row in the log below, with the "
        "reason. The Stop hook blocks a lockfile change without one.",
        "- Pinning: lockfiles pin every version. Only the package manager changes "
        "them; Claude can't edit them by hand.",
        f"- Upgrading: {upgrading}",
        "",
    ]


def observability_doc(a: Answers) -> str | None:
    assert a.observability is not None
    if not a.observability.components:
        return None
    lines = [
        "# Observability",
        "",
        "| Component | Logs | Correlation | Telemetry |",
        "|---|---|---|---|",
    ]
    lines += [
        row(c.name, c.log_format, c.correlation, c.telemetry)
        for c in a.observability.components
    ]
    lines += [
        "",
        "Levels: `info` in deployed environments, `debug` locally; errors carry the "
        "correlation id.",
    ]
    return "\n".join(lines) + "\n"


def ui_doc(a: Answers) -> str | None:
    assert a.ui is not None and a.accessibility is not None
    if not a.ui.components:
        return None
    lines = [
        "# UI",
        "",
        "## Visual system",
        "",
        "| Component | Library | Tokens | Icons | Typography | Theming |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        row(c.name, c.library, f"`{c.tokens}`", c.icons, c.typography, c.theming)
        for c in a.ui.components
    ]
    lines += [
        "",
        "Build the UI from these; no ad-hoc colors, spacing or fonts outside the "
        "tokens.",
        "",
        "## Visual regression",
        "",
    ]
    lines += [f"- {c.name}: {c.visual_regression}" for c in a.ui.components]
    lines += ["", "## Accessibility", "", f"Target: {a.accessibility.level}.", ""]
    lines += [f"- {c.name}: {c.checks}" for c in a.accessibility.components]
    lines += ["", "Every UI works with a keyboard and a screen reader."]
    return "\n".join(lines) + "\n"


def data_doc(a: Answers, principles: dict[str, Any]) -> str | None:
    assert a.data is not None
    if not a.data.components and a.data.ml is None:
        return None
    lines = ["# Data", ""]
    if a.data.components:
        lines += [
            "## Storage",
            "",
            "| Component | Storage | Migrations | Reversible |",
            "|---|---|---|---|",
        ]
        for c in a.data.components:
            globs = ", ".join(f"`{g}`" for g in c.migrations)
            migrations = f"{c.migration_tool}: {globs}" if globs else c.migration_tool
            reversible = "yes" if c.reversible else "no"
            lines.append(row(c.name, c.storage, migrations, reversible))
        lines.append("")
        migrated = any(c.migrations for c in a.data.components)
        if migrated and _active(principles, "safe-migrations"):
            lines += [
                "Every schema change is a migration. Migrations are append-only: "
                "once one exists in a commit, add a new one instead of editing it "
                "(the Stop hook checks). Write a down migration wherever the change "
                "can be undone.",
                "",
            ]
    if a.data.ml is not None:
        ml = a.data.ml
        lines += [
            "## Experiments",
            "",
            f"- Data versioning: {ml.versioning}",
            f"- Seeds: {ml.seeds}",
            f"- Experiment tracking: {ml.tracking}",
            "",
            "Every result names the data version, seed and config that produced it.",
            "",
        ]
    return "\n".join(lines).rstrip("\n") + "\n"


_SCHEMES = {
    "semver": "Semantic versioning (MAJOR.MINOR.PATCH): a breaking change bumps "
    "MAJOR, a new feature MINOR, a fix PATCH.",
    "calver": "Calendar versioning: each version is the release date (e.g. 2026.10.1).",
    "none": "No version numbers: every commit on the main branch is a release.",
}
_SCHEME_NAMES = {
    "semver": "semantic versioning",
    "calver": "calendar versioning",
}


def releases_doc(a: Answers) -> str:
    assert a.releases is not None
    r = a.releases
    scope = (
        "Each component is versioned on its own, with tags named "
        "`<component>-v<version>`."
        if r.scope == "component"
        else "One version for the whole repository."
    )
    recorded = (
        "as they land, under the date it reached main."
        if r.scheme == "none"
        else "under Unreleased as they land, and moved under the version at release."
    )
    changelog = {
        "file": f"Changes are recorded in [CHANGELOG.md](../CHANGELOG.md) {recorded}",
        "github-releases": "Changes are written up in the GitHub release notes "
        "for each version.",
        "none": "No changelog is kept; the commit history is the record.",
    }[r.changelog]
    lines = [
        "# Releases",
        "",
        _SCHEMES[r.scheme],
        "",
        scope,
        "",
        changelog,
        "",
        "## Cutting a release",
        "",
        r.process,
    ]
    return "\n".join(lines) + "\n"


def changelog(a: Answers) -> str | None:
    assert a.releases is not None
    if a.releases.changelog != "file":
        return None
    if a.releases.scheme == "none":
        return (
            "# Changelog\n\n"
            "All notable changes, newest first, grouped by the date they reached "
            "main.\n"
        )
    return (
        "# Changelog\n\n"
        f"All notable changes, newest first. Versions follow "
        f"{_SCHEME_NAMES[a.releases.scheme]}.\n\n"
        "## Unreleased\n"
    )


def performance_doc(a: Answers) -> str | None:
    assert a.performance is not None
    rows = [
        row(c.name, b.metric, b.limit, b.measured_by)
        for c in a.performance.components
        for b in c.budgets
    ]
    load = a.performance.expected_load
    if not rows and not load:
        return None
    lines = ["# Performance", ""]
    if rows:
        lines += [
            "| Component | Metric | Budget | Measured by |",
            "|---|---|---|---|",
            *rows,
            "",
            "A change that breaks a budget is fixed, or the budget is changed by a "
            "decision record.",
            "",
        ]
    if load:
        lines += [
            "## Expected load",
            "",
            load,
            "",
            "Reviews judge scale against this load, and a `shortcut:` comment "
            "names the load past which its shortcut stops holding.",
            "",
        ]
    return "\n".join(lines[:-1]) + "\n"


PHASE_NAMES = {
    "P0": "Urgent",
    "P1": "Normalize",
    "P2": "Close tool gaps",
    "P3": "Optional migrations",
    "P4": "Rework",
    "P5": "Burn-down",
    "P6": "Traceability",
}


def adoption_doc(a: Answers) -> str | None:
    """The compliance plan of an adopted repo (spec §5b, step 6)."""
    if not a.steps:
        return None
    lines = [
        "# Adoption plan",
        "",
        "alpha adopted this repo. These steps bring its code up to the "
        "principles in [principles.toml](principles.toml), phase by phase. Run "
        "`/alpha:adopt` to pick up the next one: each step gets a branch of its "
        "own, and it's done only when everything under its *Done when* holds.",
        "",
        "## Progress",
        "",
        row("Phase", "Done", "Steps"),
        row("---", "---", "---"),
    ]
    phases = [p for p in PHASE_NAMES if any(s.phase == p for s in a.steps)]
    for phase in phases:
        steps = [s for s in a.steps if s.phase == phase]
        finished = sum(s.status in ("done", "dropped") for s in steps)
        lines.append(
            row(f"{phase} {PHASE_NAMES[phase]}", str(finished), str(len(steps)))
        )
    for phase in phases:
        lines += ["", f"## {phase} {PHASE_NAMES[phase]}", ""]
        lines += [row("Step", "Component", "Status"), row("---", "---", "---")]
        steps = [s for s in a.steps if s.phase == phase]
        lines += [
            row(f"`{s.id}`", s.component or "-", s.status.replace("_", " "))
            for s in steps
        ]
        for s in steps:
            lines += ["", f"### `{s.id}`: {s.title}", "", s.why]
            facts: list[str] = []
            if s.principles:
                facts.append(
                    "Serves " + ", ".join(f"`{p}`" for p in s.principles) + "."
                )
            if s.depends_on:
                facts.append("After " + ", ".join(f"`{d}`" for d in s.depends_on) + ".")
            if s.status == "dropped" and s.decision is not None:
                facts.append(f"Dropped by decision {s.decision:04d}.")
            if facts:
                lines += ["", " ".join(facts)]
            lines += ["", "Done when:", ""]
            lines += [f"- {describe_condition(c)}" for c in s.acceptance]
    return "\n".join(lines) + "\n"
