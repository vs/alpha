# Alpha Remaining Areas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The interview covers all 17 areas of spec §5. The five still missing are §5.6 UI/UX, §5.12 versioning and releases, §5.13 data and migrations, §5.14 accessibility and §5.15 performance. Each records its decisions and docs, feeds its principle (visual system, accessibility, safe migrations, performance budgets, reproducibility for ML), and adds a mechanical check where one is cheap: migrations become append-only at Stop.

**Architecture:** The 2b pattern again: answers validated in `core_areas.py` with the shared `per_component` check, principles fed from the answers, docs rendered in `area_docs.py`, and one skill per area. An area that doesn't apply (no UI, no stored data) saves its empty answer without asking. `budgets_set` becomes a per-component fact, so the performance-budgets principle applies only where budgets were set.

**Tech Stack:** Python ≥ 3.11 stdlib runtime (hooks 3.9-parseable); pytest, ruff, pyright.

**Spec:** `docs/superpowers/specs/2026-10-19-project-kit-design.md` §5 (areas 6, 12–15), §6 (visual system, accessibility, safe migrations, performance budgets, reproducible), §7 (docs: UI/visual system, release process, data/migrations, performance budgets), §8.

**Plan series:** 2c, after 2d. Then 2e (extend generated projects) and plan 4 (evals).

## Global Constraints

- Area order, as in spec §5: identity, components, architecture, errors, testing, **ui**, documentation, build, security, dependencies, observability, **releases**, **data**, **accessibility**, **performance**, git, agent_workflow (17). A missing area in an older `project.json` is pending.
- Each area skill waits for the area before it in `AREAS` (`test_area_waits_for_the_area_before_it`).
- No ceremony: `ui` and `accessibility` ask nothing without a UI component, and `data` asks nothing without a component that stores data or does ML. Each saves its empty answer and says so in one line.
- Everything stays stack-free: tool names (component libraries, migration tools, test tools) are the user's words, recorded as text, never branched on in code.
- Facts are the kit's job: the skills look up what the component's stack usually uses (the stack is known by then) and recommend from it.
- Hooks: stdlib only, parse on Python 3.9, fail helpfully.

## Review Focus

1. **A project with no UI and no stored data** (the ML scenario has data versioning but no database; the Rust CLI has neither). The empty answers validate, no `docs/ui.md` or migration rules appear, and the ML project still gets its data-versioning section. (Tests in Tasks 1, 2 and 5.)
2. **A migration edited after it was applied.** A change to a migration file that already existed at the session's start blocks Stop; a new migration added in the session passes; a migration created and then edited in the same session passes. (Test in Task 4.)
3. **A component with budgets and one without.** `perf-budgets` applies only to the first. (Test in Task 3.)
4. **A component renamed after these areas are done.** Every per-component area names the stale entry, through the shared check. (Tests in Tasks 1 and 2.)
5. **Release scope "component" in a single-component project.** Refused with a fix: it only makes sense with more than one component. (Test in Task 2.)

---

## File Structure

```
src/alpha/core_areas.py          + Ui, Accessibility, Data (+ MlData), Releases, Performance (+ Budget)
src/alpha/answers.py             AREAS grows to 17; Answers gains five fields
src/alpha/principles.py          per-component budgets_set; params for accessibility, perf-budgets; [data] migration_paths; risk paths
project-files/hooks/stop_checks.py   migrations are append-only
src/alpha/render/area_docs.py    docs/ui.md, docs/data.md, docs/releases.md, docs/performance.md; CHANGELOG.md
src/alpha/render/docs.py         CLAUDE.md links
defaults/defaults.toml           + [ui], [accessibility], [releases], [performance.budgets]
skills/{ui,releases,data,accessibility,performance}/SKILL.md   NEW
skills/new-project/SKILL.md      17 areas; summary; report (nothing "not covered" any more)
tests/fixtures/answers_valid.json, evals/scenarios/*.json        + five areas
```

---

### Task 1: UI and accessibility answers

**Files:** Modify `src/alpha/core_areas.py`, `src/alpha/answers.py`, `skills/new-project/SKILL.md` (the pending-areas list only), the fixture and the three scenarios. Test: `tests/test_core_areas.py`.

