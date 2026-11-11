---
name: performance
description: Settle a new project's performance budgets in the alpha interview - for each component, the metrics it must stay within and how each is measured. Use only inside an alpha project interview (/alpha:new-project) or alpha:extend or when the user asks to revisit the performance budgets of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Performance

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. If the `alpha:extend` skill sent you here, go on as it says. Otherwise invoke `alpha:extend` with the Skill tool and follow it; it brings you back here.
- `areas.accessibility` isn't `"done"`: tell the user the earlier areas come first and to run `/alpha:new-project`, and stop.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

A budget that is written down and checked stops slow regressions from piling up ("Performance budgets"). The principle applies only to components that get budgets here, so a component without one carries no ceremony. Projects with budgets or an expected load get `docs/performance.md`; the reviewer holds each component to its budgets and judges scale against the expected load.

## Fields this area settles

- `performance.expected_load` - in plain words, the load the product must hold, e.g. `"one person running it on a laptop"`, `"about 50 concurrent users, 10 requests a second at peak"`.
- `performance.components[].name` - one entry per component, by name.
- `performance.components[].budgets[].metric` - what is measured, e.g. `"p95 response time"`, `"JavaScript bundle"`, `"startup"`.
- `performance.components[].budgets[].limit` - the limit, with its unit, e.g. `"300 ms"`, `"200 KB gzipped"`.
- `performance.components[].budgets[].measured_by` - how and where it is measured, e.g. `"k6 in CI against staging"`.
- `areas.performance` - `"in_progress"` while you work, `"done"` at the end.
- `decisions[]` - one entry with `"area": "performance"`.

A component's `budgets` may be `[]`: no budgets, so the principle stays off for it.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as one round covering every component:

- **Expected load** - draft it from identity (who uses it and how) and the build area (what is deployed), e.g. "one person running a script" for a local tool. Explain in one line: reviews judge scale against it (a race or a query per item matters only when the load reaches it), and a `shortcut:` comment names the load past which it stops holding.
- **Budgets** - draft each component's from `defaults.performance.budgets[kind]` (each entry reads `"<metric> < <limit>"`), then adjust them to the requirements from identity (e.g. a requirement about slow connections tightens the bundle; a batch job may need none). Say which come from the defaults.
- **Measured by** - for each budget, recommend a tool that fits the component's stack and the CI from the build area; look it up, never assume.
- Offer "no budgets" for a component where nothing is worth measuring yet, and say what it means: the principle stays off for it.

When a component's budgets differ from its kind's defaults, follow the grilling skill's override protocol (key `performance.budgets.<kind>`, with the new list in the same `"<metric> < <limit>"` form).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "performance": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` and `decisions` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `performance` set to `"in_progress"`.
3. When the user confirms the area, save the `performance` object `{"expected_load", "components": [{"name", "budgets": [{"metric", "limit", "measured_by"}]}]}`, with one entry per component. Keep the exact field names.
4. In the same call, save `decisions` with one entry for this area, replacing any earlier one with `"area": "performance"`:
   `{"area": "performance", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` names the budgets (e.g. "Response time and bundle budgets"); `context` is the requirement that motivates them; `decision` gives each component's budgets and how they're measured; `consequences` says that breaking a budget needs a fix or a decision record, plus any defaults wish from the override protocol.
5. In the same call, save `areas` with `performance` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area performance`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
