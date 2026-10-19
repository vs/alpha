---
name: identity
description: Settle a new project's identity in the alpha interview - name, value proposition, target users, requirements with acceptance checks, license and copyright. Use during /alpha:new-project, or directly to redo this area of an interview in progress.
disable-model-invocation: true
---

# Identity

## Purpose

Pin down what the project is and who it's for before any technical choice: its name, the problem it solves, its users, and a short list of requirements, each turned into an acceptance check (Given/When/Then) that tests will later trace back to. Also settle the license and copyright holder. Every later area builds on these answers.

The target folder is the one `/alpha:new-project` is working in; when you are called directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`.

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

Round 1 (independent of each other):
- **Name** - recommend a name from what the user has said, else from the folder name.
- **Value proposition** - draft one from what the user has said; if they've said nothing, ask openly.
- **Target users** - draft from the value proposition and what the user said.
- **License** - recommend `defaults.identity.license`. Explain the three choices in one line each: MIT (anyone may reuse it, with credit), Apache-2.0 (like MIT, plus an explicit patent grant), Proprietary (all rights reserved). If the user has their own license text, set `license_file` to its absolute path and `license` to its short name.
- **Copyright holder** - recommend the `git config user.name` value.
- **Domain jargon** - "Does this domain have its own vocabulary that newcomers would trip over?" Explain: yes turns on the "One vocabulary" principle, which keeps a glossary and the same names across code, docs and UI. Recommend no unless the value proposition uses specialist terms.

Round 2 (needs the name and value proposition):
- **Slug** - recommend the name in lowercase with hyphens.
- **Requirements** - ask for the technical requirements: what must the product do for its users? Recommend a short list (3 to 7) drafted from the value proposition and target users.

Round 3 (needs the requirements):
- **Acceptance checks** - turn each requirement into one Given/When/Then check, and propose all of them in one question. Explain: tests will later trace back to these checks, so each must describe something observable that a test can verify. Rework any the user rejects until they agree.

When an answer differs from `defaults.identity.license`, follow the grilling skill's override protocol (key `identity.license`).

## Writing the answers

1. Read `<target>/.claude/alpha/project.json`. If it doesn't exist, create `<target>/.claude/alpha/` and start the file as:
   `{"schema": 1, "areas": {"identity": "pending", "components": "pending", "git": "pending", "agent_workflow": "pending"}, "overrides": [], "decisions": []}`
2. Set `areas.identity` to `"in_progress"` when you start asking.
3. When the user confirms the area, write the whole `identity` object with every field above, using the Write or Edit tool. Keep the exact field names, keep the rest of the file as it is, and keep it valid JSON.
4. Add one `decisions[]` entry, replacing any earlier one with `"area": "identity"`:
   `{"area": "identity", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` is a short name (e.g. "Product identity"); `context` is the problem and audience; `decision` is the name, users and the requirement ids; `consequences` says what this rules in or out (e.g. "Features outside R1-R3 need a new requirement first"), plus any defaults wish from the override protocol.
5. Set `areas.identity` to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area identity`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.

## Calling this skill directly

- No `<target>/.claude/alpha/project.json`: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. Tell the user that extending a generated project arrives in a later version of alpha, and stop.
- Otherwise an interview is in progress: run this area with the current answers as the recommendations, then tell the user to run `/alpha:new-project` to continue.
