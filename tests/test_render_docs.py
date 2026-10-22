import copy
import json
from pathlib import Path
from typing import Any

from helpers import TODAY, override_record, single_component

from alpha.answers import Answers, load_answers
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source, load_defaults
from alpha.principles import build_principles
from alpha.render.docs import _slug, render_docs

FIXTURE = Path(__file__).parent / "fixtures" / "answers_valid.json"
D = load_defaults(Source(PLUGIN_ROOT, True, ""))


def load(tmp_path: Path, mutate: Any = None) -> Answers:
    data = copy.deepcopy(json.loads(FIXTURE.read_text()))
    if mutate:
        mutate(data)
    path = tmp_path / ".claude" / "alpha" / "project.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data))
    return load_answers(path)


def render(a: Answers) -> dict[str, str]:
    return render_docs(a, build_principles(D, a, "0.1.0"), 2026, TODAY)


def cli_only(data: dict[str, Any]) -> None:
    traits = dict.fromkeys(
        ["has_ui", "deployed", "network_calls", "persisted_data", "ml"], False
    )
    traits["nontrivial_logic"] = False
    tool = {"name": "tool", "path": ".", "kind": "cli", "stack": "python"}
    single_component(data, {**tool, "traits": traits})
    data["git"]["scopes"] = ["tool"]
    data["overrides"] = []


def test_claude_md_lists_only_active_principles(tmp_path: Path):
    out = render(load(tmp_path, cli_only))
    md = out["CLAUDE.md"]
    assert "Visual system" not in md
    assert "**Fail fast, fail helpfully**" in md
    assert "docs/principles.toml" in md
    assert len(md.splitlines()) < 150


def test_claude_md_two_components_under_limit(tmp_path: Path):
    md = render(load(tmp_path))["CLAUDE.md"]
    assert len(md.splitlines()) < 150
    assert "## Definition of done" in md
    assert ".claude/skills/commit/SKILL.md" in md


def test_claude_md_has_commands_per_component(tmp_path: Path):
    md = render(load(tmp_path))["CLAUDE.md"]
    commands = md.split("## Commands")[1].split("\n## ")[0]
    assert "uv run pytest" in commands
    assert "pnpm vitest run" in commands
    assert "add when the entry point exists" in commands


def test_claude_md_says_where_code_and_tests_live(tmp_path: Path):
    md = render(load(tmp_path))["CLAUDE.md"]
    commands = md.split("## Commands")[1].split("\n## ")[0]
    assert "Code: `api/**/*.py`" in commands
    assert "Tests: `api/tests/**/*.py`" in commands
    assert "Code: `web/**/*.ts`, `web/**/*.tsx`" in commands
    assert "`web/**/node_modules/**`" in commands


def decision_records(data: dict[str, Any]) -> set[str]:
    areas = {
        f"docs/decisions/{i:04d}-{_slug(d['title'])}.md"
        for i, d in enumerate(data["decisions"], 1)
    }
    return areas | {
        override_record(data, o["principle"], i)
        for i, o in enumerate(data["overrides"])
    }


def test_output_keys_and_decisions_numbered_with_overrides_last(tmp_path: Path):
    fixture = json.loads(FIXTURE.read_text())
    out = render(load(tmp_path))
    assert set(out) == {
        "README.md",
        "LICENSE",
        "CONTRIBUTING.md",
        "CLAUDE.md",
        "docs/product.md",
        "docs/architecture.md",
        "docs/dependencies.md",
        "docs/build.md",
        "docs/guide/README.md",
    } | decision_records(fixture)
    first = out["docs/decisions/0001-product-identity.md"]
    assert first.startswith("# 0001. Product identity")
    for heading in ("Status: accepted", "## Context", "## Decision", "## Consequences"):
        assert heading in first
    override = out[override_record(fixture, "observability")]
    assert "Principle: observability (loosen, scope component:api)" in override
    assert "single-process prototype" in override


def test_mit_license_has_year_and_holder(tmp_path: Path):
    lic = render(load(tmp_path))["LICENSE"]
    assert "Copyright (c) 2026 Semyon Vadishev" in lic
    assert "$" not in lic


def test_apache_and_proprietary_and_custom_license(tmp_path: Path):
    def apache(d: dict[str, Any]) -> None:
        d["identity"]["license"] = "Apache-2.0"

    assert "Apache License" in render(load(tmp_path, apache))["LICENSE"]

    def prop(d: dict[str, Any]) -> None:
        d["identity"]["license"] = "Proprietary"

    lic = render(load(tmp_path / "p", prop))["LICENSE"]
    assert lic.strip() == "Copyright (c) 2026 Semyon Vadishev. All rights reserved."

    custom = tmp_path / "c" / "MY-LICENSE"
    custom.parent.mkdir()
    custom.write_text("Do what thou wilt.\n")

    def own(d: dict[str, Any]) -> None:
        d["identity"]["license_file"] = str(custom)

    assert render(load(tmp_path / "c2", own))["LICENSE"] == "Do what thou wilt.\n"


def test_product_md_requirements_table(tmp_path: Path):
    md = render(load(tmp_path))["docs/product.md"]
    assert "| ID | Requirement | Acceptance check |" in md
    assert "| R1 | A user can embed a signed trust payload into an image. |" in md
    assert "returned image decodes back to the same payload" in md
    assert "Journalists and fact-checkers" in md


