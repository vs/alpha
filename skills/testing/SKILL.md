---
name: testing
description: Settle how a new project is tested in the alpha interview - the test levels each component gets (unit, integration, end-to-end, contract) and how tests trace back to the acceptance checks. Use only inside an alpha project interview (/alpha:new-project) or when the user asks to revisit the testing of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Testing

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. Tell the user that extending a generated project arrives in a later version of alpha, and stop.
- `areas.errors` isn't `"done"`: tell the user the earlier areas come first and to run `/alpha:new-project`, and stop.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

Tests get the same care as the code they test ("Tests are as important as the core"). Decide which levels of test each component needs, so effort matches risk: unit tests always, and more where a component talks to other things or users depend on whole flows. Each level's tests live under `tests/<level>/` in the component. A test that covers an acceptance check names its requirement id (e.g. `R1`), so every check in the product brief traces to a test. The Stop hook already blocks a source change that comes with no test change.

## Fields this area settles

- `testing.components[].name` - one entry per component, by name.
- `testing.components[].levels` - from `unit`, `integration`, `end-to-end`, `contract`; always includes `unit`, each level once.
- `areas.testing` - `"in_progress"` while you work, `"done"` at the end.
- `decisions[]` - one entry with `"area": "testing"`.

## Questions

Run this with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as one round.

- **Levels per component** - recommend `defaults.testing.levels[kind]` for each component, in one question, then adjust:
  - add `integration` when the component makes network calls or stores data (`traits.network_calls`, `traits.persisted_data`);
  - add `contract` for each component on either side of a call in `architecture.components[].calls` (only possible when components talk);
  - keep `end-to-end` for the component users drive (UI, CLI), testing whole flows from the acceptance checks.

  Explain each level in a few words: `unit` (one piece, no I/O), `integration` (with its real database, files or services), `end-to-end` (a whole user flow), `contract` (both sides keep to the contract file). Restate the acceptance convention in one line.

When a kind's levels differ from the default (not just this project's additions above), follow the grilling skill's override protocol (key `testing.levels.<kind>`, e.g. `testing.levels.backend`).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "testing": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` and `decisions` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `testing` set to `"in_progress"`.
3. When the user confirms the area, save the `testing` object `{"components": [{"name", "levels"}]}`, with one entry per component. Keep the exact field names.
4. In the same call, save `decisions` with one entry for this area, replacing any earlier one with `"area": "testing"`:
   `{"area": "testing", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` names the levels (e.g. "Unit, integration and end-to-end tests"); `context` is where the risk is; `decision` gives each component's levels; `consequences` says how tests trace to requirements, plus any defaults wish from the override protocol.
5. In the same call, save `areas` with `testing` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area testing`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
