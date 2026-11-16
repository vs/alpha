# Documentation

## Before you start

`/alpha:install` reads this guide for a new project's or an adoption's interview, and `/alpha:extend` when a change revisits this area. `<target>` is their target folder; the answers live in `<target>/.claude/alpha/project.json`. Their rules win over this guide's where they differ. When the user asks to revisit this area outside them, run `/alpha:extend` with the request.

## Purpose

Decide where documentation lives and how it stays true. alpha's own docs (the specification, the principles, the dependency log) always live in `docs/alpha/`, and the process in `CONTRIBUTING.md`; alpha writes nothing else into `docs/`. User-facing docs are a choice. Then map the paths that hold each component's public behavior to the docs that describe it: when an agent changes one of those paths without touching its docs, the Stop hook blocks it ("Docs move with the code").

## Fields this area settles

- `documentation.external` - where user-facing docs live: `"readme"`, `"folder"`, `"elsewhere"` or `"none"`.
- `documentation.external_path` - with `folder`, a folder under `docs/` (e.g. `"docs/guide"`); otherwise `""`.
- `documentation.external_location` - with `elsewhere`, where they live (e.g. a wiki URL); otherwise `""`.
- `documentation.mappings[].paths` - globs, relative to the project root, of code whose changes need doc changes.
- `documentation.mappings[].docs` - the docs (paths or globs, e.g. `"docs/guide/**"`) that must change with them.
- `documentation.existing` - in an existing repo, the repo's own doc for an area alpha would document, keyed by product area, `glossary` or `dependencies` (e.g. `{"architecture": "docs/design.md"}`): alpha's file in `docs/alpha/` links to it instead of repeating it. `{}` for a new project.
- `areas.documentation` - `"in_progress"` while you work, `"done"` at the end.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as a design tree in rounds. Base recommendations on the value proposition and the components.

Round 1:

- **User-facing docs** - recommend `defaults.documentation.external`, unless the users need more than a README can hold (an API many people call, a CLI with many commands, a product with non-technical users): then recommend `folder` at `docs/guide`. Explain each choice in one line:
  - `readme` - the README is the user documentation.
  - `folder` - a folder of guides inside `docs/`, versioned with the code.
  - `elsewhere` - a wiki or a separate site; ask where. alpha can't check docs outside the repository.
  - `none` - nobody outside the team uses it.

Round 2 (needs the answer above):

- **Docs mappings** - propose all mappings in one question. For each component, take `defaults.documentation.public_paths[kind]` and put the component's path in front of each glob (`api/**/routes/**`; a component at `"."` gets no prefix). Map them:
  - user-facing kinds (`backend` with outside callers, `frontend`, `cli`, `mobile`, `library`) to the user-facing docs: `README.md` for `readme`, `<external_path>/**` for `folder`;
  - everything else, and every component when user docs are `elsewhere` or `none`, to `docs/alpha/specification.md`.

  Explain: the Stop hook blocks a change to a mapped path that leaves its docs untouched, so map only real public behavior, not all code. There is no code yet, so these are the usual places; the user can edit the mappings later in `docs/alpha/principles.toml` (`docs_map`). A kind with no usual paths (e.g. `ml`) gets no mapping; that's fine.

When the user-facing docs choice differs from `defaults.documentation.external`, follow the grilling skill's override protocol (key `documentation.external`). When the user changes the usual paths for a kind (not just one project's globs), the key is `documentation.public_paths.<kind>`, e.g. `documentation.public_paths.backend`.

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "documentation": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `documentation` set to `"in_progress"`.
3. When the user confirms the area, save the `documentation` object `{"external", "external_path", "external_location", "mappings": [{"paths": [...], "docs": [...]}]}`. Keep the exact field names; `mappings` may be `[]`.
4. In the same call, save `areas` with `documentation` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area documentation`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
