import json
from pathlib import Path
from typing import Any

import pytest
from helpers import SCENARIOS, TODAY, single_component

from alpha.answers import Answers, load_answers
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source, load_defaults
from alpha.principles import build_principles
from alpha.render.docs import render_docs

FIXTURE = Path(__file__).parents[1] / "fixtures" / "answers_valid.json"
D = load_defaults(Source(PLUGIN_ROOT, True))


def load(tmp_path: Path, source: Path = FIXTURE, mutate: Any = None) -> Answers:
    data = json.loads(source.read_text())
    if mutate:
        mutate(data)
    path = tmp_path / ".claude" / "alpha" / "project.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data))
    return load_answers(path)


def render(a: Answers) -> dict[str, str]:
    return render_docs(a, build_principles(D, a, "0.1.0"), 2026, TODAY)


def section(text: str, title: str) -> str:
    return text.split(f"## {title}\n")[1].split("\n## ")[0]


def spec(out: dict[str, str]) -> str:
    return out["docs/alpha/specification.md"]


def contributing(out: dict[str, str]) -> str:
    return out["CONTRIBUTING.md"]


REMOVED = (
    "docs/product.md",
    "docs/architecture.md",
    "docs/build.md",
    "docs/security.md",
    "docs/releases.md",
    "docs/ui.md",
    "docs/data.md",
    "docs/performance.md",
    "docs/observability.md",
)


def test_architecture_lists_responsibilities_contracts_and_errors(tmp_path: Path):
    doc = spec(render(load(tmp_path)))
    resp = section(doc, "Responsibilities")
    assert "| Component | Responsibility | Calls |" in resp
    assert "| api | Embeds and verifies trust payloads in images. | - |" in resp
    assert "| web | Lets users verify an image in the browser. | api |" in resp
    contracts = section(doc, "Contracts")
    assert "openapi" in contracts and "`api/openapi.yaml`" in contracts
    errors = section(doc, "Errors")
    assert "| api | problem-json |" in errors
    assert "| web | user-message |" in errors
    assert "- not-found" in errors
    assert "Every error a user sees says what went wrong and how to fix it." in errors


def test_single_component_has_no_contracts(tmp_path: Path):
    a = load(tmp_path, SCENARIOS / "python-ml-single.json")
    doc = spec(render(a))
    assert "No contracts: components don't call each other." in section(
        doc, "Contracts"
    )


def test_glossary_written_when_terms_exist(tmp_path: Path):
    out = render(load(tmp_path))
    glossary = out["docs/alpha/glossary.md"]
    assert glossary.startswith("# Glossary\n")
    assert glossary.index("| Intact |") < glossary.index("| Payload |")
    assert "- [Glossary](docs/alpha/glossary.md)" in out["CLAUDE.md"]


def test_no_glossary_for_one_component_without_jargon(tmp_path: Path):
    def one(data: dict[str, Any]) -> None:
        single_component(data)
        data["architecture"]["glossary"] = []

    out = render(load(tmp_path, mutate=one))
    assert "docs/alpha/glossary.md" not in out
    assert "Glossary" not in out["CLAUDE.md"]


def test_glossary_with_two_components_and_no_terms_yet(tmp_path: Path):
    def empty(data: dict[str, Any]) -> None:
        data["architecture"]["glossary"] = []

    glossary = render(load(tmp_path, mutate=empty))["docs/alpha/glossary.md"]
    assert "Add terms as they come up" in glossary


def test_contributing_testing_section(tmp_path: Path):
    text = render(load(tmp_path))["CONTRIBUTING.md"]
    testing = section(text, "Testing")
    assert "| api | unit, integration, contract |" in testing
    assert "`tests/<level>/`" in testing
    assert "names its requirement id (e.g. `R1`)" in testing
    order = [text.index(f"## {t}") for t in ("Testing", "Documentation", "Branching")]
    assert order == sorted(order)
    assert "Exhaustive testing" not in text


