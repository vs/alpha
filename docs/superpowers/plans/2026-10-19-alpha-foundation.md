# Alpha Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Claude Code plugin, `alpha`, whose `/alpha:new-project` skill interviews the user (identity, components and stack, git, agent workflow) and turns an empty folder into a committed, self-enforcing skeleton for Python and/or TypeScript components.

**Architecture:** Skills are prompt-driven and own the conversation. They write the user's decisions into `.claude/alpha/project.json` in the target folder. A deterministic Python CLI (`bin/alpha`, stdlib only) validates the answers, merges them with the user's live defaults and the stack recipes, and renders every file. Enforcement scripts are copied into the project, so generated projects never depend on the installed kit.

**Tech Stack:** Python ≥ 3.11 stdlib (`tomllib`, `argparse`, `string.Template`, `subprocess`), pytest + ruff + pyright (strict) for the kit's own development via `uv`, Claude Code plugin format (skills, hooks), git.

**Spec:** `docs/superpowers/specs/2026-10-19-project-kit-design.md`

**Plan series:** 1/4. This plan covers spec §3, §4, §5 areas 1, 2, 16, and 17 (minus the reviewer), §6, §7 (minus CI), §8, §10, and §11. Plan 2 covers the remaining areas, CI, the generic-stack fallback, and §5a. Plan 3 covers §9 (reviewer and review debt). Plan 4 covers §12 interview evals.

## Global Constraints

- Generated projects contain **no app code and no placeholder source files**. Skeleton files only: config, docs, test wiring (a strictness-checking setup test per component), enforcement.
- **Nothing kit-specific at the project root.** Everything alpha owns lives under `.claude/alpha/` (hooks, git hooks, `project.json`, `state/`). Root files are only the standard ones: README.md, LICENSE, CONTRIBUTING.md, CLAUDE.md, .gitignore, plus `docs/` and component folders.
- `alpha generate` runs only on an **empty folder**, where empty means containing nothing except `.DS_Store` and a `.claude/` folder whose only content is `alpha/project.json` (the interview in progress).
- Every error message the kit or its hooks emits states **what went wrong and how to fix it** (spec §2, "Fail fast, fail helpfully").
- Kit runtime and project hooks: Python stdlib only, **Python ≥ 3.11**. On older Python, print `alpha needs Python 3.11+ (found X.Y). Install a newer one with "brew install python" or "uv python install 3.12", then retry.` and exit 1. Hooks exit 0 with that message on stderr, so they never brick a session.
- Generated projects are **self-contained**: hooks, the commit skill, and the committer agent are copied under the project's `.claude/`, never referenced from the plugin.
- Kit defaults change **only** through `alpha defaults set`, after the user said yes. Existing projects are never touched by default changes.
- Git guardrails (`--no-verify`, force-push, amending pushed commits) bind **Claude only** (Claude Code hooks). The only git hook binding everyone is `commit-msg`.
- Commit convention default: conventional commits, scopes = component names. Description after `type(scope): ` is at most **50 chars**, imperative, capitalized first letter, no trailing period. Body lines wrap at **72**.
- **No hard-coded co-author footer** anywhere. Claude Code supplies attribution lines, and `alpha commit-skeleton` takes them as `--trailer` arguments.
- Review thresholds default: `mode = "batched"`, `max_lines = 200`, `max_files = 5`. Stored in the principles file and user-overridable. `mode` may be `"every-task"`. Plan 1 only writes them, and Plan 3 consumes them.
- Before Task 9, verify Claude Code hook stdin and stdout formats (PreToolUse `permissionDecision`, Stop `decision: block`, exit code 2 semantics, `stop_hook_active`) against current docs (context7 or the claude-code-guide agent). Adjust only the I/O layer in `_common.py` if they differ.
- Kit dev commands: `uv run pytest`, `uv run ruff check`, `uv run ruff format`, `uv run pyright`.

## Review Focus

1. **A non-empty target folder.** It may contain `.git`, a stray README, or `.DS_Store`. `generate` must refuse, list the offending entries, and say how to proceed, but must accept `.DS_Store` and `.claude/alpha/project.json`. (Test in Task 15.)
2. **A missing or malformed `docs/principles.toml`** after the user hand-edits it. Every hook must print the file, the TOML error line, and a fix hint, and must not raise a traceback or block every tool call. (Test in Task 8.)
3. **A Stop hook loop.** If tests keep failing, Claude is blocked on every stop forever. Cap consecutive blocks at 3. After that, allow the stop, but the message must say checks are still failing. (Test in Task 12.)
4. **Merge, revert, `fixup!`, and `squash!` commit messages** must pass `commit-msg`. (Test in Task 13.)
5. **`--amend` detection in a repo with no commits, no upstream, or a detached HEAD** must not crash, and must allow the amend. (Test in Task 9.)

---

## File Structure

```
.claude-plugin/plugin.json            plugin manifest (name "alpha")
.claude-plugin/marketplace.json       local marketplace "alpha-local" → "./"
pyproject.toml                        kit dev tooling (not a runtime dependency)
bin/alpha                             executable shim: python check, sys.path, alpha.cli.main
src/alpha/__init__.py                 VERSION = "0.1.0"
src/alpha/pyguard.py                  check_python() (3.9-compatible syntax)
src/alpha/cli.py                      argparse subcommands
src/alpha/toml_write.py               minimal TOML emitter
src/alpha/defaults.py                 locate source, load + layer defaults, record changes
src/alpha/answers.py                  answers.json model + validation
src/alpha/recipes.py                  load recipes, render component files
src/alpha/principles.py               facts, conditions, overrides → principles.toml data
src/alpha/render/docs.py              README, LICENSE, CONTRIBUTING, CLAUDE.md, docs/*
src/alpha/render/claude_settings.py   .claude/settings.json
src/alpha/generate.py                 empty check, write files, copy project-files, manifest
src/alpha/gitops.py                   bootstrap components, git init, grouped commits
src/alpha/licenses/MIT.txt, Apache-2.0.txt
defaults/defaults.toml                hand-authored kit defaults (catalog, review, stacks)
defaults/overrides.toml               machine-managed layer written by `alpha defaults set`
defaults/CHANGELOG.md                 history of default changes
recipes/python.toml, recipes/python/*.tmpl
recipes/typescript.toml, recipes/typescript/*.tmpl
project-files/hooks/_common.py        shared hook helpers (copied into projects)
project-files/hooks/guard_bash.py     PreToolUse Bash
project-files/hooks/guard_paths.py    PreToolUse Edit|Write|MultiEdit
project-files/hooks/post_edit.py      PostToolUse Edit|Write|MultiEdit
project-files/hooks/stop_checks.py    Stop
project-files/hooks/commit_msg.py     git commit-msg
project-files/hooks/session_start.py  SessionStart
project-files/githooks/commit-msg     sh shim → commit_msg.py (installed to .claude/alpha/githooks/)
project-files/skills/commit/SKILL.md  ported /commit
project-files/agents/committer.md     ported committer agent
skills/grilling/SKILL.md
skills/new-project/SKILL.md
skills/identity/SKILL.md
skills/components/SKILL.md
skills/git-history/SKILL.md
skills/agent-workflow/SKILL.md
evals/scenarios/python-ml-single.json
evals/scenarios/web-ts-plus-python-api.json
tests/...                             mirrors src/ and project-files/hooks/
CLAUDE.md                             the kit's own agent instructions
```

Generated project layout (paths used by every task):

```
README.md  LICENSE  CONTRIBUTING.md  CLAUDE.md  .gitignore
docs/principles.toml  docs/product.md  docs/architecture.md  docs/dependencies.md
docs/decisions/NNNN-<slug>.md
.claude/settings.json  .claude/skills/commit/SKILL.md  .claude/agents/committer.md
.claude/alpha/hooks/*.py  .claude/alpha/githooks/commit-msg
.claude/alpha/project.json   (interview answers + generation manifest)
.claude/alpha/state/         (gitignored)
<component.path>/...  (recipe files: manifests, lockfile, tool configs, tests/setup test; no src/)
```

