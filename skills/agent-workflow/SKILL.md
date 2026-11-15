---
name: agent-workflow
description: Settle which extra paths count as risky in a new alpha project - a review finding on one is accepted only by the user. Use only inside an alpha project interview (/alpha:new-project) or alpha:extend or /alpha:adopt or when the user asks to revisit the agent workflow of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Agent workflow

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs the setup areas in order, and stop.
- project.json has an `installed` key: alpha is installed. If the `alpha:extend` skill sent you here, go on as it says. Otherwise invoke `alpha:extend` with the Skill tool and follow it; it brings you back here.
- project.json has an `adoption` key and no `installed`: `alpha:adopt` is bringing an existing repo in. Go on as it says; its rules win over this skill's, and don't point to `/alpha:new-project` afterwards.
- `areas.git` isn't `"done"`: tell the user the earlier areas come first and to run `/alpha:new-project`, and stop.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

The principles-reviewer agent runs once, before work reaches main (a push to main, or merging a pull request). The cheap mechanical checks (hooks on every edit, at Stop and on commit) are always on and need no answers here. A finding on a risk path is accepted only by the user; Claude may accept another one it disproves, recorded as an `Accepts:` trailer in the commit that settles it. This area adds the project's own risk paths to the kit's.

## Fields this area settles

- `agent_workflow.extra_risk_paths` - a list of globs, often empty.
- `areas.agent_workflow` - `"in_progress"` while you work, `"done"` at the end.

## Questions

Run this with the `alpha:grilling` skill (invoke it with the Skill tool and follow it):

- **Extra risk paths** - show the kit's risk paths from `defaults.review.risk_paths` and recommend adding none. Explain in one line: add globs for files where a mistake is costly, e.g. `api/billing/**`. Use `**` for any depth; write each alternative as its own glob, no `{a,b}` braces. They are per project, so they don't go through the grilling skill's override protocol.

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "agent_workflow": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `agent_workflow` set to `"in_progress"`.
3. When the user confirms the area, save the `agent_workflow` object `{"extra_risk_paths"}`. Keep the exact field names.
4. In the same call, save `areas` with `agent_workflow` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area agent_workflow`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
