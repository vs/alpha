# Adoption plan

alpha adopted this repo. These steps bring its code up to the principles in [principles.toml](principles.toml), phase by phase. Run `/alpha:install` to pick up the next one: each step gets a branch of its own, and it's done only when everything under its *Done when* holds.

## Progress

| Phase | Done | Steps |
| --- | --- | --- |
| P2 Close tool gaps | 0 | 1 |
| P4 Rework | 0 | 13 |
| P6 Traceability | 0 | 1 |

## P2 Close tool gaps

| Step | Component | Status |
| --- | --- | --- |
| `p2-ci-green` | alpha | pending |

### `p2-ci-green`: Get the generated CI green on main

The repo had no CI, so nothing ran the checks on a push or pull request. alpha generates .github/workflows/ci.yml; it must pass on GitHub.

Serves `build-hosting-upfront`.

Done when:

- `test -f .github/workflows/ci.yml && gh run list --workflow ci.yml --branch main --limit 1 --json conclusion --jq ".[0].conclusion" | grep -qx success` passes

## P4 Rework

| Step | Component | Status |
| --- | --- | --- |
| `p4-name-bad-file-in-errors` | alpha | pending |
| `p4-messages-name-real-commands` | alpha | pending |
| `p4-guard-fails-closed` | alpha | pending |
| `p4-merge-gate-fails-closed` | alpha | pending |
| `p4-run-slow-suite-in-ci` | alpha | pending |
| `p4-pin-python-and-uv` | alpha | pending |
| `p4-test-min-python` | alpha | pending |
| `p4-record-test-skips` | alpha | pending |
| `p4-narrow-optionals-in-tests` | alpha | pending |
| `p4-one-git-runner` | alpha | pending |
| `p4-parse-project-json-once` | alpha | pending |
| `p4-log-dev-dependencies` | alpha | pending |
| `p4-readme-python-requirement` | alpha | pending |

### `p4-name-bad-file-in-errors`: Name the real file in a decode error

cli._project reports every ValueError as a principles.toml problem, so a non-UTF-8 README makes apply blame a file that does not exist (src/alpha/cli.py:517, src/alpha/apply.py:84).

Serves `fail-helpfully`.

Done when:

- `uv run pytest tests/integration/test_adopt.py::test_a_non_utf8_repo_file_is_named_in_the_error` passes

### `p4-messages-name-real-commands`: Name only alpha commands that exist in messages

recipe try tells the user to run alpha adopt apply, which is not a command (src/alpha/recipe_cli.py:276).

Serves `fail-helpfully`.

Done when:

- `uv run pytest tests/unit/test_kit.py::test_every_alpha_command_named_in_a_message_exists` passes

### `p4-guard-fails-closed`: Block commands the guard cannot parse

split_segments returns None on a shlex error and check_command then checks nothing, so --no-verify after an ANSI-C quoted word passes (project-files/hooks/guard_bash.py:89, 252).

Serves `fail-helpfully`, `never-weaken-checks`.

Done when:

- `uv run pytest tests/integration/hooks/test_guard_bash.py::test_no_verify_after_an_ansi_c_quoted_word_is_blocked` passes

### `p4-merge-gate-fails-closed`: Block a merge when gh cannot report the PR head

pr_head returns None when gh fails or times out and check_merge then skips the head comparison R9.2 requires (project-files/hooks/guard_bash.py:492-527).

Serves `timeouts`.

Done when:

- `uv run pytest tests/integration/hooks/test_worktrees.py::test_merge_is_blocked_when_gh_cannot_report_the_pr_head` passes

### `p4-run-slow-suite-in-ci`: Run the end-to-end suite in CI

addopts deselects slow tests and nothing else runs them, so the tests behind R1.1, R1.3, R3.3 and R12.2 run only by hand (pyproject.toml:12).

Serves `tests-first-class`.

Done when:

- `grep -Rq "pytest -m slow" .github/workflows/` passes

