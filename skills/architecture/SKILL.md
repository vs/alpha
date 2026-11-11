---
name: architecture
description: Settle a new project's architecture in the alpha interview - what each component is responsible for, which components call which, the contract between them, and a shared glossary. Use only inside an alpha project interview (/alpha:new-project) or alpha:extend or /alpha:adopt or when the user asks to revisit the architecture of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Architecture

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. If the `alpha:extend` skill sent you here, go on as it says. Otherwise invoke `alpha:extend` with the Skill tool and follow it; it brings you back here.
- project.json has an `adoption` key and no `manifest`: `alpha:adopt` is bringing an existing repo in. Go on as it says; its rules win over this skill's, and don't point to `/alpha:new-project` afterwards.
- `areas.components` isn't `"done"`: tell the user components come first and to run `/alpha:new-project`, and stop.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

Keep the design as simple as the problem allows ("Simplest sufficient architecture"): one sentence of responsibility per component, and the calls between them. When components talk, their interface is defined once, in a contract file ("Contracts are the source of truth"); alpha treats changes there as risky for review. When there is more than one component, or the domain has its own jargon, a glossary keeps one name per idea across code, docs and UI ("One vocabulary").

## Fields this area settles

- `architecture.components[].name` - one entry per component, by name.
- `architecture.components[].responsibility` - one sentence: what this component owns.
- `architecture.components[].calls` - names of the components it calls; `[]` when none.
- `architecture.contracts.format` - `openapi`, `json-schema`, `protobuf`, `graphql`, `other`, or `none` when components don't talk.
- `architecture.contracts.paths` - the contract files or globs, relative to the project root (e.g. `"api/openapi.yaml"`); `[]` with `none`.
- `architecture.glossary[].term` - a term, unique regardless of case.
- `architecture.glossary[].meaning` - what it means here, in one sentence.
- `areas.architecture` - `"in_progress"` while you work, `"done"` at the end.
- `decisions[]` - one entry with `"area": "architecture"`.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as a design tree in rounds. Base recommendations on the identity answers (value proposition, requirements) and the components.

Round 1:

- **Responsibility per component** - draft one sentence each from the requirements, and ask for all of them in one question. Push back on overlap: two components owning the same thing is a sign one is unneeded.
- **Calls** - ask only when `components_talk` is true. Recommend from the kinds (a `frontend` calls the `backend`; a `worker` is called by the `backend` through a queue). With `components_talk` false, save `calls: []` for every component without asking.

Round 2 (needs the calls):

- **Contract** - ask only when components talk. Recommend `defaults.architecture.contract_format`, with the file in the called component's folder (e.g. `api/openapi.yaml`). Explain in one line: the interface is written down once, and changes to it are reviewed as risky. When components don't talk, save `{"format": "none", "paths": []}` without asking. If the user now says no component calls another, `components_talk` was wrong: save `components_talk` as `false` (this is the components area's field), save `calls: []` for every component and the `none` contract, and tell the user in one line.
- **Glossary** - ask when there is more than one component or `identity.domain_jargon` is true. Propose 3 to 8 terms drawn from the requirements, each with a one-sentence meaning. With jargon, at least one term is required. Otherwise save `[]` without asking.

When the contract format differs from `defaults.architecture.contract_format`, follow the grilling skill's override protocol (key `architecture.contract_format`). Responsibilities, calls and terms are per project, so they're recorded in the decision without asking.

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "architecture": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` and `decisions` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `architecture` set to `"in_progress"`.
3. When the user confirms the area, save the `architecture` object `{"components": [{"name", "responsibility", "calls"}], "contracts": {"format", "paths"}, "glossary": [{"term", "meaning"}]}`, with one component entry per component. Keep the exact field names.
4. In the same call, save `decisions` with one entry for this area, replacing any earlier one with `"area": "architecture"`:
   `{"area": "architecture", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` names the shape (e.g. "The web app calls the api through OpenAPI"); `context` is why these boundaries; `decision` gives the responsibilities, calls and contract; `consequences` says what changes are risky and which names are fixed, plus any defaults wish from the override protocol.
5. In the same call, save `areas` with `architecture` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area architecture`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
