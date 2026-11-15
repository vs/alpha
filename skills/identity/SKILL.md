---
name: identity
description: Settle a new project's identity in the alpha interview - value proposition, name, target users, requirements with acceptance checks, license and copyright. Use only inside an alpha project interview (/alpha:new-project) or alpha:extend or /alpha:adopt or when the user asks to revisit the identity of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Identity

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs the setup areas in order, and stop.
- project.json has a `manifest` key: the project is already generated. If the `alpha:extend` skill sent you here, go on as it says. Otherwise invoke `alpha:extend` with the Skill tool and follow it; it brings you back here.
- project.json has an `adoption` key and no `manifest`: `alpha:adopt` is bringing an existing repo in. Go on as it says; its rules win over this skill's, and don't point to `/alpha:new-project` afterwards.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

Pin down what the files need to name the project: what it does in a sentence or two, its name and slug, the license and the copyright holder. That is all the setup asks.

Who it's for, its requirements with their acceptance checks (Given/When/Then, which tests trace back to) and whether its domain has its own jargon are the product's specification. The user often doesn't know them yet, so the setup leaves them empty: `requirements` `[]`, `target_users` `""`, `domain_jargon` `false`. They're settled later, when `alpha:extend` sends you here for them: a feature built with `/alpha:go` adds the requirements it serves, and `/alpha:go settle the target users` settles the users.

## Fields this area settles

- `identity.name` - the product's display name, e.g. "Pico Trust".
- `identity.slug` - lowercase letters, digits and hyphens, starting with a letter; names the project in files and commits.
- `identity.value_proposition` - one or two sentences: what it does and why that matters.
- `identity.target_users` - who uses it and what they need; `""` until settled.
- `identity.requirements[].id` - `R1`, `R2`, … in order; the list is `[]` until a feature adds one.
- `identity.requirements[].text` - one requirement in plain words.
- `identity.requirements[].acceptance` - its acceptance check: "Given …, when …, then …".
- `identity.license` - `MIT`, `Apache-2.0` or `Proprietary`.
- `identity.license_file` - `null`, or the path of the user's own license text relative to `<target>`, e.g. `"LICENSE"`.
- `identity.copyright_holder` - the person or organization named in the license.
- `identity.domain_jargon` - `true` when the domain has its own vocabulary; `false` until settled.
- `areas.identity` - `"in_progress"` while you work, `"done"` at the end.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as a design tree in rounds.

Look up first (facts, never ask): the target folder's name, and `git config user.name`.

Round 1:

- **Value proposition** - what does the project do, and why does that matter? Draft one or two sentences from what the user has said; if they've said nothing, ask openly. A rough sentence is enough; it can be sharpened later.

Round 2 (needs the value proposition):

- **Name** - recommend a name that fits the value proposition, or the folder's name if it already reads as one.
- **License** - recommend `defaults.identity.license`. Explain the three choices in one line each: MIT (anyone may reuse it, with credit), Apache-2.0 (like MIT, plus an explicit patent grant), Proprietary (all rights reserved). If the user has their own license text, copy it into `<target>` (e.g. as `LICENSE`), set `license_file` to that path relative to `<target>`, and `license` to its short name.
- **Copyright holder** - recommend the `git config user.name` value.

Round 3 (needs the name):

- **Slug** - recommend the name in lowercase with hyphens.

Only when `alpha:extend` sends you here for them (from `/alpha:go`), ask what it names and nothing else:

- **Target users** - draft from the value proposition and what the user said.
- **Requirements** - the requirement a feature serves, numbered after the last one; turn each into one Given/When/Then check that describes something observable a test can verify, and rework any the user rejects until they agree.
- **Domain jargon** - "Does this domain have its own vocabulary that newcomers would trip over?" Explain: yes turns on the "One vocabulary" principle, which keeps a glossary and the same names across code, docs and UI.

When the license differs from `defaults.identity.license`, follow the grilling skill's override protocol (key `identity.license`).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "identity": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `identity` set to `"in_progress"`.
3. When the user confirms the area, save the whole `identity` object with every field above. Keep the exact field names.
4. In the same call, save `areas` with `identity` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area identity`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
