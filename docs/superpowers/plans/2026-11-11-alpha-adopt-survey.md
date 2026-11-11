# Survey and Adopted Recipes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** alpha can look at an existing repo and describe it in facts (spec §5b, step 1). For each component, it can hold a project-local **adopted recipe** that runs the repo's own tools, proven against the repo's real code (§5b, A1). This is plan 2 of the adoption series. Installing alpha's files onto the repo is plan 3, the compliance plan is plan 4 and the skill is plan 5. Plan 2 is `2026-11-11-alpha-baselines.md`.

**Architecture:**
- `alpha adopt survey <target>` reads the tracked files and git history and prints JSON:
  - candidate components, from the marker files each recipe's new `[detect]` table names
  - the files that show CI, docs, decision records, migrations, task runners and git hook managers, from glob lists in a new kit data file `defaults/survey.toml`
  - the test and source file counts per candidate
  - how many recent commits follow the conventional format
  - whether the tree is clean

  With `--save`, it stores the result under `adoption.survey` in project.json.
- An adopted recipe is a drafted recipe with `"adopted": true`:
  - Its name can't be a kit stack (`api-python`, not `python`).
  - It may `"extends"` a kit recipe, taking every field it doesn't set. A step whose command it changes drops the kit's baseline reader for that step.
  - Its templates may be empty, because the manifests already exist. Its bootstrap must be empty, because adoption doesn't edit manifests. Its `test` may be empty, and plan 4 records that as a gap.
- `alpha recipe try` proves an adopted recipe in a throwaway `git worktree` of HEAD, in each component folder that uses it:
  - `setup` must pass.
  - A failing check passes the proof only when its baseline reader reads findings. Those findings are what plan 3 will baseline, and the proof prints their counts.
  - A failing `format_check` fails the proof, with the advice to leave it `""` until the formatting step (P1).

**Tech Stack:** Python ≥ 3.11 for the kit (stdlib, git). pytest, ruff, pyright.

**Spec:** §5b (A1, the flow's step 1), §8b.

## Decisions (the planner's calls)

- **S1 Facts by data, not code.** Component detection uses each recipe's `[detect] markers` (file names whose folder is a candidate component). Every other survey glob lives in `defaults/survey.toml`, read from the plugin or `ALPHA_SOURCE` the way `defaults.toml` is. No stack or tool name appears in `adopt.py`. A stack the kit has no recipe for isn't detected; the skill (plan 5) finds it by reading the repo, as the stack-recipe skill does now.
- **S2 Tracked files only.** The survey walks `git ls-files`, so ignored folders (`node_modules`, `.venv`, build output) never count, and a folder that isn't a git repository is refused with `git init` as the fix.
- **S3 The survey reports; it never decides.** Nested candidates (a root `package.json` workspace plus `packages/*/package.json`) are all listed, each with its markers. The interview decides which are components.
- **S4 Adopted recipes don't write into the repo.** Templates may be empty and bootstrap must be `[]`. Adding a missing tool is a plan step (P2) that edits the recipe and re-proves it later, through `/alpha:extend`.
- **S5 The proof runs on the repo's code, not a scratch skeleton.** That's a worktree of HEAD, detached, removed afterwards even on failure. Uncommitted work isn't included: the survey reports a dirty tree, and the adopt skill (plan 5) stops on one.
- **S6 Extending a kit recipe.** Merged as plain data: the kit recipe's TOML, minus `files` and `proven`, overlaid by the adopted entry. Templates default to `{}`. `proven_hash` covers the adopted entry as written, like any drafted recipe. A step whose command differs from the kit's loses the kit's `[baseline.<step>]` unless the entry gives its own. The same goes for `lint_file` against `baseline.lint.file_command`.
- **S7 An empty test step.** An adopted recipe may set `test = ""` when the repo has no tests. The Stop hook and CI then run none, and plan 4's gap list turns it into a P2 step. `setup` stays required (`"true"` when there's nothing to install).

## Global Constraints

- As in plan 2:
  - generated projects render byte for byte as today
  - stack-free code
  - every refusal names the fix
  - commits as CLAUDE.md says, each ending with this session's attribution lines
  - `uv run pytest`, ruff, pyright and `mise run check` pass after every task, with real-tool tests marked `@pytest.mark.slow`