---

### Task 1: Kit repo, plugin manifest, CLI shim

**Files:**
- Create: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml`, `.gitignore`, `CLAUDE.md`, `bin/alpha`, `src/alpha/__init__.py`, `src/alpha/pyguard.py`, `src/alpha/cli.py`
- Test: `tests/test_cli.py`, `tests/test_pyguard.py`

**Interfaces:**
- Produces: `alpha.VERSION: str = "0.1.0"`. `alpha.pyguard.check_python(version: tuple[int, int]) -> str | None`, which returns the Global Constraints message or None. `alpha.cli.main(argv: list[str] | None = None) -> int`. `alpha.cli.PLUGIN_ROOT: Path` (repo root, resolved from `__file__`). Subcommand `alpha version`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_pyguard.py
from alpha.pyguard import check_python
def test_old_python_gets_fix_hint():
    msg = check_python((3, 9))
    assert msg is not None and "3.11+" in msg and "found 3.9" in msg and "uv python install" in msg
def test_new_python_passes():
    assert check_python((3, 11)) is None

# tests/test_cli.py
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def test_version_via_shim():
    out = subprocess.run([sys.executable, ROOT / "bin/alpha", "version"], capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.strip() == "0.1.0"
def test_unknown_command_explains_usage():
    out = subprocess.run([sys.executable, ROOT / "bin/alpha", "nope"], capture_output=True, text=True)
    assert out.returncode == 2 and "usage" in out.stderr.lower()
```

- [ ] **Step 2:** Run `uv run pytest tests/test_cli.py tests/test_pyguard.py -v`. Expected: FAIL (no pyproject or module yet).
- [ ] **Step 3: Implement**
  - `pyproject.toml`: project `alpha-kit`, `requires-python = ">=3.11"`, `[dependency-groups] dev = ["pytest", "ruff", "pyright"]` (add them with `uv add --dev`). Pytest `pythonpath = ["src"]`, `markers = ["slow: needs network and stack tools"]`, `addopts = "-m 'not slow'"`. `[tool.pyright] typeCheckingMode = "strict"` covering `src`, `project-files/hooks`, and `tests`. Ruff defaults plus `select = ["E","F","I","UP","B"]`.
  - `plugin.json`: `{"name": "alpha", "version": "0.1.0", "description": "Interview-driven skeletons for new projects, with principles agents must follow", "author": {"name": "Semyon Vadishev"}}`.
  - `marketplace.json`: name `alpha-local`, one plugin `{"name": "alpha", "source": "./"}`.
  - `bin/alpha`: `#!/usr/bin/env python3`, 3.9-compatible code. It puts `<root>/src` on `sys.path`, calls `check_python(sys.version_info[:2])`, prints the message and exits 1 on failure, and otherwise runs `sys.exit(main())`. Must be executable (`chmod +x`).
  - `.gitignore`: `.venv/`, `__pycache__/`, `.pytest_cache/`.
  - `CLAUDE.md`: what the kit is (one paragraph, link to spec), dev commands, the rule "the kit follows its own principles (spec §12)", and the commit convention.
- [ ] **Step 4:** Run `uv run pytest -v`. Expected: PASS.
- [ ] **Step 5: Commit**: `git add -A && git commit -m "build: Add plugin manifest and alpha CLI shim"` (plus session trailers).

---

### Task 2: Minimal TOML emitter

**Files:** Create `src/alpha/toml_write.py`. Test: `tests/test_toml_write.py`.

**Interfaces:**
- Produces: `dumps(data: Mapping[str, object]) -> str`. It supports str, int, bool, list[str], list[int], nested Mapping (tables), and list[Mapping] (arrays of tables). Scalars come before subtables. Keys not matching `[A-Za-z0-9_-]+` are quoted. Strings containing `\n` use `"""` multi-line basic strings. It raises `TypeError(f"cannot write {type!r} at {dotted.key}")` for anything else.

- [ ] **Step 1: Write failing tests**

```python
import tomllib
from alpha.toml_write import dumps
def roundtrip(d): return tomllib.loads(dumps(d))
def test_scalars_and_quoting():
    d = {"a": 'say "hi" \\ ok', "n": 3, "b": True, "xs": ["x", "y"]}
    assert roundtrip(d) == d
def test_multiline_string():
    d = {"rationale": "line one\nline two \"quoted\"\n"}
    assert roundtrip(d) == d and '"""' in dumps(d)
def test_nested_tables_and_odd_keys():
    d = {"docs_map": {"api/src/**": ["docs/architecture.md"]}, "review": {"max_lines": 200}}
    assert roundtrip(d) == d
def test_array_of_tables_with_subtable():
    d = {"components": [{"name": "api", "commands": {"test": "uv run pytest"}}, {"name": "web", "commands": {}}]}
    assert roundtrip(d) == d
def test_rejects_floats_with_key_path():
    import pytest
    with pytest.raises(TypeError, match="review.ratio"):
        dumps({"review": {"ratio": 0.5}})
```

- [ ] **Step 2:** Run `uv run pytest tests/test_toml_write.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 3:** Implement `dumps` in `src/alpha/toml_write.py` (recursive writer, string escaping per TOML basic strings).
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5: Commit**: `feat: Add minimal TOML writer`

---

### Task 3: Kit defaults (catalog, layering, live source, change recording)

**Files:**
- Create: `defaults/defaults.toml`, `defaults/overrides.toml` (contains only `# Managed by "alpha defaults set". Do not edit by hand.`), `defaults/CHANGELOG.md`, `src/alpha/defaults.py`
- Modify: `src/alpha/cli.py` (subcommands `defaults show [--json]` and `defaults set`)
- Test: `tests/test_defaults.py`

**Interfaces:**
- Produces:
  - `CONDITIONS: frozenset[str] = {"always", "has_ui", "multi_component", "communicating_components", "deployed", "network_calls", "persisted_data", "ml", "nontrivial_logic", "budgets_set", "domain_jargon"}`
  - `@dataclass(frozen=True) class Source: path: Path; live: bool; reason: str`
  - `locate_source(plugin_root: Path, env: Mapping[str, str], home: Path) -> Source`. Resolution order: `env["ALPHA_SOURCE"]`, then `source = "..."` in `home/.config/alpha/config.toml`, then `home/workspace/alpha`. The first candidate containing `defaults/defaults.toml` is used with `live=True`. Otherwise `Source(plugin_root, live=False, reason=...)`, where the reason names the paths tried and how to set `ALPHA_SOURCE`.
  - `load_defaults(source: Source) -> dict[str, Any]`: tomllib-load `defaults.toml`, then deep-merge `overrides.toml` (overrides win, lists replace). Validate that every principle's `applies` values are in `CONDITIONS`, and raise `DefaultsError(message_with_fix)` otherwise.
  - `set_default(source: Source, key: str, value: str, project: str, reason: str, trailers: list[str], today: date) -> str`. It requires `source.live`, otherwise raising `DefaultsError` that tells the skill to record the wish in the project's decision log. The value is parsed as TOML (`tomllib.loads(f"v = {value}")["v"]`) with fallback to a plain string. It writes the dotted `key` into `overrides.toml` via `toml_write.dumps`, appends `- {today} · {key} = {value} · from {project} · {reason}` to `CHANGELOG.md`, and commits both in `source.path` with `chore(defaults): Set {last key segment}` + trailers. It returns the commit hash.
- `defaults.toml` schema (exact; Task 6 and the skills read it):

