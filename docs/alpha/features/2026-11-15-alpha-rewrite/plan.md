# alpha rewrite: plan

Date: 2026-11-15
Spec: [specification.md](specification.md). Branch: `feat/alpha-rewrite`, in the worktree `.claude/worktrees/alpha-rewrite`.

Each task is one commit per the commit convention and leaves `mise run check` green; its tests are written first and fail before its code. The tests are rewritten with the code they cover: a task that replaces a module replaces its tests in the same commit.

Three rules hold for every task, because alpha runs its own hooks from `.claude/alpha/` and reads `docs/principles.toml` until task 19:

- **Docs move with the code.** alpha's docs map asks for `README.md` and `CLAUDE.md` to change with `src/alpha/cli.py`, `bin/**` and the entry skills. A task that changes those updates the two files in the same commit, so the Stop hook passes.
- **Callers move with their command.** A task that renames or removes a CLI command changes every skill, test and doc that calls it in the same commit; no skill names a command that no longer exists.
- **alpha's own copy follows the kit.** Until task 19, a task that removes a copied file (a skill, a check) re-renders alpha's own installed copy with the old kit's `alpha update` and `commit-update` in the same commit, so alpha holds what the kit ships.

Tasks run in order unless marked side by side.

## Subtract

1. **Drop the interview evals.** Delete `src/alpha_evals/`, `bin/alpha-evals`, `evals/`, `tests/integration/evals/`, the `alpha_evals` package in `pyproject.toml` (then `uv sync` to refresh `uv.lock`), the two `BLE001` Exceptions rows, and the mentions in README, CLAUDE.md and CONTRIBUTING's Overrides reason. Add `tests/unit/test_kit.py::test_R14_1_dropped_features_are_gone` for the evals part.
2. **Drop the mutation-testing gate.** `recipes/rust.toml` (`mutants`, `cargo-mutants` in bootstrap, `mutants.out*/`), `testing.mutants` in defaults, answers and the testing area skill, the `ci:mutants` step and `checked_by` entry, the exhaustive-testing statement's mutants sentence, the reviewer's `#[mutants::skip]` rule, the mutants cases in `tests/integration/test_rust_gates.py`. Extends `test_R14_1`.
3. **Drop `/debt` and the `shortcut:` ledger check.** `project-files/skills/debt/`, `project-files/checks/shortcuts.py`, the `shortcuts` repo check and its registry and catalog entries, their tests, and alpha's own copies (re-rendered). Completes `test_R14_1`. Side by side with 2.
4. **Drop the decision-record migration.** `skills/fold-decisions/`, `answers drop-decisions`, `update.py`'s `_without_records`, their tests and docs. Add `tests/unit/test_kit.py::test_R15_1_no_decision_records`.

## Answers and rendering

5. **Install and product areas.** `areas.py` (install areas; product areas `requirements` and `auth` added), `answers.py` and `core_areas.py`: identity without target users and requirements, security without auth, `agent_workflow` with extra risk paths only, no `testing.run`. `defaults/defaults.toml`: `settled_by` for the principles the new areas gate; `review.mode` and thresholds gone. `principles.py` follows. The area skills that list these fields change with them. Built: the planned `model.py` split was dropped, since moving the dataclasses into a module of their own served no requirement; until task 10, `principles.toml` keeps `review.mode` and `testing.run` at `at-merge`, which the current hooks read. Tests: `test_R5_1_install_needs_only_the_install_areas`, `test_R5_1_an_install_area_cant_stay_open`, `test_R5_3_open_areas_keep_their_principles_off`, and today's answer and principle tests rewritten.
6. **Docs layout.** `render/` split by output: `principles`, `claude_md`, `contributing`, `readme`, `specification`, `settings`, `gitignore`, `tooling`, `ci`, `components`. Output paths move to `docs/alpha/`; `docs/alpha/specification.md` with the open-area list and `/alpha:specify` requests; `documentation.existing` links (R6.2) and the dependency-log path in the principles; `CHANGELOG.md` at the root; no `docs/guide/`; `CLAUDE.md`, `CONTRIBUTING.md` and `README.md` written so each line that points at alpha names `.claude/alpha/`, `docs/alpha/`, an `/alpha:` command or one of alpha's skills or agents; `review.risk_paths` names `docs/alpha/principles.toml`. Built: the split of `render/` by output was dropped, as `model.py` was, since paths and content were the change and the modules could stay; alpha's own docs keep their old paths until task 19. Tests: `test_R6_2_an_existing_doc_is_referred_to`, `test_R6_4_root_docs_are_generated`, the render tests rewritten.

## One pipeline

