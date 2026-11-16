# Observability

## Before you start

`/alpha:update` reads this guide when the user asks to settle this area, and `/alpha:install` when the user picks it in the interview; it's a product area, open until then. `<target>` is their target folder; the answers live in `<target>/.claude/alpha/project.json`. Their rules win over this guide's where they differ. Only `/alpha:install` and `/alpha:update` settle a product area: when the user asks for it elsewhere, point to `/alpha:update <area>`.

## Purpose

A deployed system fails where nobody is watching, so it must explain itself ("Observability"): structured logs, and one request followed across components. This applies only to deployed components (`traits.deployed`). With nothing deployed there is nothing to decide: say so in one line, save the empty answer, and finish, so a small project carries no ceremony. Deployed projects get an Observability section in `docs/alpha/specification.md`.

## Fields this area settles

- `observability.components[].name` - one entry per deployed component, by name; none for the others.
- `observability.components[].log_format` - `"json"` or `"logfmt"`.
- `observability.components[].correlation` - `"traceparent"`, `"request-id"`, or `"none"` (only with a single deployed component).
- `observability.components[].telemetry` - `"none"`, `"opentelemetry"` or `"other"`.
- `areas.observability` - `"in_progress"` while you work, `"done"` at the end.

## Questions

When no component is deployed, ask nothing: save `{"components": []}`; observability applies once something is deployed.

Otherwise run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as one round covering every deployed component:

- **Log format** - recommend `defaults.observability.log_format`. Explain: one structured entry per event, so logs can be searched and joined; `logfmt` reads better in a terminal, `json` suits log services.
- **Correlation** - recommend `defaults.observability.correlation` when more than one component is deployed: the W3C `traceparent` header carries one id through every hop. `request-id` is a simpler custom header. `none` is allowed only with a single deployed component.
- **Telemetry** - recommend `defaults.observability.telemetry`. Explain: `opentelemetry` adds metrics and traces on top of logs, worth it once requests cross several services or performance budgets matter.

When an answer differs from a default, follow the grilling skill's override protocol (keys `observability.log_format`, `observability.correlation`, `observability.telemetry`).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "observability": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `observability` set to `"in_progress"`.
3. When the user confirms the area (or right away, with nothing deployed), save the `observability` object `{"components": [{"name", "log_format", "correlation", "telemetry"}]}`, with one entry per deployed component. Keep the exact field names.
4. In the same call, save `areas` with `observability` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area observability`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
