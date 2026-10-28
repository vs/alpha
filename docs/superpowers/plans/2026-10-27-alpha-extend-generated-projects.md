# Alpha Extend Generated Projects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Area skills work on a project alpha generated (spec §5a). The user can add, remove, rename or move a component, switch on an area that didn't apply, or revisit an area's decisions. Only that area is re-asked, plus every area the change leaves incomplete. The result is merged into alpha's files without losing the user's edits, shown before writing, recorded as a decision and committed by the convention.

**Architecture:** Since generation, the manifest keeps the answers the project was generated from (`applied`), the paths of its decision records (`records`), and the date each component was added (`added`). `alpha update` renders the project twice with the current kit: once from the applied answers ("before") and once from the current answers ("after"). It then merges the before→after change into each file on disk with `git merge-file`. So only the effect of the changed answers lands. A newer kit's own changes, and the user's edits, stay as they are. A conflict leaves the file alone and writes a proposal with both sides marked, for Claude to merge with the user. Decision records are append-only history: new ones get the next free number on disk. `alpha bootstrap --component` sets up only the new components. `alpha commit-update` commits only what alpha changed, in convention groups, and marks alpha's changes as reviewed. A new `alpha:extend` skill drives the loop. Every area skill hands a generated project to it.

**Tech Stack:** Python ≥ 3.11 stdlib runtime (hooks parse on 3.9); git (`merge-file`, `status`); pytest, ruff, pyright.

**Spec:** `docs/superpowers/specs/2026-10-19-project-kit-design.md` §5a; also §7 (decision records), §11 ("Existing projects never change when kit defaults change"), §15 (re-syncing with newer kit defaults is later).

**Plan series:** 2e, after 2c and the deferred-minors pass. Then plan 4 (evals).

## Global Constraints

