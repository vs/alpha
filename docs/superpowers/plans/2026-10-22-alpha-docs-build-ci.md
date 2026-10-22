# Alpha Documentation, Build and CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the documentation area (§5.7) and the build, CI and hosting area (§5.8) to the interview, so a generated project gets a filled docs-drift map, a build/hosting record, and a GitHub Actions workflow that runs every component's checks, green from the first commit.

**Architecture:** Two new area skills save their answers into `project.json` like the existing four. The CLI validates them, turns the documentation mappings into `docs_map` in `docs/principles.toml` (the Stop hook already reads it), renders `docs/build.md` and a documentation section in CONTRIBUTING, and renders `.github/workflows/ci.yml` from each component's own commands plus per-stack setup steps in the recipe. Bootstrap runs the same check commands CI runs, so a green bootstrap means a green first CI run. Nothing in the CI or docs code names a stack: stack-specific facts come only from recipes, so plan 2d's generic stack slots in without changes here.

**Tech Stack:** Python ≥ 3.11 stdlib for the kit runtime; pytest, ruff, pyright, plus PyYAML (dev only, to parse the generated workflow in tests); GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-19-project-kit-design.md`

**Plan series:** Plan 2 of the foundation plan's 1/4 series is split into five: **2a (this plan): documentation, build/CI/hosting, CI config.** 2b: architecture, errors, testing, security, dependencies, observability. 2c: UI/UX, accessibility, data and migrations, performance, versioning and releases. 2d: generic-stack fallback. 2e: area skills on kit-generated projects (§5a). Plans 3 (reviewer) and 4 (evals) are unchanged.

## Global Constraints

- Everything from the foundation plan's Global Constraints still holds (no app code, nothing kit-specific at the root, fail helpfully, stdlib-only runtime, self-contained projects, 50/72 commit rules).
- **Generic first.** No code outside `recipes/` may branch on a stack name. CI setup steps, pinned tool versions and check commands come from the recipe; area questions are worded for any kind of application.
- Area order, as in spec §5: `identity`, `components`, `documentation`, `build`, `git`, `agent_workflow`. Later plans insert their areas by spec number.
- A `project.json` written before this plan (four areas) must still load: an area missing from `areas` counts as `"pending"`.
- External docs, when kept in the repo, live under `docs/` (e.g. `docs/guide`), so the root stays standard.
- CI is checks only (setup, format check, lint, typecheck, test per component). No deploy jobs and no cloud resources (spec §2 non-goals).
- GitHub Actions: `permissions: contents: read`; triggers `push` to `main` and `pull_request`; runner `ubuntu-latest`; one job per component, named after it, with `defaults.run.working-directory` set to the component path.
- Pin every action to its current major tag (`actions/checkout`, `astral-sh/setup-uv`, `pnpm/action-setup`, `actions/setup-node`). Look the tags and each action's input names up at implementation time (context7 or the action's README); they are facts, not decisions.
- Choosing no CI loosens the `build-hosting-upfront` principle, so it needs a project-scoped override with a reason (spec §6: loosening needs a decision record).

## Review Focus

1. **Resuming an interview started on alpha 0.1.** `areas` has only the four old keys. Loading must treat the new ones as pending and the entry skill must continue at `documentation`. (Test in Task 1.)
2. **A component at the project root (`path = "."`).** The CI job's working directory is `.`, recipe `${dir}` expands to an empty prefix, and `.python-version` lands at the root. (Test in Tasks 5 and 6.)
3. **Commands with YAML-hostile characters** (`: `, `#`, quotes, `{file}`). The workflow must parse back to exactly the same strings. (Test in Task 4.)
4. **A docs mapping that names a folder of docs** (`docs/guide/**`). Changing any file under it must satisfy the drift check. (Test in Task 3.)
5. **`build.components` out of step with `components`** after the user renames, adds or removes a component. Validation names the missing or extra component and says how to fix it. (Test in Task 1.)

---

## File Structure