def test_exhaustive_testing_reaches_contributing_and_claude_md(tmp_path: Path):
    def exhaustive(data: dict[str, Any]) -> None:
        data["testing"]["exhaustive"] = True

    out = render(load(tmp_path, mutate=exhaustive))
    testing = section(out["CONTRIBUTING.md"], "Testing")
    assert "### Exhaustive testing" in testing
    assert "https://www.sqlite.org/testing.html" in testing
    assert "every line and branch it changes" in testing
    assert (
        "- **Exhaustive testing**: Tests take every branch both ways"
        in out["CLAUDE.md"]
    )


def test_security_is_process_and_auth_is_spec(tmp_path: Path):
    out = render(load(tmp_path))
    doc = section(contributing(out), "Security")
    assert "Production secrets live in: Fly.io secrets." in section(doc, "Secrets")
    assert "`.env` files, which git ignores" in section(doc, "Secrets")
    assert "API keys for publishers" in section(spec(out), "Auth")
    assert "Auth" not in doc
    protected = section(doc, "Protected paths")
    assert "- `api/keys/**`" in protected
    assert "- `api/uv.lock`" in protected
    assert "Claude can't edit these" in protected
    assert "Lockfiles change only through the package manager" in protected
    secrets = section(doc, "Secrets")
    assert "the Stop hook blocks a change that adds a secret" in secrets


def test_security_doc_with_nothing_deployed(tmp_path: Path):
    a = load(tmp_path, SCENARIOS / "python-ml-single.json")
    assert "Nothing is deployed." in section(contributing(render(a)), "Secrets")


def test_dependency_policy_precedes_the_log(tmp_path: Path):
    doc = render(load(tmp_path))["docs/alpha/dependencies.md"]
    policy = section(doc, "Policy")
    assert "Adding:" in policy and "Pinning:" in policy
    assert "Dependabot opens weekly update pull requests" in policy
    assert "adds a direct dependency without one" in policy
    assert "upgrades, removals and the packages they pull in need none" in policy
    assert doc.index("## Policy") < doc.index("## Log") < doc.index("| Dependency |")


def test_dependabot_policy_without_ci_leaves_out_the_actions(tmp_path: Path):
    def mutate(data: dict[str, Any]) -> None:
        data["build"]["ci"] = "none"
        data["overrides"].append(
            {
                "principle": "build-hosting-upfront",
                "scope": "project",
                "change": "loosen",
                "params": {},
                "reason": "No CI yet.",
            }
        )

    policy = section(
        render(load(tmp_path, mutate=mutate))["docs/alpha/dependencies.md"], "Policy"
    )
    assert "Dependabot opens weekly update pull requests, per component." in policy
    assert "CI actions" not in policy


def test_manual_updates_policy(tmp_path: Path):
    def manual(data: dict[str, Any]) -> None:
        data["dependencies"] = {"updates": "manual", "schedule": "monthly"}

    doc = render(load(tmp_path, mutate=manual))["docs/alpha/dependencies.md"]
    assert "Upgrades are manual: check for updates monthly." in doc


def test_observability_is_a_spec_section(tmp_path: Path):
    doc = section(spec(render(load(tmp_path))), "Observability")
    assert "| Component | Logs | Correlation | Telemetry |" in doc
    assert "| api | json | traceparent | none |" in doc
    assert "`info` in deployed environments, `debug` locally" in doc


def test_no_observability_doc_when_nothing_is_deployed(tmp_path: Path):
    out = render(load(tmp_path, SCENARIOS / "python-ml-single.json"))
    assert "## Observability" not in spec(out)


def scenario(tmp_path: Path, name: str) -> Answers:
    return load(tmp_path, SCENARIOS / f"{name}.json")


def test_ui_doc_lists_the_visual_system_and_accessibility(tmp_path: Path):
    doc = section(spec(render(load(tmp_path))), "UI")
    visual = section(doc, "Visual system")
    assert "| Component | Library | Tokens | Icons | Typography | Theming |" in visual
    assert (
        "| web | shadcn/ui | `web/src/styles/tokens.css` | lucide | "
        "Inter, system fallback | light-dark |"
    ) in visual
    assert (
        "Build the UI from these; no ad-hoc colors, spacing or fonts outside the "
        "tokens." in visual
    )
    assert "- web: Playwright screenshots" in section(doc, "Visual regression")
    a11y = section(doc, "Accessibility")
    assert "Target: WCAG 2.2 AA." in a11y
    assert "- web: axe in the end-to-end tests" in a11y
    assert "Every UI works with a keyboard and a screen reader." in a11y