7. **apply, update, adoption and the render notes.** One task, since the old writer, updater and adoption share `update.py` and can't be replaced apart:
   - `apply.py` (plan, three-way merge, alpha's own files replaced, write), `rendered.py` (render commits, `refs/alpha/rendered`, notes under `refs/notes/alpha-rendered`, finding the base with `--topo-order`), `git.py` (wrapper, commit groups, `alpha commit`), `status.py` (the install table's states), `installed` in place of `manifest`, `bootstrap.py` out of `generate.py`.
   - `adopt.py` keeps survey and the plan steps; its apply becomes `alpha apply` on an `existing` folder (branch `alpha/adopt`, `installed.preexisting`, proposals with no base); the plan renders to `docs/alpha/adoption.md`; `p0-chain-commit-hook` writes the marked snippet.
   - Retired copied files (the hooks this rewrite renames or drops) are listed in the kit and deleted by apply.
   - CLI `status`, `apply`, `update`, `commit`; delete `generate`, `commit-skeleton`, `commit-update`, `adopt apply`, `update.py`, `gitops.py`'s commit functions and `_RENDER_OLD`; `new-project`, `adopt` and `extend` call the new commands.
   - Tests: `test_R1_1_a_new_project_gets_the_layout`, `test_R1_2_each_folder_state_is_told_apart`, `test_R1_3_adoption_installs_on_its_branch`, `test_R1_5_an_adopted_repo_names_its_next_step`, `test_R4_1_a_new_component_merges_and_keeps_an_edit`, `test_R4_1_a_changed_answer_merges_and_keeps_an_edit`, `test_R6_1_docs_go_to_contributing_and_docs_alpha`, `test_R6_3_root_files_get_proposals`, `test_R7_1_settling_areas_writes_their_docs`, `test_R11_1_the_base_is_the_render_alpha_last_committed`, `test_R11_1_a_discarded_update_is_planned_again`, `test_R11_1_without_a_render_note_differences_become_proposals`, `test_R11_2_a_kit_change_merges_and_replaces_alphas_files`, `test_R12_3_a_step_is_done_only_when_its_acceptance_holds`, `test_R12_3_the_ratchet_only_tightens`, `test_R12_5_projects_get_the_agents_and_skills`, `test_R13_2_commit_msg_is_the_only_git_hook`, `test_R16_1_no_committed_file_holds_file_hashes`.
8. **Kit data.** `recipes.py` with the proof in `.claude/alpha/state/proofs.json`, `recipe_cli.py`, and the `defaults`, `recipe`, `registry`, `baseline` subcommands on the new model. Built: adoption was folded into task 7, and the `kit.py` merge was dropped, as `model.py` was. Tests: `test_R12_1_a_drafted_recipe_needs_a_local_proof`, `test_R12_1_stale_tools_are_listed`, `test_R12_1_a_user_default_wins`, `test_R12_2_every_check_is_wired`, `test_R12_4_ci_runs_each_components_checks`, `test_R12_4_each_stack_gets_its_permissions`.

## Hooks

9. **Guards.** `_common.py` on Python 3.11 (top-level `tomllib`; a 3.9-safe entry check; the three `PLC0415` rows go; the project found by `.claude/alpha/hooks/`), `guard_paths.py` (the wiring, `disableAllHooks`, `.claude/alpha/`), `guard_bash.py` trimmed to the spec's list, `context.py` replacing `session_start.py` and `subagent_start.py`. Tests: `test_R2_3_edits_to_the_hook_wiring_are_blocked`, `test_R2_3_shell_ways_to_switch_the_hooks_off_are_blocked`, `test_R2_4_alpha_uninstall_passes_the_guard`, guard tests rewritten.
10. **Review in git notes.** `review.py` (main refs, base by walking history with the branch fallback, files to review, brief and fix check, briefs in the common git dir, the gate with the PR head check and the dirty-tree refusal), `review_record.py` (note writer), `accept.py` (UserPromptSubmit, replacing `user_prompt.py`), the merge gate and the notes guards in `guard_bash.py`; delete the snapshot index, `_carry` and `absorb`. Tests: `test_R9_2_merge_waits_for_a_review_of_the_head_tree`, `test_R9_3_a_fix_check_reviews_only_whats_new`, `test_R9_4_only_the_users_prompt_accepts_a_risk_path_finding`, `test_R10_1_a_review_is_a_note_on_its_tree` (with a linked worktree), `test_R10_1_writing_review_notes_is_blocked`, `test_R10_2_the_last_reviewed_tree_is_found_in_history`, `test_R10_3_the_brief_holds_only_files_changed_since`, `test_R10_4_moving_review_notes_between_clones_is_blocked`.
11. **Stop, post-edit, untested.** `stop_checks.py` without the review gate and the at-stop test run, with the dependency-log path from the principles; `untested.py` out of `review.py`; `post_edit.py` as today. Tests: `test_R9_1_stop_never_asks_for_a_review`, `test_R13_1_stop_runs_types_structure_and_fast_checks`, `test_R13_1_an_edit_is_formatted_and_linted`, `test_R6_2_the_dependency_log_path_comes_from_the_principles`, `test_R12_2_main_waits_for_a_test_pass`, `test_R12_6_an_untested_note_holds_until_the_file_changes`, `test_R12_6_settings_wire_each_hook`, `test_R13_2_a_bad_message_is_rejected`.

