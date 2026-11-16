---
name: update
description: Bring a project alpha installed up to a newer alpha kit, or apply answers saved but not yet applied - merging alpha's changes into its files without overwriting the user's edits, resolving each conflict by hand, and committing. Use when the user asks to update alpha in a project. Run as /alpha:update [folder].
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Update

Bring alpha's files to the answers and to this kit. alpha merges its changes against the render it last committed; where they overlap a user's edit, it leaves a proposal, and this skill merges that by hand. It never writes app code.

Folder argument: `$ARGUMENTS`

## 1. Target

`<target>` is the folder given above, else the current working directory. Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" status <target>`; anything but `installed` or `hooks-off` means alpha isn't installed there: point to `/alpha:install` and stop.

## 2. Preview

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target> --dry-run`.

- It prints nothing to change: tell the user the project is up to date, and stop.
- It refuses because an update is waiting to be committed: that update is applied already. Merge its proposals as step 3 says, then commit as step 5 says.
- Otherwise summarize the list: the upgrade its first line names (e.g. `(kit 1.0.0 to 1.1.0)`), the files alpha adds, changes, merges and deletes, and each `conflict` that needs a hand merge. Show the diffs of `CLAUDE.md`, `CONTRIBUTING.md` and `docs/alpha/principles.toml`. Ask whether to apply it, and wait for a clear yes.

## 3. Apply and merge

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target>`. For each conflict, printed as `<path>: merge by hand; proposal: .claude/alpha/state/update/<path>`, read that proposal: it holds the user's version, the version before, and alpha's. Edit the real file so it keeps both sides: every edit of the user's, and alpha's change added. Never take only alpha's side. Show the user each merged file.

## 4. Bootstrap

For each component the update lists as new, run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" bootstrap <target> --component <name>`, telling the user first that it installs the toolchain and runs the checks.

## 5. Commit

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" commit <target> --trailer "<line>"` with one `--trailer` per attribution line from this session's Claude Code attribution instructions for commits. Never invent co-author lines. Relay its notes: a file whose "alpha's change wasn't merged in (proposal: …)" still needs the merge.

Report what changed and the commits, and tell the user to start a new Claude Code session (or run `/clear`) so Claude loads the updated hooks and rules.
