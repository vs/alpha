# Installing alpha onto an Existing Repo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** With a finished interview, alpha writes its files into an existing repo on a branch (spec §5b, step 5):
- It merges what the repo already has without losing a line of it.
- It numbers decision records after the repo's own.
- It leaves an existing git hook setup in charge.
- It captures the baselines, bootstraps green and commits in convention groups.

Afterwards the repo is an alpha project like any other: `alpha update` and `/alpha:extend` work on it. This is plan 3 of the adoption series, after `2026-11-11-alpha-baselines.md` and `2026-11-11-alpha-adopt-survey.md`. Next come the compliance plan (4), the skill (5) and the evals (6).

**Architecture:**
- `alpha adopt apply <target> [--dry-run]` reuses `alpha update`'s machinery with an empty "before" side:
  - It renders the project from the answers (`render_project`, plus `generate._copies`) and classifies each file against the disk with `merge.classify(path, None, after, disk)`.
  - A file the repo lacks is `new`. One it has with the same text is skipped. One it has differently is a `conflict`, with a proposal in `.claude/alpha/state/update/`, as `/alpha:extend` already handles.
  - Two files every repo has get mechanical merges instead: `.gitignore` (a union of lines) and `.claude/settings.json` (a JSON union).
- `apply` writes:
  - the files
  - a manifest that makes later `alpha update` runs work (`applied`, `records`, `added`, `files`, `generated_at`, plus `adopted_at`)
  - the update state, so `alpha commit-update` commits alpha's files in convention groups

  The answers' `adoption.git_hooks` decides whether alpha takes `core.hooksPath` (`"alpha"`) or leaves an existing hook manager in charge (`"chain"`). With `"chain"`, the plan model (plan 4) adds a step that wires alpha's `commit-msg` check into that manager. The session-start hook accepts either.
- Bootstrap runs with `--capture-baselines` (plan 1). Nothing in this plan edits app code, manifests or lockfiles.

**Tech Stack:** Python ≥ 3.11, git (`merge-file`, `worktree`, `switch`). Hooks: stdlib, parse on 3.9.

**Spec:** §5b, the flow's step 5, the git hooks paragraph and the refusals; §5a (the merge model); §8b.

## Decisions (the planner's calls)

- **I1 Branch.** `apply` refuses a dirty tree. On the default branch, it creates and switches to `alpha/adopt`. If that branch exists, it refuses and says to switch to it or delete it. On any other branch, it stays there: the user chose it.
- **I2 Only the empty "before" side changes.** The three-way merge, the proposals, the update state and `commit-update` are `alpha update`'s. A conflict on an existing file has an empty base, so its proposal shows the user's whole file and alpha's whole file. `/alpha:extend` step 5 already merges those by hand, keeping the user's side. The adopt skill (plan 5) does the same.
- **I3 Mechanical merges, by path.** These two paths are alpha's own outputs, not a stack branch.
  - `.gitignore`: the repo's lines first, then alpha's missing ones under `# alpha`.
  - `.claude/settings.json`: objects merge key by key, and lists are the repo's items followed by alpha's missing ones (compared as JSON). A scalar both sides set keeps the repo's value, and the change is listed as a note. If the repo's file isn't valid JSON, it becomes a conflict.
- **I4 Decision records follow the repo's.** `record_paths(a, taken=taken_numbers(target))`, as `update` already numbers them. Records in another folder (`docs/adr/`) are settled by the documentation area (plan 5). This plan only needs `taken_numbers` to read `docs/decisions/`.
- **I5 Git hooks.** The answers carry `adoption.git_hooks`:
  - `"alpha"`: `apply` sets `core.hooksPath` as `commit-skeleton` does. The skill recommends it when the survey found no hook manager and no `core.hooksPath`.
  - `"chain"`: `apply` leaves git's config alone. CONTRIBUTING then says the repo's hook manager must run `python3 .claude/alpha/githooks/commit-msg "$1"` from its commit-msg hook. The session-start hook is satisfied when the commit-msg hook in effect (under `core.hooksPath`, or `.git/hooks/`) mentions `.claude/alpha/githooks/commit-msg`; otherwise it warns with that line.
  - Without `adoption`, nothing changes.
