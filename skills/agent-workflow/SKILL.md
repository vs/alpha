---
name: agent-workflow
description: Settle how agents' work gets reviewed in a new alpha project - review mode, size thresholds that trigger a review, and extra risky paths. Use only inside an alpha project interview (/alpha:new-project) or alpha:extend or when the user asks to revisit the agent workflow of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Agent workflow

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. If the `alpha:extend` skill sent you here, go on as it says. Otherwise invoke `alpha:extend` with the Skill tool and follow it; it brings you back here.
- `areas.git` isn't `"done"`: tell the user the earlier areas come first and to run `/alpha:new-project`, and stop.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

Decide when the agents' changes get a judgment-based review against the project's principles: once, before they reach main; in batches once a change grows past a size threshold or touches a risky path; or after every task. The cheap mechanical checks (hooks on every edit, stop and commit) are always on and need no answers here.

The project gets a principles-reviewer agent that reads these settings from the principles file. It runs before work reaches main (a push to main, or merging a pull request) in every mode; in batched mode also when the unreviewed changes cross the thresholds or touch a risky path, and in every-task mode after every task. Its findings stop Claude from finishing until they're fixed or accepted (Claude may accept one it disproves, except on a risk path, where only the user does), and every acceptance is recorded in the decision log.

## Fields this area settles

- `agent_workflow.review_mode` - `"at-merge"`, `"batched"` or `"every-task"`.
- `agent_workflow.max_lines` - a whole number above 0.
- `agent_workflow.max_files` - a whole number above 0.
- `agent_workflow.extra_risk_paths` - a list of globs, often empty.
- `areas.agent_workflow` - `"in_progress"` while you work, `"done"` at the end.
- `decisions[]` - one entry with `"area": "agent_workflow"`.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as a design tree in rounds.

Round 1:

- **Review mode** - recommend `defaults.review.mode`. Explain each in one line: `at-merge` reviews once, when the work is ready to reach main (fits workflows like pstack that verify the finished change once); `batched` also reviews during the work, once the pending changes cross a threshold or touch a risky path; `every-task` reviews after every finished task (slowest, but nothing waits until the end).
- **Extra risk paths** - show the kit's risk paths from `defaults.review.risk_paths` (changes there always trigger a review) and recommend adding none. Explain in one line: add globs for files where a mistake is costly, e.g. `api/billing/**`. Use `**` for any depth; write each alternative as its own glob, no `{a,b}` braces.

Round 2 (only when the mode is `batched`):

- **Max lines** - recommend `defaults.review.max_lines`. Explain in one line: a review starts once this many lines have changed since the last one (tests and docs, `defaults.review.exclude`, don't count).
- **Max files** - recommend `defaults.review.max_files`. Explain in one line: a review starts once this many files have changed, even when each change is small.

With `at-merge` or `every-task`, still record `max_lines` and `max_files` at the defaults without asking, so switching to `batched` later needs no new decision.

When an answer differs from a default, follow the grilling skill's override protocol (keys `review.mode`, `review.max_lines`, `review.max_files`; extra risk paths are per project, so they're recorded in the decision without asking).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "agent_workflow": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` and `decisions` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `agent_workflow` set to `"in_progress"`.
3. When the user confirms the area, save the `agent_workflow` object `{"review_mode", "max_lines", "max_files", "extra_risk_paths"}`. Keep the exact field names.
4. In the same call, save `decisions` with one entry for this area, replacing any earlier one with `"area": "agent_workflow"`:
   `{"area": "agent_workflow", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` names the choice (e.g. "Batched review"); `context` weighs review speed against unreviewed risk; `decision` gives the mode and thresholds; `consequences` says when agents stop for review, plus any defaults wish from the override protocol.
5. In the same call, save `areas` with `agent_workflow` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area agent_workflow`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