## Uninstall and purge

12. **uninstall and hooks on.** `hooks_wiring.py` (hook entries, `core.hooksPath`, the chained snippet in and out of state), CLI `uninstall` and `hooks on`. Tests in `tests/integration/test_hooks_wiring.py`: `test_R2_1_uninstall_removes_only_the_hook_wiring`, `test_R2_2_a_chained_repo_keeps_its_hooks_path`, `test_R1_4_hooks_on_restores_what_uninstall_removed`.
13. **purge.** `purge.py` (the plan in memory, pure removers for `settings.json`, `CLAUDE.md`, `CONTRIBUTING.md`, `README.md`, tool configs, `mise.toml`, CI, `.gitignore`, the snippet; the scan; then uninstall, write, refs, commit), CLI `purge`. Tests: `test_R3_1_purge_removes_alpha_in_one_commit`, `test_R3_2_only_alphas_lines_leave_claude_md`, `test_R3_3_no_kept_file_names_a_deleted_path`, `test_R3_3_an_uncleanable_file_stops_purge`, `test_R3_4_purge_commits_only_alphas_paths`, `test_R3_4_purge_keeps_the_repos_own_files`.

## Skills and agents

14. **install, extend, specify, update, uninstall, purge.** New skills; area guides move to `skills/install/areas/` and `skills/specify/areas/`; `grilling` and `stack-recipe` follow; `new-project`, `adopt` and the 18 area skills go. Tests in `tests/unit/test_skills.py`: `test_R1_2_install_routes_each_state`, `test_R1_4_install_turns_hooks_on_without_asking`, `test_R1_5_install_works_the_plan`, `test_R5_2_install_reads_only_install_area_guides`, `test_R7_2_only_specify_settles_product_areas`, `test_R11_3_update_skill_merges_proposals`.
15. **do.** `skills/do/` from `skills/go/`: the playbooks without Specify; the feature playbook with deep research, superpowers-style brainstorming and the feature folder; no whole-branch review. Tests: `test_R8_1_a_feature_gets_research_spec_and_plan`, `test_R8_2_do_runs_no_whole_branch_review`. Side by side with 14.
16. **Copied agents and skills.** `principles-reviewer` (notes brief, fix-check rules), `committer`, `commit`, `decision` (docs under `docs/alpha/`), `review-change`, `audit`. Extends `test_R12_5`.

## Proof and alpha's own docs

17. **End-to-end.** Slow tests on real toolchains: `test_R1_1_empty_folder_becomes_a_checked_project`, `test_R12_2_each_check_fails_on_its_seed`, `test_R1_3_legacy_findings_pass_and_new_ones_fail`, `test_R3_3_a_purged_project_builds_and_tests`; the Rust workspace and coverage tests kept.
18. **alpha's own docs.** Rewrite `README.md`, `CLAUDE.md` and `CONTRIBUTING.md` for the new product; move `docs/live-checks.md` to `docs/alpha/live-checks.md`; delete `docs/superpowers/` (git keeps it).
19. **alpha onto the new kit.** Follow the spec's by-hand steps on alpha itself, which proves them: move `docs/principles.toml`, `docs/specification.md`, `docs/dependencies.md`, `docs/glossary.md` and `docs/adoption.md` into `docs/alpha/` and `docs/specs/` into `docs/alpha/features/`; reshape `project.json`; `alpha apply`, merge the proposals, `alpha bootstrap`, `alpha commit`. `core.hooksPath` keeps its path, so it needs no change. From here alpha runs the new hooks.
20. **Finish.** Bump the kit to 1.0.0; `mise run check`; `stop_checks.py tests`; the principles review at the merge gate; then the live runs, each recorded in `docs/alpha/live-checks.md`:
    - L1: `/alpha:install` on an empty folder, through the commit.
    - L2: `/alpha:install` on a scratch repo with code, through the commit on `alpha/adopt`; and on a folder that isn't a git repo (refused).
    - L3: `/alpha:uninstall`, then `/alpha:install` turning the hooks back on, in alpha mode and chain mode.
    - L4: `/alpha:update` after a kit change that conflicts with a hand edit.
    - L5: `/alpha:specify` on one product area.
    - L6: `/alpha:do` on a small feature, through its approved spec.
    - L7: `/alpha:purge`, then the project's checks.
    Then report per requirement.

## Traceability

| Requirement | Tasks |
|---|---|
| 1 install | 7, 12, 14, 17, 20 |
| 2 uninstall | 9, 12 |
| 3 purge | 13, 17 |
| 4 extend | 7, 14 |
| 5 scope | 5, 14 |
| 6 docs | 6, 7, 11 |
| 7 specify | 7, 14 |
| 8 do | 15 |
| 9, 10 review | 10, 11, 16 |
| 11 update | 7, 14 |
| 12 what stays | 7, 8, 11, 16, 17 |
| 13 fast checks | 11 |
| 14 dropped | 1, 2, 3 |
| 15 no decision log | 4 |
| 16 no hashes | 7, 8 |
