# 0025. An optional design-language area, enforced by the reviewer

Date: 2026-11-13
Status: accepted
Kind: product

## Context

The user asked for it on 2026-11-13: "One important part of the project is missing in alpha at the moment. It's the design language of the project which applies across all visuals involved in the project, starting from the diagrams in the documentation up to UI&UX elements that support and fit that design language. I want to make that part of the alpha projects but make it optional, so some alpha users could define the design language and alpha would enforce it for all the visuals of the project. But it's possible to skip this step and then alpha won't enforce anything or recommend anything."

That settles the direction: the design language is part of alpha, optional, enforced when defined, and silent when skipped. The rest below is Claude's choice, made without asking because it is reversible:

- Where it sits. The UI area's tokens, typography and icons should come from the design language, so it has to be settled before the UI area.
- What it holds. A stack-neutral description in the user's words, as the UI area keeps its answers, with only the palette structured, because colors are the part a reader checks value by value.
- How it is enforced. The kit holds the visual-system and accessibility principles with the reviewer, and the reviewer already sees every change before it reaches main. A mechanical palette check would need choices nobody has made yet (which files count as visuals, which color notations, what to do with third-party assets).
- Older projects. Adding a required area would stop `alpha update` on every project whose answers predate it.

The number is 0025: records 0022 to 0024 reached main from other branches while this one was open.

## Decision

alpha gets an eighteenth interview area, `design_language`, between testing and UI, with the skill `alpha:design-language`.

- Its first question is whether to define a design language. Skipping saves `{"defined": false}`, and then alpha writes no page, switches on no principle and recommends nothing about visuals anywhere in the interview.
- Defined, it holds the character, the palette (name, value and use per color), typography, shape, imagery, how diagrams and charts are drawn, and where a fuller guide lives.
- A defined language renders `docs/design-language.md`, switches on the `design-language` principle ("One design language", checked by the reviewer, with the page as its `language` parameter), makes that page a risk path, states the principle in CLAUDE.md in one line that names the page (CLAUDE.md stays under its 150-line limit), and tells the UI area to recommend from it. Its decision record is `Kind: product`.
- The principles reviewer checks every changed visual it can read as text (diagram and chart source, SVG, styles, UI markup) against the page. An image it can't read isn't a finding.
- Which files are visuals is a list in the kit defaults, `[design_language.visuals]` (user request, 2026-11-13: "Run a deep research on what files are considered as visuals and such files into the list alpha maintains for that"). It holds text formats the reviewer reads, `opaque` ones it can only name (rasters, fonts, design-tool files, video), and `exclude` for third-party and generated files (dependency folders, build output, test snapshots). A project with a design language gets the list as `[visuals]` in `docs/principles.toml`; the reviewer's brief names the changed files on it. The list came from research into each format's own docs and GitHub Linguist's extension table. Left off it: formats no extension identifies (themes written in `.py`, `.dart` or `.swift` code, tokens in plain `.json`, Structurizr's `.dsl`), which the reviewer still judges from the diff.
- Answers that hold neither `areas.design_language` nor `design_language` were saved before the area existed and read as skipped, with no decision record required. An interview that lists the area must finish it.
- The list has two tiers of text files (user go-ahead, 2026-11-13: "Do all three on this branch"): `sources` are always visuals; `carriers` (docs, UI markup, templates) are named in the brief only when the change touches a diagram block, a style or a color literal, so the section doesn't fill with every changed Markdown or component file.
- The interview asks which paths hold third-party visuals (`design_language.third_party`), and they join the list's `exclude`.
- The design language guides; it isn't a wall. The user, 2026-11-13: "I don't think alpha check must be all or nothing on design language check, the design must be flexible I guess, so don't be too strict on that". So the principle allows a visual to step outside the language for a stated reason and names only drift as a finding, and the reviewer is told the same.
- How firmly colors are held is the answer `design_language.palette_check`, default `advise`: the reviewer's brief lists each color outside the palette in the changed diagrams, SVG and stylesheets, to judge. `enforce` adds a `palette` repository check that fails on one, at Stop and on a pull request. `off` does neither. The check (`palette.py`) is lenient by design: it reads hex, rgb() and hsl() only, ignores alpha, allows a rounding step per channel, always passes black and white, reads Markdown only inside diagram blocks, and leaves named colors, variables and other notations to the reviewer. It can't be baselined, so an adopted repo with legacy colors uses `advise`.

## Consequences

Projects that skip, and every project generated or adopted before this, render exactly as before. A generated project defines one later with `/alpha:extend`. By default, enforcement is the reviewer's judgment at the review checkpoint, helped by the palette scan; only a project that chose `enforce` gets a failing check at Stop and in CI. Android and Dart alpha-first hex, design-token objects and Tailwind class names are not read by the check. The spec (§4, §5, §6, §7), the README and the glossary describe the area.
