"""Repository checks: tools that look at the whole repo, not one component.

Built from the answers, recorded in docs/principles.toml (all but the scheduled
ones) and pinned in the project's root mise.toml.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from alpha.registry import Registry, RegistryError

if TYPE_CHECKING:  # answers imports the CI renderer, which imports this module
    from alpha.answers import Answers

When = Literal["pr", "schedule", "both"]

BETTERLEAKS_CONFIG = ".betterleaks.toml"  # rendered by alpha.render.tooling
_MIGRATIONS = "python3 .claude/alpha/checks/diff_checks.py immutable-migrations"
_SQUAWK = "python3 .claude/alpha/checks/diff_checks.py squawk"
_REVIEW_DATES = "python3 .claude/alpha/checks/review_dates.py"
# Exact pins never fall behind their own request, so compare against the
# newest release (--bump), and only for the project's tools (--no-global).
TOOLCHAIN = "toolchain"  # CI runs it as its own step, after the weekly scans
TOOLCHAIN_FIX = (
    "Pinned tools have newer releases: run mise upgrade --bump --no-global "
    "and commit mise.toml (then rerun the checks)"
)
_TOOLCHAIN = (
    "mise outdated --no-global --bump --json | python3 -c "
    '"import json,sys; d=json.load(sys.stdin); print(json.dumps(d, indent=2)); '
    f"d and print('{TOOLCHAIN_FIX}'); "
    'sys.exit(1 if d else 0)"'
)


@dataclass(frozen=True)
class RepoCheck:
    id: str
    tool: str | None  # the registry id of the tool mise installs for it
    command: str  # what the mise task runs, from the project root
    globs: tuple[str, ...]  # paths whose change makes the Stop hook run it
    stop: bool
    when: When  # where CI runs it
    description: str  # what it checks, for CONTRIBUTING.md


# CI steps that aren't repository checks, which `checked_by` names as
# `ci:<step>`. The other `ci:` names are repository check ids.
CI_STEPS = {
    "tree": "every CI job ends by checking that the checks left the tree unchanged"
}


def _command(registry: Registry, tool: str) -> str:
    pin = registry.tool(tool).pin
    if pin is None:
        raise RegistryError(
            f"Tool {tool!r} has no [tools.{tool}.pin] in registry/tools.toml, so "
            "alpha can't run it as a repository check. Add the pin (mise spec, "
            "version, command, fails_with) after verifying it."
        )
    return pin.command


def _without_offline(command: str) -> str:
    return " ".join(part for part in command.split() if part != "--offline")


def repo_checks(
    a: "Answers", principles: dict[str, Any], registry: Registry
) -> list[RepoCheck]:
    """The project's repository checks, in the catalog's order."""
    lockfiles = tuple(lock for c in principles["components"] for lock in c["lockfiles"])
    data = principles["data"]
    lychee = _command(registry, "lychee")
    checks: list[RepoCheck] = []
    if a.build is not None and a.build.ci == "github-actions":
        checks.append(
            RepoCheck(
                "actions",
                "jactionlint",
                _command(registry, "jactionlint"),
                (".github/**",),
                True,
                "pr",
                "GitHub Actions workflows",
            )
        )
    # The config skips what git ignores, where local secrets belong (.env).
    secrets = f"{_command(registry, 'betterleaks')} --config {BETTERLEAKS_CONFIG}"
    checks.append(
        RepoCheck(
            "secrets",
            "betterleaks",
            secrets,
            ("**",),
            False,
            "pr",
            "Secrets in the working tree",  # `dir` doesn't read git history
        )
    )
    if lockfiles:
        vulns = _command(registry, "osv-scanner")
        checks.append(
            RepoCheck(
                "vulns",
                "osv-scanner",
                vulns,
                lockfiles,
                False,
                "both",
                "Known vulnerabilities in locked dependencies",
            )
        )
    checks += [
        RepoCheck(
            "typos",
            "typos",
            _command(registry, "typos"),
            ("**",),
            True,
            "pr",
            "Spelling in code and docs",
        ),
        RepoCheck(
            "markdown",
            "rumdl",
            _command(registry, "rumdl"),
            ("**/*.md",),
            True,
            "pr",
            "Markdown style",
        ),
        RepoCheck(
            "links",
            "lychee",
            lychee,
            ("**/*.md",),
            True,
            "pr",
            "Relative links in docs resolve",
        ),
        RepoCheck(
            "links-online",
            "lychee",
            _without_offline(lychee),
            (),
            False,
            "schedule",
            "Links to other sites still work",
        ),
        RepoCheck(
            "agent-config",
            "agnix",
            _command(registry, "agnix"),
            ("CLAUDE.md", ".claude/**"),
            True,
            "pr",
            "CLAUDE.md and .claude/ configuration",
        ),
    ]
    if data["migration_paths"]:
        checks.append(
            RepoCheck(
                "migrations",
                None,
                _MIGRATIONS,
                (),
                False,
                "pr",
                "Committed migrations are not edited",
            )
        )
    if data["squawk_paths"]:
        _command(registry, "squawk")  # mise installs it, so it needs a pin
        checks.append(
            RepoCheck(
                "squawk", "squawk", _SQUAWK, (), False, "pr", "Unsafe SQL in migrations"
            )
        )
    checks += [
        RepoCheck(
            "review-dates",
            None,
            _REVIEW_DATES,
            (),
            False,
            "both",
            "Suppressions past their review date",
        ),
        RepoCheck(
            TOOLCHAIN,
            None,
            _TOOLCHAIN,
            (),
            False,
            "schedule",
            "Pinned tools that have a newer release",
        ),
    ]
    return checks


def principles_entries(checks: list[RepoCheck]) -> list[dict[str, Any]]:
    """The `[[repo_checks]]` of docs/principles.toml: every check CI runs on a
    pull request, as the mise task that runs it."""
    return [
        {
            "id": c.id,
            "command": f"mise run check:{c.id}",
            "globs": list(c.globs),
            "stop": c.stop,
        }
        for c in checks
        if c.when != "schedule"
    ]
