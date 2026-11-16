# Performance

## Before you start

`/alpha:update` reads this guide when the user asks to settle this area; it's a product area, which install leaves open. `<target>` is its target folder; the answers live in `<target>/.claude/alpha/project.json`. Its rules win over this guide's where they differ. Only `/alpha:update` settles a product area: when the user asks for it elsewhere, point to `/alpha:update <area>`.

## Purpose

A budget that is written down and checked stops slow regressions from piling up ("Performance budgets"). The principle applies only to components that get budgets here, so a component without one carries no ceremony. Projects with budgets or an expected load get a Performance section in `docs/alpha/specification.md`; the reviewer holds each component to its budgets and judges scale against the expected load.

## Fields this area settles

- `performance.expected_load` - in plain words, the load the product must hold, e.g. `"one person running it on a laptop"`, `"about 50 concurrent users, 10 requests a second at peak"`.
- `performance.components[].name` - one entry per component, by name.
- `performance.components[].budgets[].metric` - what is measured, e.g. `"p95 response time"`, `"JavaScript bundle"`, `"startup"`.
- `performance.components[].budgets[].limit` - the limit, with its unit, e.g. `"300 ms"`, `"200 KB gzipped"`.
- `performance.components[].budgets[].measured_by` - how and where it is measured, e.g. `"k6 in CI against staging"`.
- `areas.performance` - `"in_progress"` while you work, `"done"` at the end.

A component's `budgets` may be `[]`: no budgets, so the principle stays off for it.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as one round covering every component:

- **Expected load** - draft it from the requirements area (who uses it and how) and the build area (what is deployed), e.g. "one person running a script" for a local tool. Explain in one line: reviews judge scale against it (a race or a query per item matters only when the load reaches it), and a `shortcut:` comment names the load past which it stops holding.
- **Budgets** - draft each component's from `defaults.performance.budgets[kind]` (each entry reads `"<metric> < <limit>"`), then adjust them to the requirements (e.g. a requirement about slow connections tightens the bundle; a batch job may need none). Say which come from the defaults.
- **Measured by** - for each budget, recommend a tool that fits the component's stack and the CI from the build area; look it up, never assume.
- Offer "no budgets" for a component where nothing is worth measuring yet, and say what it means: the principle stays off for it.

When a component's budgets differ from its kind's defaults, follow the grilling skill's override protocol (key `performance.budgets.<kind>`, with the new list in the same `"<metric> < <limit>"` form).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "performance": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `performance` set to `"in_progress"`.
3. When the user confirms the area, save the `performance` object `{"expected_load", "components": [{"name", "budgets": [{"metric", "limit", "measured_by"}]}]}`, with one entry per component. Keep the exact field names.
4. In the same call, save `areas` with `performance` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area performance`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
