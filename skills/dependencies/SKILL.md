---
name: dependencies
description: Settle a new project's dependency policy in the alpha interview - how dependencies are kept up to date and how often, on top of the always-on rules for adding and pinning them. Use only inside an alpha project interview (/alpha:new-project) or when the user asks to revisit the dependency policy of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Dependencies

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. Tell the user that extending a generated project arrives in a later version of alpha, and stop.
- `areas.security` isn't `"done"`: tell the user the earlier areas come first and to run `/alpha:new-project`, and stop.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

Two dependency rules are always on and need no answers: every new dependency gets a row in `docs/dependencies.md` with the reason (the Stop hook blocks a lockfile change without one), and lockfiles pin every version (only the package manager changes them; Claude can't edit them by hand). This area decides how upgrades happen, so pinned versions don't quietly rot.

## Fields this area settles

- `dependencies.updates` - `"dependabot"` or `"manual"`.
- `dependencies.schedule` - `"daily"`, `"weekly"` or `"monthly"`.
- `areas.dependencies` - `"in_progress"` while you work, `"done"` at the end.
- `decisions[]` - one entry with `"area": "dependencies"`.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it). Both questions are independent, so ask them in one round.

- **Updates** - recommend `defaults.dependencies.updates`. Explain in one line each:
  - `dependabot` - GitHub opens update pull requests for each component's dependencies and for the actions CI uses (keeping exactly pinned ones current). CI checks each one before it merges. alpha writes `.github/dependabot.yml`; it only takes effect once the repository is on GitHub.
  - `manual` - someone checks for updates on the schedule below.
- **Schedule** - recommend `defaults.dependencies.schedule`. Explain: more often means smaller, easier updates; less often means fewer pull requests to review.

Restate the two always-on rules in one line before the round. When an answer differs from a default, follow the grilling skill's override protocol (keys `dependencies.updates`, `dependencies.schedule`).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "dependencies": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` and `decisions` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `dependencies` set to `"in_progress"`.
3. When the user confirms the area, save the `dependencies` object `{"updates", "schedule"}`. Keep the exact field names.
4. In the same call, save `decisions` with one entry for this area, replacing any earlier one with `"area": "dependencies"`:
   `{"area": "dependencies", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` names the choice (e.g. "Weekly Dependabot updates"); `context` is how many toolchains drift; `decision` gives the tool and schedule; `consequences` says who reviews updates and how they're checked, plus any defaults wish from the override protocol.
5. In the same call, save `areas` with `dependencies` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area dependencies`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
