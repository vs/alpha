---
name: identity
description: Settle a new project's identity in the alpha interview - value proposition, name, target users, requirements with acceptance checks, license and copyright. Use only inside an alpha project interview (/alpha:new-project) or alpha:extend or when the user asks to revisit the identity of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Identity

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. If the `alpha:extend` skill sent you here, go on as it says. Otherwise invoke `alpha:extend` with the Skill tool and follow it; it brings you back here.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

Pin down what the project is and who it's for before any technical choice: the problem it solves, its name, its users, and a short list of requirements, each turned into an acceptance check (Given/When/Then) that tests will later trace back to. Also settle the license and copyright holder. Every later area builds on these answers.

## Fields this area settles

- `identity.name` - the product's display name, e.g. "Pico Trust".
- `identity.slug` - lowercase letters, digits and hyphens, starting with a letter; names the project in files and commits.
- `identity.value_proposition` - one or two sentences: what it does and why that matters.
- `identity.target_users` - who uses it and what they need.
- `identity.requirements[].id` - `R1`, `R2`, … in order.
- `identity.requirements[].text` - one requirement in plain words.
- `identity.requirements[].acceptance` - its acceptance check: "Given …, when …, then …".
- `identity.license` - `MIT`, `Apache-2.0` or `Proprietary`.
- `identity.license_file` - `null`, or the absolute path to the user's own license text.
- `identity.copyright_holder` - the person or organization named in the license.
- `identity.domain_jargon` - `true` when the domain has its own vocabulary.
- `areas.identity` - `"in_progress"` while you work, `"done"` at the end.
- `decisions[]` - one entry with `"area": "identity"`.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as a design tree in rounds.

Look up first (facts, never ask): the target folder's name, and `git config user.name`.

Round 1:
- **Value proposition** - what does the project do, and why does that matter? Draft one from what the user has said; if they've said nothing, ask openly.

Round 2 (needs the value proposition):
- **Name** - recommend a name that fits the value proposition, or the folder's name if it already reads as one.
- **Target users** - draft from the value proposition and what the user said.
- **Domain jargon** - "Does this domain have its own vocabulary that newcomers would trip over?" Explain: yes turns on the "One vocabulary" principle, which keeps a glossary and the same names across code, docs and UI. Recommend no unless the value proposition uses specialist terms.
- **License** - recommend `defaults.identity.license`. Explain the three choices in one line each: MIT (anyone may reuse it, with credit), Apache-2.0 (like MIT, plus an explicit patent grant), Proprietary (all rights reserved). If the user has their own license text, set `license_file` to its absolute path and `license` to its short name.
- **Copyright holder** - recommend the `git config user.name` value.

Round 3 (needs the name, value proposition and users):
- **Slug** - recommend the name in lowercase with hyphens.
- **Requirements** - ask for the technical requirements: what must the product do for its users? Recommend a short list (3 to 7) drafted from the value proposition and target users.

Round 4 (needs the requirements):
- **Acceptance checks** - turn each requirement into one Given/When/Then check, and propose all of them in one question. Explain: tests will later trace back to these checks, so each must describe something observable that a test can verify. Rework any the user rejects until they agree.

When the license differs from `defaults.identity.license`, follow the grilling skill's override protocol (key `identity.license`).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "identity": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` and `decisions` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `identity` set to `"in_progress"`.
3. When the user confirms the area, save the whole `identity` object with every field above. Keep the exact field names.
4. In the same call, save `decisions` with one entry for this area, replacing any earlier one with `"area": "identity"`:
   `{"area": "identity", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` is a short name (e.g. "Product identity"); `context` is the problem and audience; `decision` is the name, users and the requirement ids; `consequences` says what this rules in or out (e.g. "Features outside R1-R3 need a new requirement first"), plus any defaults wish from the override protocol.
5. In the same call, save `areas` with `identity` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area identity`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
