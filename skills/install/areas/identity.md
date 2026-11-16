# Identity

## Before you start

`/alpha:install` reads this guide for a new project's or an adoption's interview, and `/alpha:extend` when a change revisits this area. `<target>` is their target folder; the answers live in `<target>/.claude/alpha/project.json`. Their rules win over this guide's where they differ. When the user asks to revisit this area outside them, run `/alpha:extend` with the request.

## Purpose

Pin down what the files need to name the project: what it does in a sentence or two, its name and slug, the license and the copyright holder. That is all the setup asks.

Who it's for, its requirements with their acceptance checks and whether its domain has its own jargon are the product's specification: the requirements area, which install leaves open for later.

## Fields this area settles

- `identity.name` - the product's display name, e.g. "Pico Trust".
- `identity.slug` - lowercase letters, digits and hyphens, starting with a letter; names the project in files and commits.
- `identity.value_proposition` - one or two sentences: what it does and why that matters.
- `identity.license` - `MIT`, `Apache-2.0` or `Proprietary`.
- `identity.license_file` - `null`, or the path of the user's own license text relative to `<target>`, e.g. `"LICENSE"`.
- `identity.copyright_holder` - the person or organization named in the license.
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
