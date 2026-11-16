---
name: specify
description: Settle one or more product areas of a project alpha installed - requirements, architecture, errors, design language, UI, accessibility, observability, data, performance or auth - researching what the code and docs already imply, laying out options and writing the result into docs/alpha/. Use only when the user asks to settle a product area. Run as /alpha:specify [areas].
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Specify

Settle the product areas the user names. Install leaves them open, since the user often can't know them yet; each one settled adds its section to `docs/alpha/specification.md` (or its own page under `docs/alpha/`) and switches on the principles it gates. Only this skill settles a product area, and only when the user asks.

Areas: `$ARGUMENTS`

## 1. Target and areas

`<target>` is the current working directory, or a folder named in `$ARGUMENTS`. Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" status <target>`; anything but `installed` or `hooks-off` means alpha isn't installed there: point to `/alpha:install` and stop.

Map the request to areas: `requirements` (target users, requirements with acceptance checks, domain jargon), `architecture` (with the glossary), `errors`, `design_language`, `ui`, `accessibility`, `observability`, `data`, `performance`, `auth`. When the request names none, list the open ones (from `areas` in `<target>/.claude/alpha/project.json`) and ask which. An area that is `done` is revisited: its answers are the recommendations. A change to an install area or a component is `/alpha:extend`'s: point there.

## 2. Each area

Save answers only with `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '<object>'`: one line, the JSON typed straight into the command, never a heredoc or a python3 script. Ask one question at a time, as the `alpha:grilling` skill's "Rounds" says.

For each area, in the order the user gave:

1. Read its guide, `${CLAUDE_PLUGIN_ROOT}/skills/specify/areas/<area>.md`, with the Read tool.
2. Research first: what the project's code and docs already imply for it (a doc the project has for the area, the stack's usual choice, an approved feature spec under `docs/alpha/features/`), and the kit default from `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" defaults show --json`. Answers a feature spec already records are the user's: save them without asking again.
3. Lay out two or three options for its main decision, each in a line with its trade-off, recommending one.
4. Settle the guide's questions with `alpha:grilling`, save with `answers write`, mark the area `done`, and run the guide's check until it prints `ok`.

## 3. Apply and commit

1. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target> --dry-run`, then show the user the sections and principles it changes and confirm.
2. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target>`. For each `merge by hand` line, merge the proposal as `/alpha:update` does: keep the user's edits and add alpha's change.
3. Read the new sections in `docs/alpha/specification.md` and the principles they switched on in `docs/alpha/principles.toml`, and check they say what the user settled.
4. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" commit <target> --trailer "<line>"` with one `--trailer` per attribution line from this session's Claude Code attribution instructions for commits. Never invent co-author lines.

Report the areas settled, the principles now active, the commits, and the areas still open.
