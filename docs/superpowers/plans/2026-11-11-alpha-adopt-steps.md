# The Compliance Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An adopted repo carries a **compliance plan** (spec §5b, step 6): steps by phase (P0-P6), each with the principles it serves, why it's needed, the steps it depends on, and an **acceptance** that proves it done. alpha finds the mechanical gaps itself. The adopt skill (plan 5) adds the judgment gaps from its assessment. Claude works through the plan one step at a time: `alpha adopt next` names the next ready step, and `alpha adopt done` marks a step done only after its acceptance holds. The plan is rendered as `docs/adoption.md`. This is plan 4 of the adoption series.

**Architecture:**
- Steps live in the answers, under `adoption.steps`. So they are history like decisions, flow into `docs/adoption.md` through the ordinary render, and reach the repo through `alpha update` and `commit-update`, like any other change to the answers.
- An acceptance is a list of **conditions** of four kinds:
  - `run`: a command that must exit 0
  - `recipe`: a recipe field that must be set
  - `no_baseline`: a check that must no longer be baselined
  - `commit_hook`: alpha's commit check must run from git's commit-msg hook

  These kinds are fixed in code. What they name is data, so no stack is branched on.
- `alpha adopt gaps` derives the mechanical steps from the answers:
  - every baseline, a burn-down step each
  - every empty check step or coverage in an adopted recipe
  - an unformatted component
  - a chained hook setup

  `--save` adds only the steps that aren't there yet, and never touches an existing one.

**Tech Stack:** Python ≥ 3.11. pytest, ruff, pyright.

