---
name: components
description: Settle a new project's components and stacks in the alpha interview - which parts exist, their kind, language, folder and traits, the repo layout, and whether they talk to each other. Use only inside an alpha project interview (/alpha:new-project) or when the user asks to revisit the components of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Components and stacks

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. Tell the user that extending a generated project (e.g. adding a component) arrives in a later version of alpha, and stop.
- `areas.identity` isn't `"done"`: tell the user identity comes first and to run `/alpha:new-project`, and stop.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

Decide which parts the project is made of (a backend, a web frontend, a CLI, an ML pipeline, …), what each is written in, where it lives, and a few plain traits per part. These answers decide which test runner, linter and type checker each part gets, and which principles apply to it. Every later area applies to every component.

alpha v0.1 sets up **Python** and **TypeScript** only. Say so plainly when you ask about stacks; other stacks arrive in a later version.

## Fields this area settles

- `layout` - `"single"` (one component at the project root) or `"monorepo"` (each component in its own folder).
- `components_talk` - `true` when components call each other (HTTP, messages, shared files).
- `components[].name` - lowercase letters, digits and hyphens, e.g. `api`; also the commit scope.
- `components[].path` - the component's folder relative to the root.
- `components[].kind` - one of `backend`, `frontend`, `cli`, `mobile`, `ml`, `library`, `worker`.
- `components[].stack` - `python` or `typescript`.
- `components[].traits.has_ui` - it shows a user interface.
- `components[].traits.deployed` - it runs somewhere other than a developer's machine.
- `components[].traits.network_calls` - it calls other services or processes.
- `components[].traits.persisted_data` - it stores data that must survive restarts.
- `components[].traits.ml` - it trains or runs machine-learning models.
- `components[].traits.nontrivial_logic` - it holds real business rules, not just plumbing.
- `areas.components` - `"in_progress"` while you work, `"done"` at the end.
- `decisions[]` - one entry with `"area": "components"`.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as a design tree in rounds. Base recommendations on the identity answers (value proposition, users, requirements).

Round 1:
- **Components** - which parts does the project need? Recommend a list with a name and a kind for each, drawn from the requirements (e.g. a browser UI needs a `frontend`; an API needs a `backend`). Keep it to the simplest set that meets the requirements.

Round 2 (needs the component list):
- **Layout** - with one component, recommend `single`; with more, `monorepo` is required. Rule: `single` means exactly one component, at path `"."`.
- **Stack per component** - recommend `defaults.stacks[kind]`. Offer only `python` and `typescript`. If the user wants another language, explain that v0.1 can't set it up yet, and ask them to pick one of the two or stop here.
- **Talk to each other** - ask only when there is more than one component: "Do these components call each other?" Explain: yes turns on the "Contracts are the source of truth" principle, so their interfaces are defined once (e.g. OpenAPI) and checked. With one component, set `components_talk` to `false` without asking.

Round 3 (needs the layout):
- **Path per component** - with `single`, the path is `"."` (don't ask). With `monorepo`, recommend the component's name as its folder; folders must not be nested in each other.
- **Traits per component** - ask all six for each component in one question, recommending answers from its kind and the requirements. Explain each in one sentence:
  - *Has a UI* - turns on the visual-system and accessibility principles.
  - *Deployed* - turns on config from the environment and observability (structured logs).
  - *Makes network calls* - every external call then needs a timeout and a failure path.
  - *Stores data* - every schema change must be a migration, reversible where possible.
  - *Machine learning* - adds reproducibility rules for seeds, data versions and experiment configs.
  - *Non-trivial logic* - keeps business rules pure, with side effects at the edges, so they're easy to test.

When a stack differs from `defaults.stacks[kind]`, follow the grilling skill's override protocol (key `stacks.<kind>`, e.g. `stacks.backend`).

## Writing the answers

1. Read `<target>/.claude/alpha/project.json`.
2. Set `areas.components` to `"in_progress"` when you start asking.
3. When the user confirms the area, write `layout`, `components_talk` and the `components` list using the Write or Edit tool. Each component is `{"name", "path", "kind", "stack", "traits": {"has_ui", "deployed", "network_calls", "persisted_data", "ml", "nontrivial_logic"}}`, with every trait `true` or `false`. Keep the exact field names, keep the rest of the file as it is, and keep it valid JSON.
4. Add one `decisions[]` entry, replacing any earlier one with `"area": "components"`:
   `{"area": "components", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` names the shape (e.g. "Python api plus TypeScript web"); `context` is why these parts; `decision` lists the components with their stacks and the layout; `consequences` names the toolchains to maintain and the integration points, plus any defaults wish from the override protocol.
5. Set `areas.components` to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area components`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
