"""Render what the core areas decided: architecture sections, glossary, testing."""

from typing import Any

from alpha.answers import Answers

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
    """The Responsibilities, Contracts and Errors sections of docs/architecture.md."""
    assert a.architecture is not None and a.errors is not None
    lines = [
        "## Responsibilities",
        "",
        "| Component | Responsibility | Calls |",
        "|---|---|---|",
    ]
    lines += [
        f"| {c.name} | {c.responsibility} | {', '.join(c.calls) or '-'} |"
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
        f"| {c.name} | {c.format} | {_ERROR_FORMATS[c.format]} |"
        for c in a.errors.components
    ]
    lines += ["", "Categories:", ""]
    lines += [f"- {category}" for category in a.errors.categories]
    return lines


def glossary(a: Answers, principles: dict[str, Any]) -> str | None:
    """docs/glossary.md, when there are terms or one vocabulary is a principle."""
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
        lines += [f"| {t.term} | {t.meaning} |" for t in terms]
    else:
        lines.append("Add terms as they come up.")
    return "\n".join(lines) + "\n"


def testing_section(a: Answers) -> list[str]:
    """CONTRIBUTING's Testing section, ending with a blank line."""
    assert a.testing is not None
    lines = ["## Testing", "", "| Component | Levels |", "|---|---|"]
    lines += [f"| {c.name} | {', '.join(c.levels)} |" for c in a.testing.components]
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
    """docs/security.md: where secrets live, auth, and the protected paths."""
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
        "them. The Stop hook blocks a change that adds one.",
        "",
        "## Auth",
        "",
        a.security.auth,
        "",
        "## Protected paths",
        "",
        "Claude can't edit these; change them by hand.",
        "",
    ]
    lines += [f"- `{glob}`" for glob in principles["protected"]["paths"]]
    return "\n".join(lines) + "\n"


def dependency_policy(a: Answers) -> list[str]:
    """The Policy section of docs/dependencies.md, ending with a blank line."""
    assert a.dependencies is not None
    deps = a.dependencies
    if deps.updates == "dependabot":
        upgrading = (
            f"Dependabot opens {deps.schedule} update pull requests, per component "
            "and for the CI actions."
        )
    else:
        upgrading = f"Upgrades are manual: check for updates {deps.schedule}."
    return [
        "## Policy",
        "",
        "- Adding: every new dependency gets a row in the log below, with the "
        "reason. The Stop hook blocks a manifest change without one.",
        "- Pinning: lockfiles pin every version. Only the package manager changes "
        "them; Claude can't edit them by hand.",
        f"- Upgrading: {upgrading}",
        "",
    ]


def observability_doc(a: Answers) -> str | None:
    """docs/observability.md, or None when nothing is deployed."""
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
        f"| {c.name} | {c.log_format} | {c.correlation} | {c.telemetry} |"
        for c in a.observability.components
    ]
    lines += [
        "",
        "Levels: `info` in deployed environments, `debug` locally; errors carry the "
        "correlation id.",
    ]
    return "\n".join(lines) + "\n"