def test_architecture_md(tmp_path: Path):
    md = render(load(tmp_path))["docs/architecture.md"]
    assert "monorepo" in md
    assert "| api | api | backend | python |" in md
    assert "communicate" in md
    assert "ruff" in md and "biome" in md


def test_dependencies_md_seeded_per_component(tmp_path: Path):
    md = render(load(tmp_path))["docs/dependencies.md"]
    assert "| Dependency | Component | Why | Added |" in md
    rows = [ln for ln in md.splitlines() if ln.startswith("| ") and "2026" in ln]
    assert len(rows) == 7
    assert any(r.startswith("| pytest | api |") for r in rows)
    assert any(r.startswith("| @biomejs/biome | web |") for r in rows)


def test_contributing_and_readme(tmp_path: Path):
    out = render(load(tmp_path))
    c = out["CONTRIBUTING.md"]
    assert "git config core.hooksPath .claude/alpha/githooks" in c
    assert "50" in c and "72" in c
    assert "`api`" in c and "`feat`" in c
    assert "Trunk-based" in c
    r = out["README.md"]
    assert r.startswith("# Pico Trust")
    assert "uv sync" in r and "pnpm install" in r and "pnpm vitest run" in r


def test_dependencies_md_dates_each_row_in_full(tmp_path: Path):
    md = render(load(tmp_path))["docs/dependencies.md"]
    assert f"| pytest | api | Test runner | {TODAY.isoformat()} |" in md


def test_decision_title_without_ascii_letters_gets_a_name(tmp_path: Path):
    def mutate(data: dict[str, Any]) -> None:
        data["decisions"][0]["title"] = "製品の方向性"

    out = render(load(tmp_path, mutate))
    assert "docs/decisions/0001-decision.md" in out


def no_ci(data: dict[str, Any]) -> None:
    data["build"]["ci"] = "none"
    data["overrides"].append(
        {
            "principle": "build-hosting-upfront",
            "scope": "project",
            "change": "loosen",
            "params": {},
            "reason": "A throwaway prototype with no shared repository.",
        }
    )


def test_build_doc_lists_ci_checks_artifacts_and_environments(tmp_path: Path):
    doc = render(load(tmp_path))["docs/build.md"]
    assert doc.startswith("# Build, CI and hosting\n")
    assert "`.github/workflows/ci.yml`" in doc
    assert "every push to main and every pull request" in doc
    assert (
        "| api | `uv sync`, `uv run ruff format --check`, `uv run ruff check`, "
        "`uv run pyright`, `uv run pytest` |"
    ) in doc
    assert "| api | container | Fly.io |" in doc
    assert "| web | static-site | Cloudflare Pages |" in doc
    assert "## Environments\n\n- production\n" in doc
    assert "alpha creates no cloud resources" in doc


def test_build_doc_without_ci_points_at_the_override(tmp_path: Path):
    doc = render(load(tmp_path, no_ci))["docs/build.md"]
    assert "No CI" in doc
    data = json.loads(FIXTURE.read_text())
    no_ci(data)
    path = override_record(data, "build-hosting-upfront", 1)
    assert f"({path.removeprefix('docs/')})" in doc
    assert "ci.yml" not in doc


def test_build_doc_without_deployed_components(tmp_path: Path):
    def undeployed(data: dict[str, Any]) -> None:
        for c in data["components"]:
            c["traits"]["deployed"] = False
        data["build"]["environments"] = []
        for t in data["build"]["components"]:
            t["hosting"] = ""

    doc = render(load(tmp_path, undeployed))["docs/build.md"]
    assert "## Environments\n\nNone: nothing is deployed.\n" in doc
    assert "| api | container | - |" in doc


def test_contributing_documents_where_docs_live_and_the_mappings(tmp_path: Path):
    text = render(load(tmp_path))["CONTRIBUTING.md"]
    section = text.split("## Documentation\n")[1].split("\n## ")[0]
    assert "Internal docs" in section and "`docs/`" in section
    assert "User-facing documentation lives in `docs/guide/`." in section
    assert "| When these change | Update |" in section
    assert "| `api/**/routes/**` | `docs/guide/**` |" in section
    assert "The Stop hook blocks" in section
    assert text.index("## Documentation") < text.index("## Branching")


def test_external_folder_gets_a_readme_and_a_claude_md_link(tmp_path: Path):
    out = render(load(tmp_path))
    assert out["docs/guide/README.md"].startswith("# Pico Trust guide\n")
    assert "- [User guide](docs/guide/)" in out["CLAUDE.md"]
    assert "- [Build, CI and hosting](docs/build.md)" in out["CLAUDE.md"]


def test_readme_external_docs_add_no_folder(tmp_path: Path):
    def readme(data: dict[str, Any]) -> None:
        data["documentation"].update(external="readme", external_path="")
        data["documentation"]["mappings"] = []

    out = render(load(tmp_path, readme))
    assert not [k for k in out if k.startswith("docs/guide")]
    section = out["CONTRIBUTING.md"].split("## Documentation\n")[1]
    assert "User-facing documentation lives in README.md." in section
    assert "When these change" not in section
    assert "User guide" not in out["CLAUDE.md"]


def test_elsewhere_and_no_external_docs(tmp_path: Path):
    def elsewhere(data: dict[str, Any]) -> None:
        data["documentation"].update(
            external="elsewhere",
            external_path="",
            external_location="https://wiki.example.com/pico",
        )

    text = render(load(tmp_path, elsewhere))["CONTRIBUTING.md"]
    assert "outside this repository: https://wiki.example.com/pico." in text
