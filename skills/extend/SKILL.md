---
name: extend
description: Change a project alpha generated - add, remove, rename or move a component, switch on an area that didn't apply, or revisit an area's decisions - re-asking only what the change affects and merging the result without overwriting the user's edits. Use when the user asks to change a project alpha generated, or when an alpha area skill sends you here. Run as /alpha:extend [what to change].
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Extend

Change a project alpha already generated: re-ask only what the change affects, merge the result into alpha's files without overwriting the user's edits, bootstrap anything new and commit. It never writes app code.

What to change: `$ARGUMENTS`

Save answers only with `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '<object>'`: one line, the JSON typed straight into the command, never a heredoc or a python3 script (Claude Code would ask on every save). Each top-level key sent replaces that key in project.json.

## 1. Target and checks

`<target>` is the current working directory.

- No `<target>/.claude/alpha/project.json`: say alpha only changes projects it generated, and that existing projects are out of scope for v1. Stop.
- project.json has no `manifest` key: the interview never finished. Point to `/alpha:new-project`. Stop.
- Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target> --dry-run` first. If it lists changes, an earlier change was never applied: show them and ask whether to apply them now; on yes, go to step 4 (show and confirm), then step 5; on no, stop.
- If it refuses because an update is waiting to be committed ("Merge any proposals in .claude/alpha/state/update/, run commit-update"), that update is already applied. Tell the user, merge any proposals as step 5 says, then run step 7's commit-update. Don't rerun update first. Then continue.

## 2. What changes

Take the request from `$ARGUMENTS`, or ask. Pick the area: `components` to add, remove, rename or move a component; otherwise the area that owns the decision. Invoke its skill (`alpha:<area skill>`) with the Skill tool. These rules win over the area skill's own:

- Use the current answers as the recommendations and ask only what the change affects.
- Keep every other answer as it is.
- Keep every existing entry of `decisions` and `overrides` unchanged, and add one new decision for this change (`area` = the area; the title says what changed; the context says why). This overrides "replacing any earlier one". `answers write` replaces each top-level key, so send the whole `decisions` array: every existing entry verbatim, then the new one. Do the same for `overrides`.
- Don't tell the user to run `/alpha:new-project` afterwards; when the area skill is done, continue with step 3.
- Moving a component's folder (e.g. a root CLI moving to `cli/` so a second component can be added) means moving app code, which alpha doesn't do. The user moves it with `git mv` and commits (you can do that as ordinary work, outside alpha's files), then continues.

## 3. Loop until valid

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target> --dry-run` and read the first line it prints.

- "Revisit the <area> area: …": invoke that area's skill for this change, then rerun. If the same message comes back twice, show it to the user and ask what to change instead of invoking the area again.
- "Fix .claude/alpha/project.json: …": fix it with one one-line `answers write` call, never a heredoc or python3 script (ask the user when the fix needs a decision), then rerun.
- After a component change, also offer the git area, so the commit scopes cover the component.

Go on when it lists the changes with no problem.

## 4. Show and confirm

Summarize the list. Show the diffs of CLAUDE.md, `docs/principles.toml` and the docs, and say which files will need a hand merge (each shows as `<path>: merge by hand; proposal: .claude/alpha/state/update/<path>`). Write nothing to generated files (CLAUDE.md, docs, principles, component configs) until the user confirms; the answers in project.json are already saved.

## 5. Apply

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target>`.

- For each conflict, read its proposal under `.claude/alpha/state/update/`. It holds the user's version, the version before, and alpha's. Edit the real file so it keeps the user's edits and adds alpha's change, never just alpha's side, and show the user the result.
- Stale files: ask before deleting any. commit-update commits only alpha's writes, so `git rm` each one the user lets go and commit the deletion yourself after step 7 (e.g. `docs: Remove CHANGELOG.md`, body wrapped at 72).

## 6. Bootstrap

For each new component, run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" bootstrap <target> --component <name>`.

## 7. Commit

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" commit-update <target> --trailer "<line>"` with one `--trailer` per attribution line from this session's Claude Code attribution instructions for commits, as new-project does for its commits. Never invent co-author lines. Relay its notes: a file whose "alpha's change wasn't merged in (proposal: …)" (merge it by hand), that the reviewer will look at alpha's changes at the next Stop, and that a root component's bootstrap files must be committed by hand.

## 8. Report

Say what changed and which commits were made. Tell the user to start a new Claude Code session (or run `/clear`) so Claude loads the updated rules. If a recipe was drafted, offer to save it as new-project does: `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" recipe save <target> <stack> --trailer "<line>"`.
