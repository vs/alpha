# Alpha Core Areas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the six interview areas every project needs (§5.3 architecture, §5.4 errors, §5.5 testing, §5.9 security and secrets, §5.10 dependencies, §5.11 observability), so a generated project records its boundaries, contracts, error format, test levels, secrets policy, update policy and logging, with mechanical checks wherever one is cheap.

**Architecture:** Each area follows the 2a pattern: a skill saves answers into `project.json`, the CLI validates them, `build_principles` turns the enforceable parts into `docs/principles.toml` (extra protected paths, contract risk paths), and the renderers write the docs. Per-component answers share one cross-check against `components`. Dependency updates get a generated `.github/dependabot.yml` whose ecosystems come from the recipes, so the code stays stack-free.

**Tech Stack:** Python ≥ 3.11 stdlib runtime; pytest, ruff, pyright, PyYAML (dev); Dependabot.

**Spec:** `docs/superpowers/specs/2026-10-19-project-kit-design.md`

**Plan series:** 2b of 2a–2e (2a: documentation, build/CI/hosting; **2b: architecture, errors, testing, security, dependencies, observability**; 2c: UI/UX, accessibility, data, performance, releases; 2d: generic stack; 2e: §5a). Then plan 3 (reviewer), plan 4 (evals).

## Global Constraints

- Everything in the foundation and 2a Global Constraints still holds: no app code, nothing kit-specific at the root, fail helpfully (`_fail(where, problem, fix)`), stdlib runtime, no stack names outside `recipes/` (`test_recipes_name_no_stack_outside_recipes`), 50/72 commit rules.
- Area order, as in spec §5: `identity`, `components`, `architecture`, `errors`, `testing`, `documentation`, `build`, `security`, `dependencies`, `observability`, `git`, `agent_workflow`. An area missing from an older `project.json` is `"pending"` (2a behavior).
- Questions are worded for any kind of application; recommendations come from kit defaults keyed by component kind.
- **No ceremony on small projects** (spec §2): an area whose principles don't apply to any component (observability with nothing deployed; contracts with one component) saves its "not applicable" answer without asking and says so in one line.
- Per-component answers (`architecture.components`, `errors.components`, `testing.components`, `observability.components`) are validated against `components` exactly like `build.components`: one entry per component (observability: per *deployed* component), by name, with the 2a messages.
- Dependabot: one update entry per component (ecosystem from the recipe, `directory` `/` for a root component, else `/<path>`), plus `github-actions` at `/` when CI is GitHub Actions. Look up the current ecosystem names (`uv`, `npm` for pnpm) in GitHub's Dependabot docs at implementation time.
- Kit dev commands: `uv run pytest`, `uv run pytest -m slow`, `uv run ruff check`, `uv run ruff format`, `uv run pyright`.

## Review Focus

1. **A project with nothing deployed and one component.** Observability, contracts and calls are "not applicable": the skills must not ask, validation must accept the empty answers, and no `docs/observability.md` is written. (Tests in Tasks 3 and 6.)
2. **Components that call each other with no contract.** `calls` non-empty with `contracts.format = "none"` (or `components_talk = false`) must fail with a fix. (Test in Task 2.)
3. **An extra protected glob that blocks required work** (`docs/**`, `**/*.toml`, `**/package.json`). Protecting a mapped doc, the principles file or a component manifest would deadlock the docs and dependency checks; the principles builder must refuse it. (Test in Task 4.)
4. **Dependabot for a component at the root.** `directory` is `/`, never `/.`. (Test in Task 7.)
5. **A component renamed after these areas are done.** Every per-component area names the stale or missing entry. (Tests in Tasks 2 and 3, through the shared check.)

---

## File Structure

```
src/alpha/validate.py             NEW: AnswersError, _fail and the field validators moved out of answers.py
src/alpha/answers.py              AREAS grows; Answers gains six fields; per-component check shared
src/alpha/core_areas.py           NEW: dataclasses + validators for the six areas
src/alpha/principles.py           protected += security.extra_protected (checked); risk_paths += contracts.paths
src/alpha/render/area_docs.py     NEW: glossary, security, observability docs; architecture/CONTRIBUTING/dependencies sections
src/alpha/render/docs.py          calls area_docs; CLAUDE.md links
src/alpha/render/ci.py            + render_dependabot
src/alpha/recipes.py, recipes/*.toml  + dependabot ecosystem
src/alpha/generate.py, gitops.py  dependabot file and its commit
defaults/defaults.toml            + [architecture], [errors], [testing], [dependencies], [observability]
skills/{architecture,errors,testing,security,dependencies,observability}/SKILL.md  NEW
skills/documentation/SKILL.md     contract mappings come from architecture.contracts.paths
skills/new-project/SKILL.md       twelve areas, summary, report
tests/fixtures/answers_valid.json, evals/scenarios/*.json  + six areas
```