- §5a verbatim: "Merge into the kit-owned files (principles file, CLAUDE.md, docs, settings, hooks, configs). **Never overwrite the user's edits.** Show the proposed changes and confirm before writing." / "Record a decision record for the change, and commit per the convention." / "Never create or modify app code. Wiring a new component's test runner and configs is in scope; writing its code is not." / "On a folder the kit didn't generate, refuse and explain that existing projects are out of scope for v1."
- Only the change in answers lands. Rendering the applied answers and the current answers with the same kit cancels out every kit difference (§11; re-syncing is §15, later).
- alpha never deletes or moves a file in an update. Files it no longer generates are listed for the user, and a moved component's files are moved by the user (that's app code).
- Copied files (hooks, the project's skills and agents, the git hook) are not part of an update: they don't depend on the answers.
- Decision records are history. An earlier entry of `decisions` or `overrides` must not change. Existing record files are never renamed or renumbered.
- Stack-free: no stack, tool or component name is branched on in code.
- Every refusal says what to do next (fail helpfully). Hooks: stdlib only, parse on Python 3.9.
- A freshly generated project is byte-for-byte what it is today, apart from the three new manifest keys.

## Review Focus

1. **A user edit near alpha's change in CLAUDE.md or docs/principles.toml.** The edit is never lost: either a clean merge, or the file stays as it is with a proposal beside it. (Task 4: `test_user_edits_stay_and_the_change_lands`, `test_overlapping_edit_leaves_the_file_and_writes_a_proposal`.)
2. **Decision records written after generation** (by the project's decision skill, e.g. 0014 for accepted findings). New records are numbered after the highest number on disk. No existing record is renamed, and old overrides keep their `override_decision`. (Task 2: `test_known_paths_stay_and_new_ones_follow_the_highest_number`; Task 4: `test_new_decision_is_numbered_after_the_projects_own_records`.)
3. **Uncommitted work.** If a file alpha would change has uncommitted changes, the update is refused and names the file. Unrelated untracked files are left alone and stay out of the commits. (Task 4: `test_uncommitted_change_in_a_file_alpha_changes_is_refused`; Task 5: `test_commit_update_commits_only_alphas_files_in_groups`.)
4. **Adding a component.** Each per-component area is named in turn until it covers the component. The component gets its templates, its CI job and dependency rows dated today. Only it is bootstrapped, and it gets its own build commit. (Task 1: `test_area_of_maps_fields_to_their_area`; Task 4: `test_invalid_answers_name_the_area_to_revisit`, `test_added_component_gets_templates_ci_and_dated_rows`; Task 5.)
5. **A component moved to another folder** (the spec's example: a CLI at the root gains a UI, so the CLI moves to `cli/`). The update is refused until the user has moved the files. After that, alpha merges against the old files instead of reporting conflicts. (Task 4: `test_moved_component_waits_for_its_files`, `test_moved_component_merges_against_its_old_files`.)

---

## File Structure

```
src/alpha/validate.py        AnswersError.where; area_of
src/alpha/answers.py         parse_answers, answers_snapshot
src/alpha/records.py         NEW: Records, record_paths, taken_numbers
src/alpha/principles.py      build_principles(records=); override_decision_paths removed
src/alpha/render/docs.py     render_docs(records=, added=)
src/alpha/generate.py        render_project (shared by generate and update); manifest applied/records/added; bootstrap(only=)
src/alpha/merge.py           NEW: merge3, Change, classify
src/alpha/update.py          NEW: plan_update, apply_update, describe, plan_diff
src/alpha/gitops.py          commit_update, commit_group; shared group committing
src/alpha/cli.py             update [--dry-run], bootstrap --component, commit-update
project-files/hooks/review.py   snapshot and absorb subcommands
skills/extend/SKILL.md       NEW
skills/*/SKILL.md            generated projects go to alpha:extend (17 areas + new-project)
tests/test_records.py, tests/test_merge.py, tests/test_update.py   NEW
```

---

### Task 1: Answers from data, and the area behind a problem

**Files:** Modify `src/alpha/validate.py`, `src/alpha/answers.py`. Test: `tests/test_answers.py`.

**Interfaces:**
- Produces: `AnswersError(message: str, where: str = "")`, with a `.where` attribute. `fail(where, problem, fix)` passes `where` on, and the message stays as it is today.
- Produces: `area_of(where: str) -> str | None` in `validate.py`. Its argument is the field path up to the first `.` or `[`. A name in `AREAS` maps to itself; `layout`, `components_talk`, `components` and `recipes` map to `"components"`. Anything else (`decisions`, `overrides`, `schema`, `input`, `""`) maps to `None`.
- Produces: `parse_answers(top: Mapping[str, Any], base: Path, require_areas: Sequence[str] = AREAS, generated: bool | None = None) -> Answers`. This is the body of `load_answers` after the file is read and parsed. `base` replaces `_project_root(path)`, and `generated=None` means `"manifest" in top`. `load_answers` keeps its signature and calls it.
- Produces: `answers_snapshot(top: Mapping[str, Any]) -> dict[str, Any]`, a deep copy without `"manifest"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_area_of_maps_fields_to_their_area():
    assert area_of("testing.components[1].levels") == "testing"
    assert area_of("agent_workflow.max_lines") == "agent_workflow"
    for where in ("layout", "components_talk", "components[0].path", "recipes.rust.commands"):
        assert area_of(where) == "components"
    for where in ("decisions", "overrides[0].principle", "schema", ""):
        assert area_of(where) is None

def test_fail_keeps_where():
    assert fail("ui.components", "is wrong", "Fix it").where == "ui.components"

def test_parse_answers_matches_load_answers(tmp_path):
    path = place_answers(tmp_path, "web-ts-plus-python-api")
    top = json.loads(path.read_text())
    assert parse_answers(top, tmp_path) == load_answers(path)

def test_snapshot_leaves_out_the_manifest():
    top = {"schema": 1, "manifest": {"files": {}}, "decisions": [{"area": "git"}]}
    snap = answers_snapshot(top)
    assert snap == {"schema": 1, "decisions": [{"area": "git"}]}
    snap["decisions"].append({})
    assert len(top["decisions"]) == 1
```

- [ ] **Step 2: Run them**: `uv run pytest tests/test_answers.py -k "area_of or keeps_where or parse_answers or snapshot" -v`. Expected: FAIL (ImportError).
- [ ] **Step 3: Implement** the four interfaces above. `AnswersError` errors raised without `fail` keep `where=""`.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit**: `refactor: Parse answers from data and name their area`

---

### Task 2: Stable decision record paths and dates

**Files:** Create `src/alpha/records.py`. Modify `src/alpha/principles.py`, `src/alpha/render/docs.py`, `src/alpha/generate.py`, `tests/helpers.py` (`override_record` reads the generated principles file or `record_paths`). Tests: `tests/test_records.py`, `tests/test_generate.py`, `tests/test_principles.py`.

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Records: decisions: tuple[str, ...]; overrides: tuple[str, ...]`. There is one path per `answers.decisions` and `answers.overrides` entry, by index. `Records.to_json() -> dict[str, list[str]]` and `Records.from_json(raw: object) -> Records | None` (`None` when malformed).
- Produces: `record_paths(a: Answers, known: Records | None = None, taken: Iterable[int] = ()) -> Records`. Entries covered by `known` keep their paths. New ones get numbers from `max(taken ∪ numbers in known ∪ {0}) + 1` upward, decisions before overrides. Paths are `docs/decisions/{n:04d}-{slug(title)}.md` and `docs/decisions/{n:04d}-override-{principle}.md`. With no `known` and no `taken`, this gives exactly today's numbering. Move `_slug` into `records.py` if `docs.py` is its only user, and import it back.
- Produces: `record_number(path: str) -> int` (the leading digits of the file name) and `taken_numbers(target: Path) -> set[int]` (the numbers of every `docs/decisions/[0-9][0-9][0-9][0-9]-*.md` on disk).
- Changes: `build_principles(defaults, a, kit_version, records: Records | None = None)`. `override_decision` comes from `records.overrides[i]`, and `None` means `record_paths(a)`. `override_decision_paths` is removed, and both of its uses in `docs.py` read `records.overrides` instead.
- Changes: `render_docs(a, principles, year, today, root=Path(), records: Records | None = None, added: Mapping[str, date] | None = None)`. Each record's number comes from its path and its date is `today`. A dependency row's date is `added.get(c.name, today)`.
- Produces: generate writes three more manifest keys: `"applied": answers_snapshot(data)`, `"records": record_paths(a).to_json()` and `"added": {name: today.isoformat()}` for every component.

- [ ] **Step 1: Write the failing tests**

```python
def test_fresh_numbering_matches_generation(tmp_path, generate_scenario):
    files = generate_scenario(tmp_path, "web-ts-plus-python-api")
    a = load_answers(tmp_path / PROJECT_JSON)
    r = record_paths(a)
    assert sorted([*r.decisions, *r.overrides]) == [f for f in files if f.startswith("docs/decisions/0")]

def test_known_paths_stay_and_new_ones_follow_the_highest_number():
    # a: 4 decisions, 2 overrides; known covers 3 decisions and 1 override (0004)
    r = record_paths(a, known=Records(("docs/decisions/0001-a.md", "docs/decisions/0002-b.md", "docs/decisions/0003-c.md"), ("docs/decisions/0004-override-x.md",)), taken={1, 2, 3, 4, 14})
    assert r.decisions[:3] == known.decisions and r.overrides[0] == known.overrides[0]
    assert record_number(r.decisions[3]) == 15 and record_number(r.overrides[1]) == 16

def test_dependency_rows_use_each_components_added_date(...):
    # render_docs with added={"api": date(2026, 10, 1)}: api rows end "| 2026-10-01 |"; web rows end with today

def test_generate_records_applied_answers_records_and_added(tmp_path, generate_scenario):
    generate_scenario(tmp_path, "web-ts-plus-python-api")
    data = json.loads((tmp_path / PROJECT_JSON).read_text())
    m = data["manifest"]
    assert m["applied"] == answers_snapshot(data)
    assert Records.from_json(m["records"]) == record_paths(load_answers(tmp_path / PROJECT_JSON))
    assert m["added"] == {"api": TODAY.isoformat(), "web": TODAY.isoformat()}
```

(Build `a` in the second test from the scenario, with one decision and one override appended. The test shows the shape; the implementer fills in the fixtures.)

- [ ] **Step 2: Run** `uv run pytest tests/test_records.py tests/test_generate.py -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the interfaces above.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass, and every existing generate and render test is unchanged.
- [ ] **Step 5: Commit**: `feat: Keep generated answers and record paths`

---

### Task 3: Three-way file merge

**Files:** Create `src/alpha/merge.py`. Test: `tests/test_merge.py`.

**Interfaces:**
- Produces: `merge3(base: str, ours: str, theirs: str) -> tuple[str, bool]`, returning `(text, conflicted)`. It runs `git merge-file -p --diff3 -L yours -L before -L alpha <ours> <base> <theirs>` on UTF-8 files in a `tempfile.TemporaryDirectory()`. Exit 0 means clean, exit > 0 means conflicts, and any other exit or an `OSError` raises `GenerateError` naming git and the fix ("Install git, then rerun …").
- Produces: `@dataclass(frozen=True) class Change: path: str; kind: str; text: str | None`, where `kind` is one of `"new" | "change" | "merge" | "conflict" | "stale" | "skipped"`.
- Produces: `classify(path: str, before: str | None, after: str | None, disk: str | None) -> Change | None`. `None` means no change.

| before | after | disk | result |
|---|---|---|---|
| None | text | None | `new`, text = after |
| None | text | == after | None |
| None | text | other | `merge3("", disk, after)` → `conflict` (it can't be clean) |
| x | == x | any | None |
| x | y ≠ x | None | `skipped` (the user deleted it), text None |
| x | y ≠ x | == x | `change`, text = y |
| x | y ≠ x | other | `merge3(x, disk, y)`: clean → `merge`, else `conflict`; text = the merge output |
| x | None | None | None |
| x | None | present | `stale`, text None |

- [ ] **Step 1: Write the failing tests**: `test_separate_edits_merge_cleanly` (ours edits line 1 and theirs edits line 5 of a 6-line text: both edits are in the result and `conflicted` is False); `test_same_line_conflicts_with_three_labels` (the output contains `<<<<<<< yours`, `||||||| before`, `=======` and `>>>>>>> alpha`); `test_untouched_file_takes_alphas_version`; `test_non_ascii_survives` (`"Grüße — ok\n"`); `test_missing_final_newline_survives`; plus one test per row of the table: `test_classify_<kind>` and `test_classify_no_change_cases`.
- [ ] **Step 2: Run** `uv run pytest tests/test_merge.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 3: Implement** `merge.py`.
- [ ] **Step 4: Run** `uv run pytest tests/test_merge.py -v`. Expected: PASS.
- [ ] **Step 5: Commit**: `feat: Merge alpha's changes into edited files`

---

### Task 4: `alpha update`

**Files:** Create `src/alpha/update.py`. Modify `src/alpha/generate.py`, `src/alpha/gitops.py` (`commit_group`), `src/alpha/cli.py`, `tests/helpers.py` (`generated_repo`, `clone_component`). Test: `tests/test_update.py`.

**Interfaces:**
- Consumes: Task 1 (`parse_answers`, `answers_snapshot`, `area_of`), Task 2 (`Records`, `record_paths`, `taken_numbers`, `render_docs`/`build_principles` keywords), Task 3 (`classify`, `Change`).
- Produces in `generate.py`: `@dataclass(frozen=True) class Rendered: principles: dict[str, Any]; texts: dict[str, str]; component_of: dict[str, str]`. `texts` holds every rendered file, component templates included, but no copies; `component_of` maps each template path to its component. `render_project(target: Path, a: Answers, defaults: dict[str, Any], year: int, today: date, records: Records | None = None, added: Mapping[str, date] | None = None) -> Rendered` holds today's render half of `generate`, including the template-collision error. `generate` calls it and keeps its output.
- Produces in `update.py`: `UPDATE_STATE = ".claude/alpha/state/update.json"` and `PROPOSALS = ".claude/alpha/state/update"`. `@dataclass(frozen=True) class UpdatePlan` has the fields `changes: tuple[Change, ...]` (sorted by path), `new_components: tuple[str, ...]`, `groups: dict[str, str]` (each changed path's commit group, from `commit_group`), `manifest: dict[str, Any]` (the manifest to write) and `answers: dict[str, Any]` (the full current file).
- Produces in `gitops.py`: `commit_group(path: str, component_of: Mapping[str, str]) -> str`. A template path gives `"build:<component>"`. `.github/workflows/…` (the `WORKFLOW` constant) gives `"ci"` and `DEPENDABOT` gives `"dependabot"`. `CLAUDE.md` and anything under `.claude/` give `"chore"`. Everything else gives `"docs"`.
- Produces: `plan_update(target: Path, source: Source, today: date) -> UpdatePlan`, `apply_update(target: Path, plan: UpdatePlan) -> None`, `describe(plan: UpdatePlan, target: Path) -> str` and `plan_diff(plan: UpdatePlan, target: Path) -> str` (a unified diff of disk → new text per new, change or merge file, labelled `a/<path>` and `b/<path>`).
- CLI: `alpha update <target> [--dry-run]`. With `--dry-run` it prints `describe` and then `plan_diff`, and writes nothing. Without it, it applies the plan and prints `describe`, followed by one line per conflict naming its proposal path. Errors exit 1 with the message, through `_project`'s existing handling.

`plan_update`, in order. Every refusal raises `GenerateError`:
1. No `<target>/.claude/alpha/project.json`: "`<target>` has no alpha answers, so alpha didn't generate it. alpha changes only projects it generated; bringing an existing project in is out of scope for this version."
2. No `manifest`: "`<target>` isn't generated yet. Finish the interview with /alpha:new-project."
3. No `manifest.applied`, or `records` doesn't parse: "`<target>` was generated before alpha kept the answers it generated from, so alpha can't tell your edits from its own changes. Updating it isn't supported."
4. The applied answers don't parse or render with this kit: "The answers `<target>` was generated from don't load with this alpha (<problem>). Updating a project generated by an older alpha isn't supported yet."
5. The current answers fail `parse_answers`. With `area_of(e.where)`: "Revisit the <area> area: <problem>". Without it: "Fix .claude/alpha/project.json: <problem>".
6. An entry of applied `decisions` or `overrides` differs from the current entry at the same index, or is missing: "decisions[<i>] changed since the project was generated. Decision records are history: put it back as it was, and add a new decision for the change instead."
7. A component in both (by name) whose `path` changed, while its new folder lacks any of the recipe's manifests on disk: "The <name> component moves from <old> to <new>. alpha doesn't move app code: move its files yourself (git mv), commit, then run this again."
8. Render "before" with the applied answers, `known=records`, the manifest's `added` and the generation year. Render "after" with the current answers, `record_paths(current, known=records, taken=taken_numbers(target))`, `added` plus today for each new component, and the same year. Both get `today`. For a moved component, look up each "after" template's `before` text by its path relative to the component, under the old path. Then `classify` every path in either render. Copies are never in either render.
9. If any path with a `new`, `change`, `merge` or `conflict` change shows in `git status --porcelain -- <paths>` (in a folder that isn't a git repository, say so and stop): "Commit or stash your changes to <paths> first: alpha merges its changes into the committed files."

`apply_update` writes each `new`, `change` and `merge` text. For each `conflict`, it writes `PROPOSALS/<path>` with the merge output and leaves the file as it is. It then sets the manifest: `applied` = the current snapshot, `records`, `added`, `updated_at` = today, and `files` = rehashes of every path in the old manifest or in the plan that exists. Finally it writes `UPDATE_STATE`: `{"before_tree": <review snapshot or null>, "groups": plan.groups, "new_components": [...], "conflicts": {path: sha256 of the file on disk}}`. The review snapshot comes from `python3 .claude/alpha/hooks/review.py snapshot` (Task 5) run in the target; a non-zero exit or a missing script means `null`.

`describe` output (tests assert these strings):

```
alpha update: nothing to change
```
```
alpha update: 4 files to change
  new       worker/pyproject.toml
  change    docs/principles.toml
  merge     CLAUDE.md (your edits kept)
  conflict  docs/dependencies.md (your edits overlap alpha's change: merge by hand)
  stale     CHANGELOG.md (alpha no longer generates it: delete it if you don't need it)
  skipped   docs/ui.md (you deleted it: alpha's change to it is left out)
New components: worker. Then run: alpha bootstrap <target> --component worker
```

(The count covers new, change, merge and conflict.)

Test helpers: `generated_repo(tmp_path, scenario) -> Path` generates the scenario, runs `git init` and `commit_skeleton`, and needs `git_env`. `clone_component(data, source, name, path)` copies the `source` entry into `components` and into every per-component area's `components` list under the new name and path (names only, keeping the rest), adds `name` to `git.scopes`, and sets `layout` to `monorepo`. Tests mutate project.json with `write_answers`, or with `json` directly where a test needs to.

- [ ] **Step 1: Write the failing tests** (`tests/test_update.py`; all use `today=date(2026, 11, 2)`):
  - `test_refuses_a_folder_alpha_did_not_generate` (empty folder: the message contains "out of scope").
  - `test_unfinished_interview_points_to_new_project` (a scenario placed without generating: "/alpha:new-project").
  - `test_refuses_a_project_without_applied_answers` (drop `manifest.applied`: "generated before alpha kept").
  - `test_commit_group_sorts_paths_by_what_made_them` (a template → `build:<name>`, the workflow → `ci`, the Dependabot file → `dependabot`, CLAUDE.md and `.claude/…` → `chore`, `docs/x.md` and `README.md` → `docs`).
  - `test_nothing_to_change_after_generation` (`plan.changes == ()`, and `describe` gives "alpha update: nothing to change").
  - `test_invalid_answers_name_the_area_to_revisit` (add `worker` to `components` only, with layout monorepo: the message starts "Revisit the architecture area:").
  - `test_changed_decision_is_refused` (edit `decisions[0].title`: "decisions[0] changed").
  - `test_user_edits_stay_and_the_change_lands`: commit an edit that adds the line "Team rule: ask before deploys." at the end of CLAUDE.md. Change `agent_workflow.max_lines` from the scenario's value to 120, and append a decision. After `apply_update`, `docs/principles.toml` has `max_lines = 120`, CLAUDE.md still ends with the team rule, and both appear as `change`/`merge`.
  - `test_new_decision_is_numbered_after_the_projects_own_records`: commit `docs/decisions/0020-use-sqlite.md` first. The appended decision's record is `docs/decisions/0021-<slug>.md`, dated 2026-11-02, and every earlier record file is byte-identical.
  - `test_overlapping_edit_leaves_the_file_and_writes_a_proposal`: commit a hand edit to the `max_lines` line in `docs/principles.toml`, then change `max_lines` in the answers. The file is unchanged, `PROPOSALS/docs/principles.toml` contains `<<<<<<< yours`, and `describe` says "merge by hand".
  - `test_uncommitted_change_in_a_file_alpha_changes_is_refused` (an uncommitted edit to CLAUDE.md, then a change that touches CLAUDE.md: the message names CLAUDE.md and "Commit or stash").
  - `test_stale_files_are_listed_not_deleted` (`releases.changelog` → `"none"` plus a decision: `CHANGELOG.md` is `stale` and still on disk).
  - `test_added_component_gets_templates_ci_and_dated_rows`: `clone_component(data, "api", "worker", "worker")` plus a components decision gives `plan.new_components == ("worker",)`. `worker/pyproject.toml` is `new`. The CI workflow is `change` and mentions `worker`. The docs/dependencies.md text has the worker rows ending "| 2026-11-02 |", while the api rows keep the generation date. `docs/principles.toml` lists the worker component.
  - `test_moved_component_waits_for_its_files` (the api path becomes `backend` in every area: the message contains "git mv").
  - `test_moved_component_merges_against_its_old_files`: after `git mv api backend` and a commit, no change is a `conflict`, and `backend/pyproject.toml` is neither `new` nor a `conflict`.
  - `test_applied_update_becomes_the_new_baseline`: after `apply_update`, a second `plan_update` gives "nothing to change", `manifest.applied` equals the current answers, and `UPDATE_STATE` exists.
  - `test_cli_dry_run_prints_changes_and_writes_nothing`: run through `run_cli("update", target, "--dry-run")`. It exits 0, stdout has "files to change" and a `--- a/docs/principles.toml` line, and the tree is unchanged (`git status --porcelain` is empty apart from project.json).
- [ ] **Step 2: Run** `uv run pytest tests/test_update.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 3: Implement** `render_project` (then run `uv run pytest tests/test_generate.py -q`: still green), followed by `update.py` and the CLI subcommand.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit**: `feat: Add alpha update for generated projects`

---

### Task 5: Bootstrap one component, commit the update, absorb review

**Files:** Modify `src/alpha/generate.py`, `src/alpha/gitops.py`, `src/alpha/cli.py`, `project-files/hooks/review.py`. Tests: `tests/test_generate.py`, `tests/test_update.py`, `tests/hooks/test_review.py`.

**Interfaces:**
- Changes: `bootstrap(target, principles, only: Sequence[str] = ())`. With `only`, just those components are bootstrapped. An unknown name raises `GenerateError`: "No component named <x> in docs/principles.toml (components: <names>)." The manifest refresh is unchanged. CLI: `alpha bootstrap <target> [--component NAME]...`.
- Consumes: `commit_group` (Task 4).
- Produces: `commit_update(target: Path, principles: dict[str, Any], trailers: list[str]) -> tuple[list[str], list[str]]`, returning `(hashes, notes)`. With no `UPDATE_STATE`, it raises `GenerateError`: "Nothing to commit: run alpha update <target> first." It checks the identity like `commit_skeleton`. Groups, in order:
  - `docs: Update docs and decision records`;
  - `chore: Update Claude Code rules and settings` (always with `.claude/alpha/project.json`);
  - per component, in principles order:
    - a new component commits its whole folder with `_build_subject(c, scopes)`;
    - an existing one commits only its changed templates as `build(<name>): Update toolchain settings`, unscoped `build: Update <name> toolchain settings` when the scope isn't allowed, and `build: Update toolchain settings` when that's over 50 characters;
  - `ci: Update the CI checks`;
  - `ci: Update the dependency update schedule`.
  
  The group-committing loop is shared with `commit_skeleton` (extract `_commit_groups(target, groups, trailers) -> list[str]`). A conflict whose file hash still equals the recorded one adds a note: "<path>: alpha's change wasn't merged in (proposal: .claude/alpha/state/update/<path>)." Then, when `before_tree` is set, it runs `python3 .claude/alpha/hooks/review.py absorb <before_tree>`. If that fails, or the script is missing, it adds the note: "The reviewer will look at alpha's changes at the next Stop." Last, it deletes `UPDATE_STATE` and `PROPOSALS`. CLI: `alpha commit-update <target> [--trailer T]...` prints the hashes, then the notes.
- Produces in `review.py`: the subcommand `snapshot`, which prints `snapshot(root)`, and `absorb <tree>`. `absorb(root: Path, before: str) -> None` carries the change between `before` and the current snapshot onto `reviewed_tree`. It uses the same `merge-tree` three-way merge as `absorb_outside_changes`, which now calls a shared helper: `_carry(root, state, left) -> None`. On a conflict, it absorbs nothing. `main` keeps `brief` and the usage message, adding both subcommands to it.

- [ ] **Step 1: Write the failing tests**:
  - `test_bootstrap_only_named_components` (the fake-tools pattern from `test_bootstrap_runs_bootstrap_setup_test_per_component`: only the named component's commands run).
  - `test_bootstrap_unknown_component_is_explained`.
  - `test_commit_update_commits_only_alphas_files_in_groups`: after `clone_component` for worker, `apply_update`, and an untracked `notes.txt`, the subjects of `git log --format=%s` since the skeleton are exactly `["docs: Update docs and decision records", "chore: Update Claude Code rules and settings", "build(worker): Set up python toolchain and tests", "ci: Update the CI checks"]`, oldest first. If the scenario has Dependabot, the dependabot subject comes last. `notes.txt` is still untracked, and `UPDATE_STATE` is gone.
  - `test_commit_update_without_an_update_is_explained`.
  - `test_commit_update_notes_unmerged_conflicts`.
  - `test_commit_update_absorbs_alphas_changes_into_review`: create the review state with `review.py snapshot` before the update, so `ensure_state` runs. After `commit_update`, `review.debt(root, principles)["files"] == []`.
  - In `tests/hooks/test_review.py`:
    - `test_absorb_carries_changes_since_the_tree_onto_reviewed`;
    - `test_absorb_keeps_earlier_unreviewed_edits` (an edit made before `before` stays debt);
    - `test_snapshot_subcommand_prints_the_tree`.
- [ ] **Step 2: Run** `uv run pytest tests/test_update.py tests/test_generate.py tests/hooks/test_review.py -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the interfaces above.
- [ ] **Step 4: Run** `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: all clean. Also run `python3.9 -m py_compile project-files/hooks/review.py` when a 3.9 interpreter exists (`old_python()`; the existing parse test covers it).
- [ ] **Step 5: Commit**: `feat: Commit alpha updates and skip their review`

---

### Task 6: The extend skill, and area skills that hand over to it

**Files:** Create `skills/extend/SKILL.md`. Modify the 17 area skills (the generated-project bullet and the description), `skills/new-project/SKILL.md` (§1 step 2) and `tests/test_skills.py` (add `"extend"` to `ALL_SKILLS`; new tests).

**Interfaces:**
- Consumes: the CLI from Tasks 4–5 (`update`, `update --dry-run`, `bootstrap --component`, `commit-update`). Also its message prefixes `Revisit the <area> area:` and `Fix .claude/alpha/project.json:`, and the proposal folder `.claude/alpha/state/update/`.
- Frontmatter: `name: extend`; `allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)`; model-invocable (area skills invoke it). The description: "Change a project alpha generated - add, remove, rename or move a component, switch on an area that didn't apply, or revisit an area's decisions - re-asking only what the change affects and merging the result without overwriting the user's edits. Use when the user asks to change a project alpha generated, or when an alpha area skill sends you here. Run as /alpha:extend [what to change]."
- The area skill bullet (identical in all 17): "- project.json has a `manifest` key: the project is already generated. If the `alpha:extend` skill sent you here, go on as it says. Otherwise invoke `alpha:extend` with the Skill tool and follow it; it brings you back here." Each description keeps "Use only inside an alpha project interview (/alpha:new-project)" and adds " or alpha:extend" right after it.
- new-project §1 step 2 becomes: "If `<target>/.claude/alpha/project.json` has a `manifest` key, the project is already generated. Tell the user, then invoke `alpha:extend` with the Skill tool to change it."

The skill's sections, which are the decisions the text must carry:
1. **Target and checks:** `<target>` is the current working directory.
   - No project.json: say alpha only changes projects it generated, and that existing projects are out of scope for v1. Stop.
   - No manifest: point to `/alpha:new-project`.
   - Run `update <target> --dry-run` first. If it lists changes, an earlier change was never applied: show them and ask whether to apply them now.
2. **What changes:** take `$ARGUMENTS`, or ask. Pick the area: components for adding, removing, renaming or moving a component; otherwise the area that owns the decision. Invoke its skill. Rules while extending, which win over the area skill's own:
   - use the current answers as recommendations and ask only what the change affects;
   - keep every other answer as it is;
   - keep every existing entry of `decisions` and `overrides` unchanged, and add one new decision for this change (`area` = the area; the title says what changed; the context says why). This overrides "replacing any earlier one".
   - Moving a component's folder (e.g. a root CLI moving to `cli/` so a second component can be added) means moving app code, which alpha doesn't do. The user moves it with `git mv` and commits (Claude can do that as ordinary work, outside alpha's files), then continues.
3. **Loop until valid:** run `update <target> --dry-run`.
   - "Revisit the <area> area: …": invoke that area's skill for this change, then rerun.
   - "Fix .claude/alpha/project.json: …": fix it with `answers write` (ask the user when the fix needs a decision).
   - After a component change, also offer the git area, so the commit scopes cover the component.
4. **Show and confirm:** summarize the list. Show the diffs of CLAUDE.md, `docs/principles.toml` and the docs, and say which files will need a hand merge. Write nothing until the user confirms.
5. **Apply:** run `update <target>`.
   - For each conflict, read its proposal under `.claude/alpha/state/update/`. It holds the user's version, the version before, and alpha's. Edit the real file so it keeps the user's edits and adds alpha's change, never just alpha's side, and show the user the result.
   - Stale files: ask before deleting any.
6. **Bootstrap** each new component with `bootstrap <target> --component <name>`.
7. **Commit** with `commit-update <target> --trailer …`, using the same trailers new-project passes to `commit-skeleton`, and relay any notes.
8. **Report** what changed and the commits. Tell the user to start a new Claude Code session (or run `/clear`) so Claude loads the updated rules. If a recipe was drafted, offer to save it, as new-project does.

- [ ] **Step 1: Write the failing tests** in `tests/test_skills.py`:
  - `test_extend_runs_the_update_loop`: the extend text contains `update <target> --dry-run`, `update <target>`, `bootstrap <target> --component`, `commit-update <target>`, `Revisit the`, `.claude/alpha/state/update/` and `new Claude Code session`.
  - `test_extend_keeps_earlier_decisions`: it contains "add one new decision" and "unchanged".
  - `test_extend_refuses_projects_alpha_did_not_generate`: it contains "out of scope".
  - `test_area_skills_hand_generated_projects_to_extend` (parametrized over `AREA_SKILLS`): the bullet above is present, "arrives in a later version" is absent, and the description contains "or alpha:extend".
  - `test_new_project_hands_generated_projects_to_extend`.
  - The existing parametrized tests (frontmatter, pre-approved CLI, CLI calls naming real subcommands and options, skills stay short) now cover `extend` through `ALL_SKILLS`.
- [ ] **Step 2: Run** `uv run pytest tests/test_skills.py -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Write** `skills/extend/SKILL.md` and edit the 18 skills. If `test_skills_stay_short` fails for extend, tighten the wording; never drop a section.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass. Also run `claude plugin validate .claude-plugin/marketplace.json`. Expected: valid.
- [ ] **Step 5: Commit**: `feat: Extend generated projects through area skills`

---

### Task 7: Live check and notes

**Files:** Modify `CLAUDE.md` (a new "Extend live check (<date>)" section, and `/alpha:extend` under Install and verify).

- [ ] **Step 1: CLI run.**
  1. In a scratch folder, take `web-ts-plus-python-api` through `bin/alpha` `answers check`, `generate`, `bootstrap` and `commit-skeleton`.
  2. Commit a hand edit at the end of CLAUDE.md.
  3. Add a `worker` component by cloning api's answers: use the `clone_component` shape, plus a components decision and the git scope, written with `answers write`.
  4. Run `update --dry-run`, then `update`, then `bootstrap --component worker`, then `commit-update`.

  Expected:
  - the hand edit stays;
  - `worker/` checks pass;
  - the commits follow the convention, and the commit-msg hook accepts them;
  - the tree is clean;
  - the second `update --dry-run` prints "nothing to change".
- [ ] **Step 2: Headless run.** In that project, run `claude -p --plugin-dir /Users/vs/workspace/alpha "/alpha:extend switch the changelog off"` (accept the recommendations). Expected: the releases skill is re-asked, a new decision record is added, CHANGELOG.md is listed as stale, and the update is committed. Note anything the skills got wrong and fix it with a test, as in earlier live checks.
- [ ] **Step 3: Record** the findings in CLAUDE.md, in the style of the earlier live-check sections. Run `uv run pytest -q`. Expected: all pass.
- [ ] **Step 4: Commit**: `docs: Record the extend live check`
