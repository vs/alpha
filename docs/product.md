# alpha: product

## Value proposition

alpha interviews you about a new project, then writes what agents build on: principles, docs, decision records, Claude Code and git hooks, CI, and a test setup per component that passes from the first commit. It writes no app code, and each principle is checked, by a hook or by a reviewer agent, before a change reaches main.

## Target users

Developers building with Claude Code who want agents to follow enforced engineering principles from day one: starting a new project from an enforced skeleton, or bringing an existing repo under the same rules without stopping its work.

## Requirements

| ID | Requirement | Acceptance check |
|---|---|---|
| R1 | Interview the user area by area, recommending answers from the kit defaults, and save them to project.json. | Given an empty folder, when /alpha:new-project runs and the user accepts each recommendation, then project.json has every area done and alpha answers check prints ok. |
| R2 | From finished answers, generate, bootstrap and commit a skeleton (config, docs, test wiring, enforcement, no app code) whose checks pass. | Given finished answers, when alpha generate, bootstrap and commit-skeleton run, then the project has no app source files, every component check and mise run ci pass, and the tree is clean. |
| R3 | Enforce each active principle in a generated project through Claude Code hooks, git hooks, CI or the principles reviewer. | Given a generated project, when an agent skips git hooks, edits a protected file or stops with untested source, then the matching hook blocks it with a message naming the fix. |
| R4 | Bring an existing repo under the same enforcement on alpha/adopt, with legacy findings baselined and a compliance plan to work through. | Given a clean repo with legacy lint findings, when alpha adopt apply and bootstrap --capture-baselines run, then the files alpha writes are committed on alpha/adopt, the existing findings pass as baselined, and a new finding fails its check. |
| R5 | Change the answers of a generated or adopted project and merge the result without overwriting edits the user made. | Given a generated project with a hand edit in CLAUDE.md, when an answer changes and alpha update and commit-update run, then the change is applied, the edit survives, and a second update --dry-run prints nothing to change. |
| R6 | Support any stack through recipes: the ones the kit ships (Python, TypeScript, Rust) or drafted ones that must be proven before use. | Given a stack the kit has no recipe for, when a drafted recipe is saved, then answers check refuses it until alpha recipe try proves it, and again after any later edit. |
| R7 | Apply the user layer (their own defaults and recipes) on top of the kit, surviving plugin updates. | Given a user override set with alpha defaults set, when the plugin is updated or a new interview starts, then alpha defaults show returns the override on top of the kit defaults. |
