---
name: stack-recipe
description: Draft and prove a recipe for a stack alpha's kit has no recipe for (e.g. Go, Swift, Kotlin, Elixir) in the alpha interview - the commands, files and CI setup a component on that stack needs - so it can be generated. Use only inside an alpha project interview (/alpha:new-project), inside /alpha:adopt to adopt a repo's own tools, or when the user asks to set up a stack the kit lacks.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Stack recipe

## Before you start

You need `<target>` (the folder the interview is setting up) and `<stack>` (the stack's name, lowercase with hyphens, e.g. `go`, `swift`, `kotlin`). The answers live in `<target>/.claude/alpha/project.json`.

- No project.json: tell the user to start with `/alpha:new-project`, and stop.
- `alpha:adopt` sent you for a component of an existing repo: draft an adopted recipe as "Adopting a repo's tools" below says, whether or not the kit has the stack.
- `alpha:adopt` sent you for a component with no project structure yet: there are no tools to adopt. Go on as for a new project: the next line, then the steps below.
- Otherwise, `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" recipe list` names the stack: the kit already has a recipe; use it, and stop.

## Purpose

A recipe tells alpha how to set up a component on a stack: the commands for each check, which files are code and which are tests, what the skeleton contains, how CI installs the toolchain. The kit's own recipes are proven in many projects; this one is drafted for this project, so it's **less proven**: say so plainly. alpha proves it in a scratch folder before anything is generated, so the project's checks are green from the first commit.

## What a recipe holds

One JSON object, saved under `recipes.<stack>` in project.json. Paths and globs are relative to the component's folder.

- `bootstrap` - commands that install the dev tools into a fresh skeleton (often `[]` when the toolchain brings them).
- `commands` - one shell command each for `setup` (install dependencies), `format_check` (fails on unformatted files without changing them), `lint`, `typecheck` (type check or compile check), `test`, plus `format` (rewrites files), `format_file` and `lint_file` (one file, with `{file}` where the path goes). `setup` and `test` can't be empty; use `""` for a step the stack really doesn't have. An optional `structure` step runs between `typecheck` and `test`: unused or undeclared dependencies, dead exports and import cycles. Leave the key out when the stack has no such tool; it then counts as `""` and is skipped.
- `coverage`, `coverage_report` - optional, and only together: a command that runs the tests and writes a coverage report in Cobertura or another XML format diff-cover reads, and the report's path in the component (e.g. `"coverage.xml"`). Pull requests then run `coverage` instead of `test` and must cover `testing.diff_coverage`% of the lines they change. Add the coverage plugin to `bootstrap` and the report to `ignores`, or CI's "tree unchanged" step fails. Leave both out when the stack has no easy coverage tool; the component then gets only `test`.
- `manifests`, `lockfiles` - e.g. `["go.mod"]`, `["go.sum"]`.
- `source_globs`, `test_globs`, `exclude_globs` - which files are code, which are tests, which are build output or vendored.
- `ignores` - `.gitignore` entries (e.g. `"target/"`).
- `allow` - Claude Code permission rules for the stack's commands, each `Bash(<tool> <args>:*)` for a tool the recipe's own commands use (e.g. `"Bash(go test:*)"`); nothing broader.
- `why` - dev tool → reason, for the dependency log (`{}` when none are added).
- `templates` - file path → content: the manifest with strict settings, and **one setup test that checks the toolchain itself** (it must match `test_globs`). No source files and no app code. `$name` and `$slug` are always replaced (the component and the project), with no escape, so don't name a shell variable that; any other `$` stays as written. Templates are text only: binary files (a Gradle wrapper jar, say) must come from `bootstrap`. Nothing under `.git/`, `.claude/` or `.github/`, and no file alpha writes itself (`CLAUDE.md`, `README.md`, `.gitignore`, `docs/`).
- `ci` - `{"steps": [...], "env": {...}}`: GitHub Actions steps that install the toolchain, each with a `uses` pinned to the commit SHA of the latest release tag (`git ls-remote https://github.com/<owner>/<repo> refs/tags/<tag>`; for an annotated tag, the peeled `^{}` line), with the tag in `version`, and no `run` steps; `${dir}` in a value is the component's folder plus `/`. CI runs `setup` and the checks, never `bootstrap`, so a tool `bootstrap` installs globally (a linter, say) must instead be a project dependency, come from a CI step, or ship with the toolchain.
- `dependabot` - the Dependabot ecosystem name (e.g. `gomod`, `gradle`, `nuget`, `swift`, `mix`), or `""` if it has none.
- `baseline` - optional, for a project with legacy findings to baseline: per step (`lint`, `typecheck`, `structure`, `test`), how its findings read, as `{"command": "<the check with machine-readable output>", "pattern": "<regex with (?P<file>…) and (?P<rule>…) groups, matched per line>"}`, or `"json": {"items": "<path, * walks a list or object>", "file": "<field, or @0 for the key the first * walked>", "rule": "<field>", "where": {"<field>": "<value>"}}` instead of `pattern` for JSON output. `lint` also needs `file_command`, the same for one file with `{file}`. Write the pattern against the tool's real output, never a guess. `recipe try` runs each command on the clean skeleton, and fails when it reads findings there or fails without readable output.
- `rules` - optional: rules for code on this stack that no tool in the recipe checks, each `{"id": "<lowercase-with-hyphens>", "rule": "<one line>"}`. They go into the project's CLAUDE.md and the principles reviewer checks them. Write code names in backticks.

Leave out `proven`: a drafted recipe is always less proven, and alpha marks it so.

## Steps

1. **Facts first; never ask them.** Look up:
   - The alpha tool registry's picks: `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" registry list --stack <stack>` prints one tab-separated line per tool: id, category, last reviewed date, stacks (comma-separated). Spell `<stack>` as the registry's stacks column does; a mismatch silently returns only the cross-cutting tools. Tools marked `all` are cross-cutting and apply to every stack.
   - `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" registry show <id>` gives a tool's rationale and limitations. Its `mise:` line is the version alpha itself installs, so take a recipe's dev-tool versions from your own lookup, not from the registry.
   - Registry picks come first: use them for lint and format, type check, `structure` (unused dependencies, import rules) and `coverage`. Use the toolchain's own tool only for a check the registry has nothing for. If no row names `<stack>`, the registry doesn't cover the stack: use the toolchain's own tools for every check.
   - `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" registry stale` lists tools not reviewed lately (same columns; it prints nothing when none are). If it lists a tool you mean to use, check it is still maintained before using it, and tell the user.
   - The stack's usual test runner, formatter, linter and type or compile check, for the checks the registry leaves open.
   - Is the toolchain installed, and which version: `<tool> --version`.
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

## Adopting a repo's tools

For `alpha:adopt`, the recipe runs the tools the repo already uses, on its real code (spec §5b):

- Name it `<component>-<stack>` (e.g. `api-python`), set `"adopted": true`, and set it as the component's `stack`. When the repo's tools are the kit's (`recipe list`), add `"extends": "<kit stack>"` and give only what differs: it takes the kit's commands, globs, CI setup, rules and readers.
- Facts come from the repo: its manifests and lockfile, its CI workflow and task runner (`Makefile`, `package.json` scripts) for the commands it already runs, and its real test layout for `test_globs` (e.g. `spec/**`, `**/__tests__/**`). Use those commands as they are.
- `bootstrap` stays `[]` and `templates` `{}`: adopting installs nothing. A check the repo lacks stays `""`, and so does `test` when it has no tests; the adoption plan adds them later. Set `format_check` to `""` when today's code isn't formatted.
- For every check that fails on today's code, add `[baseline.<step>]` (see above) so its findings can be baselined.
- `recipe try` proves it on a throwaway worktree of the repo's HEAD: `setup` must pass, a failing check only when its reader reads the findings, and it lists them as `<step>: N findings` to baseline. Tell `alpha:adopt` which ones, as `<step>:<component>`.

## Done

The recipe is done when `recipe try` prints `ok`. Go back to the components area, which can now finish. After the project is generated, `/alpha:new-project` asks whether to save the recipe to the kit for future projects.