```toml
schema = 1

[review]
mode = "batched"          # or "every-task"
max_lines = 200
max_files = 5
exclude = ["**/tests/**", "**/test/**", "docs/**", "**/*.md"]
risk_paths = ["**/migrations/**", "**/*.proto", "**/openapi*.{yaml,yml,json}", "**/auth/**", "**/security/**", ".github/**", "docs/principles.toml"]

[protected]
paths = [".env", ".env.*", "**/*.pem", "**/*.key"]   # recipes add their lockfiles

[git]
convention = "conventional"
types = ["feat", "fix", "docs", "style", "refactor", "test", "build", "chore", "perf", "ci", "revert"]
branching = "trunk"

[identity]
license = "MIT"

[stacks]
ml = "python"
web = "typescript"
cli = "python"
backend = "python"

[[principles]]
id = "fail-helpfully"
title = "Fail fast, fail helpfully"
statement = "Detect errors as early as possible. Every error message describes the problem and tells the user how to proceed."
rationale = "..."
applies = ["always"]          # any-of; "always" short-circuits
checked_by = ["reviewer"]     # values: "reviewer" and/or "hook:<script name>"
core = true                   # the ★ marker
# [principles.params] optional, e.g. reproducible → ml_seeds = true
```

  The catalog contains exactly these ids, with statement text taken from spec §6 and `applies` per the list: `simplest-architecture` [always], `fail-helpfully` [always], `tests-first-class` [always], `visual-system` [has_ui], `docs-with-code` [always], `build-hosting-upfront` [always], `validate-at-edges` [always], `strict-types` [always], `pure-core` [nontrivial_logic], `no-dead-code` [always], `contracts` [communicating_components], `one-vocabulary` [multi_component, domain_jargon], `one-command` [always], `reproducible` [always], `env-config` [deployed], `timeouts` [network_calls], `observability` [deployed], `perf-budgets` [budgets_set], `accessibility` [has_ui], `safe-migrations` [persisted_data], `no-secrets` [always], `dependency-reasons` [always], `clean-history` [always], `evidence-before-done` [always], `never-weaken-checks` [always], `stay-in-scope` [always], `ask-when-ambiguous` [always], `definition-of-done` [always]. `checked_by` names the hooks from Tasks 9–13 where one applies (e.g. `no-secrets` → `hook:stop_checks`, `clean-history` → `hook:commit_msg`, `never-weaken-checks` → `hook:guard_paths`), and `reviewer` for all.

- [ ] **Step 1: Write failing tests** (use `tmp_path` fake homes and source repos; `git init` the fake source)

```python
def test_env_source_wins(tmp_path): ...  # ALPHA_SOURCE dir with defaults/defaults.toml → live=True, path == that dir
def test_config_file_source(tmp_path): ... # home/.config/alpha/config.toml source="<dir>" → live=True
def test_fallback_is_bundled_and_explains(tmp_path):
    s = locate_source(plugin_root=tmp_path / "plugin", env={}, home=tmp_path / "home")
    assert s.live is False and "ALPHA_SOURCE" in s.reason and str(tmp_path / "home/workspace/alpha") in s.reason
def test_catalog_has_all_core_principles():
    d = load_defaults(Source(ROOT, True, ""))
    ids = {p["id"] for p in d["principles"]}
    assert {"fail-helpfully", "never-weaken-checks", "clean-history", "definition-of-done"} <= ids and len(ids) == 28
def test_overrides_layer_wins(tmp_path):  # overrides.toml review.max_lines=400 → loaded value 400, max_files still 5
def test_unknown_condition_is_rejected_with_hint(tmp_path):  # applies=["sometimes"] → DefaultsError mentioning "sometimes" and listing CONDITIONS
def test_set_default_writes_logs_and_commits(tmp_path):
    h = set_default(src, "review.max_lines", "400", "demo", "small CLIs", ["Co-Authored-By: X <x@y>"], date(2026, 10, 19))
    assert tomllib.loads((src.path / "defaults/overrides.toml").read_text())["review"]["max_lines"] == 400
    assert "2026-10-19 · review.max_lines = 400 · from demo · small CLIs" in (src.path / "defaults/CHANGELOG.md").read_text()
    assert git(src.path, "log", "-1", "--format=%s") == "chore(defaults): Set max_lines" and len(h) >= 7
def test_set_default_refuses_when_not_live(tmp_path):  # DefaultsError mentioning "decision log"
```

- [ ] **Step 2:** Run `uv run pytest tests/test_defaults.py -v`. Expected: FAIL.
- [ ] **Step 3:** Write `defaults/defaults.toml` (full catalog) and implement `src/alpha/defaults.py`. CLI: `alpha defaults show` prints the source line (`live from <path>` or `bundled (<reason>)`) followed by the merged TOML. `--json` prints `{"source": {...}, "defaults": {...}}`. `alpha defaults set --key K --value V --project P --reason R [--trailer T]...` prints the commit hash, and on `DefaultsError` exits 3 with the message.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5: Commit**: `feat: Add kit defaults with live source and change log`

---

### Task 4: Answers model and validation

**Files:** Create `src/alpha/answers.py`. Modify `src/alpha/cli.py` (`answers check <path> [--area A]`). Test: `tests/test_answers.py`.

**Interfaces:**
- Produces: frozen dataclasses mirroring the JSON below (`Answers`, `Identity`, `Requirement`, `Component`, `Traits`, `GitPrefs`, `AgentWorkflow`, `Override`, `Decision`). `AREAS = ("identity", "components", "git", "agent_workflow")`. `load_answers(path: Path, require_areas: Sequence[str] = AREAS) -> Answers` raises `AnswersError(f"{json.path}: {problem}. {how to fix}")`. `KINDS = {"backend", "frontend", "cli", "mobile", "ml", "library", "worker"}`. `STACKS = {"python", "typescript"}`.
- `.claude/alpha/project.json` contract (exact; the skills write it, Task 4 parses it, Task 15 adds a top-level `manifest` key that `load_answers` ignores):

```json
{
  "schema": 1,
  "areas": {"identity": "done", "components": "done", "git": "in_progress", "agent_workflow": "pending"},
  "identity": {
    "name": "Pico Trust", "slug": "pico-trust", "value_proposition": "...", "target_users": "...",
    "requirements": [{"id": "R1", "text": "...", "acceptance": "Given ... when ... then ..."}],
    "license": "MIT", "license_file": null, "copyright_holder": "Semyon Vadishev",
    "domain_jargon": false
  },
  "layout": "monorepo",
  "components_talk": true,
  "components": [{
    "name": "api", "path": "api", "kind": "backend", "stack": "python",
    "traits": {"has_ui": false, "deployed": true, "network_calls": true, "persisted_data": true, "ml": false, "nontrivial_logic": true}
  }],
  "git": {"convention": "conventional", "scopes": ["api", "web"], "branching": "trunk"},
  "agent_workflow": {"review_mode": "batched", "max_lines": 200, "max_files": 5, "extra_risk_paths": []},
  "overrides": [{"principle": "observability", "scope": "component:api", "change": "loosen", "params": {}, "reason": "..."}],
  "decisions": [{"area": "identity", "title": "Product identity", "context": "...", "decision": "...", "consequences": "..."}]
}
```

  Rules:
  - Requested areas must be `"done"`.
  - `slug` and component `name` match `^[a-z][a-z0-9-]*$`. Names are unique.
  - `path` is relative, has no `..`, and paths don't nest in each other. `layout == "single"` requires exactly one component with `path == "."`.
  - `stack` is in STACKS, otherwise: `"<stack> is not supported yet; alpha 0.1 supports python and typescript. Pick one, or wait for the generic-stack recipe (plan 2)"`.
  - `license` is "MIT", "Apache-2.0", or "Proprietary", or `license_file` points to an existing file.
  - An override `change` is one of tighten/loosen/drop. loosen and drop need a non-empty `reason`. `principle` must exist in defaults (checked in Task 6, not here). `scope` is `"project"` or `"component:<name>"` with an existing name.
  - `review_mode` is batched or every-task. `max_lines` and `max_files` are > 0.
  - There is a decision for each done area.

