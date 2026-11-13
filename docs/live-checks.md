# Live checks

Dated runs of the real kit (headless `claude -p`, `bin/alpha`, the evals), what each verified, and what stayed open. Moved here from CLAUDE.md, which links to it.

## Live run findings (2026-10-20, Claude Code 2.1.303)

A scripted `claude -p --plugin-dir` run answered the `web-ts-plus-python-api` scenario (with `review.max_lines = 100` instead of the scenario's observability override, and "no" to making it a default). It reached a generated, bootstrapped and committed project in 15 turns.

- Verified: four grouped commits (docs, chore, build(api), build(web)) with only the session's trailer; `uv run pytest`, `pyright`, `pnpm vitest run` and `pnpm tsc --noEmit` pass; nothing kit-specific at the root and no `src/` placeholders; decision 0004 and `docs/principles.toml` record `max_lines = 100`; the kit's `defaults/` stayed unchanged.
- Hooks in the generated project: `git commit --no-verify` is blocked; `# type: ignore` gets an "ask" (a denial in `-p` mode, where nobody can answer it); a source file without a test makes Stop block (three times, then it gives up with a message); edited files are formatted and linted.
- Claude Code always asks before Write/Edit under `.claude/` (allow rules and PreToolUse "allow" can't pre-approve it), which cost an approval per save. The skills now save through `alpha answers write <target> --json '…'` instead: one-line Bash calls, so at most a Bash approval with "don't ask again". A multi-line heredoc form was still prompted; the one-line form ran without a prompt in a follow-up run.
- A skill's `allowed-tools` seemed to pre-approve the alpha CLI only in the turn the skill was invoked in (one probe each way); later turns may ask for each `bin/alpha` call unless you add the optional rule above.
- Without a git identity, `alpha commit-skeleton` now stops and says how to set one instead of committing as `you@host.local`.

## Docs and CI live check (2026-10-22)

`bin/alpha` took the `web-ts-plus-python-api` scenario through `answers check`, `generate`, `bootstrap` and `commit-skeleton`: five commits ending with `ci: Run every component's checks in CI`, clean tree.

- Bootstrap now runs each component's CI checks (setup, format check, lint, typecheck, test); all passed for Python and TypeScript, including a TypeScript component at the root (slow tests).
- The generated Stop hook blocked a new `api/app/routes/*.py` until `docs/guide/` changed, then allowed it.
- Not yet verified: the workflow on GitHub itself. `actionlint` wasn't installed; the workflow was checked by parsing it and by Biome's YAML formatter.

## Core areas live check (2026-10-22)

Both scenarios went through `bin/alpha` (`answers check`, `generate`, `bootstrap`, `commit-skeleton`) with all twelve areas answered.

- web+API: six commits ending with `ci: Run every component's checks in CI` and `ci: Schedule dependency updates`; docs include architecture (responsibilities, contracts, errors), glossary, security and observability; `.github/dependabot.yml` covers uv, npm and github-actions. Clean tree.
- ML single (nothing deployed): no glossary and no observability doc; `docs/security.md` says nothing is deployed. Clean tree.
- The generated path guard blocked `api/keys/**` (an extra protected path) and allowed normal source files. Its message used to talk about lockfiles and secrets for every protected path; it now names the glob and says to ask the user.

## Rules in context live check (2026-10-23)

In a generated web+API project, with headless `claude -p`:

- Asked what it was told at session start, without reading files, Claude listed all 13 decision records with numbers, titles and paths, and the observability override. It first read the override line ("active, components api, web") as applying to both components; the index now quotes the record's `Principle:` header ("loosen, scope component:api").
- A general-purpose subagent asked to add `api/app/routes/ping.py` without tests: post-edit recorded the file for that subagent, SubagentStop blocked it three times and then let it stop with a message, and the main session's Stop flagged the untested file the same way.
- In an untrusted folder, `-p` ignores the project's `permissions.allow` (Claude Code prints a warning), but the hooks still run.

## Reviewer live check (2026-10-23)

In a generated web+API project, headless `claude -p` was asked to add `api/app/security/files.py` (a risk path) with a catch-all `except Exception: return b''`, plus a test.

- The first run found three hook bugs, now fixed with tests: a pyproject.toml tool-config edit was taken as a new dependency (the dependency check now keys on lockfiles); giving up on that check skipped the review gate; and the working-tree snapshot failed in generated projects (their `.gitignore` covers the state folder), so review debt was always zero.
- After the fixes, the stop checks passed and Claude ran the principles-reviewer unprompted. It recorded three findings: `never-weaken-checks` (the catch-all), `fail-helpfully` (errors become `b''`, against decision 0004), and `decision:0005` (tests don't name their requirement). Stop blocked once; when the same block repeated, the turn ended with the findings shown, instead of looping until Claude Code's cap.
- `claude -p --continue "accept F-… F-…"` accepted two findings. Claude recorded decision 0014 with `Accepts:` lines, fixed the third finding, and the re-review came back clean, so the reviewed tree advanced.

## Generic stack live check (2026-10-23)

With only the identity area done, headless `claude -p --plugin-dir` ran the components area for a Rust CLI.

- The components skill handed off to stack-recipe, which looked up the installed toolchain and the current Rust setup action and drafted a recipe. It was stricter than the scenario's: `Cargo.toml` lints deny warnings and Clippy's `all` and `pedantic`; a `rust-toolchain.toml` pins Rust 1.93 with rustfmt and clippy; CI uses `actions-rust-lang/setup-rust-toolchain@v2.0.0`. There are no `src/` files.
- `alpha recipe try` printed `ok: rust recipe proven`, and `answers check --area components` printed `ok`.
- Editing the recipe afterwards (adding `-- -D warnings` to clippy) made `answers check` refuse it until it is proven again.

## Remaining areas live check (2026-10-26)

All three scenarios went through `bin/alpha` (`answers check`, `generate`, `bootstrap`, `commit-skeleton`) with all 17 areas answered. Each ended with a clean tree.

- web+API: six commits; `docs/ui.md`, `docs/data.md`, `docs/performance.md`, `docs/releases.md`, plus `CHANGELOG.md` in the docs commit. ML single: `docs/data.md` with only the experiments section, no UI or performance doc. Rust CLI: no UI or data doc; `docs/performance.md` holds the startup budget. (The Rust bootstrap needed the toolchain's own `bin` on PATH, because the `~/.cargo/bin` links on this machine are broken.)
- In the web+API project, a committed `api/migrations/0001_create_uploads.sql` was edited after SessionStart. The generated Stop hook blocked with the append-only message. After the `git checkout <base> -- …` it names and a new `0002` migration, the mechanical checks passed. The review gate then asked for the principles-reviewer, since migrations are risk paths.
- Headless `claude -p --plugin-dir` ran releases, data, accessibility and performance in order, taking every recommendation (20 turns). All four checks print `ok`. The budgets are the per-kind defaults (api p95 < 300 ms; web LCP < 2.5 s and bundle < 200 KB gzipped), each with a measuring tool looked up for its stack (k6, Lighthouse CI, size-limit), and accessibility uses axe through Playwright. Claude built each save with a multi-line `python3` heredoc instead of the skills' one-line `answers write`. That ran here because `-p` doesn't prompt, but interactively it would ask once per save.

## Extend live check (2026-10-28)

`bin/alpha` took the `web-ts-plus-python-api` scenario through `answers check`, `generate`, `bootstrap` and `commit-skeleton`. A hand edit at the end of CLAUDE.md was committed, then a `worker` component (a clone of api, with a components decision and the git scope) was saved with one `answers write`.

- `update --dry-run`, `update`, `bootstrap --component worker` and `commit-update` made five commits (docs, chore, `build(worker)`, two `ci`), through the commit-msg hook. The hand edit stayed (CLAUDE.md merged cleanly), `worker/` checks pass, the tree was clean and a second `update --dry-run` printed "nothing to change".
- Headless `claude -p --plugin-dir` ran `/alpha:extend switch the changelog off` (16 turns). Extend invoked the releases skill, kept all 18 decisions verbatim and added decision 0020; `update` listed CHANGELOG.md as stale and CLAUDE.md as a conflict (the team note sat next to the removed changelog link). Claude merged it, keeping the note, and `commit-update` committed. The Stop hook passed.
- Fixed in the extend skill (Task 6's review): decisions and overrides are sent whole; a repeated "Revisit" message goes to the user; nothing generated is written before the user confirms; an unapplied or uncommitted update resumes at the right step; area skills don't point back to `/alpha:new-project`. Only the whole-array send ran live (and the hand-off back to step 3); no "Revisit" message came up, and the §1 resume branches and the §4 wording were not exercised.
- Fixed: commit-update commits only alpha's writes, so the deleted CHANGELOG.md stayed staged and Claude improvised its commit (rejected once for the 72-char wrap). The skill now says to commit the deletion after commit-update, with a conventional message and step 7's attribution lines as trailers. The next run did it in one try, and its commit carried the same Co-Authored-By trailer as commit-update's (in `-p` there is no session line).
- In the first run, the prompt said "yes to every confirmation", so grilling's defaults question ran `alpha defaults set`, which committed to the alpha checkout's current branch (here a feature branch; reverted). Run live checks with `ALPHA_SOURCE` pointing at a throwaway copy of the checkout, and answer no to making anything a default.
- Open: dry-run diffs of long files (docs/principles.toml) show some unchanged lines as removed and re-added, because difflib's autojunk heuristic treats lines that repeat many times as junk. The diff still applies correctly; it is only noisy.
- Not verified: interactive prompts. Claude read project.json with `python3 -c` and wrote a scratch file to `/tmp`; interactively, each such Bash call would ask, unlike the Read tool.
- Found by the final branch review and fixed after this live check, with tests but not exercised live: commit-update keeps the proposals of conflicts that weren't merged (alpha update no longer clears earlier ones); alpha update refuses a new component's folder that holds uncommitted files; alpha update absorbs its own writes into the review state, so a Stop before commit-update doesn't review them, and runs the review hook with `CLAUDE_PROJECT_DIR` set to the target; an override scoped to a removed or renamed component stays valid and stops applying; the two refusals without a next step now give one; a moved component is checked by its templates, not its manifests; and the extend skill's quoted output, `<target>` and bootstrap step were corrected.

## Interview evals (2026-10-29)

`bin/alpha-evals run` drove all three scenarios through the real `/alpha:new-project` (kit 5aa99cc, Opus interviewer in auto mode, Sonnet simulated user, $20 cap per scenario). All three stopped at the cap before generating anything, so the skeleton checks and the reviewer probe were skipped. The run cost $64.66.

- How far each got: ML single had 14 of 17 areas done after 17 exchanges (performance in progress); web+API had 10 after 19; Rust CLI had 8 after 17.
- Cost grows with each exchange, from $0.28 for the first call to $2.2–3.0 by the 17th, because every resumed call carries the whole interview. A complete interview in one session would cost roughly $50 or more on Opus. Open: a fresh interviewer session every few exchanges (new-project resumes from project.json) would keep calls near the first one's cost, and would test the resume path too.
- Every answer recorded so far matched the briefs: ML 9 of 9, web+API 12 of 12, Rust 6 of 6. Free-text fields are compared by containment (a `~` pointer), after "MLflow with a local file store" failed an exact match for MLflow.
- The interviewer runs in auto mode, the mode alpha is used in here. Auto mode denied nothing (`prompts: pass`).
- In a smoke run under `dontAsk` (no approvals at all), the skill's opening `mkdir`/`ls` of the target folder was denied. In default permission mode, that step asks before it runs. Open.
- Smoke runs found two harness bugs, now fixed:
  - a relative `--out` gave the interviewer relative plugin paths, so the plugin didn't load;
  - the interviewer guessed the project type from the scenario name in the folder path, so projects now live in `<run>/projects/<slug>`.
- The six skeleton checks (answers through commits) pass on all three scenarios when run with `bin/alpha-evals check`. Each project was generated, bootstrapped with real uv, pnpm and Rust, and committed from the scenario files, not from an interview.
- Not verified live: the reviewer probe, and the checks on a skeleton an interview produced.

## Quality gates live check (2026-11-09)

The three scenarios (`python-ml-single`, `web-ts-plus-python-api`, `rust-cli`) were generated from `evals/scenarios/*.json` with `bin/alpha` (`generate`, `bootstrap`, `commit-skeleton`), not by interviews, in a scratch folder. For Rust, the toolchain's own `bin` was first on PATH.

- Bootstrap ran each component's checks (including `structure`: deptry, and Knip with dependency-cruiser for web), then `mise trust`, `mise install` of the project's pinned tools and `mise run ci`. All passed. The web+API project's `mise.toml` also pins squawk.
- `bin/alpha-evals check` now has two more checks: `repo-checks` (`mise run ci` exits 0) and `repo-seeds`. The seeds are Task 7's six violations (actions, secrets, typos, markdown, links, agent-config), shared with the slow tests. Each is applied to the project, `mise run check:<id>` must exit with the registry's `fails_with` and name the finding, and the file is restored. All eight checks (answers, files, settings, hooks, commands, repo-checks, repo-seeds, commits) pass on all three scenarios, and the trees stay clean.
- The first attempt stopped at `commit-skeleton`: the run had no git identity, and alpha refused to commit with a guessed one (as designed). A throwaway git config fixed it.
- Not yet verified: the workflows on GitHub (repo job, diff-cover on a PR, scheduled run).
- Not verified: the eval run with real interviews; the new checks ran on skeletons generated from the scenario files.

## Rust recipe live check (2026-11-11)

The kit now has a Rust recipe (`recipes/rust.toml`), and the `rust-cli` scenario uses it instead of a drafted one. The slow tests generated, bootstrapped and committed that scenario with Rust 1.99.1, cargo-llvm-cov 0.9.1 and cargo-machete 0.9.2.

- Every check passed on the skeleton, and `mise run ci` passed too (jactionlint accepts the two new CI steps). Each check failed on its seeded violation: misformatted `tests/bad.rs`, `unwrap()` in `src/lib.rs` (`clippy::unwrap_used`), and an unused `itoa`. diff-cover caught an untested `src/double.rs` and passed once a `src/double/tests.rs` covered it. The report leaves out `tests/` and `tests.rs`.
- cargo-llvm-cov asks before installing `llvm-tools-preview` and then waits on the terminal, so bootstrap adds the toolchain components first. `cargo install` of a version that's already installed does nothing in about 0.1 s.
- On this machine the global mise config sets `RUSTUP_TOOLCHAIN`, which overrides a project's `rust-toolchain.toml`.
- Not done: baseline readers for an adopted Rust repo. Clippy and cargo print findings as one JSON object per line, which the ratchet doesn't read yet. Not verified: the workflow on GitHub.