**Interfaces:**
- `THEMING = ("light", "dark", "light-dark", "custom")`; `A11Y_LEVELS = ("WCAG 2.2 A", "WCAG 2.2 AA", "WCAG 2.2 AAA")`.
- `UiPlan(name, library: str, tokens: str, icons: str, typography: str, theming: str, visual_regression: str)`, `Ui(components: tuple[UiPlan, ...])`. One entry per component with a UI (`component_facts(c)["has_ui"]`, `reason="has no UI"`). `library`, `icons`, `typography` and `visual_regression` are non-empty text (`"none"` allowed); `tokens` is the path of the design tokens file or folder (relative, matchable; it may not exist yet); `theming` is in `THEMING`.
- `A11yCheck(name, checks: str)`, `Accessibility(level: str, components: tuple[A11yCheck, ...])`. Per UI component; `checks` is non-empty text naming the automated checks (e.g. `"axe in the end-to-end tests"`). `level` is in `A11Y_LEVELS` when any component has a UI, else `""`.
- JSON shape:

```json
"ui": {"components": [{"name": "web", "library": "shadcn/ui", "tokens": "web/src/styles/tokens.css", "icons": "lucide", "typography": "Inter, system fallback", "theming": "light-dark", "visual_regression": "Playwright screenshots"}]},
"accessibility": {"level": "WCAG 2.2 AA", "components": [{"name": "web", "checks": "axe in the end-to-end tests, plus keyboard-only runs of R2"}]}
```

- [ ] **Step 1: Write failing tests**: fixture loads both; non-UI components are refused (`has no UI`); the ML and Rust scenarios have empty answers and `level == ""`; a UI project with `level == ""` fails; bad `theming` lists choices; `tokens` like `"./x"` fails; renames are named (`test_per_component_areas_follow_renames` extended to `ui` and `accessibility`).
- [ ] **Step 2: Run** `uv run pytest tests/test_core_areas.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement**, update the fixture and scenarios (web+API: as above; ML and Rust: empty), and add `ui` and `accessibility` to new-project's pending list.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Add UI and accessibility answers`

---

### Task 2: Releases, data and performance answers

**Files:** Modify `src/alpha/core_areas.py`, `src/alpha/answers.py`, `skills/new-project/SKILL.md` (pending list), the fixture and the scenarios. Test: `tests/test_core_areas.py`.

**Interfaces:**
- `SCHEMES = ("semver", "calver", "none")`, `CHANGELOGS = ("file", "github-releases", "none")`, `RELEASE_SCOPES = ("repo", "component")`.
- `Releases(scheme: str, changelog: str, scope: str, process: str)`: `process` non-empty text (how a release is cut, e.g. "tag vX.Y.Z on main; CI builds and publishes"); `scope == "component"` needs more than one component.
- `DataStore(name, storage: str, migration_tool: str, migrations: tuple[str, ...], reversible: bool)`, `MlData(versioning: str, seeds: str, tracking: str)`, `Data(components: tuple[DataStore, ...], ml: MlData | None)`. `components` is one entry per component with `persisted_data` (`reason="doesn't store data"`); `migrations` are globs of its migration files (non-empty unless `migration_tool == "none"`). `ml` is required when a component has `traits.ml`, otherwise null; its three fields are non-empty text.
- `Budget(metric: str, limit: str, measured_by: str)`, `PerfPlan(name, budgets: tuple[Budget, ...])`, `Performance(components: tuple[PerfPlan, ...])`. One entry per component; `budgets` may be empty.
- JSON shape:

```json
"releases": {"scheme": "semver", "changelog": "file", "scope": "repo", "process": "Tag vX.Y.Z on main; CI builds the container and the static site."},
"data": {"components": [{"name": "api", "storage": "PostgreSQL", "migration_tool": "Alembic", "migrations": ["api/migrations/**"], "reversible": true}], "ml": null},
"performance": {"components": [{"name": "api", "budgets": [{"metric": "p95 response time", "limit": "300 ms", "measured_by": "k6 in CI against staging"}]}, {"name": "web", "budgets": [{"metric": "JavaScript bundle", "limit": "200 KB gzipped", "measured_by": "the build's size report in CI"}]}]}
```

- [ ] **Step 1: Write failing tests**: fixture loads all three; `scope "component"` with one component fails (Review Focus 5); a data entry for a component that doesn't store data fails; missing `ml` for an ML project and present `ml` for a non-ML project fail; empty `migrations` with a real tool fails; budgets with empty fields fail; renames are named.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement**, update the fixture and scenarios (ML: no stored data, `ml` = DVC / fixed seeds recorded in the run config / MLflow; Rust: no data; budgets as above for web+API, `[]` for ML, a startup-time budget for the Rust CLI), and the pending list.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Add releases, data and performance answers`

