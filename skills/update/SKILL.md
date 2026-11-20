---
name: update
description: Keep a project alpha installed current - with no request, bring alpha's files to the answers and to a newer alpha kit; with one, add, remove, rename or move a component, change an install area's answer, or settle a product area (requirements, architecture, errors, design language, UI, accessibility, observability, data, performance, auth) - re-asking only what the request affects, merging without overwriting the user's edits, resolving each conflict by hand, and committing. Use when the user asks to update alpha, change a project alpha installed, or settle a product area. Run as /alpha:update [request].
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Update

Keep a project alpha installed current. With no request, bring alpha's files to the answers and to this kit. With one, first change what it names: a component, an install area's answer, or a product area to settle. alpha then merges its changes against the render it last committed; where they overlap a user's edit, it leaves a proposal, and this skill merges that by hand. It never writes app code.

Request: `$ARGUMENTS`

Save answers only with `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '<object>'`: one line, the JSON typed straight into the command, never a heredoc or a python3 script (Claude Code would ask on every save). Each top-level key sent replaces that key in project.json.

Ask one question at a time, as the `alpha:grilling` skill's "Rounds" says: a choice, a yes or no or a confirmation in the `AskUserQuestion` dialog when that tool is in your tool list, a draft for the user to edit in plain text.

## 1. Target and checks

`<target>` is the current working directory; a folder path in `$ARGUMENTS` (absolute, `~/…` or `./…`) is the target, not the request, and an area or a component name is never the target, even where a folder has that name. Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" status <target>`:

- `installed` or `hooks-off`: go on.
- Any other state: alpha isn't installed there, or its install isn't finished. Point to `/alpha:install`, and stop.

With a request, run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target> --dry-run` before changing any answer, and read it as "Reading a dry run" says. When it lists changes, an earlier change was never applied or this kit is newer: tell the user they are applied together with the request, and step 5 shows them all. If the user doesn't want an earlier answer change, save the earlier answers back as step 5 says for a no, then go on.

## Reading a dry run

Each `update <target> --dry-run` in this skill lists the changes, prints that there is nothing to change, or refuses. Read the first line it prints:

- It refuses because an update is waiting to be committed: that update is applied already. Merge its proposals as step 6 says, commit as step 8 says, then go on where you were.
- "Revisit the `<area>` area: …": read that area's guide for this change, then rerun. If the same message comes back twice, show it to the user and ask what to change instead of revisiting the area again.
- "Fix .claude/alpha/project.json: …": fix it with one one-line `answers write` call (ask the user when the fix needs a decision; an area left `in_progress` is finished from its guide first), then rerun.
- Any other refusal (such as files to commit first): show it to the user and do what it says, then rerun.

## 2. Route the request

| Request | Job |
|---|---|
| Empty | Sync: go to step 5. |
| A product area: requirements (target users, requirements with acceptance checks, domain jargon), architecture (with the glossary), errors, design language, UI, accessibility, observability, data, performance, auth; e.g. "let's specify performance" | Settle it: step 3. |
| A component or an install answer: add, remove, rename or move a component, or an answer of identity, components, testing, documentation, build, security, dependencies, releases, git or agent workflow; e.g. "add a worker component", "test exhaustively" | Change it: step 4. |
| Several of these | Each job in turn, in the order given; then steps 5 to 9 once. |
| Unclear | Ask one question: which area it belongs to, recommending one. Then route the answer. |

## 3. Settle a product area

For each area the request names, in the order given (an area that is `done` is revisited: its answers are the recommendations):

1. Read its guide, `${CLAUDE_PLUGIN_ROOT}/skills/install/areas/<area>.md`, with the Read tool.
2. Research first: what the project's code and docs already imply for it (a doc the project has for the area, the stack's usual choice, an approved spec under `docs/alpha/features/`, `bug-fixes/`, `refactorings/` or `perf/`), and the kit default from `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" defaults show --json`. Answers a feature spec already records are the user's: save them without asking again.
3. Lay out two or three options for its main decision, each in a line with its trade-off, recommending one.
4. Settle the guide's questions with `alpha:grilling`, save with `answers write`, mark the area `done`, and run the guide's check until it prints `ok`.