---

### Task 1: Move the field validators out of answers.py

**Files:** Create `src/alpha/validate.py`. Modify `src/alpha/answers.py`. Test: existing suite only (a pure move).

**Interfaces:**
- Produces in `validate.py` (Task 2 adds `per_component` here): `AnswersError`, `NAME` (the `[a-z][a-z0-9-]*` pattern), `fail`, `join`, `obj`, `as_list`, `get`, `string`, `boolean`, `pos_int`, `choice`, `strings`, `unmatchable`, `relative`, `paths` — the current private helpers under public names, same signatures and messages. `answers.py` re-exports `AnswersError` (tests and the CLI import it from there).

- [ ] **Step 1:** Move the helpers; rename call sites. No behavior change.
- [ ] **Step 2: Run** `uv run pytest -q && uv run pyright`. Expected: same pass count as before, 0 errors.
- [ ] **Step 3: Commit** `refactor: Move answer field validators to validate.py`

---

### Task 2: Architecture, errors and testing answers

**Files:** Create `src/alpha/core_areas.py`. Modify `src/alpha/answers.py`, the fixture and both scenarios. Test: `tests/test_core_areas.py`.

**Interfaces:**
- Consumes: `validate.*` (Task 1).
- Produces:
  - `AREAS` with `architecture`, `errors`, `testing` inserted after `components`; `_TOP_KEYS` gains them; `Answers` gains `architecture: Architecture | None`, `errors: Errors | None`, `testing: Testing | None`.
  - `per_component(targets: Sequence[Named], comps: Sequence[C], where: str, *, only: Callable[[C], bool] = lambda c: True) -> None` in `validate.py`, where `Named` is a `Protocol` with `name: str` and `C` a TypeVar bound to it: the 2a `build.components` checks (unknown name, missing, duplicate), for the components `only` selects; an entry for a component `only` rejects fails with `component 'x' <reason>` (pass `reason="isn't deployed"`). `_build` uses it too. `core_areas.py` imports `Component` only under `TYPE_CHECKING`, so `answers.py` can import `core_areas` without a cycle.
  - `CONTRACT_FORMATS = ("openapi", "json-schema", "protobuf", "graphql", "other", "none")`; `ERROR_FORMATS = ("problem-json", "message-and-exit-code", "user-message", "exceptions", "structured-log", "other")`; `TEST_LEVELS = ("unit", "integration", "end-to-end", "contract")`.
  - Dataclasses (frozen): `Responsibility(name, responsibility: str, calls: tuple[str, ...])`, `Contracts(format: str, paths: tuple[str, ...])`, `Term(term: str, meaning: str)`, `Architecture(components: tuple[Responsibility, ...], contracts: Contracts, glossary: tuple[Term, ...])`; `ErrorFormat(name, format: str)`, `Errors(components: tuple[ErrorFormat, ...], categories: tuple[str, ...])`; `TestPlan(name, levels: tuple[str, ...])`, `Testing(components: tuple[TestPlan, ...])`.
- JSON shape:

```json
"architecture": {"components": [{"name": "api", "responsibility": "Embeds and verifies payloads.", "calls": []},
                                {"name": "web", "responsibility": "Lets users verify images.", "calls": ["api"]}],
                 "contracts": {"format": "openapi", "paths": ["api/openapi.yaml"]},
                 "glossary": [{"term": "Payload", "meaning": "The signed trust data hidden in an image."}]},
"errors": {"components": [{"name": "api", "format": "problem-json"}, {"name": "web", "format": "user-message"}],
           "categories": ["validation", "not-found", "conflict", "unavailable", "internal"]},
"testing": {"components": [{"name": "api", "levels": ["unit", "integration", "contract"]},
                           {"name": "web", "levels": ["unit", "end-to-end"]}]}
```

