# The Adopt Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/alpha:adopt [folder]` drives the whole adoption (spec §5b) with the CLI the earlier plans built:
1. survey the repo
2. interview all 17 areas, with the repo's practice as the recommendations
3. assess the gaps no tool reports
4. preview and confirm
5. install on `alpha/adopt`

Run again in an adopted repo, it carries out the plan one step at a time. This is plan 5 of the adoption series. The evals are plan 6.

**Architecture:** Skills only, plus their tests. No CLI or render change.
- `skills/adopt/SKILL.md` is the entry point, modeled on `new-project` and `extend`. It hands each area to its area skill with rules that win over the area's own, as `extend` does.
- Each area skill learns one new case in "Before you start": an `adoption` key without a `manifest` means the adopt skill sent it.
- The stack-recipe skill learns adopted recipes.
- The assessment reuses the audit's lenses from the copy of `project-files/skills/audit/SKILL.md` in the plugin. Their only home stays that file.

**Spec:** §5b (all of it), §5a (extend's merge rules, reused), §4 (the interview), §9 (on-demand reports).

## Decisions (the planner's calls)

- **K1 One skill, three modes**, chosen from project.json:
  - none, or no `adoption` key: start, by surveying first
  - `adoption` and no `manifest`: resume the interview, or go to install when every area is done
  - a `manifest` with `adopted_at`: the plan
  A generated project (a manifest without `adopted_at`) goes to `alpha:extend`.
- **K2 The interview's extra rules** (these win over each area skill's):
  - Recommend what the repo already does when it meets the principle, and the kit default otherwise. Say which one each recommendation is.
  - Never ask what the survey or a file in the repo answers. Read the README for identity, the manifests and CI for components and build, and `LICENSE` for `identity.license_file`.
  - Wherever the repo falls short of an active principle, say so, and remember it for the assessment's list of gaps.
  - No app code changes during the interview.
  - Components:
    - Start from the survey's candidates.
    - Every component gets an adopted recipe, drafted with `alpha:stack-recipe`: named `<component>-<stack>`, extending the kit's recipe when the repo's tools are the kit's.
    - Prove each with `recipe try` and save the checks it reports as findings in `adoption.baselines`.
  - Git history: `adoption.git_hooks` is `alpha` when the survey found no hook manager and no `core.hooksPath`, else `chain`.
  - Documentation: keep an existing decision-record folder's numbering. alpha's own records start after it.
- **K3 The assessment** runs in one general-purpose subagent, to keep the main context clean:
  - It reads the plugin's audit skill and the answers, and applies the lenses per active principle, with no 20-finding cap.
  - It returns JSON findings: `principle`, `component`, `title`, `why`, `evidence` (file:line), `severity`, `acceptance` (preferably a test command).
  - The skill groups them, asks the user about each Must/Should finding with `alpha:grilling`, and saves the confirmed ones as P3/P4/P6 steps with one `answers write` of `adoption` whole.
  - Optional tool migrations (P3) are offered only where an adopted recipe runs a tool the kit's recipe replaces.