- Nothing in this plan writes into the surveyed repo except `.claude/alpha/project.json` (only with `--save`, through `write_answers`) and git's own worktree bookkeeping, which `try` removes.

## Review Focus

1. **The worktree is always removed**, after a failing command, a timeout or Ctrl-C, and `git worktree list` is back to one entry. Pinned by `test_try_adopted_removes_its_worktree` (Task 4).
2. **A failing check whose output its reader can't read fails the proof**, never passes it as "legacy". Pinned by `test_try_adopted_unreadable_failure` (Task 4).
3. **Inherited readers for changed commands.** An adopted recipe that runs mypy must not keep pyright's JSON reader. Pinned by `test_extends_drops_readers_of_changed_steps` (Task 3).
4. **Survey on a big repo.** No file contents are read beyond counting, and the walk is one `git ls-files` call. Pinned by `test_survey_reads_one_listing` (Task 2), which asserts the git calls.

---

## File Structure

```
recipes/python.toml, recipes/typescript.toml     [detect] markers (Task 1)
defaults/survey.toml                             NEW: survey globs (Task 1)
src/alpha/defaults.py                            load_survey (Task 1)
src/alpha/recipes.py                             detect, adopted, extends (Tasks 1, 3)
src/alpha/adopt.py                               NEW: survey (Task 2)
src/alpha/answers.py                             adoption.survey; adopted drafted recipes (Tasks 2, 3)
src/alpha/recipe_cli.py                          try in a worktree for adopted recipes (Task 4)
src/alpha/cli.py                                 alpha adopt survey [--save] (Task 2)
tests/test_adopt_survey.py, tests/test_adopted_recipes.py   NEW
tests/test_adopted_slow.py                       NEW (Task 5)
CLAUDE.md                                        dev notes (Task 5)
```

---

### Task 1: What to look for

**Files:**
- Create: `defaults/survey.toml`
- Modify: `recipes/*.toml` (`[detect]`), `src/alpha/recipes.py` (`Recipe.detect: tuple[str, ...]`, validated as file names, not globs), `src/alpha/defaults.py` (`load_survey(source) -> dict[str, list[str]]`)
- Test: `tests/test_recipes.py`, `tests/test_defaults.py`

