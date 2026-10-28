---
name: documentation
description: Settle where a new project's docs live in the alpha interview - internal versus user-facing docs, and which code paths must update which docs so they never drift. Use only inside an alpha project interview (/alpha:new-project) or alpha:extend or when the user asks to revisit the documentation of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Documentation

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. If the `alpha:extend` skill sent you here, go on as it says. Otherwise invoke `alpha:extend` with the Skill tool and follow it; it brings you back here.
- `areas.ui` isn't `"done"`: tell the user the earlier areas come first and to run `/alpha:new-project`, and stop.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

Decide where documentation lives and how it stays true. Internal docs (product brief, architecture, decisions, build, dependencies) always live in `docs/`. User-facing docs are a choice. Then map the paths that hold each component's public behavior to the docs that describe it: when an agent changes one of those paths without touching its docs, the Stop hook blocks it ("Docs move with the code").

## Fields this area settles

- `documentation.external` - where user-facing docs live: `"readme"`, `"folder"`, `"elsewhere"` or `"none"`.
- `documentation.external_path` - with `folder`, a folder under `docs/` (e.g. `"docs/guide"`); otherwise `""`.
- `documentation.external_location` - with `elsewhere`, where they live (e.g. a wiki URL); otherwise `""`.
- `documentation.mappings[].paths` - globs, relative to the project root, of code whose changes need doc changes.
- `documentation.mappings[].docs` - the docs (paths or globs, e.g. `"docs/guide/**"`) that must change with them.
- `areas.documentation` - `"in_progress"` while you work, `"done"` at the end.
- `decisions[]` - one entry with `"area": "documentation"`.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as a design tree in rounds. Base recommendations on the identity answers (who the users are) and the components.

Round 1:
- **User-facing docs** - recommend `defaults.documentation.external`, unless the users need more than a README can hold (an API many people call, a CLI with many commands, a product with non-technical users): then recommend `folder` at `docs/guide`. Explain each choice in one line:
  - `readme` - the README is the user documentation.
  - `folder` - a folder of guides inside `docs/`, versioned with the code.
  - `elsewhere` - a wiki or a separate site; ask where. alpha can't check docs outside the repository.
  - `none` - nobody outside the team uses it.

Round 2 (needs the answer above):
- **Docs mappings** - propose all mappings in one question. For each component, take `defaults.documentation.public_paths[kind]` and put the component's path in front of each glob (`api/**/routes/**`; a component at `"."` gets no prefix). Map them:
  - user-facing kinds (`backend` with outside callers, `frontend`, `cli`, `mobile`, `library`) to the user-facing docs: `README.md` for `readme`, `<external_path>/**` for `folder`;
  - everything else, and every component when user docs are `elsewhere` or `none`, to `docs/architecture.md`;
  - when components talk, also the contract files in `architecture.contracts.paths` to `docs/architecture.md`.

  Explain: the Stop hook blocks a change to a mapped path that leaves its docs untouched, so map only real public behavior, not all code. There is no code yet, so these are the usual places; the user can edit the mappings later in `docs/principles.toml` (`docs_map`). A kind with no usual paths (e.g. `ml`) gets no mapping; that's fine.

When the user-facing docs choice differs from `defaults.documentation.external`, follow the grilling skill's override protocol (key `documentation.external`). When the user changes the usual paths for a kind (not just one project's globs), the key is `documentation.public_paths.<kind>`, e.g. `documentation.public_paths.backend`.

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "documentation": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` and `decisions` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `documentation` set to `"in_progress"`.
3. When the user confirms the area, save the `documentation` object `{"external", "external_path", "external_location", "mappings": [{"paths": [...], "docs": [...]}]}`. Keep the exact field names; `mappings` may be `[]`.
4. In the same call, save `decisions` with one entry for this area, replacing any earlier one with `"area": "documentation"`:
   `{"area": "documentation", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` names the choice (e.g. "User guide in docs/guide"); `context` is who reads the docs; `decision` says where user docs live and what is mapped; `consequences` says which changes must update which docs, plus any defaults wish from the override protocol.
5. In the same call, save `areas` with `documentation` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area documentation`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