- **K4 Preview, then install.** The preview shows:
  - `adopt gaps --save` and `adopt apply --dry-run` (files new, merged and in conflict)
  - the baselines from the proofs
  - the plan by phase

  Install runs, in order: `apply`, the hand merges (extend's §5 rules), `bootstrap --capture-baselines`, then `commit-update` with this session's trailers. A secret or vulnerability bootstrap reports is resolved with the user before going on: rotate a real secret and add a P0 step; an `osv-scanner.toml` exception needs a reason and a review date. Pushing and opening the pull request are the user's call.
- **K5 The plan, one step per run** unless the user asks for more. The loop:
  1. `adopt next`
  2. branch off the default branch, or off `alpha/adopt` until that branch is merged
  3. `adopt start`
  4. do the work under the project's hooks
  5. commit
  6. `adopt done`
  7. `alpha update` and `commit-update`
  8. report

  A step that can't be done is dropped only after a decision the user agreed to, through the project's `/decision` skill.

## Global Constraints

The existing skill rules, which `tests/test_skills.py` enforces:
- at most 150 lines
- the CLI called only as `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" <real subcommand and flags>`
- CLI calls pre-approved by `allowed-tools`
- answers saved only with a one-line `answers write`, never the file tools
- the area descriptions keep their trigger phrase

Commits per CLAUDE.md, each ending with this session's attribution lines. `mise run check` passes after every task, and agnix and rumdl run on the skills.

## Review Focus

1. **Rules that conflict between adopt and an area skill.** The area skill's "tell them to run /alpha:new-project" must not fire during an adoption. Pinned by `test_area_skills_hand_adoptions_back` (Task 2).
2. **No step skipped or reordered in install.** Pinned by `test_adopt_installs_in_order` (Task 1).
3. **The skill never marks a step done itself.** Only `adopt done` does. Pinned by `test_adopt_marks_steps_only_through_the_cli` (Task 1).

---

### Task 1: `skills/adopt/SKILL.md`

**Files:** Create `skills/adopt/SKILL.md`. Modify `tests/test_skills.py`: the CLI skills list gains `adopt`, plus the new tests.

- [ ] **Step 1: Write the failing tests:**
  - `test_adopt_invokes_the_area_skills_in_order` (the same order as new-project)
  - `test_adopt_installs_in_order`: `adopt survey`, `adopt gaps`, `adopt apply --dry-run`, `adopt apply`, `bootstrap … --capture-baselines` and `commit-update` appear in that order
  - `test_adopt_marks_steps_only_through_the_cli`: the plan section calls `adopt next`, `adopt start` and `adopt done`, and never edits `adoption.steps` statuses with `answers write`
  - `test_adopt_is_user_invoked`
  - `test_skills_use_every_cli_command_the_interview_needs` gains the `adopt` subcommands, `baseline show` and `recipe try`
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Write the skill.** Sections:
  1. Target and mode (K1, with the survey's refusals)
  2. Start (survey `--save`, then project.json with every area pending, plus `adoption`)
  3. Defaults (as new-project §3)
  4. Interview (K2)
  5. Assessment (K3)
  6. Preview (K4)
  7. Install (K4)
  8. Report
  9. The plan (K5)
- [ ] **Step 4: Run** `mise run check`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Add the adopt skill`

### Task 2: Area skills hand adoptions back

**Files:** Modify the 17 area skills and `stack-recipe`: one bullet in "Before you start", and "or /alpha:adopt" in each description. Modify `skills/new-project/SKILL.md` §1 (a non-empty folder points to `/alpha:adopt`) and `skills/extend/SKILL.md` §1 (no project.json points to `/alpha:adopt`). Test: `tests/test_skills.py`.

- [ ] **Step 1: Write the failing tests:**
  - `test_area_skills_hand_adoptions_back`: each area skill says that project.json with `adoption` and no `manifest` means `alpha:adopt` sent it, to go on as that skill says, and that its rules win.
  - `test_new_project_and_extend_point_to_adopt`
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Edit the skills.** The bullet:

  > project.json has an `adoption` key and no `manifest`: `alpha:adopt` is bringing an existing repo in. Go on as it says; its rules win over this skill's, and don't point to /alpha:new-project afterwards.
- [ ] **Step 4: Run** `mise run check`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Hand adoptions back from the area skills`

### Task 3: Adopted recipes in the stack-recipe skill

**Files:** Modify `skills/stack-recipe/SKILL.md`. Test: `tests/test_skills.py`.

- [ ] **Step 1: Write the failing test** `test_stack_recipe_covers_adopted_recipes`. It names:
  - `"adopted": true` and `extends`
  - an empty `bootstrap`
  - `format_check ""` for unformatted code
  - a baseline reader for each failing step
  - `recipe try` reporting the findings to baseline
- [ ] **Step 2: Run** it. Expected: FAIL.
- [ ] **Step 3:** Add an "Adopting a repo's tools" section, within 150 lines:
  - Facts come from the repo: its manifests, lockfile, CI and task runner.
  - Use the repo's own commands, and extend the kit recipe when the tools match.
  - Test globs must match its real test files.
  - Prove the recipe on its code.
- [ ] **Step 4: Run** `mise run check`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Draft adopted recipes in the stack-recipe skill`

### Task 4: The docs

**Files:** Modify `CLAUDE.md` (the opening line mentions adoption; "Install and verify" shows `/alpha:adopt` on an existing repo) and `README.md`, if it describes the entry points.

- [ ] **Step 1:** Write it, run `mise run check`.
- [ ] **Step 2: Commit** `docs: Explain adopting an existing repo`
