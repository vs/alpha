# Quality Gates in alpha Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generated projects get the checks that dev-quality-gates (DQG) recommends and alpha lacks. alpha owns the tool registry from then on, so the user no longer needs DQG.

**Architecture:** Checks that aren't tied to one component become a new concept, **repo checks**. They're built from the answers into `docs/principles.toml` and pinned in a root `mise.toml`. They run in three places: a `repo` CI job, a scheduled workflow, and (for the fast ones) the Stop hook. Checks that belong to one component become optional recipe commands: `structure` and `coverage`. The kit's new `registry/` holds the tools, their pinned versions and the action SHAs. Generation reads them from there, and so does the stack-recipe skill.

**Tech Stack:** Python 3.12 (kit and stdlib-only hooks), mise, GitHub Actions, the tools listed in Task 2.

**Spec:** `docs/superpowers/specs/2026-10-19-project-kit-design.md`. Task 1 writes this plan's decisions into it as §8a, so executors read both. The source for the tool picks is DQG at commit 829848c (2026-11-02), which is CC0.

## Decisions (the planner's calls; the user skipped the design questions)

- **D1 Toolchain file.** Repo-check tools are pinned in a generated root `mise.toml`. CI installs them with `jdx/mise-action`; bootstrap runs `mise trust`, `mise install` and `mise run ci`. Generated projects now need mise, the same way they need uv or pnpm.
- **D2 No hk or pre-commit/pre-push hooks.** Spec §9 keeps `commit-msg` as the only git hook that binds everyone. Claude gets the fast repo checks at Stop, and CI is the gate.
- **D3 Facts, not questions.** Gates switch on from facts already in the answers. There are two new tunables, each offered inside an existing round with a recommended default: `dependencies.cooldown_days` (7) and `testing.diff_coverage` (80). No new area. This keeps interview cost flat, since an Opus interview already costs about $50.
- **D4 Existing projects stay as they are.** `alpha update` renders before and after with the current kit, so kit changes cancel out and old projects don't gain these gates. This matches spec §11. Opting an old project in is out of scope.
- **D5 Python import rules aren't generated.** import-linter needs packages a skeleton doesn't have. The Python recipe gains a reviewer-checked rule to add contracts once packages exist. TypeScript gets dependency-cruiser with rules that need no app code (no cycles, no production import of a dev dependency).
- **D6 Kept as alpha's picks:** pyright, Biome, Dependabot, alpha's regex secret check at Stop, and new-projects-only scope. Using alpha on existing repos (DQG's `adopt.md` use case) is not covered.
- **D7 Links.** lychee runs `--offline` on pull requests and at Stop; the online check runs on the schedule only, so PRs don't flake.
- **D8 Toolchain freshness.** The scheduled workflow fails when `mise outdated` lists a pinned repo-check tool. Dependabot doesn't update `mise.toml`, and a failing scheduled run emails the owner.

## Global Constraints

- Commits: `type(scope): Description`, description ≤ 50 chars, imperative, capitalized, no trailing period; body wrapped at 72; scopes are component names (`hooks`, `recipes`, `defaults`) or none.
- Hooks and the scripts in `project-files/` are copied into projects. They use the Python stdlib only and run with `python3`.
- No app code and no `src/` placeholders in a skeleton (spec §2).
- Every failure message says what's wrong and how to fix it (fail-helpfully).
- Every action `uses` in generated YAML is a full 40-hex SHA with a `# vX.Y.Z` comment.
- A freshly generated, bootstrapped skeleton passes every check it gets: component checks, `mise run ci`, and the CI YAML under jactionlint.
- `uv run pytest`, `uv run ruff check`, `uv run ruff format --check` and `uv run pyright` pass after every task. Tests that need network or real tools are marked `@pytest.mark.slow`.

## Review Focus

1. **The kit's own output fails the new linters:** generated Markdown under rumdl, a project slug or jargon under typos, generated YAML under jactionlint's policy, shipped skills and agents under agnix. A reasonable person expects a green first commit. Pinned by `test_scenarios_pass_repo_checks` (Task 7).
2. **mise is missing, or a tool download fails:** bootstrap should stop with an install hint, not a traceback. Pinned by `test_bootstrap_without_mise_says_how_to_install` (Task 7).
3. **Vendored and state folders get scanned** (`node_modules/`, `.venv/`, `.claude/alpha/state/`, lockfiles) by typos, rumdl or lychee, especially for a component at `.`. Pinned by `test_repo_checks_skip_vendored_dirs` (Task 5) and the slow run in Task 7.
4. **No base ref** (push to main, a local run, a shallow clone): the diff checks and diff-cover should skip with a note, not crash or fail. Pinned by `test_diff_checks_without_base_skip` (Task 9) and `test_pr_only_coverage_steps` (Task 12).
5. **Stop with mise or a tool missing locally:** one clear problem with the install hint, inside the existing three-blocks-then-give-up limit, never a loop. Pinned by `test_stop_repo_check_missing_mise` (Task 8).

---

## Phase A: Foundations

### Task 1: Record the design in the spec

**Files:**
- Modify: `docs/superpowers/specs/2026-10-19-project-kit-design.md` (new §8a after §8; one line each in §3, §7, §12, §15)

- [ ] **Step 1: Write §8a "Repository checks and the tool registry"** with D1–D8, the repo-check table below (Task 5 is its source of truth), the `structure` and `coverage` recipe commands, and the registry. In §3, add a `registry/` row. In §7, list `mise.toml`, the tool configs, `scheduled.yml` and `.claude/alpha/checks/`. In §12, add "seeded violations prove every repo check can fail". In §15, add "opting an existing project into newer kit gates" and "alpha on existing repos".
- [ ] **Step 2: Commit** `docs: Specify repository checks and the registry`

### Task 2: Tool registry, verified

**Files:**
- Create: `registry/tools.toml`, `registry/actions.toml`, `src/alpha/registry.py`, `tests/test_registry.py`
- Modify: `src/alpha/cli.py` (an `alpha registry` subcommand), `src/alpha/defaults.py` (only if `Source` needs a registry path helper)

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Pin: mise: str; version: str; command: str; fails_with: int`. `mise` is the mise tool spec, e.g. `"typos"` or `"github:betterleaks/betterleaks"`. `command` is the verified non-interactive check invocation. `fails_with` is the verified exit code on a violation.
  - `@dataclass(frozen=True) class Tool: id: str; name: str; repo: str; category: str; stacks: tuple[str, ...]; rationale: str; limitations: str; last_reviewed: date; pin: Pin | None`. `stacks` is empty for cross-cutting tools.
  - `@dataclass(frozen=True) class Action: repo: str; version: str; sha: str`
  - `class Registry` with `tool(id: str) -> Tool`, `action(repo: str) -> Action`, `for_stack(stack: str) -> list[Tool]`, `stale(today: date, max_age_days: int = 180) -> list[Tool]`
  - `load_registry(source: Source) -> Registry`. It reads `<source.path>/registry/` the way recipes and defaults are read (live checkout first, then the bundled copy), and raises `RegistryError(AnswersError)` naming the bad field.
  - CLI: `alpha registry list [--stack S]`, `alpha registry show <id>`, `alpha registry stale`.

- [ ] **Step 1: Seed `registry/tools.toml`** from DQG's `tools.json` at 829848c: every recommended entry, with `id`, `name`, `repo`, `category`, `rationale`, `limitations`, `last_reviewed`, and `stacks` mapped from the category (e.g. `"Python"` becomes `["python"]`). Add alpha's own picks that DQG doesn't list (pyright, Biome, pytest, vitest, Dependabot, deptry if absent), each with a `limitations` line saying where DQG differs. Put `# Source: dev-quality-gates 829848c (CC0)` at the top.
- [ ] **Step 2: Verify and pin every tool alpha generates.** That's jactionlint, betterleaks, osv-scanner, typos, rumdl, lychee, agnix, squawk and diff-cover. In a scratch folder, for each one: `mise use <spec>@<latest>`, run it on a clean fixture (exit 0) and on a violation (record the exit code). Write `[tools.pin]` with `mise`, `version`, `command` and `fails_with`. Record facts that later tasks rely on in `limitations`: the config file name (`.rumdl.toml`, `_typos.toml`, `lychee.toml`), betterleaks' ignore-file name and line format, agnix's strict flag, and how osv-scanner scans source. Set `last_reviewed` to the run date. If a tool can't be installed through mise, stop and report it; don't substitute a tool.
- [ ] **Step 3: Write `registry/actions.toml`.** One entry each for `actions/checkout`, `jdx/mise-action`, `astral-sh/setup-uv`, `pnpm/action-setup` and `actions/setup-node`: the latest release tag and its commit SHA from `git ls-remote https://github.com/<repo> refs/tags/<tag>` (peeled `^{}` when the tag is annotated).
- [ ] **Step 4: Write the failing tests** in `tests/test_registry.py`:
  - `test_registry_loads`: `load_registry(Source(PLUGIN_ROOT, True, ""))` has `tool("typos").pin.fails_with != 0`.
  - `test_generated_tools_are_pinned`: each of the nine ids above has a `pin`.
  - `test_bad_field_names_it`: a temp registry with `last_reviewed = "soon"` raises `RegistryError` whose message contains `tools.<id>.last_reviewed`.
  - `test_stale`: with `today = last_reviewed + 181 days` the tool is in `stale()`, and at +180 days it isn't.
  - `test_cli_show`: `run_cli("registry", "show", "ruff")` prints the rationale and exits 0. An unknown id exits 1 with `alpha registry list` named in the message.
  - `@pytest.mark.slow test_action_shas_match_tags`: `git ls-remote` for each action resolves its tag to the stored SHA.
- [ ] **Step 5: Run** `uv run pytest tests/test_registry.py -v`. Expected: FAIL (module missing).
- [ ] **Step 6: Implement** `src/alpha/registry.py` and the CLI. Validate with the helpers in `alpha.validate`.
- [ ] **Step 7: Run** `uv run pytest tests/test_registry.py -v` and `uv run pytest -m slow tests/test_registry.py`. Expected: PASS.
- [ ] **Step 8: Commit** `feat: Add a verified tool registry`

### Task 3: SHA-pinned actions with version comments

**Files:**
- Modify: `src/alpha/yaml_write.py`, `src/alpha/recipes.py:94,136,320-345`, `src/alpha/render/ci.py`, `recipes/python.toml`, `recipes/typescript.toml`, `evals/scenarios/rust-cli.json`, `skills/stack-recipe/SKILL.md`
- Test: `tests/test_yaml_write.py`, `tests/test_recipes.py`, `tests/test_render_ci.py`

**Interfaces:**
- Consumes: `Registry.action(repo) -> Action` (Task 2).
- Produces:
  - `@dataclass(frozen=True) class Commented: value: str; comment: str` in `yaml_write`, written as `"<value>" # <comment>`.
  - A recipe step's optional `version` key (added to `_STEP_KEYS`). `render_ci` emits `uses: Commented(uses, version)`.
  - `render_ci(principles, ci, book=None, registry: Registry | None = None)`.

- [ ] **Step 1: Write the failing tests:**
  - `test_commented_scalar`: `dumps({"uses": Commented("a/b@" + "0"*40, "v1.2.3")})` contains `uses: "a/b@000…0" # v1.2.3`, and `yaml.safe_load` gives back the plain string.
  - `test_kit_recipes_pin_shas`: every `uses` in `RecipeBook()` kit recipes matches `@[0-9a-f]{40}$` and has a `version`.
  - `test_drafted_recipe_tag_refused`: a drafted recipe with `uses = "x/y@v4"` raises `RecipeError` whose message contains `full commit SHA` and `git ls-remote`. The same recipe passes through `drafted_recipes(raw, generated=True)`, so projects generated earlier keep working.
  - `test_workflow_actions_pinned` in `test_render_ci.py`: every `uses:` line in the rendered workflow text matches `@[0-9a-f]{40}" # v`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** `_ACTION` keeps accepting tags only where `generated=True`. Kit recipes and `ci.py`'s checkout take their SHA and version from `registry/actions.toml`. Recipes write the SHA in `uses` plus `version`. In the stack-recipe skill, change "release tag or commit SHA" to "the commit SHA of the latest release tag (`git ls-remote https://github.com/<owner>/<repo> refs/tags/<tag>`), with the tag in `version`".
- [ ] **Step 4: Re-prove the Rust scenario.** Pin its recipe's actions to SHAs, run `bin/alpha recipe try` on a scratch copy of the scenario to refresh `proven_hash`, and copy the result back into `evals/scenarios/rust-cli.json`.
- [ ] **Step 5: Run** `uv run pytest` (fast) and `uv run pytest -m slow tests/test_recipe_cli.py tests/test_bootstrap_slow.py`. Expected: PASS.
- [ ] **Step 6: Commit** `feat(recipes): Pin CI actions to commit SHAs`

### Task 4: Dependabot cooldown

**Files:**
- Modify: `defaults/defaults.toml` (`[dependencies] cooldown_days = 7`), `src/alpha/core_areas.py` (`Dependencies.cooldown_days: int | None`), `src/alpha/render/ci.py:render_dependabot`, `src/alpha/generate.py:165`, `skills/dependencies/SKILL.md`
- Test: `tests/test_core_areas.py`, `tests/test_render_ci.py`

**Interfaces:**
- Produces: `render_dependabot(principles, updates, schedule, ci, book=None, cooldown_days: int = 0)`. 0 means no `cooldown` key. `generate` passes `a.dependencies.cooldown_days` when set, otherwise `defaults["dependencies"]["cooldown_days"]`.

- [ ] **Step 1: Write the failing tests:**
  - `test_cooldown_on_every_entry`: with `cooldown_days=7`, every entry (including github-actions) has `cooldown == {"default-days": 7}`.
  - `test_cooldown_zero_omits`: with 0, no entry has `cooldown`.
  - `test_cooldown_answer_validated`: `dependencies.cooldown_days = -1` or `"7"` fails `answers check` with a message naming `dependencies.cooldown_days`. A missing field is valid.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** In the skill, the Updates explanation gains one line: "updates wait `cooldown_days` days after a release, so a compromised version is usually caught first". An answer that differs from the default goes through the override protocol (key `dependencies.cooldown_days`). Save it in the `dependencies` object.
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(defaults): Delay Dependabot updates by 7 days`

---

## Phase B: Repository checks

### Task 5: The repo-check catalog, `mise.toml` and tool configs

**Files:**
- Create: `src/alpha/repo_checks.py`, `src/alpha/render/tooling.py`, `tests/test_repo_checks.py`, `tests/test_render_tooling.py`
- Modify: `src/alpha/principles.py` (adds `repo_checks` and `data.squawk_paths`), `src/alpha/generate.py:render_project`

**Interfaces:**
- Consumes: `Registry.tool(id).pin` (Task 2).
- Produces:
  - `@dataclass(frozen=True) class RepoCheck: id: str; tool: str | None; command: str; globs: tuple[str, ...]; stop: bool; when: Literal["pr", "schedule", "both"]`
  - `repo_checks(a: Answers, principles: dict[str, Any], registry: Registry) -> list[RepoCheck]`, in the table's order.
  - In `principles.toml`: `[[repo_checks]]` with `id`, `command` (always `mise run check:<id>`), `globs` and `stop`, for every check whose `when` isn't `"schedule"`. `[data] squawk_paths`: the migration globs of data stores whose `storage` contains `postgres` (case-insensitive).
  - `render_tooling(checks: list[RepoCheck], registry: Registry, excludes: list[str]) -> dict[str, str]`, which returns `mise.toml`, `.rumdl.toml`, `_typos.toml` and `lychee.toml`.
  - `mise.toml` contents: a `[tools]` entry per distinct `pin.mise`; `[tasks."check:<id>"]` with `run = <command>`; `[tasks.ci]` depending on every `pr`/`both` check; `[tasks.scheduled]` depending on every `schedule`/`both` check; `[tasks.check]` depending on `ci` plus `check:component:<name>` tasks (`dir = <path>`, running that component's `check_commands`).

| id | tool | command (actual flags from the registry `pin.command`) | globs | stop | when | applies when |
|---|---|---|---|---|---|---|
| actions | jactionlint | lint `.github/` | `.github/**` | yes | pr | `build.ci == "github-actions"` |
| secrets | betterleaks | scan the working tree | `**` | no | pr | always |
| vulns | osv-scanner | scan source recursively | lockfiles | no | both | any component has lockfiles |
| typos | typos | `typos` | `**` | yes | pr | always |
| markdown | rumdl | `rumdl check .` | `**/*.md` | yes | pr | always |
| links | lychee | `lychee --offline --no-progress .` | `**/*.md` | yes | pr | always |
| links-online | lychee | `lychee --no-progress .` | — | no | schedule | always |
| agent-config | agnix | strict lint of `.` | `CLAUDE.md`, `.claude/**` | yes | pr | always |
| migrations | — | `python3 .claude/alpha/checks/diff_checks.py immutable-migrations` | — | no | pr | `data.migration_paths` non-empty |
| squawk | squawk | `python3 .claude/alpha/checks/diff_checks.py squawk` | — | no | pr | `data.squawk_paths` non-empty |
| review-dates | — | `python3 .claude/alpha/checks/review_dates.py` | — | no | both | always |
| toolchain | — | `mise outdated --json \| python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d, indent=2)); sys.exit(1 if d else 0)"` | — | no | schedule | always |

Excludes (shared by typos, rumdl and lychee configs): the `.gitignore` entries `generate` already computes, plus `.claude/alpha/state/`, every recipe's lockfiles, and `CHANGELOG.md` for typos only.

- [ ] **Step 1: Write the failing tests:**
  - `test_catalog_web_api`: for the `web-ts-plus-python-api` scenario, the ids are the table minus `squawk`, plus `squawk` only if its data store says postgres. Assert against the scenario file's actual storage value.
  - `test_catalog_ml_single`: no `migrations` and no `squawk`.
  - `test_no_actions_check_without_github`: `build.ci = "none"` leaves out `actions`.
  - `test_principles_carry_stop_checks`: principles `repo_checks` ids equal the non-schedule checks, and each `command` starts with `mise run check:`.
  - `test_mise_pins_registry_versions`: the `mise.toml` `[tools]` values equal `registry.tool(id).pin.version`, and `tasks.ci.depends` lists `check:typos`.
  - `test_repo_checks_skip_vendored_dirs`: `_typos.toml`, `.rumdl.toml` and `lychee.toml` exclude `node_modules`, `.venv` and `.claude/alpha/state`, including `web/**/node_modules/` for a component at `web`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** `render_project` adds the tooling files to `texts`. Reuse `toml_write.dumps`.
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS. Existing `test_generate` file lists gain the new paths.
- [ ] **Step 5: Commit** `feat: Generate repository checks and mise.toml`

### Task 6: CI repo job, scheduled workflow, tree check, commit grouping

**Files:**
- Modify: `src/alpha/render/ci.py`, `src/alpha/gitops.py:commit_group,commit_skeleton,commit_update`, `src/alpha/generate.py:_copies`
- Test: `tests/test_render_ci.py`, `tests/test_generate.py` (commit groups)

**Interfaces:**
- Consumes: `repo_checks(...)` (Task 5), `Registry.action` (Task 2).
- Produces:
  - `SCHEDULED = ".github/workflows/scheduled.yml"`.
  - `render_ci(...)` returns both workflows. In `ci.yml`, the `repo` job: checkout with `fetch-depth: 0` and `persist-credentials: false`; `jdx/mise-action` (SHA, `install: true`, `cache: true`); then `mise run ci` with env `ALPHA_BASE: ${{ github.event_name == 'pull_request' && format('origin/{0}', github.base_ref) || '' }}` and `PR_BODY: ${{ github.event.pull_request.body }}`. Every job, the component jobs included, ends with the step `Checks left the tree unchanged`, which runs `git diff --exit-code && test -z "$(git status --porcelain)"`.
  - `scheduled.yml`: `on.schedule` cron `"17 6 * * 1"` plus `workflow_dispatch`; `permissions: contents: read`; one job, `mise run scheduled`.
  - `commit_group`: `mise.toml`, `.rumdl.toml`, `_typos.toml` and `lychee.toml` go to `"tooling"`, committed as `build: Pin the repository's check tools`. `SCHEDULED` goes to `"ci"`.
  - `_copies` copies `project-files/checks/*.py` to `.claude/alpha/checks/` (the scripts come in Tasks 9 and 10; until then the glob copies nothing).

- [ ] **Step 1: Write the failing tests:**
  - `test_repo_job`: steps in order are checkout (fetch-depth 0), mise-action, `mise run ci`, tree-unchanged. `ALPHA_BASE` is set as above.
  - `test_every_job_ends_with_tree_check`.
  - `test_scheduled_workflow`: it has the cron, read-only permissions and `mise run scheduled`, and is absent when `ci == "none"`.
  - `test_tooling_commit`: for `generated_repo(tmp_path, "web-ts-plus-python-api")`, `git log --format=%s` contains `build: Pin the repository's check tools`, and `mise.toml` is in that commit.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Run repository checks in CI and weekly`

### Task 7: Bootstrap runs the repo checks; seeded violations prove them

**Files:**
- Modify: `src/alpha/generate.py:bootstrap`, and whichever renderers the slow run shows fail a linter (`render/docs.py`, `render/area_docs.py`, `render/ci.py`, `project-files/skills/*`, `project-files/agents/*`)
- Test: `tests/test_bootstrap_slow.py`, `tests/test_generate.py`

**Interfaces:**
- Produces: after the component loop, `bootstrap` runs `mise trust --yes`, `mise install` and `mise run ci` in `target` when `mise.toml` exists. Errors use the existing `GenerateError` tail format. If mise isn't on PATH, the message is: `mise is not installed. Install it (brew install mise, or https://mise.jdx.dev/getting-started.html), then rerun "alpha bootstrap <target>".`

- [ ] **Step 1: Write the failing tests:**
  - `test_bootstrap_without_mise_says_how_to_install` (fast): with `PATH` stripped of mise and component steps stubbed, `bootstrap` raises `GenerateError` containing `mise is not installed` and `alpha bootstrap`.
  - `@slow test_scenarios_pass_repo_checks`: for each of the three scenarios, generate, bootstrap, then `git init` plus `commit_skeleton`, then `mise run ci` exits 0.
  - `@slow test_repo_checks_can_fail`: parametrized over seeds in a bootstrapped web+API copy. Each seed makes `mise run check:<id>` exit with that tool's `pin.fails_with`, and each is reverted afterwards:
    - `actions`: replace a `uses` SHA with `@v7`.
    - `secrets`: add `docs/x.md` containing an AWS-style key.
    - `typos`: write `teh` in `README.md`.
    - `markdown`: add a heading that skips a level.
    - `links`: add a link to `docs/missing.md`.
    - `agent-config`: break `.claude/agents/committer.md` frontmatter.
- [ ] **Step 2: Run** `uv run pytest tests/test_generate.py -k mise` and `uv run pytest -m slow tests/test_bootstrap_slow.py`. Expected: FAIL.
- [ ] **Step 3: Implement bootstrap,** then fix the renderers and shipped files until `test_scenarios_pass_repo_checks` passes. Fix the output; never add exclusions or disable rules to get through. A rumdl rule that conflicts with how alpha writes docs on purpose (e.g. line length in tables) may be switched off in `.rumdl.toml`, with a comment giving the reason.
- [ ] **Step 4: Run** `uv run pytest` and `uv run pytest -m slow`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Bootstrap and prove the repository checks`. Make a separate `fix:` commit for renderer fixes if they're substantial.

### Task 8: Stop runs the fast repo checks

**Files:**
- Modify: `project-files/hooks/stop_checks.py` (`find_problems`, plus a new function)
- Test: `tests/hooks/test_stop_checks.py`

**Interfaces:**
- Consumes: `principles["repo_checks"]` (Task 5).
- Produces: `repo_check_problems(root: Path, principles: dict[str, Any], changed: list[str], deadline: float) -> list[str]`. It runs each `stop = true` check whose `globs` match a changed file, using `run_step(command, root, ...)`. Results are cached like `command_problems`, keyed on the hash of the changed matched files plus the command. Status `missing` (mise or the tool) gives one problem: `mise is not installed or the tool is missing. Run: mise install (install mise from https://mise.jdx.dev)`. `failed` gives `repo check <id> failed (<command>):\n<tail>`.

- [ ] **Step 1: Write the failing tests** with a fake `mise` script on PATH, using the existing hook-test fixtures:
  - `test_stop_runs_matching_repo_check`: changing `README.md` makes `check:typos` run, but not `check:actions`.
  - `test_stop_repo_check_failure_blocks`: the fake exits 2, so Stop blocks and the reason contains `repo check typos failed`.
  - `test_stop_repo_check_missing_mise`: with no mise on PATH, there's exactly one problem containing `mise install`, and the existing repeat limit ends the loop on the third Stop.
  - `test_stop_repo_check_cached`: a second Stop with the same files doesn't call the fake again (it counts calls in a file).
- [ ] **Step 2: Run** `uv run pytest tests/hooks/test_stop_checks.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Call it from both the main Stop and `subagent_stop`, alongside the component checks.
- [ ] **Step 4: Run** `uv run pytest tests/hooks`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hooks): Run fast repository checks at Stop`

### Task 9: Diff checks in CI: immutable migrations and squawk

**Files:**
- Create: `project-files/checks/diff_checks.py`, `tests/checks/test_diff_checks.py` (plus `tests/checks/__init__.py`)

**Interfaces:**
- Consumes: `ALPHA_BASE` and `PR_BODY` env (Task 6), `data.migration_paths` and `data.squawk_paths` in `docs/principles.toml` (Task 5).
- Produces: the CLI `python3 diff_checks.py immutable-migrations|squawk`, run from the repo root.
  - No `ALPHA_BASE`, or a base that doesn't resolve: print `alpha: no base ref (not a pull request); <check> skipped` and exit 0.
  - `immutable-migrations`: a file matching `migration_paths` that exists at the base and is modified or deleted (`git diff --name-status --no-renames <base>...HEAD`) fails. The message names the file, the `git checkout <base> -- <file>` fix, and the escape: a line `alpha: migration edit approved` in the PR description. When `PR_BODY` contains that line, it passes with a note.
  - `squawk`: runs the registry's squawk command on the added (`A`) `.sql` files matching `squawk_paths`, and exits with squawk's code. With no such files it exits 0.

- [ ] **Step 1: Write the failing tests** (they need a real temp git repo; squawk is a fake on PATH):
  - `test_diff_checks_without_base_skip`: both subcommands exit 0 and print `skipped`, with `ALPHA_BASE` unset and also with `ALPHA_BASE=origin/nope`.
  - `test_modified_migration_fails`: exits 1, and the output contains the file and `git checkout`.
  - `test_new_migration_passes`.
  - `test_escape_marker_passes`: `PR_BODY="…\nalpha: migration edit approved\n"` exits 0.
  - `test_squawk_gets_only_added_sql`: the fake records its args, which are exactly the added `.sql` file.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** with the stdlib only, reading `docs/principles.toml` with `tomllib`.
- [ ] **Step 4: Run** `uv run pytest tests/checks`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Check migrations against the base in CI`

### Task 10: Review dates on suppressions

**Files:**
- Create: `project-files/checks/review_dates.py`, `tests/checks/test_review_dates.py`
- Modify: the generated CLAUDE.md agent rules (Task 14 adds one line about it)

**Interfaces:**
- Produces: `python3 review_dates.py [--today YYYY-MM-DD]`. It reads only this fixed list, and a missing file passes:
  - `osv-scanner.toml`: each `[[IgnoredVulns]]` needs `ignoreUntil`, which must be a real date not in the past, and a `reason` of at least two words.
  - The betterleaks ignore file named in the registry (Task 2): each entry needs a trailing `# <reason, 2+ words> (review YYYY-MM-DD)`, and the date must parse, round-trip as the same string and not be in the past.
  - Each problem gives `file:line`, what's wrong and how to fix it (a new date plus a reason, or remove the suppression). It exits 1 on any problem.

- [ ] **Step 1: Write the failing tests:**
  - `test_no_files_passes`.
  - `test_osv_missing_ignore_until_fails`.
  - `test_impossible_date_fails`: `2026-02-31` fails with `not a real date`.
  - `test_past_date_fails`: with `--today 2026-12-01`, `2026-11-30` fails with `review date passed`.
  - `test_one_word_reason_fails`.
  - `test_good_entries_pass`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest tests/checks`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Expire security suppressions by review date`

---

## Phase C: Component checks

### Task 11: `structure` recipe command: deptry, Knip, dependency-cruiser

**Files:**
- Modify: `src/alpha/recipes.py:24` (`CHECK_STEPS = ("setup", "format_check", "lint", "typecheck", "structure", "test")`; `structure` optional, default `""` when missing), `recipes/python.toml`, `recipes/typescript.toml`
- Create: `recipes/typescript/knip.json.tmpl`, `recipes/typescript/dependency-cruiser.cjs.tmpl`
- Modify: `project-files/hooks/stop_checks.py:COMMAND_PRINCIPLES` (adds `"structure": "no-dead-code"`), `defaults/defaults.toml` (`no-dead-code.checked_by` adds `"hook:stop_checks"`), `skills/stack-recipe/SKILL.md` (documents `structure`)
- Test: `tests/test_recipes.py`, `tests/hooks/test_stop_checks.py`, `tests/test_bootstrap_slow.py`

**Interfaces:**
- Produces:
  - Python: `structure = "uv run deptry ."`. Bootstrap adds `deptry`, with `[why] deptry = "Unused, missing and transitive dependencies"`.
  - TypeScript: `structure = "pnpm knip && pnpm depcruise --config .dependency-cruiser.cjs ."`. Bootstrap adds `knip dependency-cruiser`, with `[why]` lines.
  - The depcruise rules are `no-circular`, `not-to-dev-dep` (from non-test files) and `no-non-package-json`, all at `error`. Paths follow `exclude_globs`.
  - Python `[[rules]]` id `import-contracts`: "Once a component has more than one package, add import-linter contracts for the layers `docs/architecture.md` names, and add `lint-imports` to its `structure` command."
  - A drafted recipe without `structure` stays valid.

- [ ] **Step 1: Write the failing tests:**
  - `test_structure_step_order`: `check_commands` for the TS recipe yields `structure` between `typecheck` and `test`.
  - `test_drafted_recipe_without_structure_valid`.
  - `test_stop_runs_structure`.
  - `@slow test_structure_fails_on_unused_dependency`: in a bootstrapped web+API copy, `uv add requests` in `api` and `pnpm add left-pad` in `web` make each `structure` fail; reverted afterwards.
  - Extend `@slow` bootstrap: the scenarios still pass with `structure`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** If Knip or deptry flags the empty skeleton, fix it in their config templates (e.g. a Knip `entry` for `tests/`), never by switching the rule off.
- [ ] **Step 4: Run** `uv run pytest` and `uv run pytest -m slow tests/test_bootstrap_slow.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(recipes): Check unused dependencies and imports`

### Task 12: Coverage and diff-cover

**Files:**
- Modify: `src/alpha/recipes.py` (optional `coverage` command and `coverage_report` path), `recipes/python.toml`, `recipes/typescript.toml`, `defaults/defaults.toml` (`[testing] diff_coverage = 80`), `src/alpha/core_areas.py` (`Testing.diff_coverage: int | None`, 0–100), `src/alpha/principles.py` (`testing.diff_coverage` resolved from the answer or the default), `src/alpha/render/ci.py:_job`, `skills/testing/SKILL.md`, `skills/stack-recipe/SKILL.md`
- Test: `tests/test_render_ci.py`, `tests/test_core_areas.py`, `tests/test_bootstrap_slow.py`

**Interfaces:**
- Consumes: `Registry.tool("diff-cover").pin.version` (Task 2).
- Produces:
  - Python: `coverage = "uv run pytest --cov --cov-report=xml:coverage.xml"` and `coverage_report = "coverage.xml"`. Bootstrap adds `pytest-cov`. `ignores` adds `coverage.xml` and `.coverage`.
  - TypeScript: `coverage = "pnpm vitest run --coverage --coverage.reporter=cobertura"` and `coverage_report = "coverage/cobertura-coverage.xml"`. Bootstrap adds `@vitest/coverage-v8`.
  - Component job, when the component has `coverage` and `diff_coverage > 0`:
    - The `test` step gets `if: github.event_name != 'pull_request'`.
    - A step `test with coverage` runs `coverage` with `if: github.event_name == 'pull_request'`.
    - A step `diff coverage` (PR only) runs `pipx run diff-cover==<pin> <coverage_report> --compare-branch=origin/${{ github.base_ref }} --fail-under=<diff_coverage>`, plus the `--src-roots` value the slow test shows is needed for a component in a subfolder.
    - Checkout uses `fetch-depth: 0`.

- [ ] **Step 1: Write the failing tests:**
  - `test_pr_only_coverage_steps`: the three steps have the `if:` conditions above, and the fail-under equals the principles value.
  - `test_no_coverage_steps_when_zero`: `diff_coverage = 0` leaves only the plain `test` step.
  - `test_drafted_recipe_without_coverage`: only the plain `test` step.
  - `test_diff_coverage_answer_validated`: 101 and `"80"` fail with `testing.diff_coverage` in the message.
  - `@slow test_diff_cover_catches_untested_line`: in a bootstrapped web+API repo on a branch, add `api/app/x.py` with an untested function, run the component's `coverage` command and then the rendered diff-cover command with `origin/main` replaced by `main`. It exits non-zero. Once a test covers the function, it exits 0.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** In the testing skill's round, add one line to the existing per-component question: "pull requests must cover at least `diff_coverage`% of the lines they change (0 turns this off)". An answer that differs goes through the override protocol, key `testing.diff_coverage`.
- [ ] **Step 4: Run** `uv run pytest` and `uv run pytest -m slow -k "diff_cover or bootstrap"`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(recipes): Gate pull requests on diff coverage`

### Task 13: Machine-wide slots for heavy hook commands

**Files:**
- Modify: `project-files/hooks/_common.py`, `project-files/hooks/stop_checks.py:run_step`
- Test: `tests/hooks/test_common.py`, `tests/hooks/test_stop_checks.py`

**Interfaces:**
- Produces: `heavy_slot(deadline: float) -> contextlib.AbstractContextManager[bool]` in `_common`. It yields True when a slot was taken (or not needed) and False when the deadline passed while waiting.
  - Slots: `ALPHA_SLOTS` env, else `max(1, (os.cpu_count() or 2) // 4)`. They're lock files `~/.cache/alpha/slots/<n>.lock`, taken with non-blocking `fcntl.flock`, polled every 0.2 s.
  - No slot is needed when `CI` is set, when `ALPHA_SLOT_HELD=1` (and the command runs with it set, so nested calls don't deadlock), or when `fcntl` can't be imported.
  - `run_step` wraps typecheck, test, structure and repo checks. A False becomes the problem `waited for other agents' checks until alpha's <BUDGET>s budget ran out; run <command> by hand`.

- [ ] **Step 1: Write the failing tests:**
  - `test_slot_taken_and_released`.
  - `test_second_holder_waits` (`ALPHA_SLOTS=1`, the first lock held by a subprocess): it yields False at the deadline.
  - `test_ci_skips_slots`.
  - `test_nested_skips`: the child env has `ALPHA_SLOT_HELD=1`.
  - Each test sets `HOME` to `tmp_path`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest tests/hooks`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hooks): Share heavy checks across agents`

---

## Phase D: Docs, registry use, proof

### Task 14: Generated docs say what runs and what agents may not do

**Files:**
- Modify: `src/alpha/render/docs.py` (`_claude_md`, `_contributing`, `_readme`), `defaults/defaults.toml` (`checked_by` for `no-secrets` adds `"ci:secrets"`; `generated-from-source` adds `"ci:tree"`; `safe-migrations` adds `"ci:migrations"`; `dependency-reasons` unchanged)
- Test: `tests/test_render_docs.py`, `tests/test_principles.py`

**Interfaces:**
- Produces, in generated CLAUDE.md:
  - Under the command table: "Run every check: `mise run check` (CI runs the same checks)".
  - Under rules for agents:
    - "When you add a code generator, add a `generate` task to `mise.toml` and to the `ci` task's `depends`; CI fails when checks change tracked files."
    - "Never disable a lint rule to pass; an exception names one path and one rule, gives a reason, and needs the user's yes."
    - "A security suppression (osv-scanner, betterleaks) needs a reason and a review date."
- CONTRIBUTING gets "Checks": `mise install`, `mise run check`, and the repo-check table rendered from `principles["repo_checks"]`.

- [ ] **Step 1: Write the failing tests** asserting these lines (exact text above), and that `checked_by` for `no-secrets` contains `ci:secrets` in the built principles.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Check that `principles.py` and the reviewer accept the `ci:` prefix in `checked_by`, and extend the validation if they don't.
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Document repository checks in projects`

### Task 15: stack-recipe uses the registry

**Files:**
- Modify: `skills/stack-recipe/SKILL.md`, `skills/components/SKILL.md` (only if it restates recipe fields)
- Test: `tests/test_skills.py`

- [ ] **Step 1: Write the failing test** `test_stack_recipe_reads_registry`: the skill text contains `bin/alpha" registry list --stack`, `registry stale`, `structure` and `coverage`.
- [ ] **Step 2: Run it.** Expected: FAIL.
- [ ] **Step 3: Edit the skill.** Step 1 ("Facts first") begins with `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" registry list --stack <stack>`: prefer the registry's picks for lint/format, type check, `structure` (unused dependencies, import rules) and `coverage`. If `registry stale` lists one of them, verify it's still maintained before using it, and tell the user. A stack the registry doesn't cover falls back to the toolchain's own tools, as before. Add `structure`, `coverage` and `coverage_report` to "What a recipe holds".
- [ ] **Step 4: Run** `uv run pytest tests/test_skills.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Draft recipes from the tool registry`

### Task 16: Evals, live check and kit docs

**Files:**
- Modify: `src/alpha_evals/checks.py` (a new check, `repo-checks`: `mise run ci` exits 0 in the generated project), `src/alpha_evals/seeded.py` (seeds from Task 7 that `bin/alpha-evals check` also runs), `CLAUDE.md` (a live-check section), `README.md` ("What you get" gains `mise.toml` and the repo checks; mise added to requirements)
- Test: `tests/evals/test_checks.py`, `tests/evals/test_seeded.py`

- [ ] **Step 1: Write the failing tests:** `test_repo_checks_check_reports_failure` (a fake mise exiting 1 makes the check fail with its output) and a seeded-violation test in the existing `test_seeded.py` style.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Live check.** For each scenario, run `bin/alpha-evals check <project> <scenario>` on freshly generated projects (from the scenario files, not interviews). Then push the web+API project to a throwaway private GitHub repo and open a PR that adds an untested `api/app/x.py` and edits a migration, if it has one. Confirm the `repo` job and diff-cover fail with readable messages and pass once fixed. Trigger `scheduled.yml` with `workflow_dispatch`. Add a dated "Quality gates live check" section to CLAUDE.md in the style of the others, saying what ran, what passed, and what wasn't verified.
- [ ] **Step 5: Run** `uv run pytest` and `uv run pytest -m slow`. Expected: PASS.
- [ ] **Step 6: Commit** `docs: Record the quality gates live check` (plus `feat:` for the evals changes, in their own commit)

### Task 17: The kit checks itself

**Files:**
- Create: `mise.toml` (kit root: typos, rumdl, agnix at the registry's versions; tasks `check` = those plus `uv run pytest`, `ruff check`, `ruff format --check`, `pyright`), `_typos.toml`, `.rumdl.toml`
- Modify: `CLAUDE.md` (dev commands gain `mise run check`)

- [ ] **Step 1: Run** `mise run check` in the kit. Expected: findings from typos, rumdl and agnix on the kit's docs and skills.
- [ ] **Step 2: Fix the findings** in the docs and skills. Rule exclusions get a comment giving the reason. Leave the historical plans and specs under `docs/superpowers/` out of rumdl.
- [ ] **Step 3: Run** `mise run check`. Expected: exit 0.
- [ ] **Step 4: Commit** `chore: Check the kit's docs and skills`, with the fixes in a separate `docs:` commit.

---

## Not in this plan

- Using alpha on existing repos (DQG's `adopt.md`, baselines for old code): a later plan if wanted (D6).
- Opting a project generated before this into the new gates (D4).
- Python import-linter contracts in the skeleton (D5).
- DQG categories that don't apply to alpha's generated projects (IaC, Kubernetes, Ansible, GitLab CI, Rails or Django-specific tools): they're in the registry for stack-recipe and future recipes, but alpha generates nothing for them.