```
src/alpha/answers.py              + Documentation, DocMapping, Build, BuildTarget; AREAS grows; missing areas = pending
src/alpha/principles.py           docs_map from documentation.mappings; requires the new areas
src/alpha/yaml_write.py           NEW: minimal block-YAML emitter (strings always double-quoted)
src/alpha/recipes.py              + Recipe.ci (setup steps, env); CHECK_STEPS; check_commands()
src/alpha/render/ci.py            NEW: GitHub Actions workflow data
src/alpha/render/docs.py          + docs/build.md, CONTRIBUTING "Documentation", CLAUDE.md links, external guide README
src/alpha/generate.py             writes ci.yml; bootstrap runs check_commands
src/alpha/gitops.py               + "ci:" commit for .github
project-files/hooks/stop_checks.py  docs_map docs entries match as globs
recipes/python.toml, typescript.toml  + format_check, [ci], pin files
recipes/python/python-version.tmpl, recipes/typescript/node-version.tmpl  NEW
defaults/defaults.toml            + [documentation], [documentation.public_paths], [build], [build.artifacts]
skills/documentation/SKILL.md     NEW area skill
skills/build-and-hosting/SKILL.md NEW area skill
skills/new-project/SKILL.md       six areas, summary, final report
tests/…                           as named per task
tests/fixtures/answers_valid.json, evals/scenarios/*.json  + documentation, build answers
```

---

### Task 1: Answers model for the two new areas

**Files:** Modify `src/alpha/answers.py`, `tests/fixtures/answers_valid.json`, `evals/scenarios/python-ml-single.json`, `evals/scenarios/web-ts-plus-python-api.json`. Test: `tests/test_answers.py`.

**Interfaces:**
- Produces:
  - `AREAS = ("identity", "components", "documentation", "build", "git", "agent_workflow")`.
  - `EXTERNAL_DOCS = ("readme", "folder", "elsewhere", "none")`, `CI_PROVIDERS = ("github-actions", "none")`, `ARTIFACTS = ("none", "package", "container", "static-site", "binary", "app", "other")`.
  - `@dataclass(frozen=True) DocMapping(paths: tuple[str, ...], docs: tuple[str, ...])`
  - `@dataclass(frozen=True) Documentation(external: str, external_path: str, external_location: str, mappings: tuple[DocMapping, ...])`
  - `@dataclass(frozen=True) BuildTarget(name: str, artifact: str, hosting: str)`
  - `@dataclass(frozen=True) Build(ci: str, environments: tuple[str, ...], components: tuple[BuildTarget, ...])`
  - `Answers` gains `documentation: Documentation | None` and `build: Build | None`, placed after `agent_workflow`. `_TOP_KEYS` gains `"documentation"`, `"build"`.
- JSON shape (exact field names; the skills in Task 8 write them):

```json
"documentation": {"external": "folder", "external_path": "docs/guide", "external_location": "",
                  "mappings": [{"paths": ["web/**/pages/**"], "docs": ["docs/guide/**"]}]},
"build": {"ci": "github-actions", "environments": ["production"],
          "components": [{"name": "api", "artifact": "container", "hosting": "Fly.io"}]}
```

Validation rules (each error follows `_fail(where, problem, fix)`):
- `areas`: a missing area key is `"pending"`; a present one must be a valid status.
- `documentation.external` in `EXTERNAL_DOCS`. `"folder"` needs `external_path` relative, under `docs/` (not `docs` itself), no `..`; otherwise `external_path` must be `""`. `"elsewhere"` needs a non-empty `external_location`; otherwise it must be `""`.
- Each mapping: `paths` and `docs` non-empty lists of non-empty strings, relative (no leading `/`), no `..` part.
- `build.ci` in `CI_PROVIDERS`. `"none"` needs an override with `principle == "build-hosting-upfront"`, `scope == "project"`, `change` in loosen/drop, else fail at `build.ci` with fix `Add an override loosening build-hosting-upfront with the reason there is no CI`.
- `build.environments`: each matches `_NAME`; non-empty when any component has `traits.deployed`.
- `build.components`: when the components area is active, exactly one entry per component, by name. Missing → `build.components: no entry for component 'web'` / fix `Add {"name": "web", "artifact", "hosting"}`. Extra → `build.components[i].name: there is no component named 'x'` / fix lists the names. `artifact` in `ARTIFACTS`. `hosting` non-empty for a deployed component.