## 4. Change a component or an install answer

Pick the install area: `components` to add, remove, rename or move a component; else the area that owns the answer. Read its guide, `${CLAUDE_PLUGIN_ROOT}/skills/install/areas/<area>.md`, with the Read tool, and follow it with `<target>` as its target. These rules win over the guide's own:

- Use the current answers as the recommendations and ask only what the change affects. Keep every other answer as it is.
- Keep every existing entry of `overrides` unchanged. `answers write` replaces each top-level key, so send the whole `overrides` array: every existing entry verbatim, plus any new one. An override for a removed or renamed component stops applying; if it should carry over, add a new override for the new name, with its reason. Say why the change was made in the message of the commit step 8 makes.
- Moving a component's folder (e.g. a root CLI moving to `cli/` so a second component can be added) means moving app code, which alpha doesn't do. The user moves it with `git mv` and commits (you can do that as ordinary work), then continues.

Then run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target> --dry-run` until it lists the changes with no problem, handling each refusal as "Reading a dry run" says. After a component change, also offer the git area, so the commit scopes cover the component.

## 5. Preview and confirm

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target> --dry-run`, and read it as "Reading a dry run" says.

- It prints nothing to change: tell the user the project is up to date, and stop.
- Otherwise summarize the list: the upgrade its first line names (e.g. `(kit 1.0.0 to 1.1.0)`), the files alpha adds, changes, merges and deletes, and each `conflict  <path>` that needs a hand merge. Show the diffs of `CLAUDE.md`, `CONTRIBUTING.md`, `docs/alpha/principles.toml` and `docs/alpha/specification.md`: for a settled area, the sections and principles it changes: read them and check they say what the user settled, and when they don't, revise the answers and preview again before asking. When a request comes with an upgrade, say that the list holds files the request doesn't touch. Ask whether to apply it, and wait for a clear yes. Write nothing to alpha's files before it; the answers in project.json are already saved. On a no, ask what to change: revise the answers with `answers write` and preview again, or put the earlier answers back, reading them from `git show HEAD:.claude/alpha/project.json` and sending each changed top-level key with one `answers write`, so the next request doesn't find them waiting.

## 6. Apply and merge

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target>`.

- For each conflict, printed as `<path>: merge by hand; proposal: .claude/alpha/state/update/<path>`, read that proposal: it holds the user's version, the version before, and alpha's. Edit the real file so it keeps both sides: every edit of the user's, and alpha's change added. Never take only alpha's side. Show the user each merged file.
- Stale files: ask before deleting any. Step 8's commit takes only alpha's writes, so `git rm` each one the user lets go and commit the deletion yourself after step 8: a conventional message (e.g. `docs: Remove CHANGELOG.md`; description at most 50 chars, imperative, capitalized, no trailing period; body lines at most 72 chars), ending with the same attribution lines as step 8, as trailer lines.

## 7. Bootstrap

For each new component the update lists, and each component whose `path` differs from its `path` in `git show HEAD:.claude/alpha/project.json` (moved by this request or by an earlier run step 1 picked up), run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" bootstrap <target> --component <name>` (`git mv` leaves ignored env folders such as node_modules or .venv behind). Tell the user first that this installs the component's toolchain, runs its tests, then runs the whole-repo checks (`mise run ci`), and can take a few minutes. Those checks can fail on the user's own files; show the message (it names `mise run check:<id>` to rerun one check), fix the cause with them, and rerun the step.

## 8. Commit

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" commit <target> --trailer "<line>"` with one `--trailer` per attribution line from this session's Claude Code attribution instructions for commits. Never invent co-author lines. Relay its notes: a file whose "alpha's change wasn't merged in (proposal: …)" still needs the merge (the proposal is kept until you delete it), and a root component's bootstrap files must be committed by hand.

## 9. Report

Say what changed and which commits were made. Name the product areas still open, each with its `/alpha:update <area>` request. Tell the user to start a new Claude Code session (or run `/clear`) so Claude loads the updated hooks and rules. If a recipe was drafted, offer to save it: `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" recipe save <target> <stack>`.