**Spec:** §5b (A3; the flow's step 6, the phase table, and dropping a step).

## Decisions (the planner's calls)

- **C1 A step's fields:**
  - `id`: lowercase with hyphens, unique, e.g. `p5-baseline-typecheck-api`
  - `phase`: `P0`-`P6`
  - `title` and `why`: one line each
  - `component`, optional
  - `principles`: principle ids
  - `depends_on`: step ids
  - `acceptance`: a non-empty list of conditions
  - `status`: `pending`, `in_progress`, `done` or `dropped`
  - `branch`, optional
  - `decision`, for a dropped step: the record's number

  The answers check the shape. A step may depend only on steps listed before it, which keeps the graph acyclic without a graph check.
- **C2 Conditions** (`adoption.steps[i].acceptance[j]`):
  - `{"run": "<command>", "dir": "<path>"}` (dir optional, default the root)
  - `{"recipe": "<component>.<field>"}`: `commands.<step>` or `coverage` is non-empty in the component's recipe
  - `{"no_baseline": "<check id>"}`: the id isn't in `adoption.baselines`
  - `{"commit_hook": true}`: the session-start hook's check (plan 3)
  - `{"confirm": "<what the user confirms>"}`: only for judgment steps no command can prove. It needs `alpha adopt done --confirmed-by-user`, which the skill passes only after asking. The assessment (plan 5) prefers writing a test as the step's evidence and naming it in a `run`.
- **C3 Mechanical gaps** (`alpha adopt gaps`), from the answers, the recipes and the defaults. All are pure, with nothing run:

  | Gap | Phase | Steps | Acceptance |
  |---|---|---|---|
  | `adoption.git_hooks == "chain"` | P0 | `p0-chain-commit-hook` | `commit_hook` |
  | an adopted recipe's `format_check` is `""` | P1 | `p1-format-<c>` (principles `lean-structure`, `clean-history`; why: format in one commit, listed in `.git-blame-ignore-revs`) | `recipe <c>.commands.format_check`, then `run mise run check:component:<c>` |
  | an empty `lint` | P2 | `p2-lint-<c>` (`no-dead-code`, `never-weaken-checks`) | `recipe` and `run`, as above |
  | an empty `typecheck` | P2 | `p2-typecheck-<c>` (`strict-types`) | as above |
  | an empty `test` | P2 | `p2-test-<c>` (`tests-first-class`) | as above |
  | no `coverage` while `testing.diff_coverage > 0` | P2 | `p2-coverage-<c>` (`tests-first-class`) | `recipe <c>.coverage` |
  | each `adoption.baselines` id | P5 | `p5-baseline-<id with : as ->` (the principle the check serves: lint `no-dead-code`, typecheck `strict-types`, test `tests-first-class`, structure `lean-structure`, typos/markdown/links `docs-with-code`, actions `build-hosting-upfront`, agent-config `evidence-before-done`) | `no_baseline <id>` |

  P5 steps of a component depend on its P1 step, when it has one: burn findings down after formatting, so diffs stay small. The step→principle table is data in `defaults/defaults.toml` (`[adopt.principles]`), not code.
- **C4 Next.** The first step, in phase order and then list order, that is `pending` or `in_progress` and whose `depends_on` are all `done` or `dropped`. `alpha adopt next` prints its id, title, why, acceptance and a branch name (`alpha/<id>`). When none is ready, it says why: all done, or the blocking steps.
- **C5 Done and dropped** change only `adoption.steps` (through `write_answers`, sending the whole list). The skill then runs `alpha update` and `alpha commit-update`, so `docs/adoption.md` follows.
  - `done` runs every condition and reports each one. Only when all hold does it set the status.
  - `drop --decision <N>` needs `docs/decisions/<N>-*.md` with `Status: accepted` that names the step id in backticks. Dropping a step is a loosening, so the record has the user's agreement (§4).
- **C6 `docs/adoption.md`** is rendered only when `adoption.steps` isn't empty:
  - a short intro (what the plan is; `/alpha:adopt` resumes it; a step is done only when its acceptance holds)
  - progress per phase
  - one section per phase, with a table (step, component, status) and each step's why and acceptance

  It holds no baseline counts: those change with every fix and live in `alpha baseline show`. CLAUDE.md gains one line pointing to it, only then. Generated projects are unchanged.

## Global Constraints

As in plans 1 to 3:
- byte-identical generated projects
- stack-free code
- refusals with fixes
- commits per CLAUDE.md, each ending with this session's attribution lines
- `uv run pytest`, ruff, pyright and `mise run check` green after every task

## Review Focus

1. **`done` never marks a step whose acceptance fails**, including a `run` that times out or a missing command. Pinned by `test_done_needs_every_condition` (Task 3).
2. **`gaps --save` never rewrites a step**, so a step that's in progress or done keeps its status and fields, and a gap that went away leaves its step in place. Pinned by `test_gaps_save_adds_only_new_steps` (Task 2).
3. **The rendered plan passes the project's own Markdown and typos checks.** Pinned by `test_adoption_doc_passes_rumdl` (Task 4, slow).

---

### Task 1: Steps in the answers

**Files:** Modify `src/alpha/answers.py` (`_ADOPTION_KEYS` gains `steps`; `Step` and `Condition` dataclasses; `Answers.steps`). Test: `tests/test_adopt_steps.py`.

- [ ] **Step 1: Write the failing tests**: valid steps load; each rule of C1 and C2 is refused with `adoption.steps[i]…` named:
  - a bad id
  - a duplicate id
  - an unknown phase or status
  - a `depends_on` naming a later or unknown step
  - an empty acceptance
  - an unknown condition kind
  - `recipe` naming an unknown component or field
  - `dropped` without `decision`
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Hold the adoption plan's steps in the answers`

### Task 2: `alpha adopt gaps`

**Files:** Modify `defaults/defaults.toml` (`[adopt.principles]`), `src/alpha/adopt.py` (`gaps(a, defaults) -> list[dict]`, `merge_steps(existing, found)`), `src/alpha/cli.py`. Test: `tests/test_adopt_steps.py`.

- [ ] **Step 1: Write the failing tests:**
  - `test_gaps_from_baselines_and_recipe`: an adopted recipe with `format_check ""`, an empty `lint` and no coverage, plus baselines `typecheck:ml` and `typos`, give `p1-format-ml`, `p2-lint-ml`, `p2-coverage-ml`, `p5-baseline-typecheck-ml` (depending on `p1-format-ml`) and `p5-baseline-typos`, in phase order, with the principles from the table.
  - `test_chain_gap`
  - `test_no_gaps_for_a_compliant_project`: the ML scenario with an adopted recipe that keeps the kit's commands, and no baselines.
  - `test_gaps_save_adds_only_new_steps`
  - `test_gaps_cli_prints_and_saves`
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Find an adopted repo's mechanical gaps`

### Task 3: `alpha adopt next`, `done` and `drop`

**Files:** Modify `src/alpha/adopt.py`, `src/alpha/cli.py`. Test: `tests/test_adopt_steps.py`.

- [ ] **Step 1: Write the failing tests:**
  - `test_next_follows_phase_order_and_dependencies`
  - `test_next_says_what_blocks`
  - `test_next_when_all_done`
  - `test_done_needs_every_condition`: `run` failing, timing out (monkeypatched) or not found; `recipe` empty; `no_baseline` still listed; `commit_hook` missing. Each is reported, and the status is unchanged. When all hold, the status is `done`.
  - `test_done_confirm_needs_the_flag`
  - `test_drop_needs_an_accepted_record_naming_the_step`
  - `test_start_sets_in_progress_and_branch`: `alpha adopt start <id>` records the branch it prints.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.** `run` conditions use the ratchet's timeout (600 s) and run in the project root, or in `dir`.
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Work through the adoption plan step by step`

### Task 4: `docs/adoption.md`

**Files:** Modify `src/alpha/render/area_docs.py` or `docs.py` (`docs/adoption.md`; the CLAUDE.md line). Test: `tests/test_adopt_steps.py`, plus a slow rumdl/typos run.

- [ ] **Step 1: Write the failing tests:**
  - `test_adoption_doc_lists_steps_by_phase`
  - `test_no_adoption_doc_without_steps` (the scenario snapshots stay unchanged)
  - `test_claude_md_points_to_the_plan`
  - `test_update_refreshes_the_doc`: after an adoption, marking a step done and running `alpha update` changes only `docs/adoption.md` (and project.json).
  - `@pytest.mark.slow test_adoption_doc_passes_rumdl`: rumdl and typos with the project's own configs on the rendered doc.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest` and the slow test. Expected: PASS.
- [ ] **Step 5:** CLAUDE.md gets a Dev-commands bullet for `alpha adopt gaps|next|start|done|drop`. Run `mise run check`.
- [ ] **Step 6: Commit** `feat: Render the adoption plan as docs/adoption.md`
