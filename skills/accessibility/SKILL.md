---
name: accessibility
description: Settle a new project's accessibility target in the alpha interview - the WCAG level and, for each component with a UI, the automated checks that hold it. Skipped when no component has a UI. Use only inside an alpha project interview (/alpha:new-project) or alpha:extend or /alpha:adopt or when the user asks to revisit the accessibility of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Accessibility

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. If the `alpha:extend` skill sent you here, go on as it says. Otherwise invoke `alpha:extend` with the Skill tool and follow it; it brings you back here.
- project.json has an `adoption` key and no `manifest`: `alpha:adopt` is bringing an existing repo in. Go on as it says; its rules win over this skill's, and don't point to `/alpha:new-project` afterwards.
- `areas.data` isn't `"done"`: tell the user the earlier areas come first and to run `/alpha:new-project`, and stop.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

Every UI must work with a keyboard and assistive technology ("Accessibility"), and that is far cheaper to build in than to retrofit. This area sets the target level and the automated checks that keep each UI there. It covers the same components as the UI area. With no UI there is nothing to decide: say so in one line, save the empty answer, and finish. The target and checks go into `docs/ui.md` and the accessibility principle.

## Fields this area settles

- `accessibility.level` - `"WCAG 2.2 A"`, `"WCAG 2.2 AA"` or `"WCAG 2.2 AAA"`; `""` when no component has a UI.
- `accessibility.components[].name` - one entry per component with a UI, by name; none for the others.
- `accessibility.components[].checks` - the automated checks, in the user's words, e.g. `"axe in the end-to-end tests"`.
- `areas.accessibility` - `"in_progress"` while you work, `"done"` at the end.
- `decisions[]` - one entry with `"area": "accessibility"`.

## Questions

When no component has a UI, ask nothing: save `{"level": "", "components": []}` and a decision saying the project has no UI, so the accessibility principle doesn't apply.

Otherwise run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as one round:

- **Level** - recommend `defaults.accessibility.level`. Explain: AA is what most laws and public contracts ask for; AAA is rarely met in full.
- **Checks**, per UI component - recommend a checker that fits its stack and its test levels from the testing area (e.g. an axe integration in the end-to-end tests, the platform's accessibility audits on mobile), plus keyboard-only runs of the main requirements. Look up what the stack uses; never assume.

When the level differs from the default, follow the grilling skill's override protocol (key `accessibility.level`).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "accessibility": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` and `decisions` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `accessibility` set to `"in_progress"`.
3. When the user confirms the area (or right away, with no UI), save the `accessibility` object `{"level", "components": [{"name", "checks"}]}`. Keep the exact field names.
4. In the same call, save `decisions` with one entry for this area, replacing any earlier one with `"area": "accessibility"`:
   `{"area": "accessibility", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` names the target (e.g. "WCAG 2.2 AA"); `context` is who uses the UI; `decision` gives the level and each component's checks; `consequences` says what fails when a check finds a violation, plus any defaults wish from the override protocol.
5. In the same call, save `areas` with `accessibility` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area accessibility`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
