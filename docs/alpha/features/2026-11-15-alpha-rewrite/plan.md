# alpha rewrite: plan

Date: 2026-11-15
Spec: [specification.md](specification.md). Branch: `feat/alpha-rewrite`, in the worktree `.claude/worktrees/alpha-rewrite`.

Each task is one commit per the commit convention and leaves `mise run check` green; its tests are written first and fail before its code. The tests are rewritten with the code they cover: a task that replaces a module replaces its tests in the same commit. The order removes what goes first (subtract first), then rebuilds from the answers outward, and moves alpha's own docs last, because alpha's own hooks read `docs/principles.toml` until then.

Tasks run in order unless marked side by side.

## Subtract

1. **Drop the interview evals.** Delete `src/alpha_evals/`, `bin/alpha-evals`, `evals/`, `tests/integration/evals/`, the two `BLE001` Exceptions rows, and their mentions in README, CLAUDE.md and CONTRIBUTING's Overrides reason. Add `tests/unit/test_kit.py::test_R14_1_dropped_features_are_gone` for the evals part.
2. **Drop the mutation-testing gate.** `recipes/rust.toml` (`mutants`, `cargo-mutants` in bootstrap, `mutants.out*/`), `testing.mutants` in defaults and answers, the `ci:mutants` step and `checked_by` entry, the exhaustive-testing statement's mutants sentence, the reviewer's `#[mutants::skip]` rule, `tests/integration/test_rust_gates.py`'s mutants cases. Extends `test_R14_1`.
3. **Drop `/debt` and the `shortcut:` ledger check.** `project-files/skills/debt/`, `project-files/checks/shortcuts.py`, the `shortcuts` repo check and its registry and catalog entries, their tests. Completes `test_R14_1`. Side by side with 2.
4. **Drop the decision-record migration.** `skills/fold-decisions/`, `answers drop-decisions`, `update.py`'s `_without_records`. Add `tests/unit/test_kit.py::test_R15_1_no_decision_records`.

## Answers and rendering

5. **Install and product areas.** `areas.py` (install areas; product areas `requirements` and `auth` added), `model.py` split out of `answers.py`, `core_areas.py`: identity without target users and requirements, security without auth, `agent_workflow` with extra risk paths only, no `testing.run`. `defaults/defaults.toml`: `settled_by` for the principles the new areas gate, `review.mode` and thresholds gone. `principles.py` follows. Tests: `test_R5_1_install_needs_only_the_install_areas`, `test_R5_1_an_install_area_cant_stay_open`, `test_R5_3_open_areas_keep_their_principles_off`, and today's answer and principle tests rewritten.
6. **Docs layout.** `render/` split by output: `principles`, `claude_md`, `contributing`, `readme`, `specification`, `settings`, `gitignore`, `tooling`, `ci`, `components`. Output paths move to `docs/alpha/`; `docs/alpha/specification.md` with the open-area list and `/alpha:specify` requests; `documentation.existing` links (R6.2); `CHANGELOG.md` at the root; no `docs/guide/`; CLAUDE.md written so each line that points at alpha names `.claude/alpha/`, `docs/alpha/`, an `/alpha:` command or one of alpha's skills or agents. Tests: `test_R6_2_an_existing_doc_is_referred_to`, `test_R6_4_root_docs_are_generated`, the render tests rewritten.

## One pipeline

7. **apply, update and the base ref.** `apply.py` (plan, three-way merge, write, `refs/alpha/rendered` via a temporary index and `commit-tree`), `git.py` (wrapper, commit groups, `alpha commit`), `status.py`, `installed` in place of `manifest`; CLI `status`, `apply`, `update`, `commit`; delete `generate.py`'s writer, `update.py`, `gitops.py`'s two commit functions and `_RENDER_OLD`. `bootstrap.py` takes the bootstrap out of `generate.py`. Tests: `test_R1_1_a_new_project_gets_the_layout`, `test_R1_2_each_folder_state_is_told_apart`, `test_R4_1_a_new_component_merges_and_keeps_an_edit`, `test_R6_1_docs_go_to_contributing_and_docs_alpha`, `test_R7_1_settling_areas_writes_their_docs`, `test_R11_1_the_base_is_alphas_last_render`, `test_R11_1_without_the_base_differences_become_proposals`, `test_R11_2_a_kit_change_merges_into_an_edited_file`, `test_R12_5_projects_get_the_agents_and_skills`, `test_R13_2_commit_msg_is_the_only_git_hook`, `test_R16_1_no_committed_file_holds_file_hashes`.
8. **Adoption on the pipeline.** `adopt.py` keeps survey and the plan steps; its apply becomes `alpha apply` on an `existing` folder (branch `alpha/adopt`, mechanical merges, proposals with no base); the plan renders to `docs/alpha/adoption.md`. Tests: `test_R1_3_adoption_installs_on_its_branch`, `test_R6_3_root_files_get_proposals`, `test_R12_3_a_step_is_done_only_when_its_acceptance_holds`, baseline tests moved (`test_R12_3_the_ratchet_only_tightens`).
9. **Kit data CLI.** `kit.py` (defaults, user layer, registry loading), `recipes.py`, `recipe_cli.py` and the `defaults`, `recipe`, `registry`, `baseline` subcommands on the new model. Tests: `test_R12_1_a_drafted_recipe_needs_a_proof`, `test_R12_1_stale_tools_are_listed`, `test_R12_1_a_user_default_wins`, `test_R12_2_every_check_is_wired`, `test_R12_4_ci_runs_each_components_checks`, `test_R12_4_each_stack_gets_its_permissions`. Side by side with 8.

## Hooks

