---
name: extend
description: Change a project alpha installed - add, remove, rename or move a component, or revisit an install area's answers - re-asking only what the change affects and merging the result without overwriting the user's edits. Use when the user asks to change a project alpha installed. Run as /alpha:extend [what to change].
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Extend

Change a project alpha installed: re-ask only what the change affects, merge the result into alpha's files without overwriting the user's edits, bootstrap anything new and commit. It never writes app code.

What to change: `$ARGUMENTS`

Save answers only with `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '<object>'`: one line, the JSON typed straight into the command, never a heredoc or a python3 script (Claude Code would ask on every save). Each top-level key sent replaces that key in project.json.

Ask one question at a time, as the `alpha:grilling` skill's "Rounds" says: a choice, a yes or no or a confirmation in the `AskUserQuestion` dialog when that tool is in your tool list, a draft for the user to edit in plain text.

## 1. Target and checks

`<target>` is the current working directory; a folder in `$ARGUMENTS` is the target, not the change. Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" status <target>`:

- `installed` or `hooks-off`: go on.
- Any other state: alpha isn't installed there, or its install isn't finished. Point to `/alpha:install`, and stop.

Then run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target> --dry-run`. If it lists changes, an earlier change was never applied: show them and ask whether to apply them now; on yes, go to step 4, then step 5; on no, stop. If it refuses because an update is waiting to be committed, that update is applied already: merge its proposals as step 5 says, run step 7's commit, then go on to step 2 for the new request.

## 2. What changes

Take the request from `$ARGUMENTS`, or ask. A product area (requirements, architecture, errors, design language, UI, accessibility, observability, data, performance, auth) is `/alpha:specify`'s: point to `/alpha:specify <area>` and stop. Otherwise pick the install area: `components` to add, remove, rename or move a component; else the area that owns the answer. Read its guide, `${CLAUDE_PLUGIN_ROOT}/skills/install/areas/<area>.md`, with the Read tool, and follow it with `<target>` as its target. These rules win over the guide's own:

- Use the current answers as the recommendations and ask only what the change affects. Keep every other answer as it is.
- Keep every existing entry of `overrides` unchanged. `answers write` replaces each top-level key, so send the whole `overrides` array: every existing entry verbatim, plus any new one. An override for a removed or renamed component stops applying; if it should carry over, add a new override for the new name, with its reason. Say why the change was made in the message of the commit step 7 makes.
- Moving a component's folder (e.g. a root CLI moving to `cli/` so a second component can be added) means moving app code, which alpha doesn't do. The user moves it with `git mv` and commits (you can do that as ordinary work), then continues.

## 3. Loop until valid

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target> --dry-run` and read the first line it prints.

- "Revisit the `<area>` area: …": read that area's guide for this change, then rerun. If the same message comes back twice, show it to the user and ask what to change instead of revisiting the area again.
- "Fix .claude/alpha/project.json: …": fix it with one one-line `answers write` call (ask the user when the fix needs a decision), then rerun.
- Any other refusal (such as files to commit first): show it to the user and do what it says, then rerun.
- After a component change, also offer the git area, so the commit scopes cover the component.

Go on when it lists the changes with no problem.

## 4. Show and confirm

Summarize the list. Show the diffs of CLAUDE.md, `docs/alpha/principles.toml` and the docs, and say which files will need a hand merge (each `conflict  <path> (your edits overlap alpha's change: merge by hand)`). When the first line names an upgrade, such as `(kit 1.0.0 to 1.1.0)`, the change also brings the project to this kit, so it lists files the request doesn't touch: tell the user so before they confirm. Write nothing to alpha's files until the user confirms; the answers in project.json are already saved.

## 5. Apply

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target>`.

- For each conflict (printed as `<path>: merge by hand; proposal: .claude/alpha/state/update/<path>`), read that proposal. It holds the user's version, the version before, and alpha's. Edit the real file so it keeps the user's edits and adds alpha's change, never just alpha's side, and show the user the result.
- Stale files: ask before deleting any. Step 7's commit takes only alpha's writes, so `git rm` each one the user lets go and commit the deletion yourself after step 7: a conventional message (e.g. `docs: Remove CHANGELOG.md`; description at most 50 chars, imperative, capitalized, no trailing period; body lines at most 72 chars), ending with the same attribution lines as step 7, as trailer lines.

## 6. Bootstrap

For each new or moved component, run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" bootstrap <target> --component <name>` (`git mv` leaves ignored env folders such as node_modules or .venv behind). Tell the user first that this installs the component's toolchain, runs its tests, then runs the whole-repo checks (`mise run ci`), and can take a few minutes. Those checks can fail on the user's own files; show the message (it names `mise run check:<id>` to rerun one check), fix the cause with them, and rerun the step.

## 7. Commit

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" commit <target> --trailer "<line>"` with one `--trailer` per attribution line from this session's Claude Code attribution instructions for commits. Never invent co-author lines. Relay its notes: a file whose "alpha's change wasn't merged in (proposal: …)" (merge it by hand; the proposal is kept until you delete it), and that a root component's bootstrap files must be committed by hand.

## 8. Report

Say what changed and which commits were made. Tell the user to start a new Claude Code session (or run `/clear`) so Claude loads the updated rules. If a recipe was drafted, offer to save it: `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" recipe save <target> <stack>`.
