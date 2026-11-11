# Baselines and the Ratchet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A project can hold a baseline of today's findings for a check, so the check fails only on new findings, and the baseline can only shrink (spec §8b). This is the first plan for adopting existing projects (§5b, A2). Installing alpha on a legacy repo can't go green without it. Nothing in this plan surveys or adopts a repo yet: the baselines are switched on through the answers, which plans 3 and 4 will fill in from the adoption flow.

**Architecture:**
- A check that can be baselined names, as data, a command with machine-readable output and a regex with named groups `file` and `rule`. For component steps this lives in the recipe's `[baseline.<step>]`; for repo checks, in the registry pin.
- When the answers list a check under `adoption.baselines`, `build_principles` writes a `[[baselines]]` entry for it into `docs/principles.toml` (its id, folder, commands and pattern). The check's command, wherever it's rendered, becomes `python3 <path>/ratchet.py <id>`. This covers the principles file's component commands (so the Stop hook, post-edit hook and bootstrap), `mise.toml` tasks and CI jobs.
- `ratchet.py` reads its entry from the principles file, runs the command, counts findings per file and rule, and compares them with `.claude/alpha/baselines/<id>.json`.
- A new repo check, `baselines` (`diff_checks.py baselines`), fails a pull request where a count grows unless the PR adds an accepted decision record naming the check.
- `alpha baseline show|capture|tighten` manages the files.

**As built (2026-11-11):** tasks 1-8 are done. Where the build differs from the steps below:
- A baseline reads findings with a line `pattern` or, for tools whose text wraps or groups by file (pyright, lychee), a `json` reader. That's `items` (a dotted path, where `*` walks a list or object), `file` and `rule` (field paths, or `@N` for a walked key) and `where`. In the registry it's a `[tools.<id>.pin.baseline]` table, not flat keys.
- Rules have the machine's root path stripped (lychee's URLs name absolute files), so a laptop and CI count the same rule.
- `alpha bootstrap --capture-baselines` records each missing baseline after the component's setup step (or after `mise install`, for repository checks) and before its check runs. Without the flag, a missing baseline stops bootstrap before any slow step. Capture needs the toolchain, so it can't come first.
- The ratchet finds its project by the nearest `docs/principles.toml` when there's no `.git` yet: a fresh skeleton's bootstrap runs its checks before `git init`.
- The `baselines` PR check accepts an added record only when it names the check id in backticks and says `Status: accepted`.
- The tests live in `tests/checks/test_ratchet.py`, `tests/test_baselines_render.py`, `tests/hooks/test_baselined_hooks.py`, `tests/test_baseline.py` and `tests/test_baseline_slow.py`. The slow test covers the web+API scenario, and the fast render test covers a component at the root.

**Tech Stack:** Python ≥ 3.11 for the kit; the copied scripts use the stdlib only and parse on Python 3.9. pytest, ruff, pyright.

**Spec:** `docs/superpowers/specs/2026-10-19-project-kit-design.md` §8b, §5b (A2). Plan series: adoption 1 of 6 (then survey and adopted recipes, rendering onto an existing repo, the plan model, skills, evals).

## Decisions (the planner's calls)

