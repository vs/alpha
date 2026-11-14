# 0031. Playbooks live in the plugin as /alpha:go

Date: 2026-11-14
Status: accepted
Kind: product

## Context

The user wants pstack's playbooks in alpha, so that they install only alpha: "Alpha should replace pstack, I'd only install alpha have pstack-like skills available for work". The playbooks "must work respecting all the principles and guidelines that alpha generated". Copying them into each project, as the enforcement is copied (spec §7), is out: "do they become part of the source code for those projects? That I'd avoid."

The user's own workflow is research, then a spec for a feature including its tests, then implement and test. pstack writes no spec ("the best spec is code"), so the feature playbook follows the user's order instead. The user settled where a spec goes, "docs/specs/<date>-<feature>.md", and that it needs their approval "every time". They also asked for two things from superpowers: "the way superpowers execute the plan with options how to do that: native or with subagents", and being able to run some pieces of work in a worktree. The skill's name is theirs: "go with alpha:go".

Claude's choices, open to correction:

- In a repo alpha hasn't generated or adopted, `/alpha:go` stops and points to `/alpha:adopt`, because there are no principles to follow.
- The first playbooks: investigation, feature, bug fix, refactoring, perf, prototype, session pickup and pause. pstack's Cursor-only playbooks (babysit, shipping, autopilot, orchestrate) and its fan-out skills (arena, swarm) are left out.
- pstack's principles are not copied; a playbook names the project's own principles in `docs/principles.toml`.

## Decision

The plugin ships one skill, `/alpha:go`, that matches a task to a playbook and works it step by step. The playbooks are files inside the skill, not copied into projects. They read the project's principles, decision records, CLAUDE.md commands and review mode at run time, and end with the project's own review and commit tools.

A feature starts from research, settles its open questions with the grilling skill, and writes a spec to `docs/specs/<YYYY-MM-DD>-<feature>.md`: each requirement with its acceptance checks and the test that proves each one, and a plan of ordered tasks, each one commit. The user approves every spec before any test or code is written, and at the same time picks how it's built: native (Claude builds every task, one review of the whole branch at the end) or with subagents (a fresh subagent per task, a fresh reviewer after each). Each task's tests are written and run first, failing; they are committed with the code that makes them pass, because every commit passes the checks on its own (`clean-history`). A bug fix works the same way, unlike pstack, which commits the failing test first.

Work can run in its own git worktree: the user's stated preference holds, otherwise Claude offers it once for a feature or a wide refactoring. The harness's worktree tool comes first, `git worktree add .claude/worktrees/<branch>` second; subagents running side by side each get their own.

A feature spec's requirement traces to a row of `docs/product.md`: the requirement it serves, or a new one added first through `/alpha:extend`, since that file is generated from the answers.

`review-change`, which projects already copy, keeps a bug finding only when a command shows it, and names the one fact a change is safe because of.

## Consequences

- A new requirement, R8, covers working in a project.
- The playbooks change with the plugin; a project picks up nothing to merge.
- A collaborator without the plugin has no playbooks, but loses no check.
- The pstack plugin can be uninstalled. Its `/setup-pstack` model roles have no equivalent: subagents run on the parent chat's model.
- Not verified: a live `/alpha:go` run on a feature.
