# Adoption plan

alpha adopted this repo. These steps bring its code up to the principles in [principles.toml](principles.toml), phase by phase. Run `/alpha:adopt` to pick up the next one: each step gets a branch of its own, and it's done only when everything under its *Done when* holds.

## Progress

| Phase | Done | Steps |
| --- | --- | --- |
| P2 Close tool gaps | 4 | 4 |
| P4 Rework | 9 | 14 |
| P6 Traceability | 0 | 1 |

## P2 Close tool gaps

| Step | Component | Status |
| --- | --- | --- |
| `p2-ruff-rules-alpha` | alpha | done |
| `p2-pyright-strict-alpha` | alpha | done |
| `p2-structure-alpha` | alpha | done |
| `p2-coverage-alpha` | alpha | done |

### `p2-ruff-rules-alpha`: Turn on the kit ruff rules for alpha

ruff selects only E, F, I, UP and B; the kit also bans catch-all excepts (BLE), commented-out code (ERA), blanket or stale suppressions (PGH, RUF100), late imports (PLC0415) and raising bare Exception (TRY002).

Serves `never-weaken-checks`, `no-dead-code`.

Done when:

- `grep -qE "BLE.*ERA.*PGH.*RUF100.*PLC0415.*TRY002" pyproject.toml` passes
- `mise run check:component:alpha` passes

### `p2-pyright-strict-alpha`: Make pyright strict for tests and stale ignores

tests/ is checked in standard mode and an unneeded type: ignore goes unnoticed; the kit checks everything strictly and reports unnecessary ignores.

Serves `strict-types`, `never-weaken-checks`.

Done when:

- `grep -qE "typeCheckingMode = .strict." pyproject.toml` passes
- `grep -qE "reportUnnecessaryTypeIgnoreComment = .error." pyproject.toml` passes
- `mise run check:component:alpha` passes

### `p2-structure-alpha`: Add deptry as the structure check of alpha

Nothing checks for unused, missing or transitive dependencies; the kit runs deptry as the structure step.

Serves `dependency-reasons`, `lean-structure`.

Done when:

- the recipe sets alpha.commands.structure
- `mise run check:component:alpha` passes

### `p2-coverage-alpha`: Measure coverage of alpha's changed lines

Pull requests must cover 80% of the lines they change, but alpha's recipe has no coverage command.

Serves `tests-first-class`.

Done when:

- the recipe sets alpha.coverage

## P4 Rework

| Step | Component | Status |
| --- | --- | --- |
| `p4-guard-hook-bypasses` | alpha | done |
| `p4-relative-license-file` | alpha | done |
| `p4-subprocess-timeouts` | alpha | done |
| `p4-typed-principles` | alpha | pending |
| `p4-unreadable-project-json` | alpha | done |
| `p4-atomic-write-json` | alpha | done |
| `p4-one-git-status-parser` | alpha | done |
| `p4-suppression-reasons` | alpha | done |
| `p4-shortcuts-skip-strings` | alpha | done |
| `p4-betterleaks-nested-ignores` | alpha | pending |
| `p4-no-ci-wording` | alpha | done |
| `p4-tests-by-level` | alpha | pending |
| `p4-startup-budget-test` | alpha | pending |
| `p4-missing-releases` | - | pending |

### `p4-guard-hook-bypasses`: Block every way to skip the commit hooks

guard_bash matches only the exact --no-verify, so an abbreviated --no-verif, core.hooksPath set through GIT_CONFIG_* or git --config-env all commit past a failing commit-msg hook; this breaks R3.

Serves `never-weaken-checks`.

Done when:

- `uv run pytest -k "abbreviated_no_verify or env_hooks_path or config_env"` passes

### `p4-relative-license-file`: Keep license_file relative to the project

The identity skill says to save an absolute license_file path, which commits a machine path into project.json and breaks load_answers on every other clone.

Serves `reproducible`.

Done when:

- `uv run pytest -k test_license_file_must_be_relative_to_project_root` passes

### `p4-subprocess-timeouts`: Bound toolchain and check commands in time

About 30 of 45 subprocess calls (uv sync, pnpm install, mise install, cargo, a legacy test suite) have no timeout and capture output, so a prompt or a stalled download looks like a silent freeze; two comments justifying this are wrong.

Serves `timeouts`, `fail-helpfully`.

Done when:

- `uv run pytest -k "test_bootstrap_step_times_out_with_a_fix or test_run_condition_times_out"` passes

### `p4-typed-principles`: Parse principles.toml into typed data