def test_storage_is_spec_and_the_migration_rules_are_process(tmp_path: Path):
    out = render(load(tmp_path))
    storage = section(spec(out), "Data")
    assert "| Component | Storage | Migrations | Reversible |" in storage
    assert (
        "| api | PostgreSQL | Alembic: `api/migrations/versions/**` | yes |" in storage
    )
    assert "append-only" not in spec(out)
    rules = section(contributing(out), "Migrations")
    assert "Every schema change is a migration." in rules
    assert "Migrations are append-only" in rules
    assert "(the Stop hook checks)" in rules
    assert "## Experiments" not in contributing(out)


@pytest.mark.parametrize("change", ["no-migrations", "dropped"])
def test_data_doc_states_migration_rules_only_where_they_apply(
    tmp_path: Path, change: str
):
    def mutate(data: dict[str, Any]) -> None:
        if change == "no-migrations":
            entry = data["data"]["components"][0]
            entry.update(migration_tool="none", migrations=[])
        else:
            data["overrides"].append(
                {
                    "principle": "safe-migrations",
                    "scope": "project",
                    "change": "drop",
                    "params": {},
                    "reason": "Schema-less store.",
                }
            )

    out = render(load(tmp_path, mutate=mutate))
    assert "| api | PostgreSQL |" in section(spec(out), "Data")
    assert "## Migrations" not in contributing(out)
    assert "append-only" not in contributing(out)


def test_ml_data_doc_has_experiments_only(tmp_path: Path):
    out = render(scenario(tmp_path, "python-ml-single"))
    assert "## Data" not in spec(out)
    experiments = section(contributing(out), "Experiments")
    assert "- Data versioning: DVC" in experiments
    assert "- Seeds: fixed seeds recorded in the run config" in experiments
    assert "- Experiment tracking: MLflow" in experiments
    assert "## UI" not in spec(out) and "## Performance" not in spec(out)


def test_rust_cli_has_no_ui_or_data_sections(tmp_path: Path):
    out = render(scenario(tmp_path, "rust-cli"))
    assert "## UI" not in spec(out) and "## Data" not in spec(out)
    assert "| cli | startup | 200 ms | hyperfine in CI |" in section(
        spec(out), "Performance"
    )
    assert "CHANGELOG.md" not in out


def test_releases_doc_says_scheme_scope_changelog_and_process(tmp_path: Path):
    doc = section(contributing(render(load(tmp_path))), "Releases")
    assert "Semantic versioning (MAJOR.MINOR.PATCH)" in doc
    assert "One version for the whole repository." in doc
    assert "Changes are recorded in [CHANGELOG.md](CHANGELOG.md)" in doc
    assert "Tag vX.Y.Z on main; CI builds the container and the static site." in doc


def test_releases_doc_wording_follows_the_answers(tmp_path: Path):
    def mutate(data: dict[str, Any]) -> None:
        data["releases"].update(
            scheme="calver", changelog="github-releases", scope="component"
        )

    doc = section(contributing(render(load(tmp_path, mutate=mutate))), "Releases")
    assert "Calendar versioning" in doc
    assert "Each component is versioned on its own" in doc
    assert "GitHub release notes" in doc


def test_changelog_file_only_when_chosen(tmp_path: Path):
    out = render(load(tmp_path))
    log = out["CHANGELOG.md"]
    assert log.startswith("# Changelog\n")
    assert "semantic versioning" in log.lower()
    assert "## Unreleased" in log


def test_changelog_without_version_numbers_goes_by_date(tmp_path: Path):
    def mutate(data: dict[str, Any]) -> None:
        data["releases"]["scheme"] = "none"

    out = render(load(tmp_path, mutate=mutate))
    log = out["CHANGELOG.md"]
    assert "grouped by the date they reached main" in log
    assert "Unreleased" not in log and "version" not in log.lower()
    doc = section(contributing(out), "Releases")
    assert "under the date it reached main" in doc
    assert "moved under the version" not in doc