Validation rules:
- `responsibility` non-empty. Each `calls` entry names another component (not itself). Any call when `components_talk` is false → fail at `architecture.components[i].calls` with fix `Set components_talk to true in the components area, or remove the call`.
- `contracts`: `components_talk` true → `format` not `"none"` and `paths` validated with `validate.paths`; false → `format == "none"` and `paths == []`.
- `glossary` terms and meanings non-empty, terms unique (case-insensitive); non-empty when `identity.domain_jargon` is true (fix: `Add the domain's terms, e.g. {"term": "…", "meaning": "…"}`).
- `errors.categories`: non-empty, each matches `NAME`, unique; `format` in `ERROR_FORMATS`.
- `levels`: non-empty subset of `TEST_LEVELS`, must include `"unit"`, no duplicates; `"contract"` only when `components_talk`.

- [ ] **Step 1: Write failing tests** in `tests/test_core_areas.py` (same `valid()`/`check()` pattern as `test_answers.py`):

```python
def test_fixture_loads_the_three_areas(): ...
def test_calls_need_components_that_talk(tmp_path): ...            # components_talk False + calls → error at architecture.components[1].calls
def test_calls_name_other_components(tmp_path, call): ...          # parametrize "web" (self) and "ghost"
def test_talking_components_need_a_contract(tmp_path): ...         # format "none" → architecture.contracts.format error
def test_contract_paths_must_match_something(tmp_path): ...        # ["./api/openapi.yaml"] → error
def test_jargon_needs_a_glossary(tmp_path): ...
def test_duplicate_glossary_terms(tmp_path): ...                   # "Payload" and "payload"
def test_error_categories_rules(tmp_path, value): ...              # [], ["Not Found"], ["a", "a"]
def test_levels_need_unit_and_contract_needs_talk(tmp_path): ...
@pytest.mark.parametrize("area", ["architecture", "errors", "testing"])
def test_per_component_areas_follow_renames(tmp_path, area): ...   # rename components[1] to "site" → "no entry for component 'site'"
```

- [ ] **Step 2: Run** `uv run pytest tests/test_core_areas.py -q`. Expected: FAIL (unknown keys).
- [ ] **Step 3: Implement** the module, the shared `per_component`, and the fixture and scenario answers (web+api: as above; ML single: one component, `calls: []`, contracts `none`, glossary `[]`, errors `exceptions`, levels `["unit", "integration"]`), each with its decision record.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS (update hard-coded decision numbers in existing tests as 2a did).
- [ ] **Step 5: Commit** `feat: Add architecture, errors and testing answers`

---

### Task 3: Security, dependencies and observability answers

**Files:** Modify `src/alpha/core_areas.py`, `src/alpha/answers.py`, the fixture and both scenarios. Test: `tests/test_core_areas.py`.

**Interfaces:**
- Produces:
  - `AREAS` with `security`, `dependencies`, `observability` inserted after `build`; `Answers` gains the three fields.
  - `UPDATE_TOOLS = ("dependabot", "manual")`, `SCHEDULES = ("daily", "weekly", "monthly")`, `LOG_FORMATS = ("json", "logfmt")`, `CORRELATION = ("traceparent", "request-id", "none")`, `TELEMETRY = ("none", "opentelemetry", "other")`.
  - `Security(secret_store: str, auth: str, extra_protected: tuple[str, ...])`; `Dependencies(updates: str, schedule: str)`; `LogPlan(name, log_format: str, correlation: str, telemetry: str)`, `Observability(components: tuple[LogPlan, ...])`.
- JSON shape:

```json
"security": {"secret_store": "Fly.io secrets", "auth": "API keys for publishers; verification is public.", "extra_protected": ["api/keys/**"]},
"dependencies": {"updates": "dependabot", "schedule": "weekly"},
"observability": {"components": [{"name": "api", "log_format": "json", "correlation": "traceparent", "telemetry": "none"}]}
```

Validation rules:
- `secret_store` non-empty when any component is deployed (fix: `Say where production secrets live, e.g. your host's secret manager`); `auth` non-empty (`"none"` is a valid answer); `extra_protected` globs validated with `validate.relative`.
- `updates` in `UPDATE_TOOLS`, `schedule` in `SCHEDULES`.
- `observability.components`: exactly the deployed components (`per_component(..., only=lambda c: c.traits.deployed)`); a non-deployed name fails with `component 'x' isn't deployed`; enum fields as above. `correlation == "none"` is allowed only when at most one component is deployed.

- [ ] **Step 1: Write failing tests**