- **I6 Adopted components are never "new components" to commit whole.** `commit-update` commits a new component's whole folder, which for an adopted one is the app. So `apply`'s update state lists no `new_components`. `bootstrap` runs every component anyway. For an adoption, `commit-update` uses `commit-skeleton`'s subjects ("Add …", not "Update …"). It also commits `.claude/alpha/baselines/` in the chore group, since capture writes it after `apply`.
- **I7 Review.** `apply` runs before the project's review hook exists, so nothing is absorbed. The adoption branch is review debt like any feature branch, and the principles reviewer looks at it before it reaches main (§9). This is deliberate.
- **I8 What can still fail at bootstrap.** Checks that can't be baselined (secrets, vulnerabilities, and the format check of a component whose `format_check` isn't `""`) fail bootstrap with their own fix. The skill (plan 5) shows these in the preview and resolves them with the user before installing. This plan doesn't soften them.

## Global Constraints

- Generated projects render byte for byte as today, and `alpha update` on a generated project behaves as today.
- alpha never deletes, moves or edits a file outside its own outputs. App files, manifests and lockfiles stay byte-identical through `apply` and `commit-update`. Bootstrap's setup commands may touch environment folders the repo ignores (`.venv`, `node_modules`).
- Stack-free code. Every refusal names the next step. Commits as CLAUDE.md says, each ending with this session's attribution lines. `uv run pytest`, ruff, pyright and `mise run check` pass after every task, with real-tool tests marked `@pytest.mark.slow`.

## Review Focus

1. **No user line is lost.** README, CLAUDE.md, CI and settings that the repo already has come out either merged with every original line, or untouched with a proposal beside them. Pinned by `test_apply_never_loses_a_repo_line` (Task 2), which checks that every line of every pre-existing file is in the file or its proposal.
2. **App code untouched.** `git diff <before>..alpha/adopt` lists only alpha's outputs, `.gitignore`, `.claude/**`, `docs/**`, `mise.toml` and tool configs. Pinned by the slow test (Task 6).
3. **Existing hooks keep working** with `"chain"`: `core.hooksPath` and `.git/hooks/` are unchanged. Pinned by `test_chain_leaves_git_hooks_alone` (Task 3).
4. **`alpha update` after adoption** finds nothing to change. A changed answer merges into the hand-merged README without a conflict. Pinned by `test_update_after_adoption` (Task 5).

---

## File Structure

```
src/alpha/merge.py              union_lines, merge_json (Task 1)
src/alpha/adopt.py              plan_adoption, apply_adoption, branch handling (Task 2)
src/alpha/answers.py            adoption.git_hooks (Task 3)
src/alpha/render/docs.py        CONTRIBUTING for chained hooks (Task 3)
project-files/hooks/session_start.py   accepts a chained commit-msg hook (Task 3)
src/alpha/gitops.py             commit_update for an adoption (Task 4)
src/alpha/update.py             refusal points to /alpha:adopt (Task 5)
src/alpha/cli.py                alpha adopt apply [--dry-run] (Task 2)
tests/test_merge.py, tests/test_adopt_apply.py, tests/test_adopt_slow.py   (new or extended)
```

---

### Task 1: Mechanical merges

**Files:** Modify `src/alpha/merge.py`. Test: `tests/test_merge.py`.

**Interfaces:**
- `union_lines(disk: str, alpha: str, header: str = "# alpha") -> str` keeps `disk` byte for byte. It appends `\n<header>\n` and alpha's lines that `disk` lacks, comparing stripped text and skipping blank lines, unless none are missing.
- `merge_json(disk: str, alpha: str) -> tuple[str, list[str]] | None` gives the merged text (`indent=2`, trailing newline) and notes such as `permissions.defaultMode: kept yours ("acceptEdits"), alpha's is "default"`. It returns None when `disk` isn't a JSON object.

