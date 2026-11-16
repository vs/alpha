# Components and stacks

## Before you start

`/alpha:install` reads this guide for a new project's or an adoption's interview, and `/alpha:extend` when a change revisits this area. `<target>` is their target folder; the answers live in `<target>/.claude/alpha/project.json`. Their rules win over this guide's where they differ. When the user asks to revisit this area outside them, run `/alpha:extend` with the request.

## Purpose

Decide which parts the project is made of (a backend, a web frontend, a CLI, an ML pipeline, …), what each is written in, where it lives, and a few plain traits per part. These answers decide which test runner, linter and type checker each part gets, and which principles apply to it. Every later area applies to every component.

Any stack works. The kit has proven recipes for some (`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" recipe list`); for any other stack, the `alpha:stack-recipe` skill drafts a recipe with the user and proves it before this area is done.

## Fields this area settles

- `layout` - `"single"` (one component at the project root) or `"monorepo"` (each component in its own folder).
- `workspace` - optional `true` or `false`, for a monorepo: whether the components of a stack whose recipe has a workspace share it. Leave it out to take `defaults.components.workspace` (on). Today that is Rust: its components form one Cargo workspace at the repository root, with one `Cargo.lock`, toolchain and `target/`; `false` keeps each a crate of its own.
- `components_talk` - `true` when components call each other (HTTP, messages, shared files).
- `components[].name` - lowercase letters, digits and hyphens, e.g. `api`; also the commit scope.
- `components[].path` - the component's folder relative to the root.
- `components[].kind` - one of `backend`, `frontend`, `cli`, `mobile`, `ml`, `library`, `worker`.
- `components[].stack` - the stack's name, lowercase with hyphens (e.g. `python`, `typescript`, `rust`).
- `components[].traits.has_ui` - it shows a user interface.
- `components[].traits.deployed` - it runs somewhere other than a developer's machine.
- `components[].traits.network_calls` - it calls other services or processes.
- `components[].traits.persisted_data` - it stores data that must survive restarts.
- `components[].traits.ml` - it trains or runs machine-learning models.
- `components[].traits.nontrivial_logic` - it holds real business rules, not just plumbing.
- `areas.components` - `"in_progress"` while you work, `"done"` at the end.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as a design tree in rounds. Base recommendations on the value proposition and what the user said about the project.

Round 1:

- **Components** - which parts does the project need? Recommend a list with a name and a kind for each, drawn from the requirements (e.g. a browser UI needs a `frontend`; an API needs a `backend`). Keep it to the simplest set that meets the requirements.

Round 2 (needs the component list):

- **Layout** - with one component, recommend `single`; with more, `monorepo` is required. Rule: `single` means exactly one component, at path `"."`.
- **Stack per component** - recommend `defaults.stacks[kind]`. The user may pick any stack. Say which stacks the kit has proven recipes for (from `recipe list`); for any other, explain in one line that a recipe will be drafted and proven for this project, and that it's less proven.
- **Talk to each other** - ask only when there is more than one component: "Do these components call each other?" Explain: yes turns on the "Contracts are the source of truth" principle, so their interfaces are defined once (e.g. OpenAPI) and checked. With one component, set `components_talk` to `false` without asking.

Round 3 (needs the layout):

- **Workspace** - only when a `monorepo` has a Rust component: say in one line that its Rust components form one Cargo workspace at the root (one lockfile, toolchain and build folder, dependencies pinned once), and recommend it. Save `"workspace": false` only when the user wants separate crates, through the grilling skill's override protocol (key `components.workspace`).
- **Path per component** - with `single`, the path is `"."` (don't ask). With `monorepo`, recommend the component's name as its folder; folders must not be nested in each other.
- **Traits per component** - ask all six for each component in one question, recommending answers from its kind and the requirements. Explain each in one sentence:
  - *Has a UI* - turns on the visual-system and accessibility principles. (The design language is separate: any project may define one, with or without a UI.)
  - *Deployed* - turns on config from the environment and observability (structured logs).
  - *Makes network calls* - every external call then needs a timeout and a failure path.
  - *Stores data* - every schema change must be a migration, reversible where possible.
  - *Machine learning* - adds reproducibility rules for seeds, data versions and experiment configs.
  - *Non-trivial logic* - keeps business rules pure, with side effects at the edges, so they're easy to test.

When a stack differs from `defaults.stacks[kind]`, follow the grilling skill's override protocol (key `stacks.<kind>`, e.g. `stacks.backend`).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "components": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `components` set to `"in_progress"`.
3. When the user confirms the area, save `layout`, `components_talk` and the `components` list, plus `"workspace": false` only when the user declined the workspace. Each component is `{"name", "path", "kind", "stack", "traits": {"has_ui", "deployed", "network_calls", "persisted_data", "ml", "nontrivial_logic"}}`, with every trait `true` or `false`. Keep the exact field names.
4. For each stack that `recipe list` doesn't name, invoke `alpha:stack-recipe` with the Skill tool for it before marking the area done.
5. In the same call as step 3 (or after the recipes are proven), save `areas` with `components` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area components`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