10. **Guards.** `_common.py` on Python 3.11 (top-level `tomllib`; a 3.9-safe entry check; the three `PLC0415` rows go), `guard_paths.py` (the wiring and `.claude/alpha/`), `guard_bash.py` trimmed to the spec's list, `context.py` replacing `session_start.py` and `subagent_start.py`. Tests: `test_R2_3_edits_to_the_hook_wiring_are_blocked`, `test_R2_3_shell_ways_to_remove_the_hooks_are_blocked`, `test_R2_4_alpha_uninstall_passes_the_guard`, guard tests rewritten.
11. **Review in git notes.** `review.py` (base by walking history, brief, fix check, briefs in the common git dir, the gate), `review_record.py` (note writer), the merge gate in `guard_bash.py`, notes guards; delete `user_prompt.py`, the snapshot index, `_carry` and `absorb`. Tests: `test_R9_2_merge_waits_for_a_review_of_the_head_tree`, `test_R9_3_a_fix_check_adds_no_findings`, `test_R10_1_a_review_is_a_note_on_its_tree` (with a linked worktree), `test_R10_1_writing_review_notes_is_blocked`, `test_R10_2_the_last_reviewed_tree_is_found_in_history`, `test_R10_3_the_brief_holds_only_files_changed_since`, `test_R10_4_pushing_review_notes_is_blocked`.
12. **Stop, post-edit, untested.** `stop_checks.py` without the review gate and the at-stop test run, `untested.py` split out of `review.py`, `post_edit.py` as today. Tests: `test_R9_1_stop_never_asks_for_a_review`, `test_R13_1_stop_runs_types_structure_and_fast_checks`, `test_R13_1_an_edit_is_formatted_and_linted`, `test_R12_2_main_waits_for_a_test_pass`, `test_R12_6_an_untested_note_holds_until_the_file_changes`, `test_R12_6_settings_wire_each_hook`, `test_R13_2_a_bad_message_is_rejected`.

## Uninstall and purge

13. **uninstall and hooks on.** `hooks_wiring.py`, CLI `uninstall` and `hooks on`. Tests: `test_R2_1_uninstall_removes_only_the_hook_wiring`, `test_R2_2_a_chained_repo_keeps_its_hooks_path`, `test_R1_4_hooks_on_restores_what_uninstall_removed`.
14. **purge.** `purge.py` (pure removers for `CLAUDE.md`, `mise.toml`, CI, `.gitignore`, `settings.json`, hook-manager files; then delete, drop refs, commit), CLI `purge`. Tests: `test_R3_1_purge_removes_alpha_in_one_commit`, `test_R3_2_only_alphas_lines_leave_claude_md`, `test_R3_3_no_kept_file_names_a_deleted_path`, `test_R3_4_purge_commits_only_alphas_paths`.

## Skills and agents

15. **install, extend, specify, update, uninstall, purge.** New skills; area guides move to `skills/install/areas/` and `skills/specify/areas/`; `grilling` and `stack-recipe` follow; `new-project`, `adopt` and the 18 area skills go. Tests in `tests/unit/test_skills.py`: `test_R1_2_install_routes_each_state`, `test_R1_4_install_turns_hooks_on_without_asking`, `test_R5_2_install_reads_only_install_area_guides`, `test_R7_2_only_specify_settles_product_areas`, `test_R11_3_update_skill_merges_proposals`.
16. **do.** `skills/do/` from `skills/go/`: the playbooks without Specify; the feature playbook with deep research, superpowers-style brainstorming and the feature folder; no whole-branch review. Tests: `test_R8_1_a_feature_gets_research_spec_and_plan`, `test_R8_2_do_runs_no_whole_branch_review`. Side by side with 15.
17. **Copied agents and skills.** `principles-reviewer` (notes brief, fix-check rules, risk-path acceptance), `committer`, `commit`, `decision` (docs under `docs/alpha/`), `review-change`, `audit`. Extends `test_R12_5`.

## Proof and alpha's own docs

18. **End-to-end.** Slow tests on real toolchains: `test_R1_1_empty_folder_becomes_a_checked_project`, `test_R12_2_each_check_fails_on_its_seed`, `test_R1_3_legacy_findings_pass_and_new_ones_fail`, `test_R3_3_a_purged_project_builds_and_tests`; the Rust workspace and coverage tests kept.
19. **alpha's own docs.** Rewrite `README.md`, `CLAUDE.md`, `CONTRIBUTING.md`; move `docs/principles.toml`, `docs/specification.md`, `docs/dependencies.md`, `docs/glossary.md` and `docs/adoption.md` into `docs/alpha/`; the old `docs/specs/` features into `docs/alpha/features/`; delete `docs/superpowers/` (git keeps it); re-render alpha's own `.claude/alpha/` with the new `alpha apply`, following the spec's by-hand steps, which proves them.
20. **Finish.** `mise run check`, `stop_checks.py tests`, the principles review at the merge gate, live runs of `/alpha:install` on an empty folder and on a scratch repo, `/alpha:uninstall`, `/alpha:install` (hooks back on), `/alpha:purge`. Record what ran in `docs/alpha/live-checks.md` and report per requirement.

## Traceability

| Requirement | Tasks |
|---|---|
| 1 install | 7, 8, 13, 15, 18 |
| 2 uninstall | 10, 13 |
| 3 purge | 14, 18 |
| 4 extend | 7, 15 |
| 5 scope | 5, 15 |
| 6 docs | 6, 7, 8 |
| 7 specify | 7, 15 |
| 8 do | 16 |
| 9, 10 review | 11, 12, 17 |
| 11 update | 7, 15 |
| 12 what stays | 8, 9, 12, 17, 18 |
| 13 fast checks | 12 |
| 14 dropped | 1, 2, 3 |
| 15 no decision log | 4 |
| 16 no hashes | 7 |