```python
def test_fixture_loads_security_dependencies_observability(): ...
def test_deployed_projects_need_a_secret_store(tmp_path): ...
def test_extra_protected_globs_must_match_something(tmp_path): ...
def test_update_tool_and_schedule_choices(tmp_path): ...
def test_observability_covers_exactly_the_deployed_components(tmp_path): ...  # missing api; extra non-deployed
def test_nothing_deployed_needs_no_observability(tmp_path): ...               # all deployed False, components [] → loads
def test_correlation_none_only_with_one_deployed_component(tmp_path): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/test_core_areas.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement**, and add the answers and decisions to the fixture and scenarios (ML single: nothing deployed, `secret_store` `""`, `auth` `"none"`, observability `[]`).
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Add security, dependencies and observability answers`

---

### Task 4: Principles take protected and risk paths from the answers

**Files:** Modify `src/alpha/principles.py`. Test: `tests/test_principles.py`.

**Interfaces:**
- Consumes: `Answers.security`, `Answers.architecture` (Tasks 2–3).
- Produces: `build_principles` requires all twelve areas (the "Answers are incomplete" message lists them from `AREAS`). `protected.paths` gains `security.extra_protected`; `review.risk_paths` gains `architecture.contracts.paths`. Before returning, it refuses (`AnswersError` at `security.extra_protected[i]`) a glob that matches `docs/principles.toml`, any `docs_map` doc entry taken as a path, or any component manifest, with fix `Protect something narrower: alpha's checks must be able to change <path>`. Use a `fnmatch`-style matcher equivalent to `_common.matches` (copy the 15-line `_match_parts` into `principles.py` rather than importing hook code).

- [ ] **Step 1: Write failing tests**

```python
def test_extra_protected_and_contract_paths_reach_the_principles(): ...
@pytest.mark.parametrize("glob", ["docs/**", "**/*.toml", "**/package.json", "docs/guide/**"])
def test_protecting_what_checks_must_change_is_refused(tmp_path, glob): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/test_principles.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Enforce extra protected paths and contract risks`

---

### Task 5: Architecture, errors, glossary and testing docs

**Files:** Create `src/alpha/render/area_docs.py`. Modify `src/alpha/render/docs.py`. Test: `tests/test_render_area_docs.py`.

**Interfaces:**
- Produces in `area_docs.py` (each returns Markdown lines or a document; `docs.py` wires them):
  - `architecture_sections(a) -> list[str]`: `## Responsibilities` (table Component | Responsibility | Calls, `-` for none), `## Contracts` (format and paths as code, or "No contracts: components don't call each other."), `## Errors` (table Component | Format with a one-line meaning per format, the categories as a list, and the rule "Every error a user sees says what went wrong and how to fix it.").
  - `glossary(a) -> str | None`: `docs/glossary.md` (`# Glossary`, table Term | Meaning, sorted by term) when the glossary is non-empty or the one-vocabulary principle is active; `None` otherwise.
  - `testing_section(a) -> list[str]`: CONTRIBUTING `## Testing`, before `## Documentation`: table Component | Levels; "Put each level's tests under `tests/<level>/` in the component."; "A test that covers an acceptance check names its requirement id (e.g. `R1`) in its name, so each check in docs/product.md traces to a test."
- `docs.py`: architecture.md appends `architecture_sections`; CLAUDE.md Docs list adds Glossary (when written), Security and Observability (Task 6) links.

- [ ] **Step 1: Write failing tests** for each section's exact lines on the fixture, the ML scenario's "No contracts" line, glossary absent for one component without jargon, and the CONTRIBUTING section order (Testing < Documentation < Branching).
- [ ] **Step 2: Run** `uv run pytest tests/test_render_area_docs.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Document boundaries, errors, glossary and tests`

---

### Task 6: Security, dependency policy and observability docs

**Files:** Modify `src/alpha/render/area_docs.py`, `src/alpha/render/docs.py`. Test: `tests/test_render_area_docs.py`.

**Interfaces:**
- Produces:
  - `security_doc(a, principles) -> str`: `docs/security.md` — `## Secrets` (where they live in production, or "Nothing is deployed."; "Locally, secrets live in `.env` files, which git ignores; never commit them. The Stop hook blocks a change that adds one."), `## Auth` (the answer), `## Protected paths` (every `protected.paths` glob, with "Claude can't edit these; change them by hand.").
  - `dependency_policy(a) -> list[str]`: lines inserted after the title of `docs/dependencies.md`: adding (log entry with the reason, enforced at Stop), pinning (lockfiles, protected), upgrading (`Dependabot opens weekly update pull requests.` or `Upgrades are manual, checked weekly.` with the schedule).
  - `observability_doc(a) -> str | None`: `docs/observability.md` with a table Component | Logs | Correlation | Telemetry and a levels line ("`info` in deployed environments, `debug` locally; errors carry the correlation id."); `None` when nothing is deployed.