- [ ] **Step 1: Write the failing tests.**
  - `test_kit_recipes_detect`: python's markers include `pyproject.toml`, `setup.py` and `requirements.txt`. typescript's include `package.json` and `tsconfig.json`.
  - `test_detect_must_be_file_names`: `"src/pyproject.toml"` and `"*.toml"` are refused, naming `detect.markers[0]`.
  - `test_survey_globs_load`: `load_survey(Source(PLUGIN_ROOT, True))` has non-empty lists for `ci`, `docs`, `decisions`, `migrations`, `task_runners`, `hook_managers`, `license` and `env_examples`. An `ALPHA_SOURCE` checkout without the file falls back to the bundled one.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.** Seed `survey.toml` with one commented list per key:
  - `ci`: `.github/workflows/*.yml`, `.github/workflows/*.yaml`, `.gitlab-ci.yml`, `.circleci/config.yml`, `Jenkinsfile`, `azure-pipelines.yml`, `bitbucket-pipelines.yml`
  - `docs`: `README*`, `CONTRIBUTING*`, `CHANGELOG*`, `CLAUDE.md`, `AGENTS.md`, `docs/**/*.md`
  - `decisions`: `docs/decisions/*.md`, `docs/adr/*.md`, `docs/adrs/*.md`, `adr/*.md`, `docs/architecture/decisions/*.md`
  - `migrations`: `**/migrations/**`, `**/alembic/versions/**`, `**/db/migrate/**`
  - `task_runners`: `Makefile`, `justfile`, `Taskfile.yml`, `mise.toml`, `**/package.json`
  - `hook_managers`: `.husky/**`, `.pre-commit-config.yaml`, `lefthook.yml`, `.lefthook.yml`
  - `license`: `LICENSE*`, `COPYING*`
  - `env_examples`: `**/.env.example`, `**/.env.sample`
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(recipes): Name the files that mark each stack`

### Task 2: `alpha adopt survey`

**Files:**
- Create: `src/alpha/adopt.py`, `tests/test_adopt_survey.py`
- Modify: `src/alpha/cli.py`, `src/alpha/answers.py` (`_ADOPTION_KEYS` gains `survey`: any JSON object, kept as is)

**Interfaces:**
- `survey(target: Path, source: Source, book: RecipeBook | None = None) -> dict[str, Any]`, returning:
  ```
  {"git": {"head", "branch", "default_branch", "clean", "dirty": [≤20 paths],
           "commits", "conventional": {"checked", "matching", "others": [≤5 subjects]},
           "hooks_path", "hook_managers": [paths]},
   "components": [{"path", "stack", "markers": [paths], "sources": n, "tests": n}],
   "files": {"ci": [...], "docs": [...], "decisions": [...], "migrations": [...],
             "task_runners": [...], "license": [...], "env_examples": [...]},
   "tracked": n}
  ```
  - Lists are sorted and capped at 50 each, with a `"<key>_more": n` count beside them.
  - `sources` and `tests` count tracked files under the candidate's folder that match its recipe's `source_globs` / `test_globs` and not `exclude_globs`, leaving out nested candidates' folders.
  - The conventional format is checked on the last 50 subjects with the regex `^(<defaults git.types>)(\([^)]+\))?!?: \S`.
- Refusals (`AdoptError`, exit 1):
  - not a git repository: "run git init and commit, then retry"
  - no commits: "commit the code first"
  - `.claude/alpha/project.json` with a `manifest`: "alpha already generated or adopted it: use /alpha:extend"
- CLI: `alpha adopt survey <target> [--save]` prints the JSON, indented. `--save` also stores it with `write_answers(target, {"adoption": {**current adoption, "survey": result}})`. The other `adoption` keys are kept, because `answers write` replaces whole top-level keys.

- [ ] **Step 1: Write the failing tests.** Build repos in `tmp_path` with `git init` and commits:
  - `test_survey_finds_components_by_marker`: `api/pyproject.toml`, `web/package.json` + `web/tsconfig.json`, and a root `package.json` give three candidates with their markers and stacks. A `node_modules/x/package.json` that's ignored isn't one of them.
  - `test_survey_counts_sources_and_tests`: `api/app/a.py`, `api/tests/test_a.py` give 1 and 1, and a nested candidate's files aren't counted in its parent.
  - `test_survey_lists_files`: `.github/workflows/ci.yml`, `docs/adr/0001-x.md`, `.husky/pre-commit` and `LICENSE` each land in their list.
  - `test_survey_git_facts`: two conventional subjects and one not give `checked 3, matching 2`, with the odd one in `others`. A dirty file shows `clean: false` and lists it. `core.hooksPath` is reported.
  - `test_survey_refusals`: no repo, no commits, and an alpha project each give their message.
  - `test_survey_reads_one_listing`: monkeypatch the git runner and count `ls-files` calls (exactly 1).
  - `test_survey_save_keeps_other_adoption_keys`: with `adoption.baselines` present, `--save` keeps it and adds `survey`.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.** Match globs with `alpha.recipes.matches` (the `**` matcher alpha already uses), and run git with `subprocess`. `default_branch` is `origin/HEAD`'s target when it exists, else `main` or `master` if present, else the current branch.
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Survey an existing repo for adoption`

### Task 3: Adopted recipes in the answers

**Files:**
- Modify: `src/alpha/recipes.py` (`recipe_from_data(..., adopted=False)`, `Recipe.adopted: bool`, `RecipeBook.data(stack) -> dict[str, Any]`, the raw kit TOML), `src/alpha/answers.py` (`drafted_recipes` merges `extends`)
- Test: `tests/test_adopted_recipes.py`

