# Auth

## Before you start

`/alpha:update` reads this guide when the user asks to settle this area, and `/alpha:install` when the user picks it in the interview; it's a product area, open until then. `<target>` is their target folder; the answers live in `<target>/.claude/alpha/project.json`. Their rules win over this guide's where they differ. Only `/alpha:install` and `/alpha:update` settle a product area: when the user asks for it elsewhere, point to `/alpha:update <area>`.

## Purpose

Say who must prove who they are, and how. alpha records the approach in the Auth section of `docs/alpha/specification.md`, and changes under `auth/` and `security/` paths are reviewed as risky. It writes no auth code.

## Fields this area settles

- `auth.method` - who must prove who they are (end users, other services, admins) and how (sessions, API keys, OAuth, …), in the user's words; `"none"` is a valid answer.
- `areas.auth` - `"in_progress"` while you work, `"done"` at the end.

## Questions

Run this with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as one round. Facts first: a local CLI, a library or a pipeline usually needs none, and an existing repo's code may already show its approach (a login route, an API-key header, an OAuth client); never ask what it shows.

- **Method** - recommend from the components and their traits: `none` when nothing is deployed or nothing is exposed to a network; otherwise the usual approach for the stack and users (sessions for a web app with end users, API keys or OAuth client credentials between services), and say it's your suggestion. Record the user's words.

The method is per project, not a kit default, so the override protocol doesn't apply to it.

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "auth": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `auth` set to `"in_progress"`.
3. When the user confirms the area, save the `auth` object `{"method"}`. Keep the exact field name.
4. In the same call, save `areas` with `auth` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area auth`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