load_project_principles returns raw TOML that 23 functions index as dict[str, Any]; a hand edit gives a traceback, and a blanket except KeyError names the wrong cause.

Serves `validate-at-edges`, `fail-helpfully`.

Done when:

- `uv run pytest -k test_bootstrap_rejects_malformed_principles_with_component_and_fix` passes

### `p4-unreadable-project-json`: Report an unreadable project.json

project_book swallows invalid JSON and bootstrap then says No recipe for stack; refresh_manifest returns silently, so file hashes go stale.

Serves `fail-helpfully`.

Done when:

- `uv run pytest -k test_bootstrap_names_unreadable_project_json` passes

### `p4-atomic-write-json`: Write project.json atomically everywhere

write_answers replaces project.json atomically, but write_json, used by generate, refresh_manifest, apply_update and adopt, writes in place, so an interrupted write can lose the answers.

Serves `fix-at-the-root`.

Done when:

- `uv run pytest -k test_write_json_keeps_old_file_when_write_fails` passes

### `p4-one-git-status-parser`: Keep one git status parser

adopt and update each parse git status --porcelain -z; adopt ignores the exit code, so a failed git status reads as a clean tree and apply can write over files. The default-branch lookup is also written three times.

Serves `lean-structure`, `fail-helpfully`.

Done when:

- `uv run pytest -k test_apply_refuses_when_git_status_fails` passes

### `p4-suppression-reasons`: Give every suppression a reason or a fix

src/ and project-files/ hold 17 type or pyright ignores and 15 noqa E402 comments with no reason or decision, which the kit blocks in generated projects.

Serves `never-weaken-checks`, `strict-types`.

Done when:

- `! grep -rnE "# (type: ignore|pyright: ignore|noqa)(\[[^]]*\]|: [A-Z0-9, ]+)?[[:space:]]*$" src project-files/hooks project-files/checks` passes

### `p4-shortcuts-skip-strings`: Stop the shortcuts check reading string literals

The shortcuts check matches # shortcut: anywhere on a line, so test fixtures that hold one in a string fail it; tests/checks/test_shortcuts.py now splits its fixtures to avoid that.

Serves `fix-at-the-root`.

Done when:

- `uv run pytest -k test_a_shortcut_inside_a_string_is_not_a_comment` passes

### `p4-betterleaks-nested-ignores`: Allowlist folders that nested gitignores skip

The generated .betterleaks.toml lists only the root .gitignore, so a folder ignored by its own .gitignore (here .superpowers/) is scanned; it was added to the allowlist by hand.

Serves `fix-at-the-root`, `no-secrets`.

Done when:

- `uv run pytest -k test_betterleaks_allowlist_covers_nested_gitignores` passes

### `p4-no-ci-wording`: Drop CI wording when CI is none

With build.ci none, the generated CLAUDE.md still says CI runs the same checks, and mise.toml says ci runs what CI runs on a pull request.

Serves `docs-with-code`.

Done when:

- `uv run pytest -k test_no_ci_wording_without_ci` passes

### `p4-tests-by-level`: Sort alpha tests into unit, integration, e2e

Tests sit flat in tests/ with slow ones marked by name; the testing answer puts each level under tests/<level>/.

Serves `tests-first-class`.

Done when:

- `test -d tests/unit && test -d tests/integration && test -d tests/end-to-end && ! ls tests/test_*.py` passes
- `uv run pytest` passes

### `p4-startup-budget-test`: Test the 200 ms startup budget

The performance answer holds bin/alpha to startup under 200 ms, measured by a timing test that does not exist yet.

Serves `perf-budgets`.

Done when:

- `uv run pytest -k startup_budget` passes

### `p4-missing-releases`: Publish the missing GitHub releases

The changelog is GitHub releases, but v0.2.0, v0.4.1 and v0.4.2 are tagged with no release notes.

Serves `docs-with-code`.

Done when:

- `gh release view v0.2.0 -R vs/alpha && gh release view v0.4.1 -R vs/alpha && gh release view v0.4.2 -R vs/alpha` passes

## P6 Traceability

| Step | Component | Status |
| --- | --- | --- |
| `p6-requirement-tests` | alpha | pending |

### `p6-requirement-tests`: Link R1-R7 to the tests that cover them

Few tests name a requirement id, so the acceptance checks of R1-R7 do not trace to tests.

Serves `tests-first-class`.

Done when:

- `for r in R1 R2 R3 R4 R5 R6 R7; do grep -rqw $r tests || exit 1; done` passes
