# Not-code folders: research

Date: 2026-11-20

## The case

`~/workspace/mental` is a Rust workspace (`model`, `extract`, `mentalc`) that also holds Python which is not its code: `examples/report-jobs` (a sample app with four deliberate bugs, and its hand-written golden reference model under `model/`), `docs/research/*/experiments` (research scripts) and `extract/tests/fixtures` (inputs the extractor parses).

## How alpha treats such files today

The hooks decide what is code from each component's globs in `docs/alpha/principles.toml` (`project-files/hooks/_common.py:219-314`). mental's Rust globs match only `.rs`, so its Python is never formatted or linted on edit and never needs tests. But a file outside every component is still treated as code in four places:

- **Review:** a changed file outside every component makes every reviewer principle apply (`project-files/hooks/review.py:333-346`), and the file is in the brief's diff, so the reviewer reports the example's deliberate bugs.
- **Docs rule at Stop:** `is_behavior` returns true for a file in no component (`project-files/hooks/stop_checks.py:675`), so a docs-map glob over it requires a doc update.
- **Weaken guard:** `never-weaken-checks` applies when no component holds the file (`project-files/hooks/guard_paths.py:163-166`), so a lint or type suppression comment in the example is blocked. Writing this file hit it: the guard blocked a Markdown file in no component for quoting two suppression comments.
- **Survey:** `alpha adopt survey` lists every folder with a recipe's `[detect]` marker (`src/alpha/adopt.py:136-170`), so `examples/report-jobs/pyproject.toml` becomes a candidate Python component.

A file inside a component that its globs match (a Python component at the root holding `examples/`) is code to every hook, with only the recipe's `exclude_globs` to leave anything out.

mental's repository checks all pass today (`mise run --continue-on-error ci`, 2026-11-20). Its CI limit, that a Rust job can't run `uv sync` in report-jobs first (mental's CONTRIBUTING.md, Exceptions), is a different gap: a component's CI job needs an extra step.

## Prior art

| Tool | Model | Lesson for alpha |
|---|---|---|
| GitHub Linguist | Separate `.gitattributes` flags: `linguist-vendored`, `linguist-documentation` (out of language stats), `linguist-generated` (also collapsed in diffs) ([overrides](https://github.com/github-linguist/linguist/blob/main/docs/overrides.md)) | One label ends up meaning different exclusions, so each flag should say what it takes out. |
| SonarQube | `sonar.sources`/`sonar.tests` scope, `sonar.exclusions` removes files from analysis, `coverage.exclusions` drops one metric ([scope](https://docs.sonarsource.com/sonarqube-cloud/managing-your-projects/project-analysis/setting-analysis-scope/excluding-files-based-on-patterns.md)) | Exclusions win over inclusions; excluded files are "not analyzed at all". |
| ruff | `exclude` replaces the defaults, `extend-exclude` adds; a path passed explicitly is linted anyway unless `force-exclude = true` ([settings](https://docs.astral.sh/ruff/settings/)) | alpha's post-edit hook runs `ruff check {file}`, so alpha must filter before it calls a tool. |
| pyright | `exclude` only decides the project files; excluded files imported by included ones are still checked; `ignore` suppresses diagnostics ([config](https://github.com/microsoft/pyright/blob/main/docs/configuration.md)) | A tool's exclusion can be partial without saying so. |
| ESLint, typos | ESLint skips an ignored file passed explicitly with a warning; typos needs `--force-exclude` ([eslint](https://eslint.org/docs/latest/use/configure/ignore), [typos](https://github.com/crate-ci/typos/blob/master/docs/reference.md)) | Same bypass. |
| Biome, pre-commit | One root list that per-check lists may only narrow ([biome](https://biomejs.dev/reference/configuration/), [pre-commit](https://pre-commit.com/)) | A single root list is the common shape. |
| Renovate, Dependabot | Renovate's recommended preset ignores `**/examples/**`, `test`, fixtures ([presets](https://docs.renovatebot.com/presets-default/)); Dependabot has `exclude-paths` ([changelog](https://github.blog/changelog/2025-08-26-dependabot-can-now-exclude-automatic-pull-requests-for-manifests-in-selected-subdirectories/)) | Examples and fixtures are the usual non-code folders. |
| Semgrep, GitHub secret scanning | Semgrep's Secrets scans ignore every `.semgrepignore` ([semgrep](https://docs.semgrep.dev/ignoring-files-folders-code)); GitHub advises excluding as little as possible from secret scanning and reviewing the list ([docs](https://docs.github.com/en/code-security/secret-scanning/using-advanced-secret-scanning-and-push-protection-features/excluding-folders-and-files-from-secret-scanning)) | Secret scanning must not honour a "not code" list. |

## Options

1. **One project-wide list of not-code folders, honoured by the hooks, the reviewer and the survey.** One source of truth that can't drift between checks; alpha filters paths itself, so the tools' explicit-path bypass doesn't matter. A folder inside a component of the same stack is still linted by the component's own tools in CI until the tool config excludes it too. Fixes mental.
2. **The same list, also written into each kit recipe's tool configs** (ruff, pyright, coverage, pytest, tsconfig, biome, knip, dependency-cruiser). Covers a Python project's own `examples/` end to end, but every recipe template changes, each tool's syntax differs, and an adopted repo keeps its own configs anyway.
3. **Per-component extra excludes.** Precise, but they can drift apart, and mental's Python is in no component, so it changes nothing there.

The user chose option 1 on 2026-11-20, with not-code files left out of the review but named in the brief.
