import copy
import json
from pathlib import Path
from typing import Any

from helpers import TODAY, clone_component, override_record, single_component

from alpha.answers import Answers, load_answers
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source, load_defaults
from alpha.principles import build_principles
from alpha.records import slug as _slug
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
        "docs/glossary.md",
        "docs/security.md",
        "docs/observability.md",
        "docs/ui.md",
        "docs/data.md",
        "docs/releases.md",
        "docs/performance.md",
        "CHANGELOG.md",
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
    assert len(rows) == 13
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
        "`uv run pyright`, `uv run deptry .`, `uv run pytest` |"
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
        data["observability"]["components"] = []

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


WORKING_RULES = [
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
    "- Remove dead code and replaced internal APIs without asking, but ask "
    "before removing code or behavior that looks intentional.",
    "- Commit only the files you changed for the work, staged by path. Other "
    "changes in the tree may be the user's or another session's, so don't stage, "
    "stash or reset them; the hooks block the commands that would.",
    "- Subagents work under the same principles, decisions and checks.",
    "- Before you report work as done, re-read every changed file top to bottom "
    "as a stranger would.",
    "- At the end of a planned piece of work, run the principles-reviewer agent.",
    "- When you add a code generator, add a `generate` task to `mise.toml` and to "
    "the `ci` task's `depends`; CI fails when checks change tracked files.",
    "- Never disable a lint rule to pass; an exception names one path and one "
    "rule, gives a reason, and needs the user's yes.",
    "- A security suppression (osv-scanner, betterleaks) needs a reason and a "
    "review date: in the `osv-scanner.toml` next to the lockfile it applies "
    "to, `ignoreUntil` and `reason`; in "
    "`.betterleaksignore`, a `# <reason> (review YYYY-MM-DD)` line directly "
    "above the entry.",
]
COMMUNICATION = [
    "- Answer a question before making edits or running commands for it.",
    "- When responding to feedback or a review, say first whether you agree, "
    "then what you changed.",
    "- Be concise and direct: plain technical prose, no filler, no emojis. "
    "Define jargon you can't avoid.",
    "- Explain a non-trivial problem or design as the problem, a concrete example "
    "or short trace, then the solution and why it's needed.",
]


def test_claude_md_has_working_rules(tmp_path: Path):
    md = render(load(tmp_path))["CLAUDE.md"]
    section = md.split("## Working rules\n\n")[1].split("\n\n## ")[0]
    assert section.splitlines() == WORKING_RULES
    talk = md.split("## Communication\n\n")[1].split("\n\n## ")[0]
    assert talk.splitlines() == COMMUNICATION
    headings = ("## Principles", "## Working rules", "## Communication", "## Commands")
    order = [md.index(h) for h in headings]
    assert order == sorted(order)


def test_overridden_principle_names_its_record(tmp_path: Path):
    md = render(load(tmp_path))["CLAUDE.md"]
    record = override_record(json.loads(FIXTURE.read_text()), "observability")
    line = next(x for x in md.splitlines() if x.startswith("- **Observability**"))
    assert line.endswith(f"(overridden: see {record})")


def test_contributing_names_the_review_checkpoint(tmp_path: Path):
    text = render(load(tmp_path))["CONTRIBUTING.md"]
    branching = text.split("## Branching\n")[1]
    assert (
        "Claude runs the principles reviewer before its work reaches main: a "
        "push to main, or merging a pull request. People can push by hand." in branching
    )


def feature_branches(data: dict[str, Any]) -> None:
    data["git"]["branching"] = "feature-branches"


def test_feature_branches_merge_through_pull_requests(tmp_path: Path):
    out = render(load(tmp_path, feature_branches))
    branching = out["CONTRIBUTING.md"].split("## Branching\n")[1]
    assert "Feature branches: short-lived branches merged into main through " in (
        branching
    )
    assert "rebase the branch on main into small, ordered commits" in branching
    assert "--force-with-lease" in branching
    commits = out["CLAUDE.md"].split("## Commits\n")[1].split("\n## ")[0]
    assert "open a pull request into main" in commits


def test_trunk_commits_straight_to_main(tmp_path: Path):
    out = render(load(tmp_path))
    assert "Trunk-based" in out["CONTRIBUTING.md"]
    commits = out["CLAUDE.md"].split("## Commits\n")[1].split("\n## ")[0]
    assert "pull request" not in commits


def _cells(row: str) -> int:
    return row.replace("\\|", "").count("|") - 1


def test_pipes_and_line_breaks_in_answers_stay_inside_table_cells(tmp_path: Path):
    odd = "a | b\nc"

    def mutate(data: dict[str, Any]) -> None:
        data["identity"]["requirements"][0]["text"] = odd
        data["identity"]["requirements"][0]["acceptance"] = odd
        data["architecture"]["components"][0]["responsibility"] = odd
        data["architecture"]["glossary"][0]["meaning"] = odd
        data["build"]["components"][0]["hosting"] = odd
        data["ui"]["components"][0]["library"] = odd
        data["data"]["components"][0]["storage"] = odd
        data["performance"]["components"][0]["budgets"][0]["measured_by"] = odd

    out = render(load(tmp_path, mutate))
    checked = 0
    for name, text in out.items():
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("|") and i and not lines[i - 1].startswith("|"):
                header = _cells(line)
                for row in lines[i + 1 :]:
                    if not row.startswith("|"):
                        break
                    assert _cells(row) == header, f"{name}: {row}"
                    checked += 1
        assert "a | b" not in text, name
    assert checked > 20


