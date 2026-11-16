# Requirements

## Before you start

`/alpha:update` reads this guide when the user asks to settle this area, and `/alpha:install` when the user picks it in the interview; it's a product area, open until then. `<target>` is their target folder; the answers live in `<target>/.claude/alpha/project.json`. Their rules win over this guide's where they differ. Only `/alpha:install` and `/alpha:update` settle a product area: when the user asks for it elsewhere, point to `/alpha:update <area>`.

## Purpose

Say who the product is for and what it must do, each requirement with an acceptance check that tests trace back to ("Tests are as important as the core"). A check is "Given …, when …, then …" and describes something observable a test can verify. When the domain has its own vocabulary, saying so turns on "One vocabulary": a glossary, and the same names across code, docs and UI. The answers become the Requirements section of `docs/alpha/specification.md`.

## Fields this area settles

- `requirements.target_users` - who uses it and what they need, in a sentence or two.
- `requirements.items[].id` - `R1`, `R2`, … in order; ids stay once given, so a dropped requirement leaves a gap.
- `requirements.items[].text` - one requirement in plain words.
- `requirements.items[].acceptance` - its acceptance check: "Given …, when …, then …".
- `requirements.domain_jargon` - `true` when the domain has its own vocabulary newcomers would trip over.
- `areas.requirements` - `"in_progress"` while you work, `"done"` at the end.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as a design tree in rounds. Facts first: read the value proposition, the README and any docs the project already has (an existing repo's docs often state the users and requirements); never ask what they answer.

Round 1:

- **Target users** - draft from the value proposition and what the user said, and ask them to correct it.

Round 2 (needs the target users):

- **Requirements** - draft the few the value proposition implies, numbered after the last one already saved. Turn each into one acceptance check, and rework any the user rejects until they agree. Keep each one observable: "the app is fast" is a performance budget, not a requirement.
- **Domain jargon** - "Does this domain have its own vocabulary that newcomers would trip over?" Explain in one line what yes turns on.

Requirements and users are per project, not kit defaults, so the override protocol doesn't apply to them.

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "requirements": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `requirements` set to `"in_progress"`.
3. When the user confirms the area, save the `requirements` object `{"target_users", "items": [{"id", "text", "acceptance"}], "domain_jargon"}`, every requirement already saved kept. Keep the exact field names.
4. In the same call, save `areas` with `requirements` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area requirements`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