- [ ] **Step 1: Write failing tests**: one valid fixture (`tests/fixtures/answers_valid.json`, the JSON above with all areas done and two components `api` (python) and `web` (typescript, kind frontend)), plus one test per rule asserting the `AnswersError` message contains the JSON path and the fix. For example:

```python
def test_loosen_without_reason(tmp_path):
    with pytest.raises(AnswersError, match=r"overrides\[0\]\.reason: .*required.*loosen"): ...
def test_partial_check_only_requires_named_area(tmp_path):  # areas.git="pending" ok with require_areas=["identity"]
def test_unsupported_stack_mentions_supported_ones(tmp_path):  # stack "go" → message contains "python and typescript"
```

- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `answers.py`. `alpha answers check PATH [--area A ...]` prints `ok` or the error and exits 1.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5: Commit**: `feat: Add answers model with helpful validation`

---

### Task 5: Stack recipes for Python and TypeScript

**Files:** Create `recipes/python.toml`, `recipes/python/{pyproject.toml,test_setup.py}.tmpl`, `recipes/typescript.toml`, `recipes/typescript/{package.json,tsconfig.json,biome.json,setup.test.ts}.tmpl`, `src/alpha/recipes.py`. Test: `tests/test_recipes.py`.

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Recipe: stack: str; bootstrap: list[str]; commands: dict[str, str]; lockfiles: list[str]; manifests: list[str]; source_globs: list[str]; test_globs: list[str]; allow: list[str]; files: dict[str, str]` (output relpath → template name). `load_recipe(stack: str) -> Recipe`. `render_component(component: Component, project_slug: str) -> dict[str, str]` returns paths relative to the project root (component path joined). Templates use `string.Template` with `$name`, `$slug`.
- `commands` keys (exact, used by hooks and CLAUDE.md): `setup`, `test`, `lint`, `format`, `typecheck`, `format_file`, `lint_file`. `{file}` is substituted by hooks. All commands run with cwd = component path.
- Python: bootstrap `uv add --dev pytest ruff pyright`. setup `uv sync`. test `uv run pytest`. lint `uv run ruff check`. format `uv run ruff format`. typecheck `uv run pyright`. format_file `uv run ruff format {file}`. lint_file `uv run ruff check {file}`. lockfiles `["uv.lock"]`. manifests `["pyproject.toml"]`. source_globs `["src/**/*.py"]`. test_globs `["tests/**/*.py"]`. allow `["Bash(uv run:*)", "Bash(uv sync:*)", "Bash(uv add:*)"]`.
  - `pyproject.toml.tmpl`: name `$slug-$name` and `requires-python = ">=3.12"`. Strict pyright, ruff select as in Task 1. Pytest `testpaths = ["tests"]`. `[tool.uv] package = false` so no `src/` package is needed until real code exists. No pyright `include` list (defaults to the component root, so `tests/` is checked now and `src/` once it appears).
- TypeScript: bootstrap `pnpm add -D typescript vitest @biomejs/biome @types/node`. setup `pnpm install`. test `pnpm vitest run`. lint `pnpm biome lint .`. format `pnpm biome format --write .`. typecheck `pnpm tsc --noEmit`. format_file `pnpm biome format --write {file}`. lint_file `pnpm biome lint {file}`. lockfiles `["pnpm-lock.yaml"]`. manifests `["package.json"]`. source_globs `["src/**/*.ts", "src/**/*.tsx"]`. test_globs `["tests/**/*.ts", "**/*.test.ts", "**/*.test.tsx"]`. allow `["Bash(pnpm vitest:*)", "Bash(pnpm biome:*)", "Bash(pnpm tsc:*)", "Bash(pnpm install:*)", "Bash(pnpm add:*)"]`.
  - `tsconfig.json.tmpl`: `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `module`/`moduleResolution` `NodeNext`, includes `src` and `tests` (a missing `src/` is fine because `tests/` provides input). No `src/` files are generated.
- Setup tests test the setup, not app behavior. Python `tests/test_setup.py` asserts `pyproject.toml` has `tool.pyright.typeCheckingMode == "strict"`. TS `tests/setup.test.ts` asserts the parsed `tsconfig.json` has `compilerOptions.strict === true` and `noUncheckedIndexedAccess === true`.

- [ ] **Step 1: Write failing tests**

```python
def test_python_component_files():
    files = render_component(py_component(path="api"), "pico")
    assert set(files) == {"api/pyproject.toml", "api/tests/test_setup.py"}   # no src/ placeholders
    pp = tomllib.loads(files["api/pyproject.toml"])
    assert pp["tool"]["pyright"]["typeCheckingMode"] == "strict" and pp["project"]["name"] == "pico-api"
def test_typescript_component_files():
    files = render_component(ts_component(path="web"), "pico")
    tsc = json.loads(files["web/tsconfig.json"])
    assert tsc["compilerOptions"]["strict"] is True and json.loads(files["web/package.json"])["type"] == "module"
def test_single_layout_path_dot():  # path "." → keys have no "./" prefix, e.g. "pyproject.toml"
def test_command_keys_complete():
    for s in ("python", "typescript"):
        assert set(load_recipe(s).commands) == {"setup", "test", "lint", "format", "typecheck", "format_file", "lint_file"}
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Write the recipes and templates, and implement `recipes.py`.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5: Commit**: `feat: Add Python and TypeScript stack recipes`

---

### Task 6: Principles file builder

**Files:** Create `src/alpha/principles.py`. Test: `tests/test_principles.py`.

**Interfaces:**
- Consumes: `load_defaults` (Task 3), `Answers` (Task 4), `load_recipe` (Task 5), `toml_write.dumps` (Task 2).
- Produces:
  - `compute_facts(a: Answers) -> dict[str, bool]` (project-level). `has_ui` = any component kind in {frontend, mobile} or traits.has_ui. `multi_component` = len > 1. `communicating_components` = multi_component and components_talk. `deployed`, `network_calls`, `persisted_data`, `ml`, `nontrivial_logic` = any component trait. `budgets_set` = False (Plan 2). `domain_jargon` from identity.
  - `component_facts(c: Component) -> dict[str, bool]`.
  - `build_principles(defaults: dict, a: Answers, kit_version: str) -> dict[str, Any]`
  - `render_principles(data: dict) -> str`. A header comment explains the file is the single source of truth, edited by hand or by alpha skills, followed by `dumps(data)`.
  - `override_decision_paths(a: Answers, first_number: int) -> dict[int, str]` maps the override index to `docs/decisions/NNNN-override-<principle>.md` (used by Task 7 too).
- Output schema (exact; hooks in Tasks 8–12 and Plan 3 read it):

```toml
schema = 1
kit_version = "0.1.0"
[project]
name = "Pico Trust"
slug = "pico-trust"
[review]           # defaults.review merged with answers.agent_workflow; risk_paths += extra_risk_paths
mode = "batched"
max_lines = 200
max_files = 5
exclude = [...]
risk_paths = [...]
[protected]
paths = [".env", ".env.*", "**/*.pem", "**/*.key", "api/uv.lock", "web/pnpm-lock.yaml"]
[git]
convention = "conventional"
types = [...]
scopes = ["api", "web"]
[docs_map]         # glob of public-behavior paths → docs that must change with them
                   # EMPTY in plan 1 (mapping all source to a doc would block every change);
                   # plan 2's documentation area fills it. Hooks already honor it.
