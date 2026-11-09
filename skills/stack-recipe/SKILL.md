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
- `commands` - one shell command each for `setup` (install dependencies), `format_check` (fails on unformatted files without changing them), `lint`, `typecheck` (type check or compile check), `test`, plus `format` (rewrites files), `format_file` and `lint_file` (one file, with `{file}` where the path goes). `setup` and `test` can't be empty; use `""` for a step the stack really doesn't have. An optional `structure` step runs between `typecheck` and `test`: unused or undeclared dependencies, dead exports and import cycles. Leave the key out when the stack has no such tool; it then counts as `""` and is skipped.
- `coverage`, `coverage_report` - optional, and only together: a command that runs the tests and writes a coverage report in Cobertura or another XML format diff-cover reads, and the report's path in the component (e.g. `"coverage.xml"`). Pull requests then run `coverage` instead of `test` and must cover `testing.diff_coverage`% of the lines they change. Add the coverage plugin to `bootstrap` and the report to `ignores`, or CI's "tree unchanged" step fails. Leave both out when the stack has no easy coverage tool; the component then gets only `test`.
- `manifests`, `lockfiles` - e.g. `["Cargo.toml"]`, `["Cargo.lock"]`.
- `source_globs`, `test_globs`, `exclude_globs` - which files are code, which are tests, which are build output or vendored.
- `ignores` - `.gitignore` entries (e.g. `"target/"`).
- `allow` - Claude Code permission rules for the stack's commands, each `Bash(<tool> <args>:*)` for a tool the recipe's own commands use (e.g. `"Bash(cargo test:*)"`); nothing broader.
- `why` - dev tool → reason, for the dependency log (`{}` when none are added).
- `templates` - file path → content: the manifest with strict settings, and **one setup test that checks the toolchain itself** (it must match `test_globs`). No source files and no app code. `$name` and `$slug` are always replaced (the component and the project), with no escape, so don't name a shell variable that; any other `$` stays as written. Templates are text only: binary files (a Gradle wrapper jar, say) must come from `bootstrap`. Nothing under `.git/`, `.claude/` or `.github/`, and no file alpha writes itself (`CLAUDE.md`, `README.md`, `.gitignore`, `docs/`).
- `ci` - `{"steps": [...], "env": {...}}`: GitHub Actions steps that install the toolchain, each with a `uses` pinned to the commit SHA of the latest release tag (`git ls-remote https://github.com/<owner>/<repo> refs/tags/<tag>`; for an annotated tag, the peeled `^{}` line), with the tag in `version`, and no `run` steps; `${dir}` in a value is the component's folder plus `/`. CI runs `setup` and the checks, never `bootstrap`, so a tool `bootstrap` installs globally (a linter, say) must instead be a project dependency, come from a CI step, or ship with the toolchain.
- `dependabot` - the Dependabot ecosystem name (e.g. `cargo`, `gomod`, `gradle`, `nuget`, `swift`), or `""` if it has none.
- `rules` - optional: rules for code on this stack that no tool in the recipe checks, each `{"id": "<lowercase-with-hyphens>", "rule": "<one line>"}`. They go into the project's CLAUDE.md and the principles reviewer checks them. Write code names in backticks.

Leave out `proven`: a drafted recipe is always less proven, and alpha marks it so.

## Steps

1. **Facts first; never ask them.** Look up:
   - Is the toolchain installed, and which version: `<tool> --version`.
   - The stack's usual test runner, formatter, linter and type or compile check, preferring what ships with the toolchain.
   - The manifest and lockfile names.
   - The current GitHub Actions setup action and its latest release tag.
   - The Dependabot ecosystem name.

   If the toolchain isn't installed, tell the user how to install it and wait.
2. **Draft** the whole recipe. Use the strictest settings the stack offers (warnings as errors, strict type checks). The setup test asserts the toolchain works, e.g. that a trivial expression compiles and runs.
   - `bootstrap` and `setup` must not create source files: no `cargo init`, `go mod init` with a main file, `dotnet new`, `swift package init` or `gradle init` that writes code. Write the manifest as a template instead. `recipe try` fails when the commands create a file matching `source_globs`.
   - Turn the stack's well-known rules for agents and reviewers (no escape hatches from the type checker, no blanket lint suppressions, no catch-all error handling, no commented-out code) into linter and compiler settings in the templates. Add a `rules` entry only for what no tool can check, such as how dependencies are added or how external input becomes typed data: at most about five, each one that holds for every project on the stack. Don't repeat alpha's principles, which already apply.
   - `test_globs` must follow the stack's test convention (e.g. `**/*_test.go`, `src/test/**`): the Stop hook asks for a test change whenever a source file changes, and only files matching `test_globs` count.
3. **Show it** to the user in plain words: what each check runs, which files the skeleton gets, which stack rules it adds, what CI installs, and that it's less proven than the kit's own recipes. Ask: "Use this recipe?" Change it until they agree.
4. **Save** it, sending `recipes` whole (keep any other drafted recipe), on one line in single quotes (write each `'` inside it as `'\''`, and newlines in templates as `\n`):
   `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"recipes": {"<stack>": {…}}}'`
5. **Check** it: `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" recipe check <target> <stack>` prints `ok`, or the field to fix. Fix, save, check again.
6. **Try** it: `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" recipe try <target> <stack>` writes the skeleton files in a scratch folder and runs the bootstrap and every check. It prints `ok: <stack> recipe proven`, or the failing command with its output. Fix the recipe, then show the user what changed (a new or changed command, especially one that downloads or installs something) and wait for their yes before trying again; ask too when the fix is a choice, e.g. dropping a check. Save and try again until it's proven. Any later edit needs another try; generating refuses a recipe that wasn't proven in its current form.

## Done

The recipe is done when `recipe try` prints `ok`. Go back to the components area, which can now finish. After the project is generated, `/alpha:new-project` asks whether to save the recipe to the kit for future projects.
