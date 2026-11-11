---
name: data
description: Settle how a new project's stored data changes in the alpha interview - for each component that stores data, its storage, migration tool and migration files; for ML, data versioning, seeds and experiment tracking. Skipped when nothing stores data or does ML. Use only inside an alpha project interview (/alpha:new-project) or alpha:extend or /alpha:adopt or when the user asks to revisit the data of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Data

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. If the `alpha:extend` skill sent you here, go on as it says. Otherwise invoke `alpha:extend` with the Skill tool and follow it; it brings you back here.
- project.json has an `adoption` key and no `manifest`: `alpha:adopt` is bringing an existing repo in. Go on as it says; its rules win over this skill's, and don't point to `/alpha:new-project` afterwards.
- `areas.releases` isn't `"done"`: tell the user the earlier areas come first and to run `/alpha:new-project`, and stop.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

Stored data outlives the code, so every change to its shape must be repeatable and recoverable ("Safe migrations"); ML results must be repeatable too ("Reproducible"). This area covers components with `traits.persisted_data` and, for ML, the project's data and experiments. With neither there is nothing to decide: say so in one line, save the empty answer, and finish. Otherwise the project gets `docs/data.md`.

Migrations are append-only: the Stop hook blocks any edit to a migration that existed when the session started (renaming or deleting one counts), and the fix is a new migration. Explain this to the user when they choose the migration files.

## Fields this area settles

- `data.components[].name` - one entry per component that stores data, by name; none for the others.
- `data.components[].storage` - what it stores data in, e.g. `"PostgreSQL"`, `"SQLite"`, `"Core Data"`.
- `data.components[].migration_tool` - the tool that applies schema changes, in the user's words (e.g. `"Alembic"`, `"Prisma Migrate"`, `"sqlx"`), or `"none"` (a schemaless store, say).
- `data.components[].migrations` - globs that match only its migration files, relative to the project root (e.g. `["api/migrations/versions/**"]` for Alembic); `[]` only when the tool is `"none"`. Leave out the tool's own config and scripts in the same folder (Alembic's `env.py`, Django's `__init__.py`, Prisma's `migration_lock.toml`): they change normally, and the append-only rule would block them.
- `data.components[].reversible` - `true` when each migration has a down step.
- `data.ml` - `null` unless a component does ML (`traits.ml`); then an object with:
- `data.ml.versioning` - how datasets are versioned, e.g. `"DVC"`.
- `data.ml.seeds` - how randomness is fixed, e.g. `"fixed seeds recorded in the run config"`.
- `data.ml.tracking` - where experiments are recorded, e.g. `"MLflow"`.
- `areas.data` - `"in_progress"` while you work, `"done"` at the end.
- `decisions[]` - one entry with `"area": "data"`.

## Questions

When no component stores data or does ML, ask nothing: save `{"components": [], "ml": null}` and a decision saying nothing is stored, so the safe-migrations principle doesn't apply.

Otherwise run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it). There are no kit defaults here: every project's storage is its own. Facts first: look up what the component's stack usually uses and recommend from that.

- Per component that stores data, one round: **storage** (from the requirements), **migration tool** (the stack's usual one), **migration files** (look up where the tool writes each migration, and match only those files), **reversible** (recommend `true` wherever the tool supports down migrations). Explain the append-only rule.
- With ML, one round: **data versioning**, **seeds**, **experiment tracking**. Recommend tools that fit the stack and how the user works (local, or a team server).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "data": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` and `decisions` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `data` set to `"in_progress"`.
3. When the user confirms the area (or right away, when nothing applies), save the `data` object `{"components": [{"name", "storage", "migration_tool", "migrations", "reversible"}], "ml": null or {"versioning", "seeds", "tracking"}}`. Keep the exact field names.
4. In the same call, save `decisions` with one entry for this area, replacing any earlier one with `"area": "data"`:
   `{"area": "data", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` names the choice (e.g. "PostgreSQL with Alembic migrations"); `context` is what is stored and why; `decision` gives each component's storage and migrations, and the ML setup; `consequences` says that migrations are append-only.
5. In the same call, save `areas` with `data` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area data`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
