import copy
import json
from pathlib import Path
from typing import Any

from helpers import TODAY

from alpha.answers import Answers, load_answers
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source, load_defaults
from alpha.principles import build_principles
from alpha.render.docs import render_docs

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
    data["components"] = [
        {
            "name": "tool",
            "path": ".",
            "kind": "cli",
            "stack": "python",
            "traits": traits,
        }
    ]
    data["components_talk"] = False
    data["git"]["scopes"] = ["tool"]
    data["overrides"] = []
    data["build"]["components"] = [
        {"name": "tool", "artifact": "package", "hosting": ""}
    ]


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


def test_output_keys_and_decisions_numbered_with_overrides_last(tmp_path: Path):
    out = render(load(tmp_path))
    assert set(out) == {
        "README.md",
        "LICENSE",
        "CONTRIBUTING.md",
        "CLAUDE.md",
        "docs/product.md",
        "docs/architecture.md",
        "docs/dependencies.md",
        "docs/decisions/0001-product-identity.md",
        "docs/decisions/0002-python-api-plus-typescript-web.md",
        "docs/decisions/0003-user-guide-in-docs-guide.md",
        "docs/decisions/0004-github-actions-containers-and-static-hosting.md",
        "docs/decisions/0005-conventional-commits-on-trunk.md",
        "docs/decisions/0006-batched-review.md",
        "docs/decisions/0007-override-observability.md",
    }
    first = out["docs/decisions/0001-product-identity.md"]
    assert first.startswith("# 0001. Product identity")
    for heading in ("Status: accepted", "## Context", "## Decision", "## Consequences"):
        assert heading in first
    override = out["docs/decisions/0007-override-observability.md"]
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
