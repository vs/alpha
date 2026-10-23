# Alpha Generic Stacks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A component can use any stack. When the kit has no recipe for it, the interview drafts one from looked-up facts, the user confirms it, alpha proves it in a scratch folder before anything is generated, and the project marks it as less proven. After a successful project, the user can save the recipe to the kit for the next one.

**Architecture:** A recipe becomes data that can come from three places: the kit's bundled `recipes/`, the live kit source's `recipes/` (recipes saved from earlier projects), or the project's own `project.json` (`recipes.<stack>`, drafted in the interview, with templates inline). A `RecipeBook` resolves a stack to one `Recipe`, and every caller that used `load_recipe(stack)` gets the book instead. Three CLI commands support the interview: `alpha recipe check` validates a drafted recipe, `alpha recipe try` proves it in a scratch folder (templates, bootstrap, every check command), and `alpha recipe save` copies it into the kit source with a commit.

**Tech Stack:** Python ≥ 3.11 stdlib runtime; pytest, ruff, pyright; Rust (cargo) for the proof scenario.

**Spec:** `docs/superpowers/specs/2026-10-19-project-kit-design.md` §2 ("Any other stack still works, set up from that stack's usual conventions and marked as less proven"), §3 (stack recipes: "generic fallback for others"), §4 ("Facts are the kit's job"), §7 (per-component config, tests green from day one, no placeholder sources), §11 (kit changes only with the user's yes, committed to the source), §12 (a fallback-path eval).

**Plan series:** 2d, after plan 3. Then 2c, 2e and plan 4.

## Global Constraints

- No code outside `recipes/` names a stack: `test_recipes_name_no_stack_outside_recipes` loses its `answers.py` exception (`STACKS` goes).
- A drafted recipe never shadows a kit recipe: a stack the kit has always uses the kit's.
- Every drafted recipe is proven by `alpha recipe try` before `generate` accepts it: `answers check` refuses a drafted recipe whose `proven_hash` doesn't match its current content hash (Task 4).
- Skeleton rules stay: no app code and no placeholder sources; the recipe's templates are config plus a setup test that tests the toolchain, not app behavior.
- Kit changes need the user's yes and land in the live source with a commit (§11), like `alpha defaults set`: exit 4 when the source isn't live.
- Facts are the kit's job: the skill looks up installed tool versions, the stack's usual tools and the current CI setup action before asking anything.
- The spec names a Go CLI for the fallback eval. Go isn't installed on this machine; Rust (cargo 1.93) stands in. A Go scenario can be added where Go is available.
- Kit dev commands: `uv run pytest`, `uv run pytest -m slow`, `uv run ruff check`, `uv run ruff format`, `uv run pyright`.

## Review Focus

1. **A drafted recipe edited after it was proven.** `generate` must refuse it until `recipe try` passes again. (Test in Task 4.)
2. **A drafted recipe for a stack the kit has, or with a name that isn't a valid stack name** (`Rust`, `c++`). Refused with the fix. (Test in Task 2.)
3. **`recipe try` on a machine without the toolchain.** The failure names the missing tool and how to install it, and leaves no scratch folder behind. (Test in Task 4.)
4. **Templates with `$` in them** (shell snippets, Cargo's `$schema`, Makefiles). Only `$name` and `$slug` substitute; anything else must survive. (Test in Task 1.)
5. **Saving a recipe the kit already has, or saving without a live source.** Refused with exit 3 or 4 and the fix; nothing half-written. (Test in Task 5.)

---

## File Structure

```
src/alpha/recipes.py          Recipe from data (TOML or JSON), inline templates, `proven`; RecipeBook; render with $name/$slug only
src/alpha/answers.py          Answers.recipes (drafted); stack validated through the book; STACKS removed
src/alpha/principles.py, render/docs.py, render/ci.py, render/claude_settings.py, generate.py   take a RecipeBook
src/alpha/recipe_cli.py       NEW: check / try / save
src/alpha/cli.py              `alpha recipe check|try|save`
skills/stack-recipe/SKILL.md  NEW: draft, confirm, check, try
skills/components/SKILL.md, skills/new-project/SKILL.md   any stack; save offer; less-proven report
evals/scenarios/rust-cli.json NEW: a Rust CLI with a drafted recipe
recipes/python.toml, recipes/typescript.toml   + proven = true
```

---

### Task 1: Recipes as validated data

**Files:** Modify `src/alpha/recipes.py`, `recipes/python.toml`, `recipes/typescript.toml`. Test: `tests/test_recipes.py`.

**Interfaces:**
- `RecipeError(Exception)`; messages follow `<where>: <problem>. <fix>`.
- `Recipe` gains `proven: bool` and `templates: dict[str, str]` (output relpath → template text). Kit recipes keep `files` (relpath → template file name), which the loader reads into `templates`; drafted recipes give `templates` inline. `files` leaves the dataclass.
- `recipe_from_data(stack: str, data: Mapping[str, Any], where: str, template_dir: Path | None) -> Recipe`. Required: `bootstrap` (list of commands, may be empty), `commands` with non-empty `setup` and `test` and every other `CHECK_STEPS` key present (empty allowed), `format_file`/`lint_file` empty or containing `{file}`; `lockfiles`, `manifests`, `source_globs`, `test_globs`, `exclude_globs`, `ignores`, `allow` (lists of strings, globs relative and matchable per `validate.unmatchable`); `why` (string → string); `ci.steps` (list of mappings, each `uses` matching `owner/repo@ref` with `ref` a `vN`, `vN.N.N` or 40-hex SHA), `ci.env` (string → string); `dependabot` (string, may be empty: no updates for that component); `proven` (bool, default false); at least one template whose path matches `test_globs` (the setup test).
- `render_template(text: str, name: str, slug: str) -> str`: replaces exactly `$name` and `$slug` (and `${name}`, `${slug}`); every other `$` stays.
- `render_component(component, slug, recipe: Recipe) -> dict[str, str]` (the recipe is passed in).

- [ ] **Step 1: Write failing tests**: kit recipes load with `proven = True`; each missing or malformed field above fails at its dotted path with a fix (parametrize); a recipe without a setup test template fails; `render_template("$name $slug $HOME ${name} $$x", ...)` keeps `$HOME` and `$$x`.
- [ ] **Step 2: Run** `uv run pytest tests/test_recipes.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement**; set `proven = true` in both kit recipes.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(recipes): Load recipes as validated data`

---

### Task 2: The recipe book and drafted recipes in the answers

**Files:** Modify `src/alpha/recipes.py`, `src/alpha/answers.py`, `src/alpha/validate.py` if needed. Test: `tests/test_recipes.py`, `tests/test_answers.py`.

**Interfaces:**
- `kit_dirs() -> list[Path]`: the live source's `recipes/` (from `defaults.locate_source(PLUGIN_ROOT, os.environ, Path.home())`, when live and different from the bundled one) then the bundled `RECIPES_DIR`.
- `RecipeBook(drafted: Mapping[str, Recipe] = {})` with `get(stack) -> Recipe` (kit first, then drafted; unknown → `RecipeError` listing kit stacks and saying how to draft one), `kit_stacks() -> list[str]`, `drafted` (the mapping).
- `Answers.recipes: dict[str, Recipe]`, from the optional top-level `recipes` object (`_TOP_KEYS` gains it), validated with `recipe_from_data(stack, data, f"recipes.{stack}", None)`. A key that isn't a valid name (`NAME`) or that the kit has fails at `recipes.<stack>` with a fix. `components[i].stack` must be a kit stack or a drafted one; otherwise fail with `"<stack>" has no recipe. Draft one with the stack-recipe skill, or use one of: <kit stacks>`.
- `Answers.book() -> RecipeBook` convenience.

- [ ] **Step 1: Write failing tests**: a drafted `shell` recipe (trivial `sh -c true` commands, inline templates) loads and the component using it validates; `recipes.Rust`, `recipes.c++` and `recipes.python` are refused; an unknown stack names the kit stacks and the skill; `test_recipes_name_no_stack_outside_recipes` without the `answers.py` exception.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement**; delete `STACKS`.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Accept any stack that has a recipe`

---

### Task 3: Every generator works from the book

**Files:** Modify `src/alpha/principles.py`, `src/alpha/render/docs.py`, `src/alpha/render/ci.py`, `src/alpha/render/claude_settings.py`, `src/alpha/generate.py`. Test: `tests/test_generate.py`, `tests/test_scenarios.py`, plus signature updates where tests call these.

**Interfaces:** `build_principles(defaults, a, kit_version, book: RecipeBook | None = None)` (default `a.book()`); `render_docs(..., book=None)`; `render_ci(principles, ci, book)`; `render_dependabot(principles, updates, schedule, ci, book)` (skips components whose recipe has no ecosystem); `render_settings(principles, book)`; `generate` builds `a.book()` once and passes it everywhere; `bootstrap(target, principles)` builds the book from `target/.claude/alpha/project.json`. `docs/architecture.md`'s tool-choices line for a recipe with `proven = false` ends with ` (less proven: recipe drafted for this project)`.

- [ ] **Step 1: Write failing tests**: generate a scenario whose one component uses a drafted `shell` recipe (fast test, `sh` commands): the component's templates, CI job, Dependabot (none), settings allow-list and `.gitignore` all come from the drafted recipe; the architecture doc marks it less proven; `bootstrap` runs its commands.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q` and `uv run pytest -m slow -q`. Expected: PASS both.
- [ ] **Step 5: Commit** `feat: Generate components from drafted recipes`

---

### Task 4: Check and try a drafted recipe

**Files:** Create `src/alpha/recipe_cli.py`. Modify `src/alpha/cli.py`, `src/alpha/answers.py`. Test: `tests/test_recipe_cli.py`, `tests/test_bootstrap_slow.py`.

**Interfaces:**
- `recipe_hash(data: Mapping[str, Any]) -> str`: sha256 of the recipe JSON with sorted keys, excluding `proven_hash`.
- `alpha recipe list`: the kit's stacks, one per line, each with `(proven)` or `(drafted in a project)` from its `proven` flag.
- `alpha recipe check <target> <stack>`: validates `recipes.<stack>` in the target's project.json; prints `ok` or the error (exit 1).
- `alpha recipe try <target> <stack>`: in a new temp folder, renders the templates for a throwaway component (`name` = the stack, `slug` = `try`), then runs `bootstrap` and every `check_commands` step in order, streaming `alpha: try: <command>` to stderr. On success, writes `recipes.<stack>.proven_hash = recipe_hash(...)` through `answers.write_answers` and prints `ok: <stack> recipe proven`. On failure, prints the failing command, its last 40 lines and `Fix the recipe's <step> command (or install <first word> if it's missing), save it, and try again.`; exit 1. The temp folder is removed either way.
- `load_answers` (for `generate` and `answers check` with the components area) refuses a drafted recipe whose `proven_hash` is missing or not its current `recipe_hash`: `recipes.<stack>: not proven since it last changed. Run "alpha recipe try <target> <stack>"`.

- [ ] **Step 1: Write failing tests** (fast, with the `shell` recipe and stand-in tools on PATH): list shows `python (proven)` and `typescript (proven)`; check ok and error; try success records the hash; try failure names the command and leaves no temp folder; a missing tool (exit 127) says to install it; editing the recipe after try makes `generate` refuse it. Slow: `test_rust_recipe_is_proven_by_try` (skips without `cargo`) using the Task 7 scenario's recipe.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q` and `uv run pytest -m slow -q`. Expected: PASS both.
- [ ] **Step 5: Commit** `feat: Prove a drafted recipe before generating`

---

### Task 5: Save a recipe to the kit

**Files:** Modify `src/alpha/recipe_cli.py`, `src/alpha/cli.py`. Test: `tests/test_recipe_cli.py`.

**Interfaces:** `alpha recipe save <target> <stack> --trailer …` (same trailer convention as `defaults set`): needs a live source (else exit 4 with the `SourceNotLive` message) and a proven drafted recipe that the kit doesn't have (else exit 3 with the fix). Writes `recipes/<stack>.toml` (data, `proven = false`, `files` naming the templates) and `recipes/<stack>/<n>.tmpl` per template into the source, then `git add` and `git commit -m "feat(recipes): Add <stack> recipe from <project slug>"` plus trailers. On any failure, removes what it wrote. The bundled kit sees it at once through `kit_dirs()`.

- [ ] **Step 1: Write failing tests** with a temporary source repo (the pattern in `tests/test_defaults.py`): saved files load back as the same recipe with `proven = False`; the commit message and trailers; exit 4 without a live source; exit 3 for a kit stack or an unproven recipe; no files left after a failed commit.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Save a proven recipe to the kit`

---

### Task 6: The stack-recipe skill and the interview

**Files:** Create `skills/stack-recipe/SKILL.md`. Modify `skills/components/SKILL.md`, `skills/new-project/SKILL.md`. Test: `tests/test_skills.py`.

**Interfaces:**
- **stack-recipe** (model-invocable, interview-only description, ≤ 150 lines, `allowed-tools` the CLI). Steps:
  1. Facts first (never asked): is the toolchain installed and which version (`<tool> --version`); the stack's usual test runner, formatter, linter and type or compile check; its manifest and lockfile names; the current GitHub Actions setup action and its pinned tag; the Dependabot ecosystem. Look them up (docs, the action's releases).
  2. Draft the whole recipe in the JSON shape of Task 1, strict settings where the stack has them, one setup test that checks the toolchain itself, no source files.
  3. Show it to the user in plain words: the commands per step, the files the skeleton gets, what CI runs. Say it's less proven than the kit's own recipes.
  4. Save with `answers write <target> --json '{"recipes": {…}}'` (send `recipes` whole), then `recipe check`, then `recipe try`. On a failure, fix the recipe (asking the user when the fix is a choice), save, and try again until it prints `ok`.
- **components**: drop "v0.1 sets up Python and TypeScript only". Stack per component: recommend `defaults.stacks[kind]`; any stack is possible; a stack without a kit recipe (`alpha recipe list` doesn't name it) goes through `alpha:stack-recipe` before the area is done.
- **new-project**: after `commit-skeleton`, for each drafted recipe, ask "Save the <stack> recipe to the kit for future projects?" and on yes run `recipe save` with the trailers; report the exit code honestly as for `defaults set`. The final report names any less-proven recipe.
- `test_skills.py`: stack-recipe in `ALL_SKILLS`/`CLI_SKILLS`; its CLI calls are real subcommands; `test_skills_use_every_cli_command_the_interview_needs` adds `recipe list`, `recipe check`, `recipe try`, `recipe save`.

- [ ] **Step 1: Write failing tests** for the above.
- [ ] **Step 2: Run** `uv run pytest tests/test_skills.py -q`. Expected: FAIL.
- [ ] **Step 3: Write** the skill and edits.
- [ ] **Step 4: Run** `uv run pytest -q` and `claude plugin validate .claude-plugin/marketplace.json`. Expected: PASS, valid.
- [ ] **Step 5: Commit** `feat: Draft recipes for stacks the kit lacks`

---

### Task 7: The Rust CLI scenario

**Files:** Create `evals/scenarios/rust-cli.json`. Modify `tests/test_scenarios.py`, `tests/test_bootstrap_slow.py`.

**Interfaces:** A single-component Rust CLI project (all twelve areas answered) with a drafted `rust` recipe: `cargo` commands (`cargo fetch` setup, `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo check --all-targets`, `cargo test`), `Cargo.toml` and `tests/setup.rs` templates (no `src/`), `Cargo.lock` lockfile, `target/` ignored, a pinned Rust toolchain setup action looked up at implementation time, `dependabot = "cargo"`, `proven_hash` set by running `recipe try` once.

- [ ] **Step 1: Write failing tests**: the fast scenario test generates it (root entries include `Cargo.toml`, `tests`, no `src`); slow `test_bootstrap_runs_green` parametrizes over it (skipped without `cargo`) and commits it with a clean tree.
- [ ] **Step 2: Run** them. Expected: FAIL (no scenario).
- [ ] **Step 3: Write** the scenario; run `alpha recipe try` on it to set `proven_hash`.
- [ ] **Step 4: Run** `uv run pytest -q` and `uv run pytest -m slow -q`. Expected: PASS both.
- [ ] **Step 5: Commit** `test: Add a Rust CLI scenario for drafted recipes`

---

### Task 8: Live check

**Files:** Modify `CLAUDE.md` (kit live-run notes).

- [ ] **Step 1:** In a scratch folder, write a `project.json` with the identity area done for a small Rust CLI and the components area pending. Run `claude -p --plugin-dir /Users/vs/workspace/alpha "Run the alpha components area for <folder>: one cli component in Rust at the root, nothing deployed. Accept the recommendations."` with the alpha CLI pre-approved. Expected: the stack-recipe skill drafts a Rust recipe, `recipe try` prints `ok`, and `answers check --area components` prints `ok`.
- [ ] **Step 2:** Record what was drafted and anything the skill got wrong in the kit's live-run notes.
- [ ] **Step 3: Commit** `docs: Record the generic stack live check`
