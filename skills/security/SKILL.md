---
name: security
description: Settle a new project's security basics in the alpha interview - where secrets live, how users or callers prove who they are, and which extra paths Claude must never edit. Use only inside an alpha project interview (/alpha:new-project) or alpha:extend or when the user asks to revisit the security of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Security and secrets

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. If the `alpha:extend` skill sent you here, go on as it says. Otherwise invoke `alpha:extend` with the Skill tool and follow it; it brings you back here.
- `areas.build` isn't `"done"`: tell the user the earlier areas come first and to run `/alpha:new-project`, and stop.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

Secrets never live in the repository ("No secrets in the repo"): locally they sit in `.env` files git ignores, and the Stop hook blocks a change that adds one. This area records where production secrets live, the auth approach, and any extra paths Claude must never edit (beyond secrets files and lockfiles, which are always protected). It all goes in `docs/security.md`.

## Fields this area settles

- `security.secret_store` - where production secrets live, in the user's words; `""` when nothing is deployed.
- `security.auth` - who must prove who they are, and how; `"none"` is a valid answer.
- `security.extra_protected` - globs, relative to the project root, Claude may not edit; often `[]`.
- `areas.security` - `"in_progress"` while you work, `"done"` at the end.
- `decisions[]` - one entry with `"area": "security"`.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it). The three questions are independent, so ask them in one round. None has a kit default: they're per project, so recommend from the answers so far and say it's your suggestion.

- **Secret store** - ask only when a component is deployed. Recommend the secret manager of the hosting the user chose in the build area (`build.components[].hosting`), and mention one or two alternatives as examples. With nothing deployed, save `""` and say in one line that local `.env` files are enough until something is deployed.
- **Auth** - who must prove who they are (end users, other services, admins), and how (sessions, API keys, OAuth, none)? Recommend from the requirements and kinds: `none` for a local CLI or a pipeline, a concrete approach for anything users sign in to. Record the user's words.
- **Extra protected paths** - recommend none. Explain: Claude can't edit protected paths, so they suit files where a careless change is costly (e.g. `api/keys/**`, signed migration snapshots). alpha refuses a glob that covers files its own checks may require changing, such as docs or package manifests.

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "security": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` and `decisions` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `security` set to `"in_progress"`.
3. When the user confirms the area, save the `security` object `{"secret_store", "auth", "extra_protected"}`. Keep the exact field names.
4. In the same call, save `decisions` with one entry for this area, replacing any earlier one with `"area": "security"`:
   `{"area": "security", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` names the choice (e.g. "Secrets in Fly.io, API keys for publishers"); `context` is what's at risk; `decision` gives the store, the auth approach and any protected paths; `consequences` says what Claude can't edit and how secrets reach production.
5. In the same call, save `areas` with `security` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area security`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`. A protected glob that covers docs or manifests is refused later, when the project is generated; avoid such globs now.
