# 0036. The command guard catches habits, not evasion

Date: 2026-11-15
Status: accepted
Kind: product

## Context

The user: "I noticed that alpha hooks sometimes do not allow run a complex command in a worktree because it can't confirm that this command does not apply outside of the worktree. I think it's meaningless, because it's easy to bypass such a limitation. Remove this check and remove any similar check alpha has now that does not make sense because Claude is able to bypass it easily."

The worktree prompt turned out to be Claude Code's own check on compound commands with `cd`, not alpha's. Every check in guard_bash can be bypassed by writing a script to a file and running it, so Claude sorted them into checks that catch an honest habit (`git add -A`, `git stash`, `reset --hard`, a plain force push, amending main, pushing or merging unreviewed work) and checks that only catch deliberate evasion or block when alpha can't tell what a command does. The user chose to remove three of the second kind and keep the guard on Bash writes to protected paths.

## Decision

guard_bash no longer:

- blocks `gh pr merge` when it can't tell which branch is merged, or when no checkout here has that branch. It checks the review and tests in the checkout that has the branch, when there is one, and lets the merge through otherwise;
- looks for `core.hooksPath` overridden through `git -c`, `--config-env` or `GIT_CONFIG_*` variables. Changing it with `git config` is still blocked;
- looks inside `bash -c`, `sh -c`, `zsh -c` and `eval` scripts, or past the `uv run`, `pnpm exec`, `npx`, `nohup` and `xargs` wrappers, and no longer treats an abbreviation of `--no-verify` as `--no-verify`.

These checks only caught commands written to get past a check, and the same goal is one script file away. They added parsing and false blocks without stopping a determined bypass.

## Consequences

- The command guard checks the git and gh commands as written at the top level of a command, after `cd`, environment assignments, `env`, `command` and `exec`.
- The adoption step `p4-guard-hook-bypasses` is dropped: it added the abbreviation and `GIT_CONFIG_*`/`--config-env` checks this record removes.
- R3 still holds for the plain forms: `--no-verify`, `commit -n` and `git config core.hooksPath` are blocked.