---

### Task 3: Principles take the new answers

**Files:** Modify `src/alpha/principles.py`. Test: `tests/test_principles.py`.

**Interfaces:**
- `budgets_set` leaves `_PROJECT_ONLY` and becomes a component fact: true for a component whose performance entry has budgets. `compute_facts` reports it true when any component's is.
- `accessibility.params = {"level": <level>}`; `perf-budgets.component_params[<name>] = {"budgets": ["<metric> < <limit> (<measured_by>)", …]}` for each component with budgets; `visual-system.component_params[<name>] = {"tokens": <tokens>}`.
- New top-level `[data] migration_paths = [...]` (every component's `migrations`, deduplicated); `review.risk_paths` gains them and every UI component's `tokens` path (as `<path>` and `<path>/**`).
- The "Answers are incomplete" check covers the 17 areas (it reads `AREAS`).

- [ ] **Step 1: Write failing tests**: `perf-budgets` applies to `["api", "web"]` in the fixture and to none in the ML scenario (Review Focus 3, with one component's budgets emptied); the params above; `migration_paths` and the risk paths.
- [ ] **Step 2: Run** `uv run pytest tests/test_principles.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Feed the principles from the remaining areas`

---

### Task 4: Migrations are append-only

**Files:** Modify `project-files/hooks/stop_checks.py`. Test: `tests/hooks/test_stop_checks.py`.

**Interfaces:** in `find_problems`, for each changed file matching `principles["data"]["migration_paths"]` whose component has `safe-migrations` applying: if the file existed at the session base (`git cat-file -e <base>:<path>`), the change is a problem: `<rel> existed before this session and was changed. Migrations are append-only: put it back (git checkout <base> -- <rel>) and add a new migration instead. Principle safe-migrations.` A file added in the session (absent at the base) may be edited freely. Without a base (no commits yet), nothing is checked. The rule also holds at SubagentStop, through the same function.

- [ ] **Step 1: Write failing tests** (Review Focus 2): editing a committed migration blocks with the message; deleting one blocks; adding a new migration passes; creating then editing one in the session passes; a dropped `safe-migrations` principle turns the check off; no commits, no check.
- [ ] **Step 2: Run** `uv run pytest tests/hooks/test_stop_checks.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hooks): Keep migrations append-only`

---

### Task 5: The remaining docs

**Files:** Modify `src/alpha/render/area_docs.py`, `src/alpha/render/docs.py`. Test: `tests/test_render_area_docs.py`, `tests/test_render_docs.py`.

**Interfaces** (each returns `None` when its area doesn't apply):
- `ui_doc(a) -> str | None`: `docs/ui.md`: `## Visual system` (table Component | Library | Tokens | Icons | Typography | Theming), the rule "Build the UI from these; no ad-hoc colors, spacing or fonts outside the tokens.", `## Visual regression` per component, and `## Accessibility` (the target level and each component's automated checks, plus "Every UI works with a keyboard and a screen reader.").
- `data_doc(a) -> str | None`: `docs/data.md`: `## Storage` (table Component | Storage | Migrations | Reversible), the rules "Every schema change is a migration. Migrations are append-only: once one exists in a commit, add a new one instead of editing it (the Stop hook checks). Write a down migration wherever the change can be undone.", and, for ML, `## Experiments` (data versioning, seeds, tracking).
- `releases_doc(a) -> str`: `docs/releases.md`: scheme, scope, changelog and process in plain words.
- `performance_doc(a) -> str | None`: `docs/performance.md`: table Component | Metric | Budget | Measured by; `None` when no component has budgets.
- `CHANGELOG.md` when `changelog == "file"`: `# Changelog`, one line on the scheme, and `## Unreleased`.
- CLAUDE.md's Docs list links each written doc.

- [ ] **Step 1: Write failing tests** for each document on the fixture, the ML scenario (data doc with `## Experiments` and no storage table; no `ui.md`; no `performance.md`), and the Rust scenario (no `ui.md`, no `data.md`; `performance.md` with the startup budget).
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement**; update `test_output_keys_and_decisions_numbered_with_overrides_last` and `ROOT_ENTRIES` in `tests/test_scenarios.py` (`CHANGELOG.md` at the root when a scenario keeps a changelog file).
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Document UI, data, releases and performance`

---

### Task 6: The five area skills and the entry point

**Files:** Create `skills/ui/SKILL.md`, `skills/releases/SKILL.md`, `skills/data/SKILL.md`, `skills/accessibility/SKILL.md`, `skills/performance/SKILL.md`. Modify `defaults/defaults.toml`, `skills/new-project/SKILL.md`. Test: `tests/test_skills.py`.

**Interfaces:**
- Defaults:

```toml
[ui]
theming = "light-dark"
visual_regression = "screenshots in the end-to-end tests"

[accessibility]
level = "WCAG 2.2 AA"

[releases]
scheme = "semver"
changelog = "file"
scope = "repo"

# Starting budgets per kind; the interview adjusts them to the requirements.
[performance.budgets]
backend = ["p95 response time < 300 ms"]
frontend = ["Largest Contentful Paint < 2.5 s", "JavaScript bundle < 200 KB gzipped"]
mobile = ["cold start < 2 s"]
cli = ["startup < 200 ms"]
library = []
ml = []
worker = ["p95 job time < 30 s"]
```

- Skills (the six sections, interview-only description, one-line `answers write`, `--area <key>` check, ≤ 150 lines, prerequisite = the previous area):
  - **ui**: nothing to ask without a UI. Per UI component, one round: component library, design tokens location, icons, typography, theming (recommend `defaults.ui.theming`), visual regression (recommend `defaults.ui.visual_regression`). Recommend tools that fit the component's stack, looked up, never assumed. Override keys `ui.theming`, `ui.visual_regression`.
  - **releases**: one round: scheme, changelog, scope (ask only with more than one component), and the release process in a sentence drafted from the build answers. Override keys `releases.scheme`, `releases.changelog`, `releases.scope`.
  - **data**: nothing to ask without stored data or ML. Per data component: storage, migration tool (recommend what the stack usually uses), migration file globs, reversible. Explain the append-only rule the Stop hook enforces. With ML: data versioning, seeds, experiment tracking. No kit defaults: per project.
  - **accessibility**: nothing to ask without a UI. Target level (recommend `defaults.accessibility.level`) and, per UI component, the automated checks (recommend a checker that fits its test levels). Override key `accessibility.level`.
  - **performance**: per component, budgets drafted from `defaults.performance.budgets[kind]` and the requirements, each with how it's measured; empty is fine ("no budgets: the principle stays off for it"). Override key `performance.budgets.<kind>`.
- new-project: step 4 lists all 17 skills in `AREAS` order; the summary covers each new area in one line; the final report drops "Not covered yet" and adds "Claude can't edit a migration that existed before the session".
- `test_skills.py`: the five skills join `AREA_SKILLS`; defaults values are within their choice tuples; the report has no "Not covered yet".

- [ ] **Step 1: Write failing tests** for the above.
- [ ] **Step 2: Run** `uv run pytest tests/test_skills.py -q`. Expected: FAIL.
- [ ] **Step 3: Write** the defaults, skills and entry-point changes.
- [ ] **Step 4: Run** `uv run pytest -q` and `claude plugin validate .claude-plugin/marketplace.json`. Expected: PASS, valid.
- [ ] **Step 5: Commit** `feat: Add UI, releases, data, accessibility and performance areas`

---

### Task 7: Live check

**Files:** Modify `CLAUDE.md` (kit live-run notes).

- [ ] **Step 1:** Take all three scenarios through `bin/alpha` (`answers check`, `generate`, `bootstrap`, `commit-skeleton`). Expected: clean trees; the web+API project has `docs/ui.md`, `docs/data.md`, `docs/performance.md`, `docs/releases.md` and `CHANGELOG.md`; the ML project has `docs/data.md` with experiments only; the Rust project has neither ui nor data docs.
- [ ] **Step 2:** In the web+API project, commit a migration under `api/migrations/`, start a new session baseline, edit it, and run the generated Stop hook. Expected: blocked with the append-only message.
- [ ] **Step 3:** With identity through observability done for the web+API scenario (ui included), run `claude -p --plugin-dir /Users/vs/workspace/alpha` on the `releases`, `data`, `accessibility` and `performance` areas in that order, accepting recommendations. Expected: each area's check prints `ok`; the budgets come from the defaults and the requirements.
- [ ] **Step 4:** Record what was verified in the kit's live-run notes.
- [ ] **Step 5: Commit** `docs: Record the remaining areas live check`
