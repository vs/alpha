---
name: errors
description: Settle how a new project reports errors in the alpha interview - the error format each component uses and the shared error categories, so every error says what went wrong and how to fix it. Use only inside an alpha project interview (/alpha:new-project) or alpha:extend or when the user asks to revisit the error handling of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Errors

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. If the `alpha:extend` skill sent you here, go on as it says. Otherwise invoke `alpha:extend` with the Skill tool and follow it; it brings you back here.
- `areas.architecture` isn't `"done"`: tell the user the earlier areas come first and to run `/alpha:new-project`, and stop.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

Decide how errors reach whoever uses each component, before any code exists ("Fail fast, fail helpfully"): one format per component and one shared list of categories, so the same problem is named the same way everywhere. Whatever the format, every error a user sees says what went wrong and how to fix it; that rule is always on and needs no answer.

## Fields this area settles

- `errors.components[].name` - one entry per component, by name.
- `errors.components[].format` - `problem-json`, `message-and-exit-code`, `user-message`, `exceptions`, `structured-log` or `other`.
- `errors.categories` - the kinds of error, lowercase with hyphens (e.g. `["validation", "not-found", "internal"]`).
- `areas.errors` - `"in_progress"` while you work, `"done"` at the end.
- `decisions[]` - one entry with `"area": "errors"`.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it). Both questions are independent, so ask them in one round.

- **Format per component** - recommend `defaults.errors.formats[kind]` for each component, in one question. Explain each format by what its users see:
  - `problem-json` - HTTP callers get a problem-details body (RFC 9457) with a type, a title and a detail that says how to fix it.
  - `message-and-exit-code` - a CLI prints the problem and the fix on stderr and exits non-zero.
  - `user-message` - a UI shows a message next to the problem, in plain words, with what to do next.
  - `exceptions` - code that calls a library or pipeline gets a typed exception whose message names the fix.
  - `structured-log` - a background worker logs the failure with its category and the fix, since no person is waiting.
  - `other` - ask what, and record it in the decision.
- **Categories** - recommend `defaults.errors.categories`. Explain: each error belongs to one category, and each category has one meaning across components (e.g. `not-found` is a 404 in the api and "We couldn't find that image" in the web app). Drop categories that can't happen here; add domain ones (e.g. `payment-declined`).

When a format or the categories differ from the defaults, follow the grilling skill's override protocol (keys `errors.formats.<kind>`, e.g. `errors.formats.backend`, and `errors.categories`).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "errors": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` and `decisions` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `errors` set to `"in_progress"`.
3. When the user confirms the area, save the `errors` object `{"components": [{"name", "format"}], "categories": [...]}`, with one entry per component. Keep the exact field names.
4. In the same call, save `decisions` with one entry for this area, replacing any earlier one with `"area": "errors"`:
   `{"area": "errors", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` names the choice (e.g. "Problem details and user messages"); `context` is who meets the errors; `decision` gives each format and the categories; `consequences` says what every error must contain, plus any defaults wish from the override protocol.
5. In the same call, save `areas` with `errors` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area errors`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