- [ ] **Step 1: Write the failing tests:**
  - `test_union_lines_keeps_the_repo_and_adds_the_rest`
  - `test_union_lines_nothing_missing_is_unchanged`
  - `test_merge_json_unions_lists_and_objects`: Claude Code's `permissions.allow` and `deny` and the `hooks.Stop[]` entries are merged, with no duplicates.
  - `test_merge_json_keeps_repo_scalars_with_a_note`
  - `test_merge_json_invalid_repo_file`
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Merge alpha's gitignore and settings into a repo's`

### Task 2: `alpha adopt apply`

**Files:** Modify `src/alpha/adopt.py`, `src/alpha/update.py` (move what both need into small shared helpers there; don't duplicate), `src/alpha/cli.py`. Test: `tests/test_adopt_apply.py`.

**Interfaces:**
- `plan_adoption(target: Path, plugin_root: Path, source: Source, today: date) -> UpdatePlan`:
  - Refusals, each with its fix:
    - not a repo root, or no commits (reuse `adopt._repo`)
    - already alpha's (manifest)
    - answers not complete (`load_answers` with all areas; the message names the area, as `update` does)
    - no `adoption` key: "this is a new project's interview; run /alpha:new-project"
    - a dirty tree
  - `changes` cover every rendered text and every copied file:
    - `new`, `conflict` (with merge3's two-sided proposal), or `merge` for `.gitignore` and settings (I3)
    - unchanged files are left out
  - `groups` come from `commit_group`, `new_components` is `()` (I6), and `kit_changed` is False.
  - The `manifest` holds `kit_version`, `generated_at` and `adopted_at` (both today), `defaults` (as `generate` writes it), `applied`, `records` (I4) and `added` (every component today). `files` is filled in by apply.
- `apply_adoption(target, plan) -> list[str]` (notes):
  - I1's branch, then `update.apply_update`'s writes. The update state is marked `"kind": "adopt"`.
  - Copied files keep their mode: the git hook stays executable.
- CLI: `alpha adopt apply <target> [--dry-run]` prints `update.describe` and, on a dry run, `update.plan_diff`, plus the conflicts' proposal paths and the merge notes. Exit 1 on a refusal.

- [ ] **Step 1: Write the failing tests.** Each test builds a repo in `tmp_path` with code, README, `.gitignore`, `.github/workflows/ci.yml`, `.claude/settings.json` and `docs/decisions/0001-use-x.md`, committed, plus complete answers. The answers are the ML scenario adapted: an adopted recipe for the repo's component, `adoption: {"git_hooks": "alpha"}`.
  - `test_apply_dry_run_writes_nothing`: the tree is unchanged, and the output lists `new`, `merge` (`.gitignore`, `.claude/settings.json`) and `conflict` (README.md, ci.yml).
  - `test_apply_never_loses_a_repo_line`
  - `test_records_follow_the_repos`: the first new record is `docs/decisions/0002-…`.
  - `test_apply_makes_the_branch`: on main it creates `alpha/adopt`. An existing `alpha/adopt` is refused. On `feature`, it stays there.
  - `test_apply_refusals`: dirty, incomplete answers (naming the area), no `adoption`, already adopted.
  - `test_apply_writes_a_manifest_update_can_use`: `plan_update` on the result reports nothing to change.
  - `test_copied_hook_stays_executable`
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Install alpha onto an existing repo`

### Task 3: Leave an existing hook setup in charge