[[components]]
name = "api"
path = "api"
kind = "backend"
stack = "python"
manifests = ["api/pyproject.toml"]
source_globs = ["api/src/**/*.py"]
test_globs = ["api/tests/**/*.py"]
[components.commands]   # recipe commands verbatim
[[principles]]
id = "timeouts"
title = "..."
statement = "..."
rationale = "..."
applies = ["network_calls"]
core = false
checked_by = ["reviewer"]
active = true
components = ["api"]    # components where it applies; all components for project-level "always"
override_decision = ""  # path from override_decision_paths when overridden
[principles.params]
```

  Override semantics:
  - `tighten` merges `params`.
  - `loosen` merges `params`.
  - `drop` with scope project sets `active = false`. With scope `component:X` it removes X from `components`, and if the list becomes empty, sets `active = false`.
  - All three set `override_decision`.
  - An unknown principle id raises `AnswersError("overrides[i].principle: unknown principle '<id>'. Known ids: ...")`.

- [ ] **Step 1: Write failing tests**

```python
def test_cli_only_project_has_no_visual_system():    # one cli component → visual-system active False
def test_two_talking_components_enable_contracts():  # fixture → contracts active True, components == ["api","web"]
def test_component_scoped_condition():               # timeouts.components == ["api"] when only api has network_calls
def test_drop_for_one_component(): ...               # drop observability component:api → components excludes api; override_decision set
def test_lockfiles_become_protected():               # "api/uv.lock" and "web/pnpm-lock.yaml" in protected.paths
def test_review_settings_come_from_answers():        # answers max_lines 50, mode every-task → review.max_lines == 50, mode == "every-task"
def test_output_parses_and_is_deterministic():
    s1 = render_principles(build_principles(D, A, "0.1.0")); s2 = render_principles(build_principles(D, A, "0.1.0"))
    assert s1 == s2 and tomllib.loads(s1)["schema"] == 1
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `principles.py`.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5: Commit**: `feat: Build principles file from defaults and answers`

---

### Task 7: Docs, CLAUDE.md, README, LICENSE, CONTRIBUTING

**Files:** Create `src/alpha/render/__init__.py`, `src/alpha/render/docs.py`, `src/alpha/licenses/MIT.txt`, `src/alpha/licenses/Apache-2.0.txt` (the official texts from spdx.org, with `[year]`/`[fullname]` placeholders → `$year`/`$holder`). Test: `tests/test_render_docs.py`.

**Interfaces:**
- Consumes: `Answers`, the principles data dict (Task 6), `override_decision_paths`.
- Produces: `render_docs(a: Answers, principles: dict, year: int) -> dict[str, str]` with exactly these keys: `README.md`, `LICENSE`, `CONTRIBUTING.md`, `CLAUDE.md`, `docs/product.md`, `docs/architecture.md`, `docs/dependencies.md`, and `docs/decisions/NNNN-<slug>.md` for each decision in answer order (numbered from 0001), followed by one per override.
- Content requirements (the tests check these):
  - **CLAUDE.md**: under 150 lines. Sections `## Principles` (one line per *active* principle: `- **{title}**: {statement}`, and a pointer that `docs/principles.toml` is the source of truth with parameters), `## Commands` (a table per component with setup/test/lint/format/typecheck; `run` reads "add when the entry point exists"), `## Definition of done` (the five items of spec §6 `definition-of-done`), `## Commits` (convention, scopes, "use the commit skill"), `## Docs` (links).
  - **CONTRIBUTING.md**: one-time setup (`git config core.hooksPath .claude/alpha/githooks`, then per-component setup), the commit convention with types and scopes, the 50/72 rules, and the branching model.
  - **docs/product.md**: name, value proposition, target users, and a requirements table `| ID | Requirement | Acceptance check |`.
  - **docs/architecture.md**: layout, a components table (name, path, kind, stack, traits), whether components talk, and the tool choices per stack.
  - **docs/dependencies.md**: the dependency log, seeded with one row per recipe dev tool: `| Dependency | Component | Why | Added |`.
  - **Decision records**: `# NNNN. {title}`, `Date`, `Status: accepted`, `## Context`, `## Decision`, `## Consequences`. Override records add a `Principle: {id} ({change}, scope {scope})` line and use the reason as Context.
  - **README.md**: name, value proposition, and setup/test commands per component.
  - **LICENSE**: the template with year and holder. Proprietary → `Copyright (c) {year} {holder}. All rights reserved.` `license_file` → copied verbatim.

- [ ] **Step 1: Write failing tests**

