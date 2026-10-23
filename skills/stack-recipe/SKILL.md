---
name: stack-recipe
description: Draft and prove a recipe for a stack alpha's kit has no recipe for (e.g. Rust, Go, Swift, Kotlin) in the alpha interview - the commands, files and CI setup a component on that stack needs - so it can be generated. Use only inside an alpha project interview (/alpha:new-project) or when the user asks to set up a stack the kit lacks.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Stack recipe

## Before you start

You need `<target>` (the folder the interview is setting up) and `<stack>` (the stack's name, lowercase with hyphens, e.g. `rust`, `go`, `swift`). The answers live in `<target>/.claude/alpha/project.json`.

- No project.json: tell the user to start with `/alpha:new-project`, and stop.
- `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" recipe list` names the stack: the kit already has a recipe; use it, and stop.

## Purpose

A recipe tells alpha how to set up a component on a stack: the commands for each check, which files are code and which are tests, what the skeleton contains, how CI installs the toolchain. The kit's own recipes are proven in many projects; this one is drafted for this project, so it's **less proven**: say so plainly. alpha proves it in a scratch folder before anything is generated, so the project's checks are green from the first commit.

## What a recipe holds

One JSON object, saved under `recipes.<stack>` in project.json. Paths and globs are relative to the component's folder.

- `bootstrap` - commands that install the dev tools into a fresh skeleton (often `[]` when the toolchain brings them).
- `commands` - one shell command each for `setup` (install dependencies), `format_check` (fails on unformatted files without changing them), `lint`, `typecheck` (type check or compile check), `test`, plus `format` (rewrites files), `format_file` and `lint_file` (one file, with `{file}` where the path goes). `setup` and `test` can't be empty; use `""` for a step the stack really doesn't have.
- `manifests`, `lockfiles` - e.g. `["Cargo.toml"]`, `["Cargo.lock"]`.
- `source_globs`, `test_globs`, `exclude_globs` - which files are code, which are tests, which are build output or vendored.
- `ignores` - `.gitignore` entries (e.g. `"target/"`).
- `allow` - Claude Code permission rules for the stack's commands (e.g. `"Bash(cargo test:*)"`).
- `why` - dev tool → reason, for the dependency log (`{}` when none are added).
- `templates` - file path → content: the manifest with strict settings, and **one setup test that checks the toolchain itself** (it must match `test_globs`). No source files and no app code. `$name` is the component, `$slug` the project; any other `$` stays as written.
- `ci` - `{"steps": [...], "env": {...}}`: GitHub Actions steps that install the toolchain, each `uses` pinned to a release tag or commit SHA; `${dir}` in a value is the component's folder plus `/`.
- `dependabot` - the Dependabot ecosystem name, or `""` if it has none.

## Steps

1. **Facts first; never ask them.** Look up:
   - Is the toolchain installed, and which version: `<tool> --version`.
   - The stack's usual test runner, formatter, linter and type or compile check, preferring what ships with the toolchain.
   - The manifest and lockfile names.
   - The current GitHub Actions setup action and its latest release tag.
   - The Dependabot ecosystem name.

   If the toolchain isn't installed, tell the user how to install it and wait.
2. **Draft** the whole recipe. Use the strictest settings the stack offers (warnings as errors, strict type checks). The setup test asserts the toolchain works, e.g. that a trivial expression compiles and runs.
3. **Show it** to the user in plain words: what each check runs, which files the skeleton gets, what CI installs, and that it's less proven than the kit's own recipes. Ask: "Use this recipe?" Change it until they agree.
4. **Save** it, sending `recipes` whole (keep any other drafted recipe), on one line in single quotes (write each `'` inside it as `'\''`, and newlines in templates as `\n`):
   `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"recipes": {"<stack>": {…}}}'`
5. **Check** it: `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" recipe check <target> <stack>` prints `ok`, or the field to fix. Fix, save, check again.
6. **Try** it: `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" recipe try <target> <stack>` writes the skeleton files in a scratch folder and runs the bootstrap and every check. It prints `ok: <stack> recipe proven`, or the failing command with its output. Fix the recipe (ask the user when the fix is a choice, e.g. dropping a check), save, and try again until it's proven. Any later edit needs another try; generating refuses a recipe that wasn't proven in its current form.

## Done

The recipe is done when `recipe try` prints `ok`. Go back to the components area, which can now finish. After the project is generated, `/alpha:new-project` asks whether to save the recipe to the kit for future projects.
