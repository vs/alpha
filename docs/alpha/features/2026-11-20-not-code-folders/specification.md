# Not-code folders

Date: 2026-11-20
Status: approved by the user on 2026-11-20, built native
Serves: R17.1 in docs/specification.md, a new requirement this spec proposes (the user's yes to this spec adds it)
Research: research.md · Plan: plan.md

## Why

A project can hold files in a component's language that aren't its code: mental, a Rust project, keeps a sample Python app with deliberate bugs, its golden reference model, research scripts and parser fixtures. alpha treats such files as code: the reviewer holds them to every principle, the weaken guard blocks suppression comments in them, the docs rule counts them as behavior, and the survey offers them as components. A project needs to name folders that aren't code, so that alpha's code checks and review leave them alone.

## Requirements

| ID | Requirement | Acceptance check | Test |
|---|---|---|---|
| F1 | The components area takes a list of not-code folders, checked at the boundary. | Given `"not_code": ["examples/report-jobs", "docs/research/*/experiments"]`, when `alpha answers check` runs, then it prints ok; given `"/abs"`, `"../x"` or `""`, it fails naming `not_code[i]` and how to write a relative folder; given a folder that holds a component's folder or is one (`"model"`, `"."`), it fails naming that component. | `tests/unit/test_answers.py::test_R17_1_not_code_folders_are_checked` (unit) |
| F2 | The render carries the list to the hooks and tells Claude. | Given answers with `not_code`, then `docs/alpha/principles.toml` has a top-level `not_code` with those folders, and CLAUDE.md's Commands section and CONTRIBUTING.md's Components section each name them and say what still checks them (secrets and the repository's text checks); without `not_code`, neither doc mentions it. | `tests/unit/test_principles.py::test_R17_1_not_code_reaches_the_principles` (unit); `tests/unit/test_render_docs.py::test_R17_1_docs_name_the_not_code_folders` (unit) |
| F3 | An edit in a not-code folder isn't formatted or linted, even inside a component whose globs match it. | Given a Python component at the root and `not_code = ["examples"]`, when Claude edits `examples/app.py`, then post-edit runs neither `format_file` nor `lint_file`; an edit of `src/app.py` still runs both. | `tests/integration/hooks/test_post_edit.py::test_R17_1_a_not_code_file_is_left_alone` (integration) |
| F4 | At Stop, a not-code file needs no test or doc and runs no component check, but secrets are still found in it. | Given `not_code = ["examples"]` and a docs map over `examples/**`, when `examples/app.py` changes, then the Stop hook reports no missing test, no missing doc and runs no component command, and `stop_checks.py tests` runs no suite; given a secret added to it, the Stop hook still blocks. | `tests/integration/hooks/test_stop_checks.py::test_R17_1_not_code_needs_no_tests_or_docs` (integration); `tests/integration/hooks/test_stop_checks.py::test_R17_1_not_code_runs_no_test_suite` (integration); `tests/integration/hooks/test_stop_checks.py::test_R17_1_secrets_are_found_in_not_code` (integration) |
| F5 | The weaken guard lets a suppression comment into a not-code file. | Given `not_code = ["examples"]`, an Edit adding a lint suppression comment to `examples/app.py` passes; the same edit to `src/app.py` is blocked. | `tests/integration/hooks/test_guard_paths.py::test_R17_1_not_code_may_suppress_checks` (integration) |
| F6 | The review leaves not-code files out, and names them. | Given a branch that changes `src/app.py` and `examples/app.py` with `not_code = ["examples"]`, then the brief's changed files and diff hold only `src/app.py`, a "Not code (not reviewed)" section lists `examples/app.py`, and the principles chosen are those of the touched components only; given a branch that changes only `examples/app.py`, the merge gate asks for no review. | `tests/integration/hooks/test_review.py::test_R17_1_the_review_leaves_out_not_code` (integration) |
| F7 | The survey lists no component inside a not-code folder saved in the answers. | Given a repo with `pyproject.toml` at the root and in `examples/report-jobs/`, and an interview's `project.json` with `not_code = ["examples"]`, when `alpha adopt survey` runs, then it lists the root candidate only, and its source count leaves out `examples/`; without the answer, both are listed. | `tests/integration/test_adopt_survey.py::test_R17_1_the_survey_skips_not_code` (integration) |
| F8 | The components guide asks for not-code folders. | Given the components area guide, then it names `not_code`, asks whether the project holds examples, fixtures, reference data or research code that isn't its code, recommends listing a survey candidate that sits in such a folder, and says secrets are still scanned there. | `tests/unit/test_skills.py::test_R17_1_components_guide_asks_for_not_code` (unit) |

## Design

**Data shape.** `Answers.not_code: tuple[str, ...]`, default `()`, a field of the components area (`_COMPONENTS_FIELDS`, `_TOP_KEYS`), saved in `project.json` as `"not_code": [...]`. Each entry is a folder relative to the project root; `*` matches within one path segment (`docs/research/*/experiments`). `validate.relative` checks each entry, and a new check refuses an entry that matches a component's folder or one of its parents, since that would take a component's code out of every check.

**principles.toml.** `build_principles` writes `not_code = [...]` at the top level, as given. Components' `exclude_globs` don't change, so CLAUDE.md's per-component "Not checked" lines stay the recipe's.

**Hooks.** `_common.not_code(rel, principles) -> bool` matches `rel` against each folder and everything under it (`<folder>` and `<folder>/**`), with the existing segment matcher. It's called at the edges, before any tool runs, since a tool given a path explicitly ignores its own excludes (research.md):

- `post_edit.py`: exits before format and lint.
- `stop_checks.py`: `find_problems` drops not-code files before grouping by component (tests rule, docs rule, component commands); `components_to_test` drops them too. `secret_problems` and the repository checks still get every changed file.
- `guard_paths.py`: skips the weaken check for a not-code file; every other guard (protected paths, `.claude/alpha/`, the settings wiring) is unchanged.
- `review.py`: `brief` and `gate` split `files_to_review` into reviewable and not-code files. Not-code files leave the changed files, the diff and the principle choice; the brief lists them under `## Not code (not reviewed)`. A branch with only not-code changes needs no review.

**Survey.** `adopt.survey` reads `not_code` from the project's `project.json` when the interview has saved one (`read_project_json`), and drops tracked files under those folders before anything else, so neither the candidates nor the listed files hold them. A survey before the answer exists lists everything, as today.

**Docs.** CLAUDE.md's Commands section, after the component tables, and CONTRIBUTING.md's Components section get one line when `not_code` is set: "Not code: `examples/report-jobs/`, …: examples, fixtures and reference data. No format, lint, test or docs rule and no principles review applies there; the secrets scan and the repository's text checks (spelling, Markdown, links) still do." The components area guide asks for the list. `docs/specification.md` gets R17.1, the field in the Answers section, and the not-code behavior in Hooks and checks and Review.

**Failure paths.** A bad entry fails `answers check` with the field, the problem and the fix. A missing or unreadable `not_code` in principles.toml means an empty list, as the hooks treat every other missing key.

## Decisions

- One project-wide list honoured by the hooks, the reviewer and the survey; the kit recipes' tool configs aren't changed (the user, 2026-11-20). A folder inside a same-stack component still needs the tool's own exclude for CI, said in the guide.
- Not-code files leave the review and are listed in the brief, so a mislabeled folder stays visible (the user, 2026-11-20).
- Secrets and the repository's text checks keep reading not-code folders: secret scanners deliberately ignore such lists (research.md), and typos, Markdown and links already have their own excludes.
- The field lives in the components area, because it says what the components' code isn't; it's named `not_code` to say what it means rather than which checks it skips.
- An entry may not cover a component's folder: listing `model` would silently switch off every check for that component.

## Out of scope

- Writing the folders into the kit recipes' tool configs (ruff, pyright, coverage, tsconfig, biome and the rest).
- An extra step in a component's CI job, such as `uv sync` in report-jobs before mental's Rust tests (mental's Exceptions row): a separate gap.
- Updating mental itself: after a kit release, `/alpha:update not_code: examples/report-jobs, docs/research/*/experiments, extract/tests/fixtures` there.
- Changing what the weaken guard treats as code in files no component holds and no not-code folder lists, such as Markdown that quotes a suppression comment.