- [ ] **Step 1: Write the failing tests** in `tests/test_answers.py`, using the existing `valid()`/`check()` helpers:

```python
def test_old_interview_without_new_areas_still_loads(tmp_path):
    data = valid(); data["areas"] = {k: "done" for k in ("identity", "components", "git", "agent_workflow")}
    for key in ("documentation", "build"): data.pop(key)
    a = load_answers(write(tmp_path, data), ["identity"])
    assert a.areas["documentation"] == "pending" and a.documentation is None

def test_external_folder_must_be_under_docs(tmp_path): ...       # "guide" → "documentation.external_path" + "under docs/"
def test_external_path_only_with_folder(tmp_path): ...           # readme + "docs/x" → error at documentation.external_path
def test_elsewhere_needs_a_location(tmp_path): ...
def test_mapping_paths_and_docs_rules(tmp_path, field, value): ... # parametrize: [], ["/abs"], ["a/../b"], [""] for paths and docs
def test_ci_none_needs_a_loosening_override(tmp_path): ...      # error names build-hosting-upfront; passes once the override is added
def test_build_components_must_match_components(tmp_path): ...   # drop "web" → "no entry for component 'web'"; add "x" → "no component named 'x'"
def test_deployed_component_needs_hosting_and_an_environment(tmp_path): ...
def test_bad_artifact_lists_choices(tmp_path): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/test_answers.py -q`. Expected: the new tests FAIL (unknown key or attribute errors).
- [ ] **Step 3: Implement** the dataclasses, constants and validators (`_documentation(raw)`, `_build(raw, comps, overrides)`) in `answers.py`; validate `build` after `overrides` are parsed. Add `documentation` and `build` answers (all areas `"done"`, a decision for each) to the fixture and both scenarios: the ML scenario uses `external: "readme"`, `ci: "github-actions"`, no deployed components (`environments: []`, artifact `"package"`, hosting `""`); the web+API scenario uses `external: "folder"` at `docs/guide` with one mapping per component and `environments: ["production"]`.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all PASS (the hook and scenario suites load the updated fixture and scenarios).
- [ ] **Step 5: Commit** `feat: Add documentation and build answers`

---

### Task 2: Documentation mappings become docs_map

**Files:** Modify `src/alpha/principles.py`. Test: `tests/test_principles.py`.

**Interfaces:**
- Consumes: `Answers.documentation` (Task 1).
- Produces: `build_principles` raises the existing "Answers are incomplete" `AnswersError` (wording extended to name `documentation` and `build`) when either is `None`. `docs_map: dict[str, list[str]]` maps each mapping glob to the deduplicated docs of every mapping that names it, in answer order.

- [ ] **Step 1: Write failing tests**

```python
def test_docs_map_comes_from_the_mappings(): ...           # fixture → docs_map == {"web/**/pages/**": ["docs/guide/**"], ...}
def test_same_glob_in_two_mappings_merges_docs(tmp_path): ...
def test_principles_need_documentation_and_build(tmp_path): ...  # documentation None → AnswersError mentioning "documentation"
```

Update `tests/test_principles.py:238` (`assert parsed["docs_map"] == {}`) to expect the fixture's map.
- [ ] **Step 2: Run** `uv run pytest tests/test_principles.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** in `build_principles`; drop the `# filled by plan 2's documentation area` comment.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Build docs_map from the documentation answers`

---

### Task 3: Drift check accepts doc globs

**Files:** Modify `project-files/hooks/stop_checks.py` (the `docs_map` loop in `find_problems`). Test: `tests/hooks/test_stop_checks.py`.

**Interfaces:** Docs entries in `docs_map` are globs matched with `_common.matches`; a plain path still matches only itself.

- [ ] **Step 1: Write failing tests**

```python
def test_docs_drift_satisfied_by_any_file_under_a_doc_glob(project): ...
    # docs_map {"api/src/**/*.py": ["docs/guide/**"]}; change api/src/x.py and docs/guide/api/x.md → no docs problem
def test_docs_drift_glob_still_flags_unrelated_doc_changes(project): ...
    # same map; change api/src/x.py and docs/other.md → problem names docs/guide/**
```