- [ ] **Step 1: Write the failing tests:**
  - `test_adopted_needs_its_own_name`: `recipes.python` with `adopted: true` is refused ("name it after the component, e.g. api-python").
  - `test_adopted_may_have_no_templates`: an adopted recipe with `templates: {}` loads, while a plain drafted one still needs its setup test.
  - `test_adopted_bootstrap_must_be_empty`: refused with S4's reason and the fix ("a missing tool is a plan step").
  - `test_adopted_test_may_be_empty`, and `setup` still may not be.
  - `test_extends_fills_from_the_kit`: `{"adopted": true, "extends": "python", "commands": {...kit commands...}, "templates": {}}` gets the kit's rules, ignores, CI steps, lockfiles and all four baseline readers.
  - `test_extends_drops_readers_of_changed_steps`: `commands.typecheck = "uv run mypy ."` drops the inherited `baseline.typecheck`, and an own `baseline.typecheck` is kept. A changed `lint_file` with an unchanged `lint` keeps the reader but needs its own `file_command` (the recipe check names it).
  - `test_extends_unknown_stack`: refused, listing the kit stacks.
  - `test_extends_needs_adopted`: `extends` without `adopted` is refused.
  - `test_adopted_hash_covers_the_entry`: editing the adopted entry un-proves it, and `extends` is part of the hash.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.** `drafted_recipes` resolves `extends` before `recipe_from_data`, with `generated` passed through. The rule "a drafted recipe may not use a kit stack's name" stays as it is: adopted recipes have their own names.
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(recipes): Adopt a repo's own tools as a recipe`

### Task 4: Prove an adopted recipe on the repo

**Files:** Modify `src/alpha/recipe_cli.py`. Test: `tests/test_adopted_recipes.py`.

**Interfaces:**
- `try_recipe(target, stack)`, for an adopted recipe:
  - It reads `components` in project.json for the folders using that stack. With none, it refuses: "save the component that uses <stack> first".
  - It runs `git worktree add --detach <scratch>/repo HEAD`, then per folder runs `setup` and each check step.
  - It always removes the worktree in `finally`, with `git worktree remove --force` plus `git worktree prune`.
- A check that exits 0 is fine. A non-zero check is fine when its baseline reader reads ≥1 finding, and these counts are reported. Otherwise the proof fails:
  - `format_check`: "today's code isn't formatted; set commands.format_check to "" until the formatting step, which the adoption plan adds".
  - any other step without a reader: "add [baseline.<step>] so its N legacy findings can be baselined, or fix them first".
  - a reader that can't read the output: the same message as plan 2's clean-skeleton proof.
- On success it prints `ok: <stack> recipe proven on <path>@<short sha>`, then one line per step that has findings, e.g. `typecheck: 37 findings in 12 files (baseline it: typecheck:<component>)`.

- [ ] **Step 1: Write the failing tests** (fast; the recipe's commands are shell one-liners over a temp repo):
  - `test_try_adopted_proves_on_head`: a check that greps the repo's real file passes, and an uncommitted edit isn't seen.
  - `test_try_adopted_reports_legacy_findings`: a failing lint whose reader reads 3 findings proves, printing the count and the check id to baseline.
  - `test_try_adopted_unreadable_failure`
  - `test_try_adopted_unformatted`
  - `test_try_adopted_needs_a_component`
  - `test_try_adopted_removes_its_worktree`, after success, failure and a timeout (with the timeout monkeypatched short)
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Prove an adopted recipe on the repo's code`

### Task 5: End to end on real tools, and the docs

**Files:** Create `tests/test_adopted_slow.py`. Modify `CLAUDE.md`.

- [ ] **Step 1: Write the slow test.**
  - Build a repo in `tmp_path`: a uv Python project at `svc/` with dev dependencies mypy, black and pytest (locked with `uv lock`), one module with a mypy error, one failing test and one passing test, plus a GitHub workflow and a README. Commit it.
  - `alpha adopt survey` lists `svc` as a python candidate with 1 source and 2 tests, and the workflow under `ci`.
  - Save components, plus an adopted `svc-python` recipe:
    - `extends: python`
    - `commands.typecheck = "uv run mypy --strict ."`, with a `baseline.typecheck` pattern for mypy's `file:line: error: … [code]`
    - `commands.lint = ""` and `lint_file = ""` (no linter in the repo)
    - `format_check = "uv run black --check ."`
  - `alpha recipe try` proves it, reporting the typecheck and test findings. The worktree is gone afterwards, and the repo's tree is unchanged.
- [ ] **Step 2: Run** `uv run pytest -m slow tests/test_adopted_slow.py`. Expected: PASS.
- [ ] **Step 3: CLAUDE.md.** Add a Dev-commands bullet for `alpha adopt survey`. Note that adopted recipes are proven on a worktree of the repo's HEAD.
- [ ] **Step 4: Run** `mise run check`. Expected: PASS.
- [ ] **Step 5: Commit** `test: Prove an adopted recipe on a real repo`