def test_performance_lists_every_budget(tmp_path: Path):
    doc = section(spec(render(load(tmp_path))), "Performance")
    assert "| Component | Metric | Budget | Measured by |" in doc
    assert "| api | p95 response time | 300 ms | k6 in CI against staging |" in doc
    assert (
        "| web | JavaScript bundle | 200 KB gzipped | the build's size report in CI |"
        in doc
    )


def with_load(data: dict[str, Any]) -> None:
    data["performance"]["expected_load"] = "about 50 concurrent users at peak"


def no_budgets(data: dict[str, Any]) -> None:
    with_load(data)
    for c in data["performance"]["components"]:
        c["budgets"] = []


def test_performance_doc_records_the_expected_load(tmp_path: Path):
    a = load(tmp_path, mutate=with_load)
    doc = section(spec(render(a)), "Performance")
    assert doc.index("| api | p95 response time") < doc.index("### Expected load")
    assert "### Expected load\n\nabout 50 concurrent users at peak\n" in doc
    principles = build_principles(D, a, "0.1.0")
    assert principles["review"]["expected_load"] == "about 50 concurrent users at peak"


def test_an_expected_load_alone_still_gets_a_performance_section(tmp_path: Path):
    doc = spec(render(load(tmp_path, mutate=no_budgets)))
    assert "## Performance\n\n### Expected load\n" in doc
    assert "| Component | Metric |" not in doc


def test_claude_md_links_the_specification_and_contributing(tmp_path: Path):
    out = render(load(tmp_path))
    claude = out["CLAUDE.md"]
    for link in (
        "- [Specification](docs/alpha/specification.md)",
        "- [Contributing](CONTRIBUTING.md)",
        "- [Changelog](CHANGELOG.md)",
    ):
        assert link in claude
    for removed in REMOVED:
        assert removed not in out and removed not in claude, removed


def skip_design_language(data: dict[str, Any]) -> None:
    data["design_language"] = {"defined": False}


def test_design_language_doc_declares_every_part(tmp_path: Path):
    out = render(load(tmp_path))
    doc = out["docs/alpha/design-language.md"]
    assert doc.startswith("# Design language\n")
    assert "It guides; it isn't a wall." in doc
    assert "a deliberate exception passes, drift is a finding" in doc
    assert "mise run check:palette" not in doc
    assert "Calm and technical" in section(doc, "Character")
    assert (
        "| accent | `#0B5FFF` | links, primary actions and the highlighted path in "
        "a diagram |" in section(doc, "Colors")
    )
    assert "Inter for text and labels" in section(doc, "Typography")
    assert "4 px grid" in section(doc, "Shape")
    assert "lucide outline icons" in section(doc, "Icons and imagery")
    assert "Mermaid in Markdown" in section(doc, "Diagrams and charts")
    assert "## Source" not in doc
    assert "[design language](design-language.md)" in section(
        spec(out), "Visual system"
    )


def test_design_language_doc_names_a_fuller_guide(tmp_path: Path):
    def with_guide(data: dict[str, Any]) -> None:
        data["design_language"]["source"] = "docs/brand/guide.pdf"

    doc = render(load(tmp_path, mutate=with_guide))["docs/alpha/design-language.md"]
    assert "The full guide: docs/brand/guide.pdf." in section(doc, "Source")


def test_a_skipped_design_language_writes_nothing_about_visuals(tmp_path: Path):
    out = render(load(tmp_path, mutate=skip_design_language))
    assert "docs/alpha/design-language.md" not in out
    assert "design language" not in section(spec(out), "UI")
    claude = out["CLAUDE.md"]
    assert "design language" not in claude.lower()
    assert "design-language" not in claude


def test_design_language_doc_says_when_the_palette_is_enforced(tmp_path: Path):
    def enforce(data: dict[str, Any]) -> None:
        data["design_language"]["palette_check"] = "enforce"

    doc = render(load(tmp_path, mutate=enforce))["docs/alpha/design-language.md"]
    assert "the `palette` check (`mise run check:palette`) fails on a color" in doc