- [ ] **Step 2: Run** `uv run pytest tests/hooks/test_stop_checks.py -q`. Expected: the first FAILS.
- [ ] **Step 3: Implement**: replace `any(d in changed for d in doc_list)` with `any(_common.matches(f, doc_list) for f in changed)`.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hooks): Match docs_map docs as globs`

---

### Task 4: YAML writer

**Files:** Create `src/alpha/yaml_write.py`. Modify `pyproject.toml` (dev group: `pyyaml`, `types-pyyaml`, added with `uv add --dev`). Test: `tests/test_yaml_write.py`.

**Interfaces:**
- Produces: `dumps(data: Mapping[str, object]) -> str`. Block style, two-space indent, insertion order. Values: `str` (always `json.dumps`, so double-quoted), `bool`, `int`, `Mapping`, `list` of any of these. A list item that is a mapping starts on the `- ` line. Empty list `[]`, empty mapping `{}`. Keys are bare when they match `[A-Za-z0-9_-]+` and are not a YAML 1.1 boolean word (`on off yes no true false y n`, any case); otherwise `json.dumps`-quoted. Any other value type raises `TypeError` naming its dotted path, like `toml_write`.

- [ ] **Step 1: Write failing tests**

```python
def test_round_trips_through_pyyaml():
    data = {"on": {"push": {"branches": ["main"]}}, "jobs": {"api": {"steps": [
        {"uses": "actions/checkout@v9"},
        {"name": "lint", "run": 'uv run ruff check # x: "y" {file}'}]}},
        "n": 3, "ok": True, "empty": [], "none": {}}
    assert yaml.safe_load(dumps(data)) == data

def test_boolean_word_keys_are_quoted(): assert dumps({"on": 1}).startswith('"on":')
def test_unsupported_value_names_its_path(): ...   # {"a": {"b": 1.5}} → TypeError mentioning "a.b"
```

- [ ] **Step 2: Run** `uv run pytest tests/test_yaml_write.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `dumps`.
- [ ] **Step 4: Run** the test file, then `uv run pyright`. Expected: PASS, 0 errors.
- [ ] **Step 5: Commit** `feat: Add a minimal YAML writer for CI config`

---

### Task 5: Recipes carry CI setup and the check commands

**Files:** Modify `src/alpha/recipes.py`, `recipes/python.toml`, `recipes/typescript.toml`, `src/alpha/generate.py` (`bootstrap`), `src/alpha/render/docs.py` (`_STEPS`). Create `recipes/python/python-version.tmpl`, `recipes/typescript/node-version.tmpl`. Test: `tests/test_recipes.py`, `tests/test_generate.py`, `tests/test_bootstrap_slow.py`.

**Interfaces:**
- Produces:
  - `CHECK_STEPS = ("setup", "format_check", "lint", "typecheck", "test")` in `recipes.py`.
  - `check_commands(commands: Mapping[str, str]) -> list[tuple[str, str]]`: `(step, command)` for each of `CHECK_STEPS` whose command is a non-empty string, in that order.
  - `Recipe.ignores: list[str]` (the `.gitignore` entries `generate._IGNORES` held) and `Recipe.why: dict[str, str]` (the dependency-log reasons `docs._WHY` held; tools missing from it keep the reason `Tooling`).
  - `Recipe.ci: CiSetup`, with `@dataclass(frozen=True) CiSetup(steps: list[dict[str, Any]], env: dict[str, str])`. `steps` are GitHub Actions step mappings; any string inside may contain `${dir}`, which Task 6 replaces with the component folder plus `/` (empty for a root component).
- Recipe data:
  - python: `format_check = "uv run ruff format --check"`; `[ci] env = {UV_LOCKED = "1"}`; steps: `astral-sh/setup-uv@<major>` with `enable-cache: true` and its cache-glob input set to `${dir}uv.lock`. Files: `".python-version" = "python-version.tmpl"` containing `3.12` (matches `requires-python = ">=3.12"`).
  - typescript: `format_check` = a Biome command that exits non-zero on an unformatted file without writing (verify; `pnpm biome format .` or `pnpm biome ci --linter-enabled=false .`). Steps: `pnpm/action-setup@<major>` reading `${dir}package.json`; `actions/setup-node@<major>` with `node-version-file: ${dir}.node-version`, `cache: pnpm`, `cache-dependency-path: ${dir}pnpm-lock.yaml`. Files: `".node-version" = "node-version.tmpl"` holding the current Node Active LTS major (look it up). Bootstrap gains a last entry `pnpm pkg set packageManager=pnpm@$(pnpm --version)` so CI uses the local pnpm version.
