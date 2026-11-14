---
name: design-language
description: Settle a new project's design language in the alpha interview - optionally, the one look every visual follows, from diagrams in the docs to the UI - its character, colors, typography, shape, imagery and diagram style. The user may skip it, and then alpha enforces and recommends nothing about visuals. Use only inside an alpha project interview (/alpha:new-project) or alpha:extend or /alpha:adopt or when the user asks to revisit the design language of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Design language

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. If the `alpha:extend` skill sent you here, go on as it says. Otherwise invoke `alpha:extend` with the Skill tool and follow it; it brings you back here.
- project.json has an `adoption` key and no `manifest`: `alpha:adopt` is bringing an existing repo in. Go on as it says; its rules win over this skill's, and don't point to `/alpha:new-project` afterwards.
- `areas.testing` isn't `"done"`: tell the user the earlier areas come first and to run `/alpha:new-project`, and stop.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

A design language is the one look every visual of the project shares: the diagrams and charts in its docs, its images, and its UI ("One design language"). This area is optional, and the choice is the user's. Defined, it becomes `docs/design-language.md`, a principle the reviewer checks every changed visual against (CLAUDE.md states it and names the page), and the source the UI area's tokens, typography and icons come from. Which files count as visuals comes from `defaults.design_language.visuals` and lands as `[visuals]` in `docs/principles.toml`, with the user's third-party paths excluded. It is guidance with room for deliberate exceptions, not a wall: how firmly colors are held is the user's choice. Skipped, alpha writes none of that, and enforces and recommends nothing about how visuals look.

## Fields this area settles

- `design_language.defined` - `true` when the project has a design language, `false` when the user skips it. With `false`, send no other field.
- `design_language.character` - the look and feel in a sentence or two, in the user's words, e.g. `"Calm and technical: flat, high contrast, generous whitespace, no gradients or shadows."`
- `design_language.colors[].name` - one entry per color of the palette, named by its role, e.g. `"accent"`, `"surface"`, `"text"`, `"danger"`.
- `design_language.colors[].value` - the color as written in code, e.g. `"#0B5FFF"`; for a color that differs by theme, both, e.g. `"#0B5FFF (light), #6EA8FF (dark)"`.
- `design_language.colors[].use` - where the color is used, e.g. `"links, primary actions, the highlighted path in a diagram"`.
- `design_language.typography` - the typefaces by role, with fallbacks, e.g. `"Inter for text and labels, JetBrains Mono for code; system fallbacks"`.
- `design_language.shape` - spacing, corner radius, line weight and depth, e.g. `"4 px grid, 6 px corners, 1.5 px lines, no shadows"`.
- `design_language.imagery` - the style of icons, illustrations and screenshots, or `"none"`.
- `design_language.diagrams` - how diagrams and charts are drawn: the tool, and how the language applies to them, e.g. `"Mermaid in Markdown, themed with the palette; boxes for components, the accent color for the path being explained"`.
- `design_language.source` - where a fuller guide lives (a path in the project or a URL), or `""` when these answers are all of it.
- `design_language.palette_check` - what happens to a color outside the palette in diagrams, SVG and stylesheets: `"advise"` (the reviewer sees it and judges whether it is a deliberate exception or drift), `"enforce"` (a repository check also fails on it, at Stop and in CI) or `"off"`.
- `design_language.third_party` - paths or globs of visuals that follow somebody else's design (partner logos, payment icons, badges), relative to the project root, e.g. `["docs/partners/**"]`; `[]` when there are none.
- `areas.design_language` - `"in_progress"` while you work, `"done"` at the end.
- `decisions[]` - one entry with `"area": "design_language"`.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it).

Round one is a single question:

- **Define a design language?** - explain in two lines what defining it switches on (the page, the reviewer's check on every visual, the UI area drawing from it) and that skipping it switches all of that off. Recommend yes when a component has a UI or the user already has a brand or style guide, and skipping otherwise. Either answer is fine; never argue for one.

When the user skips, ask nothing else: save `{"defined": false}` and a decision saying the project has no design language, so alpha enforces nothing about its visuals. Don't suggest colors, typefaces or diagram styles anywhere later in the interview.

When the user defines one, facts first: read any guide, tokens file or brand page the user points to and recommend from it. With nothing to read, propose a small, complete language that fits the product and its users from identity, and say it's a starting point. Then one round:

- **Character** - the look and feel in a sentence or two.
- **Colors** - the palette by role: at least the background, the text, one accent, and the status colors the project needs. Recommend the fewest that cover the visuals the project will have; each needs enough contrast with the surface it sits on.
- **Typography** - typefaces for text and for code, with fallbacks.
- **Shape** - spacing, corners, line weight, depth.
- **Icons and imagery** - one icon and illustration style, or none.
- **Diagrams and charts** - the tool (recommend one that lives as text in the repo, such as Mermaid, so the reviewer can read it) and how the colors and shapes apply.
- **Source** - where a fuller guide lives, if there is one.
- **How firmly** - recommend `defaults.design_language.palette_check`. Explain: a design language guides, and good design sometimes steps outside it, so `advise` shows off-palette colors to the reviewer, who lets a deliberate exception through and reports drift; `enforce` suits a strict brand, and fails the check on any color the palette lacks; `off` leaves it all to the reviewer's reading. In an adoption, never recommend `enforce`: the repo's existing colors would fail it.
- **Third-party visuals** - which paths hold other people's brand assets? Look for them first (logo, partner, vendor and badge folders) and recommend what you find, or none.

When the palette check differs from the default, follow the grilling skill's override protocol (key `design_language.palette_check`).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "design_language": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` and `decisions` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `design_language` set to `"in_progress"`.
3. When the user confirms the area, save the `design_language` object: `{"defined": false}` when skipped, else `{"defined": true, "character", "colors": [{"name", "value", "use"}], "typography", "shape", "imagery", "diagrams", "source", "palette_check", "third_party": []}`. Keep the exact field names.
4. In the same call, save `decisions` with one entry for this area, replacing any earlier one with `"area": "design_language"`:
   `{"area": "design_language", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` names the choice (e.g. "A flat, high-contrast design language", or "No design language"); `context` is which visuals the project will have and who sees them; `decision` gives the character, the palette and the diagram style, or says it was skipped; `consequences` says the reviewer checks every changed visual against `docs/design-language.md`, or that nothing about visuals is enforced.
5. In the same call, save `areas` with `design_language` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area design_language`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
