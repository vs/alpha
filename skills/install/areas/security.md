# Security and secrets

## Before you start

`/alpha:install` reads this guide for a new project's or an adoption's interview, and `/alpha:update` when a change revisits this area. `<target>` is their target folder; the answers live in `<target>/.claude/alpha/project.json`. Their rules win over this guide's where they differ. When the user asks to revisit this area outside them, run `/alpha:update` with the request.

## Purpose

Secrets never live in the repository ("No secrets in the repo"): locally they sit in `.env` files git ignores, and the Stop hook blocks a change that adds one. This area records where production secrets live and any extra paths Claude must never edit (beyond secrets files and lockfiles, which are always protected). Both go in the Security section of `CONTRIBUTING.md`. How users prove who they are is the auth area, which install leaves open.

## Fields this area settles

- `security.secret_store` - where production secrets live, in the user's words; `""` when nothing is deployed.
- `security.extra_protected` - globs, relative to the project root, Claude may not edit; often `[]`.
- `areas.security` - `"in_progress"` while you work, `"done"` at the end.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it). The questions are independent, so ask them in one round. None has a kit default: they're per project, so recommend from the answers so far and say it's your suggestion.

- **Secret store** - ask only when a component is deployed. Recommend the secret manager of the hosting the user chose in the build area (`build.components[].hosting`), and mention one or two alternatives as examples. With nothing deployed, save `""` and say in one line that local `.env` files are enough until something is deployed.
- **Extra protected paths** - recommend none. Explain: Claude can't edit protected paths, so they suit files where a careless change is costly (e.g. `api/keys/**`, signed migration snapshots). alpha refuses a glob that covers files its own checks may require changing, such as docs or package manifests.

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "security": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `security` set to `"in_progress"`.
3. When the user confirms the area, save the `security` object `{"secret_store", "extra_protected"}`. Keep the exact field names.
4. In the same call, save `areas` with `security` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area security`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`. A protected glob that covers docs or manifests is refused later, when the project is generated; avoid such globs now.