- `bootstrap()` runs `recipe.bootstrap`, then every command from `check_commands(c["commands"])`, with the existing failure message.
- `docs.py` `_STEPS` gains `format_check` after `format` (the CLAUDE.md command table and the architecture doc's command list show it).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_recipes.py
def test_check_commands_keep_order_and_skip_empty():
    assert check_commands({"test": "t", "setup": "s", "lint": ""}) == [("setup", "s"), ("test", "t")]
@pytest.mark.parametrize("stack", ["python", "typescript"])
def test_every_recipe_has_every_check_step_and_pinned_ci_actions(stack): ...
    # each CHECK_STEPS command non-empty; every step "uses" matches r"^[\w.-]+/[\w.-]+@v\d+$"
def test_recipes_name_no_stack_outside_recipes(): ...
    # grep src/alpha/**/*.py for '"python"' and '"typescript"' → none, except answers.py's STACKS
    # (plan 2d derives it from the recipes). To pass: move generate._IGNORES into each recipe as
    # `ignores`, and docs._WHY into each recipe as a `[why]` table (tool → reason for the dependency log)

# tests/test_generate.py
def test_bootstrap_runs_bootstrap_then_every_check(...):  # extend the existing bootstrap test: recorded commands ==
    # [*recipe.bootstrap, setup, format_check, lint, typecheck, test] per component

# tests/test_bootstrap_slow.py
def test_format_check_fails_on_an_unformatted_file(...): ... # per stack, after bootstrap: write a badly formatted
    # source file, run format_check in the component → non-zero; nothing rewritten
```

- [ ] **Step 2: Run** `uv run pytest tests/test_recipes.py tests/test_generate.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the recipe data, `CiSetup`, `check_commands`, the `ignores` and `why` moves, and the bootstrap change.
- [ ] **Step 4: Run** `uv run pytest -q`, then `uv run pytest -m slow -q`. Expected: PASS both; the slow run proves the skeletons pass format_check, lint and typecheck as well as tests.
- [ ] **Step 5: Commit** `feat(recipes): Add CI setup and run every check at bootstrap`

---

### Task 6: GitHub Actions workflow

**Files:** Create `src/alpha/render/ci.py`. Modify `src/alpha/generate.py`, `src/alpha/gitops.py`. Test: `tests/test_render_ci.py`, `tests/test_scenarios.py`.

**Interfaces:**
- Consumes: `yaml_write.dumps` (Task 4), `load_recipe`, `check_commands`, `Recipe.ci` (Task 5), `Answers.build` (Task 1).
- Produces:
  - `WORKFLOW = ".github/workflows/ci.yml"`.
  - `render_ci(principles: dict[str, Any], ci: str) -> dict[str, str]`: `{}` when `ci == "none"`, else `{WORKFLOW: text}`. Text is a header comment (`# Generated by alpha: each component's checks, as in CLAUDE.md.`) plus `dumps` of:

```yaml
name: CI
"on": {push: {branches: [main]}, pull_request: {}}
permissions: {contents: read}
jobs:
  <component name>:
    runs-on: ubuntu-latest
    defaults: {run: {working-directory: <component path>}}
    env: <recipe ci env>              # key omitted when empty
    steps:
      - uses: actions/checkout@<major>
      - <recipe ci steps, ${dir} replaced>
      - {name: <step>, run: <command>}  # one per check_commands(component commands)
```

  - `generate()` adds `render_ci(principles, a.build.ci)` to `texts`.
  - `commit_skeleton` appends the group `("ci: Run every component's checks in CI", [".github"])` after the component groups.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_render_ci.py (parse with yaml.safe_load)
def test_one_job_per_component_running_its_checks(): ...   # fixture principles: jobs == {"api", "web"};
    # api run steps == [c for _, c in check_commands(api commands)]; working-directory "api"
def test_root_component_paths_have_no_prefix(): ...        # path "." → working-directory "."; no "${dir}" or "./" in any value
def test_triggers_and_permissions(): ...                   # on.push.branches == ["main"]; "pull_request" in on; permissions == {"contents": "read"}
def test_no_ci_writes_nothing(): assert render_ci(principles, "none") == {}

# tests/test_scenarios.py
# ROOT_ENTRIES gain ".github" (both scenarios) and ".python-version" (python-ml-single)
def test_commit_skeleton_commits_ci_last(...): ...          # last subject == "ci: Run every component's checks in CI"
```

- [ ] **Step 2: Run** `uv run pytest tests/test_render_ci.py tests/test_scenarios.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `render_ci`, the generate wiring and the commit group.
- [ ] **Step 4: Run** `uv run pytest -q`. If `actionlint` is installed, also run it on a generated scenario's workflow. Expected: PASS, no actionlint findings.
- [ ] **Step 5: Commit** `feat: Generate a GitHub Actions workflow`

---

### Task 7: Build and documentation docs

**Files:** Modify `src/alpha/render/docs.py`. Test: `tests/test_render_docs.py`.

**Interfaces:**
- Consumes: `Answers.documentation`, `Answers.build`, `check_commands`, `WORKFLOW` (Tasks 1, 5, 6).
- Produces, in `render_docs`:
  - `docs/build.md`: `# Build, CI and hosting`; `## CI` saying what runs where (GitHub Actions in `.github/workflows/ci.yml` on pushes to main and pull requests, with a table Component | Checks listing each component's check commands), or, for `none`, "No CI" plus a link to the override decision record; `## Components` table Component | Artifact | Hosting (`-` for empty); `## Environments` as a list, or "None: nothing is deployed."; a closing line that hosting is decided and documented here, and alpha creates no cloud resources.
  - CONTRIBUTING.md gains `## Documentation` before `## Branching`: internal docs live in `docs/`; where external docs live (README, `<external_path>/`, the external location, or none); and, when there are mappings, a table "When these change | Update" from `documentation.mappings`, followed by "The Stop hook blocks a change to these paths that leaves the docs untouched."
  - For `external == "folder"`: `<external_path>/README.md` with `# <name> guide` and one line saying user-facing documentation lives here.
  - CLAUDE.md's Docs list gains `- [Build, CI and hosting](docs/build.md)` and, for a folder, `- [User guide](<external_path>/)`.

- [ ] **Step 1: Write failing tests**

```python
def test_build_doc_lists_ci_checks_artifacts_and_environments(): ...
def test_build_doc_without_ci_points_at_the_override(tmp_path): ...
def test_contributing_documents_where_docs_live_and_the_mappings(): ...
def test_external_folder_gets_a_readme_and_a_claude_md_link(): ...
def test_readme_external_docs_add_no_folder(tmp_path): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/test_render_docs.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `_build_doc(a, principles)`, `_docs_section(a)` and the additions.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Document build, CI, hosting and docs mapping`

---

### Task 8: Area skills and the entry point

**Files:** Create `skills/documentation/SKILL.md`, `skills/build-and-hosting/SKILL.md`. Modify `skills/new-project/SKILL.md`, `defaults/defaults.toml`. Test: `tests/test_skills.py`.

**Interfaces:**
- Consumes: the JSON shape and rules from Task 1.
- Defaults added to `defaults/defaults.toml`:

```toml
[documentation]
external = "readme"

[documentation.public_paths]   # globs inside a component where its public behavior usually lives
backend = ["**/api/**", "**/routes/**", "**/handlers/**"]
frontend = ["**/pages/**", "**/routes/**"]
cli = ["**/cli/**", "**/commands/**"]
mobile = ["**/screens/**"]
ml = []
library = ["**/index.*", "**/__init__.py", "**/public/**"]
worker = ["**/jobs/**", "**/tasks/**"]

[build]
ci = "github-actions"

[build.artifacts]
backend = "container"
frontend = "static-site"
cli = "package"
mobile = "app"
ml = "none"
library = "package"
worker = "container"
```

- Skills follow the existing area-skill structure exactly (the six sections, the "Before you start" checks, one-line `answers write`, `--area <key>` check, ≤ 150 lines, description containing "Use only inside an alpha project interview (/alpha:new-project)").
  - **documentation** (area key `documentation`, needs `components` done). Round 1: *External docs* (recommend `defaults.documentation.external`; one line per choice; for `folder` recommend `docs/guide`). Round 2: *Docs mappings*, one question listing, per component, its public paths (recommend `defaults.documentation.public_paths[kind]`, prefixed with the component path; `.` adds no prefix) and the docs they map to (user-facing kinds to the external docs: README.md for `readme`, `<external_path>/**` for `folder`; others, and contract files when `components_talk`, to `docs/architecture.md`). Explain: the Stop hook blocks a change to those paths that leaves the docs untouched, so map only real public behavior; mappings can be edited later in `docs/principles.toml`. With `elsewhere` or `none`, external docs can't be checked, so map only to in-repo docs. Override keys: `documentation.external`, `documentation.public_paths.<kind>`.
  - **build-and-hosting** (area key `build`, needs `components` done). Round 1: *CI* (recommend `defaults.build.ci`; explain CI runs the same checks as bootstrap on every push and pull request, and that `none` loosens build-hosting-upfront, so it needs an override with a reason); *Environments*, asked only when a component is deployed (recommend `["production"]`). Round 2: per component *Artifact* (recommend `defaults.build.artifacts[kind]`) and, for deployed components, *Hosting*: where it runs, in the user's words; offer two or three common fits for the kind but never pick one silently. Say plainly that alpha documents hosting and wires CI checks, but creates no cloud resources and no deploy jobs. Override keys: `build.ci`, `build.artifacts.<kind>`.
- `new-project`: the create command lists all six areas as pending; the resume step says areas missing from `areas` count as pending; step 4 lists `alpha:documentation` and `alpha:build-and-hosting` between components and git history; the summary covers both areas; the final report adds "CI runs every component's checks on each push and pull request" (when chosen) and the docs-drift rule, and "Not covered yet" drops documentation and build/CI/hosting.

- [ ] **Step 1: Write failing tests**: add both skills to `AREA_SKILLS` (`"documentation": ("documentation", ("documentation",))`, `"build-and-hosting": ("build", ("build",))`); add

```python
def test_every_kind_has_public_paths_and_an_artifact():
    kit = tomllib.loads((PLUGIN_ROOT / "defaults" / "defaults.toml").read_text())
    assert answers.KINDS <= set(kit["documentation"]["public_paths"])
    assert {kit["build"]["artifacts"][k] for k in answers.KINDS} <= set(answers.ARTIFACTS)
    assert kit["build"]["ci"] in answers.CI_PROVIDERS
    assert kit["documentation"]["external"] in answers.EXTERNAL_DOCS

def test_new_project_creates_every_area_as_pending():
    start = _section("new-project", "2. Start or resume")
    for area in answers.AREAS: assert f'"{area}": "pending"' in start
```

- [ ] **Step 2: Run** `uv run pytest tests/test_skills.py -q`. Expected: FAIL (missing skills and defaults).
- [ ] **Step 3: Write** the defaults, the two skills and the `new-project` changes.
- [ ] **Step 4: Run** `uv run pytest -q` and `claude plugin validate .claude-plugin/marketplace.json`. Expected: PASS, valid.
- [ ] **Step 5: Commit** `feat: Add documentation and build-and-hosting areas`

---

### Task 9: Live check

**Files:** Modify `CLAUDE.md` (the kit's, "Live run findings").

- [ ] **Step 1:** Generate, bootstrap and commit the `web-ts-plus-python-api` scenario into a temp folder with `bin/alpha` (`answers check`, `generate`, `bootstrap`, `commit-skeleton`). Expected: five commits ending with the `ci:` one; `git status` clean.
- [ ] **Step 2:** If `actionlint` is installed, run it on the workflow; if `gh` is authenticated and the user agrees, push the folder to a new private repo and watch the run with `gh run watch`. Ask before creating any remote repo. Expected: green, or a finding fixed in the owning task's code with a regression test.
- [ ] **Step 3:** Record what was verified, briefly, under "Live run findings" in the kit's `CLAUDE.md`.
- [ ] **Step 4: Commit** `docs: Record the docs and CI live check`