- **B1 One principles entry per baselined check.** `[[baselines]]` holds `id`, `dir` (the folder it runs in, relative to the root), `command`, `file_command` (only for `lint`, with `{file}`) and `pattern`. The ratchet reads its entry by id, so commands are never quoted into another command.
- **B2 Check ids.** A component step is `<step>:<component>` (e.g. `typecheck:api`), with `<step>` one of `lint`, `typecheck`, `structure` or `test`. A repo check uses its own id (`typos`, `markdown`, `links`, `agent-config`, `actions`). The baseline file is `.claude/alpha/baselines/<id with ":" as ".">.json`.
- **B3 Counts per (file, rule).** The baseline file is `{"check": id, "counts": {file: {rule: n}}}`, with keys sorted and files relative to the repo root. A missing `rule` group counts as `"-"`. Absolute paths and paths relative to `dir` are both normalized to root-relative.
- **B4 Frozen in CI.** With `CI=true` in the environment (GitHub Actions sets it), the ratchet never writes. A count below the baseline fails there, with the command to tighten and commit. Locally, counts below the baseline tighten the file, but only when nothing exceeds it.
- **B5 Growth is gated in the PR, not by a guard.** Baseline files are protected paths (no Edit/Write by Claude) and risk paths (the reviewer sees every change to them). The `baselines` repo check fails a PR where any count rose against the base, unless the PR adds a decision record under `docs/decisions/` whose text names the check id and that has `Status: accepted`. This replaces the spec's "Claude can't run it without one" (Task 1 corrects §8b): a Bash guard can't tell a legitimate capture from a forged file, but the PR diff can.
- **B6 Not baselined:** `format_check` (plan 5's P1 step fixes it once), `setup`, `secrets`, `vulns`, the diff checks, `shortcuts`, `review-dates` and `toolchain`. `adoption.baselines` refuses them with the reason.
- **B7 A missing baseline file is an error, not an empty baseline.** The ratchet says "no baseline for <id>: run alpha baseline capture <root> --check <id>". So a baseline listed in the answers but never captured can't silently fail every legacy finding, or silently pass.

## Global Constraints

- A project without `adoption.baselines` renders byte for byte as today. `tests/test_generate.py`, `tests/test_scenarios.py` and the scenario snapshots must not change.
- Stack-free: no stack, tool or component name is branched on in code. Patterns and machine-output commands are data in recipes and the registry.
- Copied scripts (`project-files/`): stdlib only, run with `python3`. `ratchet.py` runs from the hooks, so like them it parses on 3.9 and exits with a helpful message below the version they need (`_common.check_python`); `diff_checks.py` runs only in CI and may use 3.11 as today.
- Every failure says what's wrong and how to fix it, naming the command to run.
- Commits: `type(scope): Description`, description ≤ 50 chars, imperative, capitalized, no trailing period, body wrapped at 72, scopes are component names (`hooks`, `recipes`, `defaults`, `spec`) or none. End each with this session's attribution lines.
- `uv run pytest`, `uv run ruff check`, `uv run ruff format --check` and `uv run pyright` pass after every task. Tests that need real tools are `@pytest.mark.slow`.

## Review Focus

1. **A tool fails but its output doesn't parse** (crash, missing binary, config error, a new output format). The ratchet must fail, never pass. Pinned by `test_unparsed_failure_fails_closed` (Task 3).
2. **Paths.** A tool printing absolute paths, paths relative to the component, or `./` prefixes must match the baseline entry for the same file. A component at `.` and one at `api/` both work. Pinned by `test_paths_normalize_to_root` (Task 3).
3. **Tightening in CI.** CI must never write a baseline, and a stale one must fail with the fix. Pinned by `test_frozen_fails_on_stale` (Task 3).
4. **Growth slipping through.** A PR that raises a count, adds a new file or rule to a baseline, or deletes a finding's file and re-adds it elsewhere fails `baselines` without an accepted record naming the check. Pinned by `test_growth_needs_a_decision` (Task 5).
5. **Generated projects unchanged.** Pinned by the existing snapshot tests plus `test_no_baselines_renders_as_before` (Task 4).

---

## File Structure

```
docs/superpowers/specs/2026-10-19-project-kit-design.md   §8b growth wording (Task 1)
recipes/python.toml, recipes/typescript.toml              [baseline.<step>] tables (Task 2)
registry/tools.toml                                      baseline_command / baseline_pattern on pins (Task 2)
src/alpha/recipes.py                                     Baseline dataclass, validation (Task 2)
src/alpha/registry.py                                    Pin.baseline (Task 2)
project-files/checks/ratchet.py                          NEW (Task 3)
src/alpha/answers.py                                     adoption.baselines (Task 4)
src/alpha/principles.py                                  [[baselines]], wrapped commands, protected + risk paths (Task 4)
src/alpha/repo_checks.py                                 wrapped repo checks, the `baselines` check (Tasks 4, 5)
project-files/checks/diff_checks.py                      `baselines` subcommand (Task 5)
project-files/hooks/_common.py                           protected message for baselines (Task 6)
src/alpha/baseline.py                                    NEW: show, capture, tighten (Task 7)
src/alpha/cli.py                                         `alpha baseline` (Task 7)
src/alpha/generate.py                                    bootstrap names a missing baseline (Task 7)
tests/test_ratchet.py, tests/test_baseline.py            NEW
tests/checks/test_diff_checks.py, tests/test_principles.py, tests/test_recipes.py,
tests/test_registry.py, tests/test_answers.py, tests/hooks/test_post_edit.py   extended
CLAUDE.md                                                dev notes (Task 8)
```

---

### Task 1: Correct the spec on growth

**Files:** Modify `docs/superpowers/specs/2026-10-19-project-kit-design.md` §8b, the "Only shrinking" bullet.

- [ ] **Step 1:** Replace "Claude can't run it without one." with B5: baseline files are protected and risk paths, and the `baselines` repo check fails a pull request where a count rises unless the PR adds an accepted decision record that names the check. Add `baselines` to the §8a check table (`none`, `python3 .claude/alpha/checks/diff_checks.py baselines`, no globs, stop no, `pr`, applies when `adoption.baselines` is non-empty).
- [ ] **Step 2:** `mise run check` passes (typos, rumdl and agnix on the spec).
- [ ] **Step 3: Commit** `docs(spec): Gate baseline growth in the pull request`

### Task 2: Baseline data in recipes and the registry

**Files:**
- Modify: `src/alpha/recipes.py` (`_RECIPE_KEYS`, `Recipe`, `recipe_from_data`), `src/alpha/registry.py` (`Pin`), `recipes/python.toml`, `recipes/typescript.toml`, `registry/tools.toml`, `skills/stack-recipe/SKILL.md`
- Test: `tests/test_recipes.py`, `tests/test_registry.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Baseline: command: str; pattern: str; file_command: str = ""`
  - `Recipe.baselines: Mapping[str, Baseline]`, keyed by step (`lint`, `typecheck`, `structure`, `test`).
  - `Pin.baseline: Baseline | None`, from `baseline_command` and `baseline_pattern` on a pin.
  - `BASELINE_STEPS = ("lint", "typecheck", "structure", "test")` in `recipes.py`.

- [ ] **Step 1: Write the failing tests:**
  - `test_baseline_pattern_needs_file_and_rule_groups`: a recipe whose `[baseline.lint] pattern` lacks `(?P<file>` raises `RecipeError` naming `baseline.lint.pattern` and both group names. A pattern that doesn't compile names `re.error`'s message.
  - `test_baseline_step_must_exist`: `[baseline.typecheck]` with an empty `commands.typecheck` fails. `[baseline.format_check]` fails, naming B6's reason.
  - `test_lint_file_command_needs_file_slot`: `[baseline.lint] file_command` without `{file}` fails. It's required when `commands.lint_file` isn't empty.
  - `test_kit_recipes_have_baselines`: python and typescript have entries for lint, typecheck and test. Python also has structure.
  - `test_registry_baseline_pins`: typos, rumdl, lychee, agnix and jactionlint pins have a `baseline` whose pattern compiles with both groups.
  - Drafted recipes take the same table (round-trip through `drafted_recipes`). `recipe_hash` covers it, so editing it un-proves the recipe.
- [ ] **Step 2: Run** `uv run pytest tests/test_recipes.py tests/test_registry.py -v`. Expected: FAIL.
- [ ] **Step 3: Find the real output formats.** In a scratch folder with the kit's pinned versions, seed one violation per tool and record the exact line each prints:
  - ruff: `ruff check --output-format concise`
  - pyright: `pyright` text output, absolute paths, `(reportXxx)` suffix, some errors without a rule
  - pytest: `pytest -rf -q` and its `FAILED path::test` lines
  - deptry: `deptry .` and its `DEP00x` codes
  - biome: `biome lint --reporter=github`
  - tsc: `tsc --noEmit --pretty false`, giving `file(l,c): error TSnnnn`
  - vitest: `vitest run --reporter=verbose` failure lines
  - typos: `typos --format brief`
  - rumdl: `rumdl check .`, giving `[MDnnn]`
  - lychee: `lychee --offline --format compact --no-progress .`
  - agnix: `agnix --strict .`
  - jactionlint: its default output

  Write each pattern to match the recorded line and nothing in the tool's summary lines. Keep the recorded lines as test fixtures under `tests/fixtures/baseline-output/<tool>.txt`. If a tool can't name the file or rule in any output mode, leave it out of the table and record why in its registry `limitations`. Don't guess a format.
- [ ] **Step 4: Implement.** Add the tables to the recipes and the pin fields to the registry. Validate with the helpers in `alpha.validate`. In `skills/stack-recipe/SKILL.md`, add one bullet: a drafted recipe may add `[baseline.<step>]` with a machine-output command and a pattern with `file` and `rule` groups, proven by `recipe try`. Task 3 makes `try` parse its output.
- [ ] **Step 5:** Add `test_kit_patterns_read_recorded_output`, which runs each recipe and registry pattern over its fixture and asserts at least one `(file, rule)` per seeded violation, with no match on the summary lines. Run `uv run pytest`. Expected: PASS.
- [ ] **Step 6: Commit** `feat(recipes): Describe how each check's findings read`

### Task 3: The ratchet

**Files:**
- Create: `project-files/checks/ratchet.py`, `tests/test_ratchet.py`
- Modify: `src/alpha/generate.py` (`_copies` already copies `checks/*.py`; nothing to add), `src/alpha/recipe_cli.py` (`try_recipe` parses baseline output)

**Interfaces:**
- CLI: `python3 ratchet.py <id> [--file <path>] [--capture]`. The cwd is anything inside the repo: the script finds the root the way `_common.project_root` does (the nearest `.git` with `docs/principles.toml` beside it).
- Exit codes: 0 pass, 1 findings or a stale baseline, 2 a usage or setup problem (no entry, no baseline file, unreadable output).
- Module functions, for tests and the kit: `parse(output, pattern, root, cwd) -> dict[str, dict[str, int]]`, `compare(current, baseline, only_file=None) -> Verdict` where `Verdict = (grown: list[tuple[str, str, int, int]], shrunk: ...)`, `baseline_path(root, id) -> Path`.

- [ ] **Step 1: Write the failing tests** (fast; the commands are `printf` scripts and `sh -c 'printf …; exit 1'`, in a temp repo with a minimal `docs/principles.toml` holding a `[[baselines]]` entry):
  - `test_new_finding_fails`: baseline `{a.py: {E1: 1}}`, output with two E1 in a.py. Exit 1; the message quotes both output lines for `a.py`/E1, says "1 more than the baseline", and says to fix them or record a decision.
  - `test_same_findings_pass`
  - `test_fewer_tightens_locally`: output with zero findings and exit 0. Exit 0, and the file now holds `{}`.
  - `test_frozen_fails_on_stale`: same with `CI=true`. Exit 1, the file is unchanged, and the message names `alpha baseline tighten` and "commit".
  - `test_grown_and_shrunk_does_not_tighten`: one rule up, another down. Exit 1, file unchanged.
  - `test_unparsed_failure_fails_closed`: exit 1 with output that doesn't match. Exit 2, with "can't read the output" and the last 40 lines.
  - `test_paths_normalize_to_root`: absolute path, `./a.py` and component-relative `a.py` with `dir = "api"` all count as `api/a.py`.
  - `test_missing_rule_counts_as_dash`
  - `test_file_mode_compares_one_file`: `--file api/a.py` runs `file_command` with the quoted file and ignores other files' entries. It tightens only that file's entries.
  - `test_capture_writes_counts`: `--capture` writes the current counts, sorted, and exits 0.
  - `test_missing_baseline_names_capture` (B7)
  - `test_unknown_id_names_known`
  - `test_old_python_fails_helpfully`: it parses on 3.9 (extend `test_hooks_parse_and_import_on_python_3_9` in `tests/hooks/test_common.py` to cover `project-files/checks/ratchet.py`). On a python3 older than the hooks need, it exits 2 with `_common.python_problem()`'s message. A check must fail, not skip, so it uses `check_python(fail_code=2)` rather than the session hooks' 0, and imports `tomllib` lazily as `_common.load_principles` does.
- [ ] **Step 2: Run** `uv run pytest tests/test_ratchet.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `ratchet.py`. It runs the command with `shell=True` and `cwd=root/dir`, stdout and stderr merged, with a 600 s timeout. A timeout exits 2 with the command and how to run it by hand. It writes JSON with `indent=2`, `sort_keys=True` and a trailing newline.
- [ ] **Step 4: `recipe try` parses baselines.** For each `[baseline.<step>]` in a drafted recipe, `try_recipe` runs its command in the scratch folder too. A non-zero exit whose output the pattern doesn't parse fails the proof with the same "can't read the output" message. A clean exit passes.
- [ ] **Step 5: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 6: Commit** `feat(hooks): Add a ratchet for baselined checks`

### Task 4: Switch baselines on from the answers

**Files:**
- Modify: `src/alpha/answers.py` (`_TOP_KEYS` gains `adoption`; `Answers.baselines: tuple[str, ...]`), `src/alpha/principles.py`, `src/alpha/repo_checks.py`
- Test: `tests/test_answers.py`, `tests/test_principles.py`, `tests/test_render_tooling.py`, `tests/test_render_ci.py`

**Interfaces:**
- Answers: `"adoption": {"baselines": ["typecheck:api", "typos"]}`. Plans 3 to 5 add more keys to `adoption`, so unknown keys inside it are refused for now with "unknown key".
- Principles file:
  - `[[baselines]]` entries (B1).
  - The component's `commands[step]` becomes `python3 <rel>/.claude/alpha/checks/ratchet.py <id>`, where `<rel>` is `os.path.relpath(".", c.path)` (empty for `.`). `lint_file` becomes the same with ` --file {file}`, and the ratchet maps the component-relative file to the root.
  - `protected.paths` gains `.claude/alpha/baselines/**`, and `review.risk_paths` gains the same.
- `RepoCheck.command` for a baselined repo check becomes `python3 .claude/alpha/checks/ratchet.py <id>`. Only `mise.toml` carries it, so CI and the Stop hook (through `mise run check:<id>`) follow.
- `repo_checks(...)` appends `RepoCheck("baselines", None, "python3 .claude/alpha/checks/diff_checks.py baselines", (), False, "pr", "Baselines only shrink")` when the list is non-empty. Task 5 implements the subcommand.

- [ ] **Step 1: Write the failing tests:**
  - `test_no_baselines_renders_as_before`: for each scenario in `evals/scenarios/`, `render_project` texts with `adoption` absent equal those with `adoption: {"baselines": []}`, and both equal today's.
  - `test_baselined_step_is_wrapped`: web+API scenario with `["typecheck:api", "lint:web"]`. The principles file's `api` typecheck command is `python3 ../.claude/alpha/checks/ratchet.py typecheck:api`. `[[baselines]]` holds the recipe's machine command and pattern with `dir = "api"`. `web`'s `lint_file` ends with `--file {file}`. The CI job and the `check:component:*` task show the wrapped commands.
  - `test_root_component_wrap`: ML single (`.`) gives `python3 .claude/alpha/checks/ratchet.py typecheck:<name>`.
  - `test_baselined_repo_check`: `["typos"]` makes the `check:typos` task run the ratchet, adds the `baselines` check to `ci`, and protects and risk-lists the folder.
  - `test_refused_baselines`: `format_check:api`, `secrets`, `nope:api`, `typecheck:ghost` and a step whose recipe has no `[baseline.<step>]` each fail `answers check`, naming `adoption.baselines[i]` and the reason (B6, the known ids, or "the <stack> recipe has no [baseline.typecheck]").
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Validation lives in `answers.py` next to the other cross-field checks (it needs the recipe book and the repo-check ids). `build_principles` does the wrapping in one helper used for both commands and repo checks.
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS, with no snapshot changes.
- [ ] **Step 5: Commit** `feat: Run baselined checks through the ratchet`

### Task 5: Baselines only shrink in a pull request

**Files:** Modify `project-files/checks/diff_checks.py`. Test: `tests/checks/test_diff_checks.py`.

- [ ] **Step 1: Write the failing tests** (temp git repo, `ALPHA_BASE` set to the base commit):
  - `test_growth_needs_a_decision`: a PR that raises a count, adds a rule, or adds a file entry fails. It names the check, file, rule and both counts, and says to add an accepted decision record naming the check id. With such a record added in the PR, it passes. A record that names the check but says `Status: proposed` still fails.
  - `test_new_baseline_file_needs_a_decision`: a whole new baseline file counts as growth from zero.
  - `test_shrink_passes`, `test_deleted_baseline_passes`
  - `test_no_base_skips` (reuses `resolve_base`)
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** `baselines`. It reads each baseline JSON at the base (`git show <base>:<path>`) and at HEAD, and compares counts. It takes the decision files the PR added from `changes(base)` (status `A` under `docs/decisions/`), then reads their `Status:` line and text. Read the record format in `src/alpha/render/docs.py` first, to match the real `Status:` header.
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hooks): Fail a pull request that grows a baseline`

### Task 6: Hooks

**Files:** Modify `project-files/hooks/_common.py` (`protected_message`). Test: `tests/hooks/test_post_edit.py`, `tests/hooks/test_guard_paths.py`, `tests/hooks/test_stop_checks.py`.

The wrapping in Task 4 already runs `post_edit` and Stop through the ratchet. This task pins that down and fixes the messages.

- [ ] **Step 1: Write the failing tests:**
  - `test_post_edit_allows_legacy_findings`: in a project with `lint:<c>` baselined and a legacy finding in the edited file (in the baseline), an edit that adds no finding passes. One that adds a finding blocks, quoting the new line.
  - `test_stop_typecheck_through_ratchet`: Stop with a baselined typecheck passes on legacy errors and blocks on a new one, with the ratchet's message.
  - `test_baseline_edit_is_blocked`: `Write` to `.claude/alpha/baselines/typecheck.api.json` is blocked. The message says baselines shrink by themselves when the checks run, and that growth needs a decision record and `alpha baseline capture`.
- [ ] **Step 2: Run them.** Expected: FAIL on the message test, and pass or fail on the others depending on Task 4. Fix what fails.
- [ ] **Step 3: Implement** the message branch in `protected_message`, keyed on the `.claude/alpha/baselines/` prefix. That's a path alpha owns, not a stack branch.
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hooks): Explain how baselines change`

### Task 7: `alpha baseline`

**Files:**
- Create: `src/alpha/baseline.py`, `tests/test_baseline.py`
- Modify: `src/alpha/cli.py`, `src/alpha/generate.py` (`bootstrap`)

**Interfaces:**
- `alpha baseline show <target> [--json]` prints one line per check: id, total, then the top rules with counts, plus a per-component total. It reads only the baseline files and `[[baselines]]`, so it runs no tools.
- `alpha baseline capture <target> --check <id> [--decision <NNNN>]` runs the project's own `ratchet.py <id> --capture`. With an existing baseline that the capture would grow, it needs `--decision`, naming a record in `docs/decisions/` that names the id. Otherwise it refuses with that instruction. This is a convenience: Task 5's check is the gate.
- `alpha baseline capture <target> --all`: every listed id that has no file yet. Plan 4's install step uses it.
- `alpha baseline tighten <target>` runs `ratchet.py <id>` locally for every id and reports which files changed and should be committed.
- `bootstrap`: before running a component's commands, a listed id with no baseline file stops with B7's message, before any slow step.

- [ ] **Step 1: Write the failing tests:**
  - `test_show_counts`
  - `test_capture_all_creates_missing_only`
  - `test_capture_growth_needs_decision`
  - `test_tighten_reports_changed`
  - `test_bootstrap_names_missing_baseline`
  - CLI exit codes: 0 ok, 1 a refusal with its fix, 3 a setup error, matching the other subcommands.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Add alpha baseline show, capture and tighten`

### Task 8: End to end, and the docs

**Files:** Create `tests/test_baseline_slow.py`. Modify `CLAUDE.md` (Dev commands: `alpha baseline`).

- [ ] **Step 1: Write the slow test.** For the web+API and ML scenarios:
  - Generate from the scenario with `adoption.baselines` set to every component's lint, typecheck and test steps plus `typos` and `markdown`. Add a legacy source file per component with one lint error and one type error, a failing test, a typo and a Markdown violation. Use `seeded.py`'s seeds where they fit.
  - Run `alpha baseline capture --all`, then `bootstrap` and `commit-skeleton`. Expect green, and `mise run ci` exits 0.
  - Add a second type error. `mise run check:component:<c>` fails, naming it.
  - Fix the first legacy error. `alpha baseline tighten` changes the file. Under `CI=true` before tightening, the check fails as stale.
  - On a branch that raises a count, `ALPHA_BASE=main mise run check:baselines` fails. Adding an accepted record naming the id makes it pass.
- [ ] **Step 2: Run** `uv run pytest -m slow tests/test_baseline_slow.py`. Expected: PASS.
- [ ] **Step 3:** In CLAUDE.md, add one Dev-commands bullet for `alpha baseline show|capture|tighten`, and note that baselines exist only for adopted projects (spec §8b).
- [ ] **Step 4: Run** `mise run check`. Expected: PASS.
- [ ] **Step 5: Commit** `test: Prove baselines end to end`
