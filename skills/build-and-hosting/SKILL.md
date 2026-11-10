---
name: build-and-hosting
description: Settle how a new project is built, checked in CI and hosted in the alpha interview - CI provider, environments, and per component what it builds into and where it runs. Use only inside an alpha project interview (/alpha:new-project) or alpha:extend or when the user asks to revisit the build, CI or hosting of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Build, CI and hosting

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. If the `alpha:extend` skill sent you here, go on as it says. Otherwise invoke `alpha:extend` with the Skill tool and follow it; it brings you back here.
- `areas.documentation` isn't `"done"`: tell the user the earlier areas come first and to run `/alpha:new-project`, and stop.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

Decide build and hosting up front, so nothing about shipping is left for later ("Build and hosting are decided up front"). CI runs each component's checks (setup, format check, lint, typecheck, test) on every push to main and every pull request, the same commands alpha runs when it sets the project up, so the first run is green. alpha records what each component builds into and where it runs in `docs/build.md`. It creates no cloud resources and no deploy jobs; say so plainly.

## Fields this area settles

- `build.ci` - `"github-actions"` or `"none"`.
- `build.environments` - environment names, lowercase with hyphens (e.g. `["staging", "production"]`); `[]` when nothing is deployed.
- `build.components[].name` - one entry per component, by name.
- `build.components[].artifact` - `none`, `package`, `container`, `static-site`, `binary`, `app` or `other`.
- `build.components[].hosting` - where a deployed component runs, in the user's words; `""` for one that isn't deployed.
- `areas.build` - `"in_progress"` while you work, `"done"` at the end.
- `decisions[]` - one entry with `"area": "build"`.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as a design tree in rounds. Base recommendations on the components, their kinds and their `deployed` traits.

Round 1:

- **CI** - recommend `defaults.build.ci`. Explain in one line: GitHub Actions runs every component's checks on each push and pull request, from `.github/workflows/ci.yml`. If the user wants another provider, say this version of alpha sets up GitHub Actions only and ask them to accept it or choose `none`. `none` loosens the build-hosting-upfront principle, so it needs a reason (see below).
- **Environments** - ask only when a component is deployed; recommend `["production"]`, or `["staging", "production"]` when the users' requirements make a broken release costly. With nothing deployed, save `[]` without asking.

Round 2 (needs the CI answer):

- **Artifact per component** - recommend `defaults.build.artifacts[kind]`, adjusted to what the component is (a backend that is a library for others is a `package`). Explain each in a few words: `package` (published to a registry), `container` (an image), `static-site` (files a CDN serves), `binary` (an executable), `app` (a store release), `none` (nothing is shipped), `other`.
- **Hosting per deployed component** - where does it run? Offer two or three common fits for the artifact and say they're examples; never pick one silently. Record the user's words. Components that aren't deployed get `""` without asking.

When CI is `none`, also save an override `{"principle": "build-hosting-upfront", "scope": "project", "change": "loosen", "params": {}, "reason": "<the user's reason>"}` in `overrides` (send the list whole). When CI or an artifact differs from a default, follow the grilling skill's override protocol (keys `build.ci`, `build.artifacts.<kind>`, e.g. `build.artifacts.backend`). Environments and hosting are per project, so they're recorded in the decision without asking.

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "build": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` and `decisions` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `build` set to `"in_progress"`.
3. When the user confirms the area, save the `build` object `{"ci", "environments", "components": [{"name", "artifact", "hosting"}]}`, with one entry per component. Keep the exact field names.
4. In the same call, save `decisions` with one entry for this area, replacing any earlier one with `"area": "build"`:
   `{"area": "build", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` names the shape (e.g. "GitHub Actions, container api, static web"); `context` is who ships what, and how often; `decision` gives the CI, environments, artifacts and hosting; `consequences` says what CI checks on every change and that hosting is documented, not provisioned, plus any defaults wish from the override protocol.
5. In the same call, save `areas` with `build` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area build`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