```python
def test_claude_md_lists_only_active_principles():   # cli-only fixture: "Visual system" absent, "Fail fast" present; len(lines) < 150
def test_claude_md_has_commands_per_component():     # "uv run pytest" and "pnpm vitest run" both present under ## Commands
def test_decisions_numbered_with_overrides_last():   # 4 area decisions + 1 override → 0005-override-observability.md exists
def test_mit_license_has_year_and_holder():          # "Copyright (c) 2026 Semyon Vadishev" in LICENSE
def test_product_md_requirements_table():            # "| R1 |" row with the acceptance text
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `render_docs` with plain f-string builders (one private function per file).
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5: Commit**: `feat: Render CLAUDE.md, docs and license`

---

### Task 8: Hook common library

**Files:** Create `project-files/hooks/_common.py`. Test: `tests/hooks/conftest.py` (fixture `project(tmp_path)` builds a git repo with a principles file whose component commands are `python3 -c` stubs controlled by the test), `tests/hooks/test_common.py`.

**Interfaces:**
- Produces (all hooks import these; scripts do `sys.path.insert(0, str(Path(__file__).parent))`):
  - `check_python() -> None`: on < 3.11, prints the Global Constraints message to stderr and `sys.exit(0)`.
  - `read_input() -> dict[str, Any]`: JSON from stdin. `{}` on empty.
  - `project_root(inp: dict) -> Path`: `$CLAUDE_PROJECT_DIR`, else `inp["cwd"]`, else cwd.
  - `load_principles(root: Path) -> dict[str, Any] | None`. Missing file → None (hooks then exit 0 silently; not an alpha project). Malformed → prints `docs/principles.toml is not valid TOML: <tomllib message>. Fix the file (it is the single source of truth for alpha's checks), or restore it with "git checkout docs/principles.toml".` to stderr and `sys.exit(0)`.
  - `component_for(rel_path: str, principles: dict) -> dict | None`: longest matching component `path` prefix; path "." matches everything.
  - `changed_files(root: Path) -> list[str]`: tracked changes vs HEAD plus untracked (`git status --porcelain=v1 -z`), handling no-commits repos and paths with spaces.
  - `matches(rel_path: str, globs: list[str]) -> bool`: `**` aware (`fnmatch` on path parts, or `PurePath.full_match` on 3.13+ with a fallback).
  - `block(message: str) -> NoReturn`: stderr + exit 2.
  - `state_path(root: Path, name: str) -> Path`: `root/.claude/alpha/state/name`, creating the dir.

- [ ] **Step 1: Write failing tests**

```python
def test_malformed_principles_explains_and_exits_zero(project):
    project.write("docs/principles.toml", "schema = = 1")
    r = project.run_hook("guard_bash.py", {"tool_name": "Bash", "tool_input": {"command": "ls"}})  # any hook works
    assert r.returncode == 0 and "not valid TOML" in r.stderr and "git checkout docs/principles.toml" in r.stderr
def test_component_for_longest_prefix():   # components "." and "web" → "web/src/a.ts" → web; "README.md" → "."
def test_changed_files_no_commits_and_spaces(project):  # untracked "a b.py" appears as "a b.py"
def test_matches_double_star():  # matches("api/src/x/y.py", ["api/src/**/*.py"]) is True; ("api/tests/t.py", same) False
```

  (The first test needs a minimal `guard_bash.py` that only calls `check_python`, `read_input`, `load_principles`, then exits 0. Create that stub here, and Task 9 fills it in.)

- [ ] **Step 2:** Run `uv run pytest tests/hooks -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `_common.py` and the stub.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5: Commit**: `feat(hooks): Add shared hook helpers`

---

### Task 9: `guard_bash.py` (PreToolUse Bash)

**Files:** Modify `project-files/hooks/guard_bash.py`. Test: `tests/hooks/test_guard_bash.py`.

**Interfaces:**
- Consumes: `_common` helpers.
- Produces: blocks (exit 2) commands that, in any `&&`/`;`/`|`-separated segment:
  - contain `git commit|push|merge|rebase|cherry-pick ... --no-verify` (or `-n` on `git commit`). Message: `--no-verify skips the project's commit checks. Fix what the hook reports instead; if the hook itself is wrong, tell the user.`
  - contain `git push` with `--force`, `-f`, `--force-with-lease`, `--force-if-includes`, or a `+refspec`. Message names the flag and suggests a new commit or asking the user.
  - contain `git commit --amend` when HEAD is on a remote branch (`git branch -r --contains HEAD` non-empty). Message: `HEAD is already pushed (<branches>); amending rewrites shared history. Make a new commit instead.`

  It otherwise exits 0. Use `shlex.split` per segment. If parsing fails, allow.

- [ ] **Step 1: Write failing tests**: parametrized blocked commands (`git commit -m x --no-verify`, `git commit -nm x`, `cd a && git push -f`, `git push origin +main`, `git push --force-with-lease`) and allowed commands (`git push`, `git commit -m "mention --no-verify in text"`, `echo git push -f`, `ls -f`). Amend: allowed with no commits, allowed with no remote, allowed with a detached HEAD, and blocked after `git push` to a bare repo created in `tmp_path`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5: Commit**: `feat(hooks): Block no-verify, force-push and pushed amends`

---

### Task 10: `guard_paths.py` (PreToolUse Edit|Write|MultiEdit)

**Files:** Create `project-files/hooks/guard_paths.py`. Test: `tests/hooks/test_guard_paths.py`.

**Interfaces:**
- Produces:
  - **Protected paths.** If `file_path` (made relative to the root) matches `principles.protected.paths`, block with `"<path> is protected. Lockfiles change only through the package manager (e.g. <component setup/add command>); secrets belong in the environment, never in files Claude edits."`
  - **Weakening.** If the new text (`content`, `new_string`, or every `edits[].new_string`) adds any of these patterns not present in the old text, print the PreToolUse JSON `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": "This edit weakens a check (<pattern>). Principle never-weaken-checks: fix the cause instead, or approve if you are sure."}}` and exit 0. Patterns: `@pytest.mark.skip`, `pytest.skip(`, `@unittest.skip`, `it.skip(`, `test.skip(`, `describe.skip(`, `xit(`, `# type: ignore`, `# pyright: ignore`, `# noqa`, `biome-ignore`, `eslint-disable`, `@ts-ignore`, `@ts-expect-error`, `"strict": false`, `typeCheckingMode = "basic"`, `typeCheckingMode = "off"`, and `except Exception: pass`/`except: pass` (whitespace-insensitive).

  For `Write`, old text is the current file content if it exists.

- [ ] **Step 1: Write failing tests**: lockfile edit blocked with a message naming the path; `.env.local` blocked; adding `# type: ignore` yields `ask` JSON; editing a line that already had `# type: ignore` (present in both old and new) passes; a file outside the protected list passes; a non-alpha project (no principles file) passes.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5: Commit**: `feat(hooks): Guard protected paths and check weakening`

---

### Task 11: `post_edit.py` (PostToolUse Edit|Write|MultiEdit)

**Files:** Create `project-files/hooks/post_edit.py`. Test: `tests/hooks/test_post_edit.py`.

**Interfaces:**
- Produces: for an edited file inside a component and matching its `source_globs` or `test_globs`, it runs `format_file` then `lint_file` (cwd = component path, `{file}` = path relative to the component, shell-quoted). Lint failure → block with the tool output (last 60 lines) and `Fix the lint errors above in <file>.` A command not found (exit 127) → block with `"<tool> is not installed for component <name>. Run its setup command: <setup>"`. Files outside components or globs → exit 0 without running anything. Per-command timeout: 60 s, and on timeout block with a message naming the command.
- [ ] **Step 1: Write failing tests** with stub commands in the conftest principles: lint stub exits 1 with "E1 bad" → blocked and the output is in stderr; format stub writes a marker file proving it ran first; a `README.md` edit runs nothing; a 127 stub → setup hint.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5: Commit**: `feat(hooks): Format and lint files after edits`

---

### Task 12: `stop_checks.py` (Stop)

**Files:** Create `project-files/hooks/stop_checks.py`. Test: `tests/hooks/test_stop_checks.py`.

**Interfaces:**
- Produces: computes `changed = changed_files(root)`. With no changes, it exits 0. Otherwise it collects problems in this order:
  1. **Secrets** in added lines (`git diff HEAD -U0` plus the contents of untracked text files). Patterns: `AKIA[0-9A-Z]{16}`, `-----BEGIN [A-Z ]*PRIVATE KEY-----`, `gh[pousr]_[A-Za-z0-9]{36,}`, `sk-[A-Za-z0-9_-]{20,}`, `xox[abpr]-[A-Za-z0-9-]{10,}`, and `(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*["'][^"'\s]{12,}["']`. Report the file:line and `move it to the environment and reference it by name`, never the secret value.
  2. **Code without tests.** Per affected component, if any changed file matches `source_globs` and none matches `test_globs`: `"<component>: source changed (<files>) but no tests changed. Principle tests-first-class: add or update tests."`
  3. **Dependencies without a log entry.** A changed file is in a component's `manifests` and `docs/dependencies.md` is not changed: `"Dependency manifest changed (<file>) without an entry in docs/dependencies.md. Record what was added and why."`
  4. **Docs drift.** A changed file matches a `docs_map` key and none of its mapped docs changed: `"<file> changed but <docs> did not. Principle docs-with-code: update them, or say why no doc change is needed."`
  5. **Typecheck and tests.** For each affected component, run `typecheck` then `test` (timeout 600 s each). Failures report the last 60 lines.

  If there are problems, print `{"decision": "block", "reason": "<numbered problems>"}` and increment `state_path(root, "stop-blocks")`. When the counter is ≥ 3, instead print the problems to stderr with the prefix `alpha: checks still failing after 3 attempts; stopping so the user can decide:`, reset the counter, and exit 0. On a clean run it resets the counter.

- [ ] **Step 1: Write failing tests**:
  - A secret in a new file blocks, and the output has the file:line but not the secret value.
  - A source-only change blocks with tests-first-class.
  - Source + test changes with passing stubs exits 0, and the counter resets.
  - A manifest change without the dependency log blocks.
  - A failing test stub blocks.
  - Three consecutive blocks, then the fourth call exits 0 with "still failing after 3 attempts".
  - A clean tree exits 0 without running any command.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5: Commit**: `feat(hooks): Gate stopping on tests, docs and secrets`

---

### Task 13: `commit_msg.py`, git shim, and `session_start.py`

**Files:** Create `project-files/hooks/commit_msg.py`, `project-files/githooks/commit-msg`, `project-files/hooks/session_start.py`. Tests: `tests/hooks/test_commit_msg.py`, `tests/hooks/test_session_start.py`.

**Interfaces:**
- `commit_msg.py <msgfile>`. Strip `#` comment lines. Pass if the header starts with `Merge `, `Revert "`, `fixup! `, `squash! `, or `amend! `.
  - Otherwise the header must match `^(?P<type>[a-z]+)(\((?P<scope>[a-z0-9-]+)\))?!?: (?P<desc>.+)$`.
  - `type` is in `git.types`. `scope`, if present, is in `git.scopes`.
  - `desc` is ≤ 50 chars and starts uppercase.
  - `desc` has no trailing `.`.
  - `desc`'s first word doesn't end in `ed` or `ing` and isn't in `{"Adds", "Fixes", "Updates", "Removes", "Changes", "Makes", "Uses", "Moves", "Renames"}`.
  - There is a blank line after the header if a body exists. Body lines are ≤ 72 except lines containing `://` or trailer lines (`^[A-Za-z-]+: `).
  - Each failure prints `commit-msg: <rule broken>. Example: "feat(api): Add token refresh"` and exits 1.
  - If there's no principles file, use the default types and allow any scope.
- `githooks/commit-msg`: `#!/bin/sh` → `exec python3 "$(git rev-parse --show-toplevel)/.claude/alpha/hooks/commit_msg.py" "$1"`.
- `session_start.py`: collects warnings (`git config core.hooksPath` != `.claude/alpha/githooks` → `Run: git config core.hooksPath .claude/alpha/githooks`; Python < 3.11 → the guard message; principles malformed → that message). It prints `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "alpha: <warnings>"}}` only when there are warnings.

- [ ] **Step 1: Write failing tests**: valid examples (`feat(api): Add token refresh`, `docs: Add design doc`), each rule's rejection (`feat: add x` lowercase, `feat: Added x`, `feat: Add x.`, a 51-char description, `feet: Add x`), `Merge branch 'x'`, `Revert "feat: X"`, `fixup! feat: X` pass, an unknown scope fails and lists the scopes, a trailer line > 72 passes, and session_start warns on an unset hooksPath and stays silent when set.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. `chmod +x` the shim.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5: Commit**: `feat(hooks): Check commit messages and session setup`

---

### Task 14: Ported commit skill and committer agent, settings renderer

**Files:** Create `project-files/skills/commit/SKILL.md`, `project-files/agents/committer.md`, `src/alpha/render/claude_settings.py`. Test: `tests/test_claude_settings.py`, `tests/test_ported_commit_tools.py`.

**Interfaces:**
- Ported files: copy `~/.claude/commands/commit.md` (add frontmatter `name: commit`, `description: Commit changes with proper, fine-grained, atomic commits.`) and `~/.claude/agents/committer.md`. In both:
  - Replace step 5's footer block with: `End each message with the attribution lines Claude Code provides for this session, if any. Never invent or hard-code co-author lines.`
  - Add to step 1: `This project's convention is in CONTRIBUTING.md (types, scopes = component names) and is enforced by the commit-msg hook.`
  - Everything else verbatim.
- `render_settings(principles: dict) -> dict[str, Any]`:
  - `permissions.allow` = the union of the recipes' `allow` for the project's stacks + `["Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git add:*)", "Bash(git commit:*)"]`, sorted.
  - `permissions.deny` = `["Bash(git push --force:*)", "Bash(git push -f:*)", "Bash(rm -rf:*)", "Read(./.env)", "Read(./.env.*)", "Read(**/*.pem)", "Read(**/*.key)"]`.
  - `hooks` wires SessionStart → session_start.py, PreToolUse `Bash` → guard_bash.py, PreToolUse `Edit|Write|MultiEdit` → guard_paths.py, PostToolUse `Edit|Write|MultiEdit` → post_edit.py, and Stop → stop_checks.py. Each is `{"type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/alpha/hooks/<script>"}`. The Stop timeout is 1200 s.
- [ ] **Step 1: Write failing tests**:
  - Settings for the two-stack fixture: allow contains `Bash(uv run:*)` and `Bash(pnpm vitest:*)`; deny contains the force-push entries; every hook command names a script that exists under `project-files/hooks/`.
  - The ported files contain no `Co-Authored-By` and contain `attribution lines Claude Code provides`.
  - The ported skill has valid frontmatter (`name: commit`).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Port the files and implement the renderer.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5: Commit**: two commits. First the ported tools, `feat: Port commit skill and committer agent`. Then the renderer, `feat: Render Claude Code settings for projects`.

---

### Task 15: Generator, manifest, bootstrap and grouped commits

**Files:** Create `src/alpha/generate.py`, `src/alpha/gitops.py`, `evals/scenarios/python-ml-single.json`, `evals/scenarios/web-ts-plus-python-api.json`. Modify `src/alpha/cli.py`. Test: `tests/test_generate.py`, `tests/test_scenarios.py`, `tests/test_bootstrap_slow.py`.

**Interfaces:**
- Consumes: Tasks 3–7 and 14, and `project-files/`.
- Produces:
  - `generate(target: Path, plugin_root: Path, source: Source, year: int) -> list[str]`:
    - **Empty check.** If anything besides `.DS_Store` and `.claude/alpha/project.json` exists, raise `GenerateError("<target> is not empty (found: a, b, …). alpha v0.1 starts projects only in empty folders. Choose a new folder, or move these files out first.")`.
    - Load `target/.claude/alpha/project.json` (all areas) and the defaults.
    - Write principles (`docs/principles.toml`), docs (Task 7), component files (Task 5), and `.claude/settings.json` (Task 14).
    - Copy `project-files/hooks/*.py` → `.claude/alpha/hooks/`, the skill → `.claude/skills/commit/SKILL.md`, the agent → `.claude/agents/committer.md`, and the githook → `.claude/alpha/githooks/commit-msg` (exec bit preserved).
    - Write `.gitignore`: `.claude/alpha/state/`, plus `.venv/`, `__pycache__/`, `.pytest_cache/` for python components, plus `node_modules/`, `dist/`, `coverage/` for typescript components, each prefixed by the component path when not `.`.
    - Add a top-level `manifest` key to `.claude/alpha/project.json`: `{"kit_version", "generated_at" (ISO date), "defaults": {"path", "live", "commit": <git HEAD of source or null>}, "files": {relpath: sha256}}` covering every generated file except `project.json` itself.
    - Return the sorted relpaths.
  - `bootstrap(target: Path, principles: dict) -> None`: per component, run the recipe `bootstrap` then `setup` then `test`. On failure, raise `GenerateError` with the command, its last 40 lines of output, and `Fix the toolchain (is uv/pnpm installed?) and rerun "alpha bootstrap <target>"`.
  - `commit_skeleton(target: Path, principles: dict, trailers: list[str]) -> list[str]`. It runs `git init -b main` (if `.git` is absent) and `git config core.hooksPath .claude/alpha/githooks`. Then it commits in this order, returning the hashes:
    1. `docs: Add product brief, principles and decisions` (README.md, LICENSE, CONTRIBUTING.md, docs/, .gitignore).
    2. `chore: Add Claude Code settings and guardrails` (CLAUDE.md, .claude/).
    3. One per component: `build(<name>): Set up <stack> toolchain and tests` (the component path, including lockfiles).

    Messages carry the trailers after a blank line. Commits go through the real `commit-msg` hook, so the messages must pass it.
  - CLI: `alpha generate <target>`, `alpha bootstrap <target>`, `alpha commit-skeleton <target> [--trailer T]...`. Each prints a summary and turns errors into the message plus exit 1.
- Scenarios: `python-ml-single.json` has one `ml` component at `.`, layout single, stack python, traits ml + nontrivial_logic. `web-ts-plus-python-api.json` matches the Task 4 fixture.

- [ ] **Step 1: Write failing tests**

```python
def test_refuses_non_empty_folder(tmp_path):
    (tmp_path / "README.md").write_text("x"); (tmp_path / ".DS_Store").write_text("")
    with pytest.raises(GenerateError, match=r"not empty \(found: README.md\)"): generate(tmp_path, ROOT, SRC, 2026)
def test_accepts_alpha_dir_and_ds_store(tmp_path): ...
@pytest.mark.parametrize("scenario", ["python-ml-single", "web-ts-plus-python-api"])
def test_scenario_skeleton(tmp_path, scenario):
    files = generate_scenario(tmp_path, scenario)
    for f in ["CLAUDE.md", "docs/principles.toml", ".claude/settings.json", ".claude/alpha/hooks/stop_checks.py",
              ".claude/skills/commit/SKILL.md", ".claude/alpha/githooks/commit-msg", ".claude/alpha/project.json"]:
        assert f in files
    root_entries = {p.name for p in tmp_path.iterdir()} - {".git"}
    assert root_entries <= {"README.md", "LICENSE", "CONTRIBUTING.md", "CLAUDE.md", ".gitignore", "docs", ".claude", "api", "web",
                            "pyproject.toml", "uv.lock", "tests"}   # nothing kit-specific at the root
    assert not any("/src/" in f or f.startswith("src/") for f in files)    # no placeholder sources
    s = json.loads((tmp_path / ".claude/settings.json").read_text())
    for cmd in hook_commands(s): assert (tmp_path / script_of(cmd)).exists()
    m = json.loads((tmp_path / ".claude/alpha/project.json").read_text())["manifest"]
    assert all(sha256(tmp_path / p) == h for p, h in m["files"].items())
def test_generated_guard_blocks_no_verify(tmp_path):  # run copied guard_bash.py inside generated project → exit 2
def test_commit_skeleton_groups_and_trailers(tmp_path):
    # generate web-ts-plus-python-api, skip bootstrap, commit_skeleton(trailers=["Co-Authored-By: T <t@t>"])
    subjects = git_log_subjects(tmp_path)
    assert subjects == ["build(web): Set up typescript toolchain and tests", "build(api): Set up python toolchain and tests",
                        "chore: Add Claude Code settings and guardrails", "docs: Add product brief, principles and decisions"]
    assert "Co-Authored-By: T <t@t>" in git(tmp_path, "log", "-1", "--format=%B")
    assert git(tmp_path, "status", "--porcelain") == ""

# tests/test_bootstrap_slow.py
@pytest.mark.slow
@pytest.mark.parametrize("scenario", ["python-ml-single", "web-ts-plus-python-api"])
def test_bootstrap_runs_green(tmp_path, scenario):  # generate + bootstrap; lockfiles exist; test commands exit 0
```

- [ ] **Step 2:** Run `uv run pytest tests/test_generate.py tests/test_scenarios.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `generate.py`, `gitops.py`, and the CLI commands.
- [ ] **Step 4:** Run `uv run pytest -v`, then `uv run pytest -m slow -v` (needs network, uv, pnpm). Expected: all PASS. If the slow run fails because of a recipe (e.g. a tool rejects a template), fix the recipe in Task 5's files and rerun.
- [ ] **Step 5: Commit**: `feat: Generate, bootstrap and commit project skeletons`

---

### Task 16: Interview skills

**Files:** Create `skills/grilling/SKILL.md`, `skills/identity/SKILL.md`, `skills/components/SKILL.md`, `skills/git-history/SKILL.md`, `skills/agent-workflow/SKILL.md`, `skills/new-project/SKILL.md`. Test: `tests/test_skills.py`.

**Interfaces:**
- Consumes: CLI commands `defaults show --json`, `defaults set`, `answers check`, `generate`, `bootstrap`, `commit-skeleton`. The answers.json contract from Task 4.
- Every skill locates the CLI as `<this skill's base directory>/../../bin/alpha`. Claude Code prints the base directory when the skill loads.
- **`grilling`** (model-invocable): the method from spec §4, adapted from `mattpocock/skills` `grilling` (MIT, credit in a comment):
  - Use a design tree and ask the frontier per round, as numbered `❓ **Qn** - **title**: body` / `➡️ recommendation`, worded so "yes" accepts.
  - Facts are looked up, never asked.
  - The interview is done when the frontier is empty and the user confirms.
  - Recommendations come from `alpha defaults show --json` (and the project's earlier answers).
  - **Override protocol:** when the user's answer differs from a default, (1) add an `overrides[]` entry (or record it in the area's decision), (2) ask exactly "Make this the default for future projects too?", and (3) on yes run `alpha defaults set --key … --value … --project <slug> --reason "<user's reason>" --trailer <each attribution line>`. If it exits 3 (source not live), tell the user and note the wish in the area's decision `consequences`.
- **Area skills** (`identity`, `components`, `git-history`, `agent-workflow`; `disable-model-invocation: true`, user-callable). Each one:
  - lists the exact answers.json fields it must settle (from Task 4),
  - lists the questions that settle them,
  - uses `grilling`,
  - writes its section plus one `decisions[]` entry,
  - sets `areas.<area> = "done"`,
  - runs `alpha answers check .claude/alpha/project.json --area <area>` and fixes anything it reports.

  Area specifics:
  - **identity**: turns requirements into acceptance checks with the user (Given/When/Then).
  - **components**: per component, asks kind, stack (recommend from `defaults.stacks[kind]`), path, and the six traits; also `components_talk` when there's more than one; supports only python/typescript in v0.1 and says so.
  - **git-history**: convention, scopes (default = component names), branching.
  - **agent-workflow**: review mode (`batched` / `every-task`), thresholds, extra risk paths, explaining each threshold in one line.

  Called directly on an already-generated project, an area skill says that extending projects arrives in plan 2 and stops.
- **`new-project`** (`disable-model-invocation: true`; the user runs `/alpha:new-project [folder]`):
  1. Resolve the target folder (argument or cwd), and run the empty check by listing it. If `.claude/alpha/project.json` exists, resume and report which areas are done.
  2. Run `alpha defaults show` and tell the user whether defaults are live or bundled.
  3. Run the areas in order identity → components → git-history → agent-workflow, never skipping one.
  4. Show a summary of all answers and wait for confirmation.
  5. `alpha generate`, `alpha bootstrap`, `alpha commit-skeleton --trailer …` (attribution lines from the session).
  6. Report the commits, what's enforced now, and that the areas in plan 2 are not yet covered.
- [ ] **Step 1: Write failing tests**: every `skills/*/SKILL.md` has frontmatter with `name` and `description`; the area skills and `new-project` have `disable-model-invocation: true`; every `alpha <subcommand>` mentioned in a skill exists in `cli.py`'s parser; every answers.json field named in an area skill exists in the Task 4 dataclasses.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Write the skills. Keep each under ~150 lines, in imperative voice.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5: Commit**: `feat: Add interview skills and new-project entry point`

---

### Task 17: Install and live end-to-end run

**Files:** Modify `CLAUDE.md` (an install section). No new code.

- [ ] **Step 1:** Ask the user before changing their Claude Code config. Then run `claude plugin marketplace add /Users/vs/workspace/alpha` and `claude plugin install alpha@alpha-local`. Verify the skills appear as `alpha:new-project`, etc.
- [ ] **Step 2:** Create an empty folder in the scratchpad and run `/alpha:new-project <folder>` in a fresh Claude Code session in that folder, answering as for the `web-ts-plus-python-api` scenario. Override one default (e.g. `max_lines = 100`) and decline making it a default.
- [ ] **Step 3: Verify**:
  - `git log --oneline` shows the grouped commits.
  - Each component's test command passes.
  - In a session in that project, attempting `git commit --no-verify` is blocked.
  - Adding `# type: ignore` asks for approval.
  - A source edit without a test edit makes Stop block.
  - `docs/decisions/` has the override record.
  - `defaults/overrides.toml` in the kit is unchanged.
- [ ] **Step 4:** Record the findings in the kit's `CLAUDE.md` install section. Fix any defect through its owning task's tests first.
- [ ] **Step 5: Commit**: `docs: Add install and verification notes`
