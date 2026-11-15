# Setup first, specification later

Date: 2026-11-15
Status: approved by the user on 2026-11-15, built native in a worktree
Serves: R1, R2 and R4 in docs/product.md (R1's acceptance check changes), and R8

## Why

`/alpha:new-project` and `/alpha:adopt` ask for the whole product up front: requirements with acceptance checks, each component's responsibility and contracts, error categories, performance budgets, data and migrations, UI, accessibility, observability. The user often doesn't know these yet and would need research to answer. In mental the adoption interview settled all eighteen areas and its plan then carried specification work (`p4-spec-open-points`) beside the tooling steps. alpha should own the development lifecycle (checks, tests, reviews, CI, docs wiring) and leave the specification to `/alpha:go`, which grows it as the work needs it.

## Requirements

| ID | Requirement | Acceptance check | Test |
|---|---|---|---|
| F1 | The setup interview runs only the setup areas; the spec areas start `open`. | Given an empty folder, when /alpha:new-project starts, then project.json lists architecture, errors, design_language, ui, observability, data, accessibility and performance as `open`, and the interview invokes only the other ten area skills. | `tests/unit/test_skills.py::test_new_project_runs_only_the_setup_areas` (unit) |
| F2 | Answers accept `open` for a spec area only, and an open area needs no decision. | Given answers with ui `open` and no ui decision, when `alpha answers check` runs, then it prints ok; given git `open`, then it fails naming git as a setup area. | `tests/unit/test_answers.py::test_open_is_allowed_only_for_spec_areas` (unit) |
| F3 | Identity at setup needs no requirements or target users. | Given identity with `requirements: []` and `target_users: ""`, when the project is generated, then docs/product.md says both are not settled yet and names /alpha:go. | `tests/integration/test_generate.py::test_open_areas_render_as_not_settled` (integration) |
| F4 | A generated project lists its open areas that can apply in one place and writes no doc for them. | Given a project generated with every spec area open, then docs/product.md lists each open area that can apply to the components under "Not settled yet" with the /alpha:go request that settles it (UI and accessibility only with a UI component, observability only with a deployed one, data only with one that stores data or does ML), docs/architecture.md says the architecture and errors are not settled, and design-language.md, ui.md, data.md, performance.md, observability.md and glossary.md are not written. | `tests/integration/test_generate.py::test_open_areas_render_as_not_settled`, `::test_open_areas_that_cannot_apply_are_not_listed` (integration) |
| F5 | A principle whose parameters an open area holds stays off until the area is settled. | Given a component with a UI and ui and accessibility open, then visual-system and accessibility are inactive in docs/principles.toml; likewise observability, safe-migrations, contracts, one-vocabulary, design-language and perf-budgets for their areas. | `tests/unit/test_principles.py::test_open_areas_keep_their_principles_off` (unit) |
| F6 | Settling an open area later applies it to the project. | Given a project generated with ui open, when ui is answered and marked done and `alpha update` runs, then ui.md lists the component's library and visual-system becomes active. | `tests/integration/test_update.py::test_settling_an_open_area_applies_it` (integration) |
| F7 | Adopt runs the same setup interview, and its plan holds only tooling and principle work. | Given adopt's skill, then its interview names only the setup areas, and its assessment leaves findings about specification content out of `adoption.steps` and lists them in the final report as /alpha:go tasks. | `tests/unit/test_skills.py::test_adopt_runs_only_the_setup_areas_and_plans_no_spec_work` (unit) |
| F8 | `/alpha:go` settles open areas: on request, and before a feature that needs one. | Given the go skill, then a Specify playbook settles a named open area through /alpha:extend, and the feature playbook settles each open area the feature touches before its spec. | `tests/unit/test_go_skill.py::test_open_areas_are_settled_by_specify_and_before_a_feature` (unit) |

## Design

**Setup areas** (asked by new-project and adopt, as today): identity, components, testing, documentation, build, security, dependencies, releases, git, agent_workflow. Identity keeps name, slug, value proposition, license and copyright; `requirements` may be `[]`, `target_users` and `security.auth` may be `""`, and `domain_jargon` defaults to false.

**Spec areas** (start `open`): architecture, errors, design_language, ui, observability, data, accessibility, performance. `answers.py` gains the status `open`, allowed only for these. `require_areas` accepts `open` for them; an open area parses to `None` and needs no decision.

**Principles.** Each catalog principle whose parameters a spec area holds names it, `settled_by = "<area>"` in `defaults/defaults.toml`: visual-system (ui), accessibility (accessibility), observability (observability), safe-migrations (data), contracts and one-vocabulary (architecture), design-language (design_language), perf-budgets (performance). `build_principles` keeps such a principle inactive while its area is open, and reads an open area's parameters as empty (no migration paths, tokens, contract paths or budgets).

**Docs.** An open area's own doc isn't written, as today for an area that doesn't apply. docs/product.md gains a "Not settled yet" section: one line per open area (and for empty requirements or target users) with the request that settles it, e.g. "Performance budgets: `/alpha:go settle the performance budgets`". docs/architecture.md, always written, says the same for open architecture and errors.

**Settling later.** Unchanged machinery: `/alpha:extend` runs the area skill, marks the area done with its decision, and `alpha update` re-renders. The spec area skills' "Before you start" accepts an open area on a generated or adopted project.

**Skills.** new-project and adopt invoke only the setup areas and write the spec areas as `open`; their summaries list the open areas. Adopt's assessment keeps findings about code, checks and principles, and reports findings about specification content (open questions, proposals in the product docs) as `/alpha:go` tasks. The identity skill stops asking requirements and target users at setup. `/alpha:go` gets a Specify playbook (research the options, then settle the area through `/alpha:extend`), and the feature playbook settles each open area the feature touches before its spec.

**Existing projects.** Every area of a project generated or adopted before this change is done, so nothing changes for it. The files that changed since kit 0.8.0 are updated by hand in alpha and mental: the copied `review-change` skill and the `.claude/alpha/notes/` ignore line, plus whatever this change alters in copied files.

## Plan

1. Answers: the `open` status, spec-area list, open areas need no decision, empty identity requirements and target users (`answers.py`, `tests/unit/test_answers.py`). Makes F2 pass.
2. Principles: `settled_by` in the catalog and the gate in `build_principles` (`defaults/defaults.toml`, `principles.py`, `tests/unit/test_principles.py`). Makes F5 pass.
3. Rendering: open areas and empty identity fields as not settled (`render/area_docs.py`, `render/docs.py`, a scenario fixture with open areas, `tests/integration/test_generate.py`). Makes F3 and F4 pass.
4. Settling later: `alpha update` from open to done (`tests/integration/test_update.py`, any fix it needs). Makes F6 pass.
5. Skills: new-project, adopt, identity, the spec area skills and extend (`skills/*/SKILL.md`, `tests/unit/test_skills.py`). Makes F1 and F7 pass.
6. `/alpha:go`: the Specify playbook and the feature playbook step (`skills/go/`, `tests/unit/test_go_skill.py`). Makes F8 pass.
7. Records and docs: a decision record, the design spec (§2, §4, §5, §5b), README and CLAUDE.md; R1's acceptance check through `/alpha:extend`; the eval briefs if they assume spec answers.
8. Hand updates in alpha and mental (mental after the merge).

## Decisions

- Two kinds of area, settled by the user (Q1): setup areas wire tooling, spec areas describe the product.
- An explicit `open` status (Q2), so alpha and the reviewer can tell an unsettled area from an empty answer.
- `/alpha:go` settles open areas on request (a Specify playbook) and before a feature that touches one (Q3).
- Adopt's plan holds only tooling and principle work (Q4).
- No migration for existing projects; their changed files are updated by hand in alpha and mental (Q5, and the user's follow-up).
- Claude's choice: requirements, target users and auth stay fields of their setup areas, allowed empty, rather than becoming new areas; fewer moving parts, and the feature playbook already adds requirements through `/alpha:extend`.
- Claude's choice: the gate lives in the catalog as `settled_by`, so the principles file stays the one place that says when a principle applies.
- Found while building: each area skill refused to start until the area before it in the old order was done, so open areas broke the chain. A setup area now waits for the setup area before it, and a spec area waits for the whole setup (agent workflow done).
- Found while building: adopt's advice for the design language of an existing repo (define one only when the repo has one; palette check `advise`) moved into the design-language skill, which now runs only when the area is settled later.
- Found while building: settling an area runs `/alpha:extend`, which commits, so the feature playbook grills the open areas a feature needs with its other questions and applies them only after the spec is approved, on the feature branch.
- Found while building: the evals fail an interview that settles a spec area, and their briefs drop the design language, observability and data notes.
- Approved by the user after a run of the CLI showed the gap: docs/product.md lists only the open areas that can apply, so a CLI with no UI, deployment or stored data isn't told to settle its UI, observability or data.
- The hand updates for mental wait until this branch is merged, since this work runs in an alpha worktree.

## Out of scope

- Reopening a done area.
- Changing what any setup area asks, beyond identity.
- Migrating existing projects' answers.
