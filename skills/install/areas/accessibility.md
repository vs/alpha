# Accessibility

## Before you start

`/alpha:update` reads this guide when the user asks to settle this area, and `/alpha:install` when the user picks it in the interview; it's a product area, open until then. `<target>` is their target folder; the answers live in `<target>/.claude/alpha/project.json`. Their rules win over this guide's where they differ. Only `/alpha:install` and `/alpha:update` settle a product area: when the user asks for it elsewhere, point to `/alpha:update <area>`.

## Purpose

Every UI must work with a keyboard and assistive technology ("Accessibility"), and that is far cheaper to build in than to retrofit. This area sets the target level and the automated checks that keep each UI there. It covers the same components as the UI area. With no UI there is nothing to decide: say so in one line, save the empty answer, and finish. The target and checks go into the UI section of `docs/alpha/specification.md` and the accessibility principle.

## Fields this area settles

- `accessibility.level` - `"WCAG 2.2 A"`, `"WCAG 2.2 AA"` or `"WCAG 2.2 AAA"`; `""` when no component has a UI.
- `accessibility.components[].name` - one entry per component with a UI, by name; none for the others.
- `accessibility.components[].checks` - the automated checks, in the user's words, e.g. `"axe in the end-to-end tests"`.
- `areas.accessibility` - `"in_progress"` while you work, `"done"` at the end.

## Questions

When no component has a UI, ask nothing: save `{"level": "", "components": []}`, so the accessibility principle doesn't apply.

Otherwise run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as one round:

- **Level** - recommend `defaults.accessibility.level`. Explain: AA is what most laws and public contracts ask for; AAA is rarely met in full.
- **Checks**, per UI component - recommend a checker that fits its stack and its test levels from the testing area (e.g. an axe integration in the end-to-end tests, the platform's accessibility audits on mobile), plus keyboard-only runs of the main requirements. Look up what the stack uses; never assume.

When the level differs from the default, follow the grilling skill's override protocol (key `accessibility.level`).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "accessibility": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `accessibility` set to `"in_progress"`.
3. When the user confirms the area (or right away, with no UI), save the `accessibility` object `{"level", "components": [{"name", "checks"}]}`. Keep the exact field names.
4. In the same call, save `areas` with `accessibility` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area accessibility`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
