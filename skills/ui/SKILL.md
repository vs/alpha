---
name: ui
description: Settle a new project's visual system in the alpha interview - for each component with a UI, its component library, design tokens, icons, typography, theming and visual regression checks. Skipped when no component has a UI. Use only inside an alpha project interview (/alpha:new-project) or when the user asks to revisit the UI of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# UI

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. Tell the user that extending a generated project arrives in a later version of alpha, and stop.
- `areas.testing` isn't `"done"`: tell the user the earlier areas come first and to run `/alpha:new-project`, and stop.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

A UI built from a declared set of tools stays consistent and cheap to change ("A deliberate visual system"). This area names that set for every component with a UI: frontends and mobile apps always, plus any component with `traits.has_ui`. With no UI there is nothing to decide: say so in one line, save the empty answer, and finish. Projects with a UI get `docs/ui.md`, and the tokens file becomes a risk path the reviewer looks at closely.

## Fields this area settles

- `ui.components[].name` - one entry per component with a UI, by name; none for the others.
- `ui.components[].library` - the component library, in the user's words (e.g. `"shadcn/ui"`, `"Material 3"`, `"SwiftUI only"`), or `"none"`.
- `ui.components[].tokens` - where the design tokens (colors, spacing, type scale) live, as a path relative to the project root (e.g. `"web/src/styles/tokens.css"`); the file may not exist yet.
- `ui.components[].icons` - the icon set, or `"none"`.
- `ui.components[].typography` - the typefaces and fallbacks, e.g. `"Inter, system fallback"`.
- `ui.components[].theming` - `"light"`, `"dark"`, `"light-dark"` or `"custom"`.
- `ui.components[].visual_regression` - how visual changes are caught, e.g. `"Playwright screenshots"`, or `"none"`.
- `areas.ui` - `"in_progress"` while you work, `"done"` at the end.
- `decisions[]` - one entry with `"area": "ui"`.

## Questions

When no component has a UI, ask nothing: save `{"components": []}` and a decision saying the project has no UI, so the visual-system principle doesn't apply.

Otherwise run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as one round per component with a UI. Facts first: look up what the component's stack and framework usually use (its manifest, the stack's docs) and recommend from that. Never assume a library the stack can't use.

- **Component library** - recommend one that fits the stack and the users from identity; explain that a library brings accessible, consistent building blocks.
- **Design tokens** - recommend a path inside the component (e.g. `<path>/src/styles/tokens.css`, or the platform's theme file). Explain: every color, spacing and font comes from there, so a restyle is one file.
- **Icons** and **typography** - recommend what the library pairs with.
- **Theming** - recommend `defaults.ui.theming`.
- **Visual regression** - recommend `defaults.ui.visual_regression`, adapted to the component's end-to-end tool from the testing area.

When an answer differs from a default, follow the grilling skill's override protocol (keys `ui.theming`, `ui.visual_regression`).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "ui": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` and `decisions` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `ui` set to `"in_progress"`.
3. When the user confirms the area (or right away, with no UI), save the `ui` object `{"components": [{"name", "library", "tokens", "icons", "typography", "theming", "visual_regression"}]}`. Keep the exact field names.
4. In the same call, save `decisions` with one entry for this area, replacing any earlier one with `"area": "ui"`:
   `{"area": "ui", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` names the choice (e.g. "shadcn/ui on one tokens file"); `context` is who uses the UI; `decision` gives each component's library, tokens path and theming; `consequences` says how drift is caught, plus any defaults wish from the override protocol.
5. In the same call, save `areas` with `ui` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area ui`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