### `p4-pin-python-and-uv`: Pin Python and uv in mise.toml

mise install installs only typos, rumdl and agnix, and no Python is pinned, so the documented setup fails without uv and tests run on whatever Python uv picks (mise.toml:6-9).

Serves `one-command`, `reproducible`.

Done when:

- `grep -q "^python = " mise.toml && grep -q "^uv = " mise.toml` passes

### `p4-test-min-python`: Run the Python 3.11 test without skipping

The only test of the 3.11 minimum skips when python3.11 is not on PATH, so newer syntax passes every check (tests/end-to-end/test_cli.py:36-39).

Serves `tests-first-class`. After `p4-pin-python-and-uv`.

Done when:

- `out=$(uv run --python 3.11 pytest -q -rs tests/end-to-end/test_cli.py) && ! printf %s "$out" | grep -q SKIPPED` passes

### `p4-record-test-skips`: Record each tool-dependent skip as an exception

Six tests skip when a tool is missing, with no row in an Exceptions table, so a runner without them gets a green run that proves less.

Serves `never-weaken-checks`.

Done when:

- `for f in test_pyguard.py test_session_start.py test_render_tooling.py test_defaults.py test_bootstrap_slow.py test_cli.py; do grep -q "$f" CONTRIBUTING.md || exit 1; done` passes

### `p4-narrow-optionals-in-tests`: Narrow Optionals instead of ignoring pyright

Six type: ignore[union-attr] and one pyright: ignore silence strict pyright in tests with no recorded reason (tests/unit/test_core_areas.py:543-578, tests/integration/test_render_tooling.py:80).

Serves `never-weaken-checks`.

Done when:

- `! grep -rnE "type: ignore|pyright: ignore" tests && uv run pyright` passes

### `p4-one-git-runner`: Share one timed git runner in src

gitops, adopt, rendered, purge and status each wrap git with their own timeout and error wording, and fixes such as core.quotepath reach only one.

Serves `lean-structure`.

Done when:

- `test $(grep -rnE "^def (_git|run_git|git_output)[(]" src/alpha | wc -l) -le 1 && uv run pytest -q` passes

### `p4-parse-project-json-once`: Read project.json only through answers.py

adopt, status, recipe_cli, apply and generate each re-parse project.json and dig through raw dicts, though the spec says it is parsed once at the boundary into frozen dataclasses.

Serves `validate-at-edges`.

Done when:

- `test $(grep -rnE "PROJECT_JSON[)][.]read_text|json[.]loads[(]path[.]read_text" src/alpha | grep -v answers.py | wc -l) -le 1 && uv run pytest -q` passes

### `p4-log-dev-dependencies`: Log a reason for each dev dependency

deptry, pyright, pytest, pytest-xdist, pyyaml, ruff and types-pyyaml have no recorded reason; the dependency log starts empty.

Serves `dependency-reasons`.

Done when:

- `for d in deptry pyright pytest pytest-xdist pyyaml ruff types-pyyaml; do grep -q "$d" docs/alpha/dependencies.md || exit 1; done` passes

### `p4-readme-python-requirement`: Say in the README that alpha needs Python 3.11

bin/alpha refuses to run below Python 3.11, but the README Needs section lists only uv, pnpm, rustup and mise.

Serves `docs-with-code`.

Done when:

- `grep -q "Python 3.11" README.md` passes

## P6 Traceability

| Step | Component | Status |
| --- | --- | --- |
| `p6-r9-2-pr-head-test` | alpha | pending |

### `p6-r9-2-pr-head-test`: Test R9.2 through the command guard

No test asserts that gh pr merge is blocked while the PR head on GitHub differs from local HEAD; the only R9.2 test calls review.gate directly.

Serves `tests-first-class`.

Done when:

- `uv run pytest tests/integration/hooks/test_worktrees.py::test_R9_2_a_pr_head_that_differs_from_local_head_blocks_the_merge` passes
