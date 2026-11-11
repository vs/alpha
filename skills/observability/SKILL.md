---
name: observability
description: Settle how a new project's deployed components can be watched in the alpha interview - log format, how one request is followed across components, and telemetry. Skipped when nothing is deployed. Use only inside an alpha project interview (/alpha:new-project) or alpha:extend or /alpha:adopt or when the user asks to revisit the observability of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Observability

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. If the `alpha:extend` skill sent you here, go on as it says. Otherwise invoke `alpha:extend` with the Skill tool and follow it; it brings you back here.
- project.json has an `adoption` key and no `manifest`: `alpha:adopt` is bringing an existing repo in. Go on as it says; its rules win over this skill's, and don't point to `/alpha:new-project` afterwards.
- `areas.dependencies` isn't `"done"`: tell the user the earlier areas come first and to run `/alpha:new-project`, and stop.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

A deployed system fails where nobody is watching, so it must explain itself ("Observability"): structured logs, and one request followed across components. This applies only to deployed components (`traits.deployed`). With nothing deployed there is nothing to decide: say so in one line, save the empty answer, and finish, so a small project carries no ceremony. Deployed projects get `docs/observability.md`.

## Fields this area settles

- `observability.components[].name` - one entry per deployed component, by name; none for the others.
- `observability.components[].log_format` - `"json"` or `"logfmt"`.
- `observability.components[].correlation` - `"traceparent"`, `"request-id"`, or `"none"` (only with a single deployed component).
- `observability.components[].telemetry` - `"none"`, `"opentelemetry"` or `"other"`.
- `areas.observability` - `"in_progress"` while you work, `"done"` at the end.
- `decisions[]` - one entry with `"area": "observability"`.

## Questions

When no component is deployed, ask nothing: save `{"components": []}` and a decision saying observability applies once something is deployed.

Otherwise run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as one round covering every deployed component:

- **Log format** - recommend `defaults.observability.log_format`. Explain: one structured entry per event, so logs can be searched and joined; `logfmt` reads better in a terminal, `json` suits log services.
- **Correlation** - recommend `defaults.observability.correlation` when more than one component is deployed: the W3C `traceparent` header carries one id through every hop. `request-id` is a simpler custom header. `none` is allowed only with a single deployed component.
- **Telemetry** - recommend `defaults.observability.telemetry`. Explain: `opentelemetry` adds metrics and traces on top of logs, worth it once requests cross several services or performance budgets matter.

When an answer differs from a default, follow the grilling skill's override protocol (keys `observability.log_format`, `observability.correlation`, `observability.telemetry`).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "observability": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` and `decisions` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `observability` set to `"in_progress"`.
3. When the user confirms the area (or right away, with nothing deployed), save the `observability` object `{"components": [{"name", "log_format", "correlation", "telemetry"}]}`, with one entry per deployed component. Keep the exact field names.
4. In the same call, save `decisions` with one entry for this area, replacing any earlier one with `"area": "observability"`:
   `{"area": "observability", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` names the choice (e.g. "JSON logs correlated by traceparent"); `context` is what runs where; `decision` gives each component's format, correlation and telemetry; `consequences` says how a failure is traced, plus any defaults wish from the override protocol.
5. In the same call, save `areas` with `observability` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area observability`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