def test_claude_md_lists_each_stacks_rules_once(tmp_path: Path):
    md = render(
        load(tmp_path, lambda d: clone_component(d, "api", "worker", "worker"))
    )["CLAUDE.md"]
    section = md.split("## Stack rules\n\n")[1].split("\n## ")[0]
    assert section.splitlines() == [
        "### python (api, worker)",
        "",
        "- **python:uv-for-dependencies**: Add and remove dependencies with "
        "`uv add` and `uv remove`, never by editing the dependency lists in "
        "`pyproject.toml` or with `pip`.",
        "- **python:typed-boundaries**: Parse external input (JSON, files, "
        "environment, requests) into dataclasses or typed models at the "
        "boundary; don't pass `dict[str, Any]` inward.",
        "- **python:import-contracts**: Once a component has more than one "
        "package, add import-linter contracts for the layers "
        "`docs/architecture.md` names, and add `lint-imports` to its "
        "`structure` command.",
        "",
        "### typescript (web)",
        "",
        "- **typescript:top-level-imports**: Import at the top of the file only: "
        'no `await import()` and no `import("pkg").Type` in types.',
        "- **typescript:unknown-at-boundaries**: External data (JSON, request "
        "bodies, environment) enters as `unknown` and is narrowed by a schema or "
        "a type guard, never by `as`.",
        "- **typescript:pnpm-for-dependencies**: Add and remove dependencies with "
        "`pnpm add` and `pnpm remove`, and don't approve a dependency's install "
        "scripts (`pnpm approve-builds`) without asking the user.",
    ]
    headings = ("## Communication", "## Stack rules", "## Commands")
    assert [md.index(h) for h in headings] == sorted(md.index(h) for h in headings)


def test_claude_md_has_no_stack_rules_section_without_rules(tmp_path: Path):
    a = load(tmp_path)
    principles = build_principles(D, a, "0.1.0")
    for comp in principles["components"]:
        comp["rules"] = []
    md = render_docs(a, principles, 2026, TODAY)["CLAUDE.md"]
    assert "## Stack rules" not in md
    assert "## Communication" in md and "## Commands" in md


def test_claude_md_says_how_to_run_every_check(tmp_path: Path):
    md = render(load(tmp_path))["CLAUDE.md"]
    assert "Run every check: `mise run check` (CI runs the same checks)" in md
    assert md.index("Run every check") > md.index("## Commands")
    assert md.index("Run every check") < md.index("## Definition of done")


def test_claude_md_rules_for_generators_lint_and_suppressions(tmp_path: Path):
    md = render(load(tmp_path))["CLAUDE.md"]
    for line in (
        "- When you add a code generator, add a `generate` task to `mise.toml` and "
        "to the `ci` task's `depends`; CI fails when checks change tracked files.",
        "- Never disable a lint rule to pass; an exception names one path and one "
        "rule, gives a reason, and needs the user's yes.",
        "- A security suppression (osv-scanner, betterleaks) needs a reason and a "
        "review date: in the `osv-scanner.toml` next to the lockfile it applies "
        "to, `ignoreUntil` and `reason`; in "
        "`.betterleaksignore`, a `# <reason> (review YYYY-MM-DD)` line directly "
        "above the entry.",
    ):
        assert line in md
    assert "trailing comment" not in md


def test_claude_md_points_at_the_commit_skill(tmp_path: Path):
    # The skill is user-invoked only, so this line is how Claude finds it.
    md = render(load(tmp_path))["CLAUDE.md"]
    assert "Follow the commit skill (`.claude/skills/commit/SKILL.md`" in md
    assert md.index("## Commits") < md.index("commit skill")


def test_contributing_documents_the_checks(tmp_path: Path):
    md = render(load(tmp_path))["CONTRIBUTING.md"]
    section = md[md.index("## Checks") :].split("\n## ")[0]
    assert "mise install" in section
    assert "mise run check" in section
    assert "| Check | What it checks | Runs |" in section
    rows = section.splitlines()
    assert (
        "| secrets | Secrets in the working tree (betterleaks) | pull request |" in rows
    )
    assert (
        "| typos | Spelling in code and docs (typos) | pull request, at Stop |" in rows
    )
    assert (
        "| links-online | Links to other sites still work (lychee) | weekly |" in rows
    )
    assert (
        "| vulns | Known vulnerabilities in locked dependencies (osv-scanner) "
        "| pull request, weekly |"
    ) in rows
    assert "`ci:tree` is when every CI job ends by checking" in section


def test_contributing_lists_no_data_checks_without_data(tmp_path: Path):
    md = render(load(tmp_path, cli_only))["CONTRIBUTING.md"]
    section = md[md.index("## Checks") :].split("\n## ")[0]
    assert "| typos |" in section
    assert "| migrations |" not in section and "| squawk |" not in section
