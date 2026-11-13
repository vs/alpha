---
name: testing
description: Settle how a new project is tested in the alpha interview - the test levels each component gets (unit, integration, end-to-end, contract), how tests trace back to the acceptance checks, and whether the project is tested exhaustively. Use only inside an alpha project interview (/alpha:new-project) or alpha:extend or /alpha:adopt or when the user asks to revisit the testing of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Testing

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. If the `alpha:extend` skill sent you here, go on as it says. Otherwise invoke `alpha:extend` with the Skill tool and follow it; it brings you back here.
- project.json has an `adoption` key and no `manifest`: `alpha:adopt` is bringing an existing repo in. Go on as it says; its rules win over this skill's, and don't point to `/alpha:new-project` afterwards.
- `areas.errors` isn't `"done"`: tell the user the earlier areas come first and to run `/alpha:new-project`, and stop.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

Tests get the same care as the code they test ("Tests are as important as the core"). Decide which levels of test each component needs, so effort matches risk: unit tests always, and more where a component talks to other things or users depend on whole flows. Each level's tests live under `tests/<level>/` in the component. A test that covers an acceptance check names its requirement id (e.g. `R1`), so every check in the product brief traces to a test. The Stop hook already blocks a source change that comes with no test change.

A project that must not fail (a library or tool others build on, a data store, anything handling money or safety) can opt into **exhaustive testing**, modeled on [how SQLite is tested](https://www.sqlite.org/testing.html). It switches on the "Exhaustive testing" principle: every branch taken both ways, every failure path forced by an injected failure, fuzz or property-based tests for whatever reads outside input, limits tested on both sides, a failing test before each bug fix, invariants asserted in the code, and tests run on the build that ships. The reviewer checks every change against it, and pull requests must cover every line and branch they change. It takes several times more test code than product code, so it is off unless the user wants it.

## Fields this area settles

- `testing.components[].name` - one entry per component, by name.
- `testing.components[].levels` - from `unit`, `integration`, `end-to-end`, `contract`; always includes `unit`, each level once.
- `testing.diff_coverage` - optional whole percentage, 0 to 100: the share of the lines a pull request changes that its tests must cover (0 turns the check off). Leave it out to take `defaults.testing.diff_coverage`. Only components whose recipe has a `coverage` command are checked.
- `testing.exhaustive` - optional `true` or `false`: whether the project is tested exhaustively. Leave it out to take `defaults.testing.exhaustive`. When it is on, the diff coverage check is 100% of changed lines and branches, so leave `diff_coverage` out.
- `testing.run` - optional, `"at-merge"` or `"at-stop"`: when alpha's hooks run a component's full test suite. `at-merge`: once, before Claude's work reaches main (a push to main, or merging a pull request). `at-stop`: every time Claude finishes a turn in which the component changed, which suits a suite that takes seconds. Leave it out to take `defaults.testing.run`.
- `areas.testing` - `"in_progress"` while you work, `"done"` at the end.
- `decisions[]` - one entry with `"area": "testing"`.

## Questions

Run this with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as one round.

- **Levels per component** - recommend `defaults.testing.levels[kind]` for each component, in one question, then adjust:
  - add `integration` when the component makes network calls or stores data (`traits.network_calls`, `traits.persisted_data`);
  - add `contract` for each component on either side of a call in `architecture.components[].calls` (only possible when components talk);
  - keep `end-to-end` for the component users drive (UI, CLI), testing whole flows from the acceptance checks.

  Explain each level in a few words: `unit` (one piece, no I/O), `integration` (with its real database, files or services), `end-to-end` (a whole user flow), `contract` (both sides keep to the contract file). Restate the acceptance convention in one line.
- **Exhaustive testing** - ask whether to test this project exhaustively, with one line on what it demands and what it costs (see Purpose). Recommend `defaults.testing.exhaustive`, or yes when the user already asked for it (e.g. "extremely well tested", "tested like SQLite").
- **Diff coverage** - say in one line that pull requests must cover at least `diff_coverage`% of the lines they change (0 turns this off), and recommend `defaults.testing.diff_coverage`. Ask it in the same round, as the threshold that holds if exhaustive testing stays off; when the user turns exhaustive testing on, pull requests must cover every line and branch they change, and `diff_coverage` isn't saved.
- **When the full suite runs** - say in one line that alpha's hooks run the full test suite once, before Claude's work reaches main, and that `at-stop` runs it after every turn instead (worth it only while the suite takes seconds). Recommend `defaults.testing.run`.

When a kind's levels differ from the default (not just this project's additions above), follow the grilling skill's override protocol (key `testing.levels.<kind>`, e.g. `testing.levels.backend`). An answer for `diff_coverage`, `exhaustive` or `run` that differs from the default goes through it too, with key `testing.diff_coverage`, `testing.exhaustive` or `testing.run`.

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "testing": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` and `decisions` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `testing` set to `"in_progress"`.
3. When the user confirms the area, save the `testing` object `{"components": [{"name", "levels"}]}`, with one entry per component, plus `"diff_coverage": <0-100>`, `"exhaustive": <true|false>` and `"run": "<at-merge|at-stop>"`, each only when the user chose a value other than the default. Keep the exact field names.
4. In the same call, save `decisions` with one entry for this area, replacing any earlier one with `"area": "testing"`:
   `{"area": "testing", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` names the levels (e.g. "Unit, integration and end-to-end tests"); `context` is where the risk is; `decision` gives each component's levels and says whether testing is exhaustive; `consequences` says how tests trace to requirements, plus any defaults wish from the override protocol.
5. In the same call, save `areas` with `testing` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area testing`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
