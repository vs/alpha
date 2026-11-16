# Dependencies

## Before you start

`/alpha:install` reads this guide for a new project's or an adoption's interview, and `/alpha:extend` when a change revisits this area. `<target>` is their target folder; the answers live in `<target>/.claude/alpha/project.json`. Their rules win over this guide's where they differ. When the user asks to revisit this area outside them, run `/alpha:extend` with the request.

## Purpose

Two dependency rules are always on and need no answers: every new dependency gets a row in `docs/alpha/dependencies.md` with the reason (the Stop hook blocks a lockfile change without one), and lockfiles pin every version (only the package manager changes them; Claude can't edit them by hand). This area decides how upgrades happen, so pinned versions don't quietly rot.

## Fields this area settles

- `dependencies.updates` - `"dependabot"` or `"manual"`.
- `dependencies.schedule` - `"daily"`, `"weekly"` or `"monthly"`.
- `dependencies.cooldown_days` - whole days, 0 or more; optional. When left out, alpha uses `defaults.dependencies.cooldown_days`.
- `areas.dependencies` - `"in_progress"` while you work, `"done"` at the end.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it). The questions are independent, so ask them in one round.

- **Updates** - recommend `defaults.dependencies.updates`. Explain in one line each:
  - `dependabot` - GitHub opens update pull requests for each component's dependencies and for the actions CI uses (keeping exactly pinned ones current). CI checks each one before it merges. alpha writes `.github/dependabot.yml`; it only takes effect once the repository is on GitHub.
  - `manual` - someone checks for updates on the schedule below.
  - With `dependabot`, updates wait `cooldown_days` days after a release, so a compromised version is usually caught first.
- **Schedule** - recommend `defaults.dependencies.schedule`. Explain: more often means smaller, easier updates; less often means fewer pull requests to review.
- **Cooldown** - recommend `defaults.dependencies.cooldown_days`. Explain: updates wait that many days after a release, so a compromised version is usually caught first; 0 means no delay.

Restate the two always-on rules in one line before the round. When an answer differs from a default, follow the grilling skill's override protocol (keys `dependencies.updates`, `dependencies.schedule`, `dependencies.cooldown_days`).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "dependencies": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `dependencies` set to `"in_progress"`.
3. When the user confirms the area, save the `dependencies` object `{"updates", "schedule", "cooldown_days"}`. Keep the exact field names.
4. In the same call, save `areas` with `dependencies` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area dependencies`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