**Files:** Modify `src/alpha/answers.py` (`adoption.git_hooks`: `"alpha"` or `"chain"`, required when `adoption` has `survey` or is used by `apply`), `src/alpha/adopt.py` (`apply` sets `core.hooksPath` only for `"alpha"`), `src/alpha/render/docs.py` (CONTRIBUTING's one-time setup), `project-files/hooks/session_start.py`. Test: `tests/test_adopt_apply.py`, `tests/hooks/test_session_start.py`, `tests/test_render_docs.py`.

- [ ] **Step 1: Write the failing tests:**
  - `test_alpha_takes_the_hooks_path`
  - `test_chain_leaves_git_hooks_alone`: a repo with `core.hooksPath=.husky` and a `.git/hooks/pre-commit` keeps both after `apply`.
  - `test_contributing_says_how_to_chain`: the line names `python3 .claude/alpha/githooks/commit-msg "$1"`. A generated project's CONTRIBUTING is unchanged.
  - `test_session_start_accepts_a_chained_hook`: with `core.hooksPath=.husky` and `.husky/commit-msg` calling alpha's check, there's no warning. When it doesn't call it, the warning says to add the line. The current `alpha` behavior is unchanged.
  - `test_git_hooks_answer_validated`
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hooks): Chain to a repo's own git hooks`

### Task 4: Commit an adoption

**Files:** Modify `src/alpha/gitops.py`. Test: `tests/test_adopt_apply.py`.

- [ ] **Step 1: Write the failing tests:**
  - `test_commit_adoption_groups`: after `apply`, conflicts merged by hand and baselines captured, `commit-update` makes `docs: Add product brief, principles and decisions`, `chore: Add Claude Code settings and guardrails` (including the baselines and project.json), `build: Pin the repository's check tools` and `ci: …`, with the trailers. App files aren't in any commit, and the tree is clean.
  - `test_commit_update_unchanged_for_updates`: an ordinary update keeps its "Update …" subjects, and an absent baselines folder is skipped.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement** (`state.get("kind") == "adopt"` picks the subjects).
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Commit an adoption in convention groups`

### Task 5: An adopted project is an alpha project

**Files:** Modify `src/alpha/update.py` (the "no answers" refusal now says `/alpha:adopt` brings an existing repo in). Test: `tests/test_adopt_apply.py`, `tests/test_update.py`.

- [ ] **Step 1: Write the failing tests:**
  - `test_update_after_adoption`: after apply, hand merge and commit, `alpha update --dry-run` prints "nothing to change". Changing `releases.changelog` adds CHANGELOG.md and merges the README cleanly, keeping the user's lines.
  - `test_update_refusal_points_to_adopt`
- [ ] **Step 2: Run** them. Expected: FAIL (the refusal), PASS (the update), or fix what fails.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Point alpha update at adopt for other repos`

### Task 6: End to end

**Files:** Create `tests/test_adopt_slow.py`. Modify `CLAUDE.md`.

- [ ] **Step 1: Write the slow test.** Use plan 2's slow repo (uv service with mypy, black, pytest, legacy type errors and a failing test), plus a README, a `.gitignore`, a GitHub workflow and `docs/decisions/0001-*.md`. Write complete answers with:
  - the adopted `svc-python` recipe
  - `adoption.baselines` `["typecheck:svc", "test:svc"]`
  - `adoption.git_hooks` `"alpha"`

  Then:
  1. `adopt apply`, then resolve each conflict by writing the proposal's two sides, user first. That's a mechanical stand-in for Claude's hand merge.
  2. `bootstrap --capture-baselines`, then `commit-update` with a trailer.
  3. Expect:
     - `git diff main..alpha/adopt --stat` touches no file under `svc/`
     - every app file is byte-identical
     - `mise run ci` exits 0
     - a new type error fails `mise run check:component:svc`
     - `alpha update --dry-run` prints "nothing to change"
     - the first alpha record is 0002
- [ ] **Step 2: Run** `uv run pytest -m slow tests/test_adopt_slow.py`. Expected: PASS.
- [ ] **Step 3:** In CLAUDE.md, add a bullet for `alpha adopt apply`.
- [ ] **Step 4: Run** `mise run check`. Expected: PASS.
- [ ] **Step 5: Commit** `test: Adopt a real repo end to end`