- [ ] **Step 1: Write failing tests** for each document on the fixture, and `observability_doc` returning `None` for the ML scenario.
- [ ] **Step 2: Run** the test file. Expected: FAIL.
- [ ] **Step 3: Implement** and wire into `render_docs` and the CLAUDE.md links.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Document security, dependency policy and logging`

---

### Task 7: Dependabot config

**Files:** Modify `src/alpha/recipes.py`, `recipes/python.toml`, `recipes/typescript.toml`, `src/alpha/render/ci.py`, `src/alpha/generate.py`, `src/alpha/gitops.py`. Test: `tests/test_render_ci.py`, `tests/test_scenarios.py`.

**Interfaces:**
- Produces:
  - `Recipe.dependabot: str` (python `"uv"`, typescript `"npm"`; verify both names).
  - `DEPENDABOT = ".github/dependabot.yml"`; `render_dependabot(principles, updates: str, schedule: str, ci: str) -> dict[str, str]`: `{}` for `manual`; else `{DEPENDABOT: header + dumps({"version": 2, "updates": [...]})}`, one entry per component `{"package-ecosystem", "directory", "schedule": {"interval": schedule}}`, then `github-actions` at `/` when `ci == "github-actions"`.
  - `commit_skeleton` adds the group `("ci: Schedule dependency updates", [DEPENDABOT])` after the workflow group; the workflow group's path becomes `.github/workflows`; the root component's exclude stays `.github`.

- [ ] **Step 1: Write failing tests**

```python
def test_dependabot_per_component_and_for_actions(): ...   # fixture: ["uv" at "/api", "npm" at "/web", "github-actions" at "/"], weekly
def test_dependabot_root_component_directory_is_slash(): ...
def test_manual_updates_write_nothing(): ...
def test_commit_skeleton_commits_dependabot_after_ci(...): ... # subjects end with the two ci: commits
```

- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q` and `uv run pytest -m slow -q`. Expected: PASS both.
- [ ] **Step 5: Commit** `feat: Generate Dependabot updates per component`

---

### Task 8: Architecture, errors and testing skills

**Files:** Create `skills/architecture/SKILL.md`, `skills/errors/SKILL.md`, `skills/testing/SKILL.md`. Modify `defaults/defaults.toml`. Test: `tests/test_skills.py`.

**Interfaces:**
- Defaults:

```toml
[architecture]
contract_format = "openapi"

[errors]
categories = ["validation", "not-found", "conflict", "unavailable", "internal"]

[errors.formats]
backend = "problem-json"
frontend = "user-message"
mobile = "user-message"
cli = "message-and-exit-code"
library = "exceptions"
worker = "structured-log"
ml = "exceptions"

[testing.levels]
backend = ["unit", "integration"]
frontend = ["unit", "end-to-end"]
mobile = ["unit", "end-to-end"]
cli = ["unit", "end-to-end"]
library = ["unit"]
worker = ["unit", "integration"]
ml = ["unit", "integration"]
```

- Skills keep the six-section structure and the 2a conventions (one-line `answers write`, `--area <key>` check, prerequisite = the previous area in `AREAS` done, ≤ 150 lines, interview-only description).
  - **architecture** (needs `components`). Round 1: *Responsibility* per component, one sentence each, drafted from the requirements; *Calls*, asked only when `components_talk` (recommend from kinds: a frontend calls the backend). Round 2: *Contract format and location*, only when components talk (recommend `defaults.architecture.contract_format` at `<provider path>/openapi.yaml`); *Glossary*, asked when one-vocabulary applies (more than one component, or `domain_jargon`): propose 3–8 terms from the requirements. Skip what doesn't apply and say so in one line. Override key: `architecture.contract_format`.
  - **errors** (needs `architecture`). One round: *Format per component* (recommend `defaults.errors.formats[kind]`, one line on what each format means for its users) and *Categories* (recommend `defaults.errors.categories`). Explain the always-on rule: every error says what went wrong and how to fix it. Override keys: `errors.formats.<kind>`, `errors.categories`.
  - **testing** (needs `errors`). One round: *Levels per component* (recommend `defaults.testing.levels[kind]`, add `contract` when components talk, `integration` when it makes network calls or stores data). Explain the acceptance convention (tests name their requirement id) and that a source change without a test change blocks Stop. Override key: `testing.levels.<kind>`.
