# One process doc, one spec doc

Date: 2026-11-15
Status: approved by the user on 2026-11-15, built native in this checkout
Serves: R2 in docs/specification.md (what a generated skeleton holds)

## Why

A generated project spreads its docs over a dozen files in `docs/`, mixing how the team works with what the product is. The user wants the development process in one file and the product's specification in another, so `/alpha:go` grows the specification in one place while the process stays put.

## Requirements

| ID | Requirement | Acceptance check | Test |
|---|---|---|---|
| F1 | The project's specification is one file, `docs/specification.md`. | Given a generated project with its spec areas settled, then docs/specification.md holds the value proposition, target users, requirements, the "Not settled yet" list, architecture, errors, auth, UI and accessibility, data storage, performance and observability (each section only where its area applies), and product.md, architecture.md, security.md, ui.md, data.md, performance.md and observability.md are not written. | `tests/integration/test_generate.py::test_the_specification_is_one_file` (integration) |
| F2 | The development process is in `CONTRIBUTING.md`. | Given a generated project, then CONTRIBUTING.md holds, besides what it holds today, the layout and components, build, CI and hosting, releases, secrets and protected paths, and the migration and experiment rules where they apply, and build.md and releases.md are not written. | `tests/integration/test_generate.py::test_the_process_is_in_contributing` (integration) |
| F3 | The files that stay separate keep their paths. | Given a generated project, then docs/principles.toml, docs/decisions/, docs/dependencies.md, and where they apply docs/design-language.md, docs/glossary.md and docs/adoption.md, are written as today. | `tests/integration/test_generate.py::test_the_specification_is_one_file` (integration) |
| F4 | Nothing the kit ships names a removed doc. | Given the kit's skills, playbooks, copied project files, recipes and renderers, then none names docs/product.md, docs/architecture.md, docs/build.md, docs/security.md, docs/releases.md, docs/ui.md, docs/data.md, docs/performance.md or docs/observability.md. | `tests/unit/test_skills.py::test_no_kit_file_names_a_removed_doc` (unit) |
| F5 | CLAUDE.md's docs list links only files the project has. | Given a generated project, then every link under "## Docs" in CLAUDE.md points to a file that exists. | `tests/integration/test_generate.py::test_claude_md_links_only_existing_docs` (integration) |

## Design

**docs/specification.md** (rendered from the answers, as today's spec docs are): `# <Name>: specification`, then Value proposition, Target users, Requirements, Not settled yet, Architecture (responsibilities, contracts), Errors, Auth, UI (visual system, visual regression, accessibility), Data (storage per component), Performance (budgets, expected load), Observability. A section whose area can't apply (no UI component, nothing deployed, nothing stored) is left out; an open area that applies says so and is listed under "Not settled yet". Feature specs stay in `docs/specs/`.

**CONTRIBUTING.md** gains: Components (layout, the components table, the workspace), Build, CI and hosting (today's build.md), Releases (today's releases.md), Security (secrets and protected paths), Migrations (the append-only rule, when a component has migrations) and Experiments (data versioning, seeds, tracking, when a component does ML).

**Stay separate:** docs/principles.toml (the hooks parse it), docs/decisions/ (numbered records), docs/dependencies.md (the Stop hook checks the file changed when a lockfile did; inside a shared file any edit would pass), docs/design-language.md (a risk path; user decision), docs/glossary.md (user decision), docs/adoption.md (a temporary plan). README.md, CLAUDE.md and CHANGELOG.md keep their places.

**Renderers.** `render/area_docs.py`'s per-area docs become sections; `render/docs.py` builds the two files and CLAUDE.md's docs list from what exists.

**References.** Every skill, playbook, copied skill (review-change, audit, debt) and the Python recipe's import-contracts rule names docs/specification.md or CONTRIBUTING.md instead. Requirements still trace to rows, now in docs/specification.md.

**Existing projects.** Nothing migrates. alpha's own docs move to the new layout by hand; mental is re-adopted from scratch by the user.

## Plan

1. Renderers: the specification, the CONTRIBUTING sections and CLAUDE.md's docs list (`render/docs.py`, `render/area_docs.py`, their unit tests, `tests/integration/test_generate.py`). Makes F1, F2, F3 and F5 pass.
2. References: skills, playbooks, copied skills and the recipe rule (`skills/**`, `project-files/skills/**`, `recipes/python.toml`, `tests/unit/test_skills.py`). Makes F4 pass.
3. Records and docs: a decision record, the design spec (§7), README and CLAUDE.md.
4. alpha's own docs by hand: render the two files from its answers, remove the old ones, and keep `alpha update` at nothing to change.

## Decisions

- Process goes in CONTRIBUTING.md (user).
- The whole project's specification is docs/specification.md, rendered from the answers; feature specs stay in docs/specs/ (user).
- docs/design-language.md keeps its own file and its risk path (user).
- docs/glossary.md keeps its own file (user).
- Migration and experiment rules go in CONTRIBUTING.md, storage in the specification (user).
- Claude's choice: docs/dependencies.md and docs/adoption.md stay separate, for the reasons above.

## Out of scope

- Letting a project choose other file names.
- Migrating existing projects.