- `test_skills.py`: add the three to `AREA_SKILLS`; extend `test_every_kind_has_…` to `errors.formats` (values in `ERROR_FORMATS`) and `testing.levels` (subsets of `TEST_LEVELS` containing `unit`).

- [ ] **Step 1: Write failing tests** (the `AREA_SKILLS` entries and the defaults test).
- [ ] **Step 2: Run** `uv run pytest tests/test_skills.py -q`. Expected: FAIL.
- [ ] **Step 3: Write** the defaults and the three skills.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Add architecture, errors and testing areas`

---

### Task 9: Security, dependencies and observability skills; entry point

**Files:** Create `skills/security/SKILL.md`, `skills/dependencies/SKILL.md`, `skills/observability/SKILL.md`. Modify `defaults/defaults.toml`, `skills/documentation/SKILL.md`, `skills/new-project/SKILL.md`. Test: `tests/test_skills.py`.

**Interfaces:**
- Defaults:

```toml
[dependencies]
updates = "dependabot"
schedule = "weekly"

[observability]
log_format = "json"
correlation = "traceparent"
telemetry = "none"
```

- Skills:
  - **security** (needs `build`). One round: *Secret store*, asked only when something is deployed (offer the hosting answers' native secret managers as examples; record the user's words); *Auth* (who must prove who they are, and how; `none` is fine for local tools); *Extra protected paths* (recommend none; explain Claude can't edit them, and that alpha refuses globs its checks must change). No kit default for the store or auth: they are per project.
  - **dependencies** (needs `security`). One round: *Updates* (recommend `defaults.dependencies.updates`; Dependabot opens update pull requests per component and for CI actions, which keeps pinned actions like setup-uv current) and *Schedule* (recommend `defaults.dependencies.schedule`). Restate what's already enforced: a new dependency needs a log entry with its reason; lockfiles are protected. Override keys: `dependencies.updates`, `dependencies.schedule`.
  - **observability** (needs `dependencies`). With nothing deployed: save `{"components": []}`, say observability applies once something is deployed, and finish. Otherwise one round per deployed component: *Log format* (recommend `defaults.observability.log_format`), *Correlation* (recommend `defaults.observability.correlation` when more than one component is deployed; `none` is allowed for one), *Telemetry* (recommend `defaults.observability.telemetry`). Override keys: `observability.log_format`, `observability.correlation`, `observability.telemetry`.
- `documentation` skill: the contract mapping uses `architecture.contracts.paths` instead of the generic OpenAPI/proto globs.
- `new-project`: the create command lists all twelve areas as pending; step 4 lists the twelve skills in `AREAS` order; the summary covers each new area in one line; the final report adds "Claude can't edit the extra protected paths" (when any) and Dependabot (when chosen), and "Not covered yet" lists only UI/UX, versioning, data, accessibility and performance.
- `test_skills.py`: add the three skills to `AREA_SKILLS`; `test_new_project_invokes_the_area_skills_in_order` then covers all twelve.

- [ ] **Step 1: Write failing tests** (the `AREA_SKILLS` entries; defaults values in `UPDATE_TOOLS`, `SCHEDULES`, `LOG_FORMATS`, `CORRELATION`, `TELEMETRY`; the report's "Not covered yet" no longer names these six areas).
- [ ] **Step 2: Run** `uv run pytest tests/test_skills.py -q`. Expected: FAIL.
- [ ] **Step 3: Write** the defaults, skills and edits.
- [ ] **Step 4: Run** `uv run pytest -q` and `claude plugin validate .claude-plugin/marketplace.json`. Expected: PASS, valid.
- [ ] **Step 5: Commit** `feat: Add security, dependencies and observability areas`

---

### Task 10: Live check

**Files:** Modify `CLAUDE.md` (the kit's live-run notes).

- [ ] **Step 1:** Take both scenarios through `bin/alpha` (`answers check`, `generate`, `bootstrap`, `commit-skeleton`) in scratch folders. Expected: the web+API project gets seven commits ending with the two `ci:` commits; the ML project gets no `docs/observability.md`; both trees clean.
- [ ] **Step 2:** In the web+API project, run the generated `guard_paths.py` hook on an edit to an `extra_protected` path. Expected: blocked with the protected-path message.
- [ ] **Step 3:** Record what was verified under the live-run notes in the kit's `CLAUDE.md`.
- [ ] **Step 4: Commit** `docs: Record the core areas live check`
