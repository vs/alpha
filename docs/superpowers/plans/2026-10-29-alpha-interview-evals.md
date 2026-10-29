# Interview evals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Plan series:** 4/4. This plan covers spec §12's skill evals.

**Goal:** `uv run python -m alpha_evals run` drives the real `/alpha:new-project` interview headlessly for each scenario. A simulated user answers from a written brief. The harness then checks the skeleton the interview produced and writes a report.

**Architecture:**
- The interviewer is `claude -p --plugin-dir <kit copy>`. Each user reply resumes its session.
- The simulated user is a second, tool-less `claude -p` session. Its system prompt holds the scenario's brief.
- After the interview, deterministic checks inspect the generated project:
  - answers;
  - files;
  - settings;
  - hooks fed seeded violations;
  - each component's checks;
  - commits.
- One more live session in the generated project seeds a principle violation on a risk path. The check passes only if the reviewer records a finding for it.
- Everything runs against a throwaway clone of the kit, outside the repo.
- Everything that calls `claude` is tested offline with a fake `claude` executable.

**Tech Stack:** Python 3.11+ stdlib only (tomllib, json, subprocess); pytest, ruff and pyright (strict for `src/`) via uv; Claude Code CLI 2.1.x (`-p`, `--output-format json`, `--resume`).

**Spec:** [docs/superpowers/specs/2026-10-19-project-kit-design.md](../specs/2026-10-19-project-kit-design.md), §12. The rest of the spec is background.

## Global Constraints

- Spec §12, verbatim: "The skills have evals: scripted interview scenarios (e.g. "Python ML pipeline, single component", "TypeScript web app + Python API", "Go CLI" for the fallback path). They check the generated skeleton: required files exist, settings are valid, hooks fire on seeded violations, each component's test command runs green, commits follow the convention, and the reviewer catches seeded principle violations."
- The fallback-path scenario is the existing `rust-cli` (the generic-stack plan used Rust instead of Go). Don't add a Go scenario.
- The evals reuse the three scenarios in `evals/scenarios/*.json` as the expected answers. Those files stay unchanged: the fast suite generates from them.
- Code lives in a new package `src/alpha_evals/`, which is strict under pyright because `src` is. It must not be imported by `src/alpha/` or the hooks. The runtime is stdlib only (`dependencies = []` stays empty).
- Exact names:
  - check names: `interview`, `answers`, `files`, `settings`, `hooks`, `commands`, `commits`, `prompts`, `reviewer`;
  - statuses: `pass`, `warn`, `fail`, `skip`;
  - the simulated user's end token is `<<END>>`.
- No eval writes to the real kit checkout. The defaults source is a clone (`ALPHA_SOURCE`), and the git config is isolated (`GIT_CONFIG_GLOBAL`, `GIT_CONFIG_NOSYSTEM=1`).
- Runs go under `tempfile.gettempdir()/alpha-evals/<YYYYMMDD-HHMMSS>/` by default (`--out` overrides). Never put them inside the repo, where Claude would load alpha's own CLAUDE.md.
- Every `claude` call passes:
  - `--setting-sources project,local`, so the user's plugins, hooks and CLAUDE.md stay out;
  - `--output-format json`;
  - an explicit `--model`;
  - the prompt on stdin, never as an argument, since a reply may start with `-`.
- Commits follow CLAUDE.md: conventional, scope = component name (here `evals` is not a component, so the scope is omitted), description at most 50 chars, imperative, capitalized, no trailing period, body wrapped at 72. Each ends with the session's attribution trailers.

## Review Focus

1. **`claude` fails outright** (expired login, rate limit, non-JSON stdout, non-zero exit). The scenario is recorded as `interview: fail`, with the exit code and the last lines of stderr. The report is still written, and the other scenarios still run (Task 4, Task 6 tests).
2. **The interview loops or stalls** (the same question again and again, or no end). The run stops at the exchange cap with `interview: fail` "stopped after N exchanges" and keeps the transcript (Task 4 test).
3. **The budget runs out mid-interview.** The harness stops before the next call when the spent total reaches `--max-usd`, and records `interview: fail` "budget" (Task 4 test).
4. **The kit checkout has uncommitted changes.** The evals clone HEAD, so they would silently test old skill text. The summary and each report must say so, with the HEAD sha (Task 6 test).
5. **The seeded-hook checks touch the real generated project.** The project must be byte-for-byte unchanged after `run_checks`, apart from its git-ignored `.claude/alpha/state/`, because the reviewer probe runs in it next (Task 3 test).

---

## File Structure

- `evals/briefs/<scenario>.toml`: per scenario, the simulated user's brief and the answer fields the interview must reproduce. There is one for each of `web-ts-plus-python-api`, `python-ml-single` and `rust-cli`.
- `src/alpha_evals/__init__.py`: an empty package marker.
- `src/alpha_evals/scenario.py`: loads a brief and its expected answers, resolves selector pointers, compares answers.
- `src/alpha_evals/checks.py`: the `Check` result type, plus the deterministic skeleton checks (answers, files, settings, commits).
- `src/alpha_evals/seeded.py`: the hook and command checks. These run seeded violations against a copy of the project, and the components' checks in the project.
- `src/alpha_evals/claude.py`: runs one `claude -p` call and parses its JSON into a `Turn`.
- `src/alpha_evals/interview.py`: the interviewer and simulated-user loop.
- `src/alpha_evals/reviewer.py`: the live reviewer probe.
- `src/alpha_evals/run.py`: per-run setup (kit clone, git isolation), running the scenarios, the report and the summary.
- `src/alpha_evals/__main__.py`: the CLI (`run`, `check`).
- `tests/evals/fake_claude.py`: a stand-in `claude` that replays scripted replies.
- `tests/evals/test_*.py`: one test file per module.
- `CLAUDE.md`: how to run the evals, and the findings of the first live run.

---

### Task 1: Briefs and answer comparison

**Files:**
- Create: `src/alpha_evals/__init__.py`, `src/alpha_evals/scenario.py`, `evals/briefs/web-ts-plus-python-api.toml`, `evals/briefs/python-ml-single.toml`, `evals/briefs/rust-cli.toml`
- Test: `tests/evals/test_scenario.py`

**Interfaces:**
- Produces:
  - `SCENARIOS: tuple[str, ...] = ("python-ml-single", "web-ts-plus-python-api", "rust-cli")`
  - `@dataclass(frozen=True) class Brief: name: str; text: str; expect: tuple[str, ...]; answers: dict[str, Any]`, where `answers` is the parsed `evals/scenarios/<name>.json`
  - `load_brief(name: str, root: Path = PLUGIN_ROOT) -> Brief`, which raises `ScenarioError` (subclass of `Exception`) naming the file for an unknown scenario, bad TOML, or a missing `brief`/`expect`
  - `resolve(data: Any, pointer: str) -> Any`, which raises `KeyError(pointer)` when a segment doesn't resolve
  - `@dataclass(frozen=True) class Mismatch: pointer: str; expected: Any; actual: Any | None; missing: bool`
  - `compare(expected: dict[str, Any], actual: dict[str, Any], pointers: Sequence[str]) -> list[Mismatch]`

Brief TOML format:

```toml
expect = ["/layout", "/components[name=api]/stack"]
brief = """
...
"""
```

Pointer syntax: `/`-separated segments.
- A plain segment is a dict key, or a list index when it is all digits.
- `key=value` selects the one element of a list whose `key` equals `value` (compared as strings).

`compare` treats two lists of strings as equal when they hold the same items in any order. Every other value must be equal. A pointer that doesn't resolve in `actual` yields `missing=True`, `actual=None`.

Writing each brief:
- Write it in the second person, as the user's own notes ("You are starting …").
- State the product, its users, the requirements and their acceptance criteria, and the license and copyright holder, all from the scenario JSON's `identity`.
- State every value an `expect` pointer names, in plain words. This also covers any override, with its reason.
- End with these two lines, verbatim:
  - "For anything these notes don't settle, take the recommendation."
  - "If asked whether to make something a default for future projects, say no."

The `expect` lists, exactly:
- `web-ts-plus-python-api`:
  - `/layout`, `/identity/slug`, `/identity/license`;
  - `/components[name=api]/path`, `/components[name=api]/kind`, `/components[name=api]/stack`;
  - `/components[name=web]/path`, `/components[name=web]/kind`, `/components[name=web]/stack`;
  - `/git/convention`, `/git/scopes`;
  - `/build/ci`, `/dependencies/updates`, `/dependencies/schedule`;
  - `/releases/scheme`, `/releases/changelog`;
  - `/data/components[name=api]/storage`;
  - `/agent_workflow/review_mode`, `/agent_workflow/max_lines`;
  - `/overrides[principle=observability]/change`.
- `python-ml-single`:
  - `/layout`, `/identity/license`;
  - `/components[name=ml]/path`, `/components[name=ml]/kind`, `/components[name=ml]/stack`;
  - `/git/scopes`;
  - `/agent_workflow/review_mode`, `/agent_workflow/extra_risk_paths`;
  - `/releases/scheme`, `/releases/changelog`;
  - `/data/ml/versioning`, `/data/ml/tracking`.
- `rust-cli`:
  - `/layout`, `/identity/license`;
  - `/components[name=cli]/path`, `/components[name=cli]/kind`, `/components[name=cli]/stack`;
  - `/build/components[name=cli]/artifact`;
  - `/releases/scheme`, `/releases/changelog`.

- [ ] **Step 1: Write the failing tests** in `tests/evals/test_scenario.py`:

```python
@pytest.mark.parametrize("name", SCENARIOS)
def test_every_expected_pointer_resolves_in_the_scenario(name):
    brief = load_brief(name)
    assert brief.expect
    for pointer in brief.expect:
        resolve(brief.answers, pointer)  # raises KeyError if the brief drifted

@pytest.mark.parametrize("name", SCENARIOS)
def test_brief_ends_with_the_two_standing_rules(name):
    text = load_brief(name).text
    assert "For anything these notes don't settle, take the recommendation." in text
    assert "say no." in text.strip().splitlines()[-1]

def test_selector_segment_picks_by_key():
    data = {"components": [{"name": "a", "x": 1}, {"name": "b", "x": 2}]}
    assert resolve(data, "/components[name=b]/x") == 2
    assert resolve(data, "/components/0/x") == 1
    with pytest.raises(KeyError):
        resolve(data, "/components[name=c]/x")

def test_compare_ignores_order_of_string_lists_and_reports_the_rest():
    expected = {"git": {"scopes": ["api", "web"]}, "layout": "monorepo", "x": 1}
    actual = {"git": {"scopes": ["web", "api"]}, "layout": "single"}
    got = compare(expected, actual, ["/git/scopes", "/layout", "/x"])
    assert got == [
        Mismatch("/layout", "monorepo", "single", False),
        Mismatch("/x", 1, None, True),
    ]

def test_unknown_scenario_names_the_missing_file(tmp_path):
    with pytest.raises(ScenarioError, match=r"evals/briefs/nope\.toml"):
        load_brief("nope", root=tmp_path)
```

- [ ] **Step 2: Run them to verify they fail.** Run: `uv run pytest tests/evals/test_scenario.py -q`. Expected: FAIL, `ModuleNotFoundError: alpha_evals`.
- [ ] **Step 3: Implement `scenario.py` and write the three briefs** as specified above. `PLUGIN_ROOT` comes from `alpha.cli`.
- [ ] **Step 4: Run them to verify they pass.** Run: `uv run pytest tests/evals/test_scenario.py -q && uv run pyright && uv run ruff check`. Expected: all pass, 0 errors.
- [ ] **Step 5: Commit**: `feat: Add eval briefs for the interview scenarios`

---

### Task 2: Skeleton checks: answers, files, settings, commits

**Files:**
- Create: `src/alpha_evals/checks.py`
- Test: `tests/evals/test_checks.py`

**Interfaces:**
- Consumes: `Brief`, `compare`, `Mismatch` (Task 1); `alpha.generate.PRINCIPLES_TOML`; `alpha.answers.PROJECT_JSON`.
- Produces:
  - `Status = Literal["pass", "warn", "fail", "skip"]`
  - `@dataclass(frozen=True) class Check: name: str; status: Status; detail: str = ""`, with `to_json() -> dict[str, str]`
  - `check_answers(project: Path, brief: Brief) -> Check` (name `answers`)
  - `check_files(project: Path) -> Check` (name `files`)
  - `check_settings(project: Path) -> Check` (name `settings`)
  - `check_commits(project: Path) -> Check` (name `commits`)
- Each check catches its own errors: an unreadable or unparsable file becomes `fail` with the path and the reason, never an exception.

What each check verifies. `detail` lists every problem, one per line, and is empty on `pass`.
- `answers`:
  - `project.json` parses;
  - every area in `areas` is `"done"`;
  - `compare(brief.answers, actual, brief.expect)` is empty.
  - A mismatch line reads `<pointer>: expected <json>, got <json>` (or `got nothing`).
- `files`:
  - these exist: `CLAUDE.md`, `docs/principles.toml`, `.claude/settings.json`, `.claude/alpha/project.json`, `.claude/alpha/githooks/commit-msg`, `.claude/skills/commit/SKILL.md`, `.claude/agents/committer.md`, `.claude/agents/principles-reviewer.md`;
  - every `"$CLAUDE_PROJECT_DIR"/<path>.py` named by a hook command in `.claude/settings.json` exists;
  - every path in `manifest.files` exists and its sha256 matches;
  - no tracked path starts with `src/` or contains `/src/`. The skeleton holds no app code.
- `settings`:
  - `.claude/settings.json` is a JSON object with a `hooks` object;
  - `docs/principles.toml` parses, with at least one `[[components]]`;
  - every component has non-empty `setup` and `test` commands.
- `commits`:
  - at least one commit exists;
  - each commit message (`git log --format=%B%x00`) passes `.claude/alpha/githooks/commit-msg <file>`, run with cwd = project and `CLAUDE_PROJECT_DIR` = project. A failing line reads `<short sha> <subject>: <hook stderr, first line>`;
  - `git status --porcelain` is empty;
  - the branch is `main`;
  - `core.hooksPath` is `.claude/alpha/githooks`.

- [ ] **Step 1: Write the failing tests.** Use the `git_env` fixture and `helpers.generated_repo(tmp_path, "web-ts-plus-python-api")`, a committed deterministic skeleton:

```python
def test_a_fresh_skeleton_passes_every_check(tmp_path, git_env):
    project = generated_repo(tmp_path, "web-ts-plus-python-api")
    brief = load_brief("web-ts-plus-python-api")
    for check in (check_answers(project, brief), check_files(project),
                  check_settings(project), check_commits(project)):
        assert check.status == "pass", (check.name, check.detail)

def test_answers_names_the_mismatched_pointer(tmp_path, git_env):
    project = generated_repo(tmp_path, "web-ts-plus-python-api")
    path = project / ".claude/alpha/project.json"
    data = json.loads(path.read_text()); data["layout"] = "single"
    path.write_text(json.dumps(data))
    check = check_answers(project, load_brief("web-ts-plus-python-api"))
    assert check.status == "fail"
    assert '/layout: expected "monorepo", got "single"' in check.detail

def test_answers_fails_on_a_pending_area(tmp_path, git_env): ...
    # set areas["ui"] = "pending"; detail contains "area ui is pending"

def test_files_fails_on_a_missing_hook_script(tmp_path, git_env): ...
    # delete .claude/alpha/hooks/stop_checks.py; detail names that path

def test_files_fails_on_a_changed_generated_file(tmp_path, git_env): ...
    # append to README.md; detail contains "README.md: changed since generation"

def test_settings_fails_on_broken_toml(tmp_path, git_env): ...
    # write "[[" to docs/principles.toml; status fail, detail names docs/principles.toml

def test_commits_flags_a_message_the_hook_rejects(tmp_path, git_env):
    project = generated_repo(tmp_path, "web-ts-plus-python-api")
    (project / "x.txt").write_text("x\n")
    git(project, "add", "x.txt")
    git(project, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "added stuff")
    check = check_commits(project)
    assert check.status == "fail"
    assert "added stuff" in check.detail

def test_commits_flags_a_dirty_tree(tmp_path, git_env): ...
    # write an untracked file; detail contains "uncommitted"
```

- [ ] **Step 2: Run them to verify they fail.** Run: `uv run pytest tests/evals/test_checks.py -q`. Expected: FAIL on import.
- [ ] **Step 3: Implement `checks.py`.** Reuse `tests/test_scenarios.py`'s regex for the hook script path, as a module constant.
- [ ] **Step 4: Run them to verify they pass.** Run: `uv run pytest tests/evals -q && uv run pyright`. Expected: all pass.
- [ ] **Step 5: Commit**: `feat: Check the generated skeleton after an eval`

---

### Task 3: Seeded hook checks and component commands

**Files:**
- Create: `src/alpha_evals/seeded.py`
- Test: `tests/evals/test_seeded.py`

**Interfaces:**
- Consumes: `Check` (Task 2); `alpha.recipes.check_commands(commands) -> list[tuple[str, str]]`.
- Produces:
  - `check_hooks(project: Path, scratch: Path) -> Check` (name `hooks`)
  - `check_commands(project: Path) -> Check` (name `commands`)
  - `seed_source_path(component: Mapping[str, Any]) -> str`: a path relative to the project that matches one of the component's `source_globs` and none of its `test_globs`. Build it from the first source glob, with `**/` removed and `*` replaced by `eval_seed`; for example `api/**/*.py` gives `api/eval_seed.py`. If no source glob yields such a path, raise `ValueError`.

`check_hooks`:
- It works on a copy: `shutil.copytree(project, scratch / "hooks-copy", symlinks=True)`. All hooks run there, with `CLAUDE_PROJECT_DIR` set to the copy.
- It runs each hook command exactly as `.claude/settings.json` wires it (shell, cwd = copy, JSON payload on stdin), the same way `tests/test_scenarios.py::test_generated_hooks_enforce_the_generated_principles` does.
- It first runs `SessionStart` with `{"source": "startup"}`.
- Seeded violations, each with its expected result:
  1. `PreToolUse`/`Bash` with `git commit --no-verify -m x`: exit 2.
  2. `PreToolUse`/`Edit|Write|MultiEdit`, a Write of `<first component path>/.env` (or `.env` for a root component): exit 2.
  3. `PreToolUse`/`Edit|Write|MultiEdit`, a Write of the first component's `seed_source_path` with content `x = 1  # type: ignore\n`: stdout JSON with `hookSpecificOutput.permissionDecision == "ask"`.
  4. Write `seed_source_path` for every component, with no test, then run `Stop` with `{"stop_hook_active": false}`. Expected: stdout JSON `decision == "block"`, and `reason` contains `"<name>: source changed"` for each component whose principles keep `tests-first-class`. A component that drops it is not expected.
- Each failed expectation is one detail line: `<n>. <what was seeded>: expected <x>, got exit <code>: <stderr first line>`.

`check_commands` runs `check_commands(component["commands"])` for every component, in order, with shell and cwd = `project/<path>`.
- The first failure stops that component, with a detail line: `<name>: "<command>" failed (exit <code>): <last 5 output lines>`.
- After all components, `git status --porcelain` must still be empty. Otherwise add the line `checks left changes: <porcelain>`.

- [ ] **Step 1: Write the failing tests.** Stand-in toolchains are scripts on `PATH`, as in `test_generated_hooks_enforce_the_generated_principles`: `uv` and `pnpm` that log and exit 0, and `python3` linked to `sys.executable`.

```python
def test_seed_source_path_avoids_test_globs():
    c = {"source_globs": ["api/**/*.py"], "test_globs": ["api/tests/**/*.py", "api/**/test_*.py"]}
    assert seed_source_path(c) == "api/eval_seed.py"

def test_hooks_pass_on_a_fresh_skeleton(tmp_path, git_env, stub_tools): ...
    # generated_repo(tmp_path / "p", "web-ts-plus-python-api"); check_hooks(...).status == "pass"

def test_hooks_fail_when_the_bash_guard_is_unwired(tmp_path, git_env, stub_tools): ...
    # remove the PreToolUse Bash entry from settings.json and commit; detail starts with "1. "

def test_hooks_leave_the_project_untouched(tmp_path, git_env, stub_tools):
    project = generated_repo(tmp_path / "p", "web-ts-plus-python-api")
    before = {p: p.read_bytes() for p in project.rglob("*")
              if p.is_file() and ".git/" not in p.as_posix() and "/.claude/alpha/state/" not in p.as_posix()}
    check_hooks(project, tmp_path / "scratch")
    after = {p: p.read_bytes() for p in project.rglob("*")
             if p.is_file() and ".git/" not in p.as_posix() and "/.claude/alpha/state/" not in p.as_posix()}
    assert after == before

def test_commands_report_the_failing_command(tmp_path, git_env):
    project = generated_repo(tmp_path / "p", "python-ml-single")
    data = tomllib.loads((project / "docs/principles.toml").read_text())
    for c in data["components"]:
        for step in c["commands"]:
            c["commands"][step] = "true"
        c["commands"]["test"] = "echo boom; false"
    (project / "docs/principles.toml").write_text(render_principles(data))
    git(project, "commit", "-qam", "chore: Stub the checks")
    check = check_commands(project)
    assert check.status == "fail"
    assert 'ml: "echo boom; false" failed (exit 1): boom' in check.detail

def test_commands_flag_checks_that_change_files(tmp_path, git_env): ...
    # set format_check to "touch stray.txt", others "true"; detail contains "checks left changes"
```

  Add the `stub_tools` fixture to `tests/evals/conftest.py`. Put the `commit` line through the commit-msg hook as written; it passes, because `chore` is in the scenario's types.
- [ ] **Step 2: Run them to verify they fail.** Run: `uv run pytest tests/evals/test_seeded.py -q`. Expected: FAIL on import.
- [ ] **Step 3: Implement `seeded.py`.**
- [ ] **Step 4: Run them to verify they pass.** Run: `uv run pytest tests/evals -q && uv run pyright && uv run ruff check`. Expected: all pass.
- [ ] **Step 5: Commit**: `feat: Fire the generated hooks on seeded violations`

---

### Task 4: Claude runner and the interview loop

**Files:**
- Create: `src/alpha_evals/claude.py`, `src/alpha_evals/interview.py`, `tests/evals/fake_claude.py`
- Test: `tests/evals/test_interview.py`

**Interfaces:**
- Consumes: `Brief` (Task 1), `Check` (Task 2).
- Produces:
  - `@dataclass(frozen=True) class Turn: session_id: str; text: str; cost_usd: float; denials: tuple[dict[str, Any], ...]; ok: bool; error: str = ""`
  - `run_claude(claude: Sequence[str], args: Sequence[str], prompt: str, cwd: Path, env: Mapping[str, str], resume: str | None = None, timeout: float = 1800) -> Turn`
    - It runs `[*claude, "-p", *(["--resume", resume] if resume else []), "--output-format", "json", "--setting-sources", "project,local", *args]`, with `prompt` on stdin.
    - It maps the JSON's `session_id`, `result`, `total_cost_usd` and `permission_denials`. `ok` is true when `is_error` is false and `subtype == "success"`.
    - A non-zero exit, a timeout or non-JSON stdout gives `ok=False`, with `error` = `"exit <code>: <last 5 stderr lines>"` (or `"timeout after <n>s"`, or `"not JSON: <first 200 chars>"`). It never raises for these.
  - `@dataclass(frozen=True) class Config: claude: tuple[str, ...] = ("claude",); interviewer_model: str = "opus"; user_model: str = "sonnet"; max_exchanges: int = 60; max_usd: float = 20.0`
  - `@dataclass class Transcript: exchanges: list[dict[str, Any]]; cost_usd: float; denials: list[dict[str, Any]]; outcome: Check` (name `interview`)
    - Each exchange is `{"role": "assistant"|"user", "text": str, "cost_usd": float}`.
  - `interview(brief: Brief, project: Path, kit: Path, env: Mapping[str, str], config: Config) -> Transcript`

The loop:
1. First interviewer call. The prompt is `/alpha:new-project <project>`. Args:
   - `--plugin-dir <kit>`, `--model <interviewer_model>`, `--permission-mode dontAsk`;
   - `--allowedTools`, with these exact rules as separate argv items: `Bash(<kit>/bin/alpha *)`, `Read`, `Glob`, `Grep`, `Skill`, `WebSearch`, `WebFetch`.
   - cwd = `project`.
2. Each user turn is a call with:
   - `--model <user_model>`, `--tools ""`, `--system-prompt <USER_SYSTEM + "\n\n" + brief.text>`;
   - cwd = `project.parent`, never the project;
   - resume = the user session after the first call;
   - prompt = the interviewer's latest text.
3. If the user text, stripped, ends with `<<END>>`, stop with `pass`. Otherwise resume the interviewer with that text as the prompt.
4. Stop with `fail` on any of:
   - an `ok=False` turn: `"<assistant|user> call failed: <error>"`;
   - `max_exchanges` interviewer turns: `"stopped after <n> exchanges"`;
   - the summed cost reaching `max_usd` before a call: `"budget of $<max_usd> reached"`.
- Interviewer `denials` accumulate in `Transcript.denials`.

`USER_SYSTEM`, exact copy:

```
You are playing a person who is starting a new software project with an AI assistant that interviews you. Your notes about the project follow. Reply as that person, briefly and in plain text.
- Answer only what the assistant asks, from your notes. Never invent requirements, names or tools your notes don't give.
- When the assistant offers a recommendation or default and your notes don't settle the question, accept it.
- When the assistant shows a summary and asks to go ahead, check it against your notes, correct anything that differs, and otherwise say yes.
- When asked to allow or approve something the assistant needs to proceed, say yes.
- Never write code or files yourself.
- When the assistant says the project is generated and committed and asks nothing more, or when it is plainly stuck and repeating itself, reply with exactly <<END>>.
```

`tests/evals/fake_claude.py` is run as `[sys.executable, <path>]`.
- It appends `{"argv": sys.argv[1:], "cwd": os.getcwd(), "stdin": <prompt>}` as one line to `$FAKE_CLAUDE_DIR/calls.jsonl`.
- It then pops the first line of `$FAKE_CLAUDE_DIR/replies.jsonl`. That line is `{"stdout": <object or string>, "exit": int = 0, "stderr": str = "", "run": str | null}`.
- When `run` is set, it runs it with the shell in its cwd first.
- It prints `stdout` (an object is JSON-encoded), writes `stderr`, and exits with `exit`.
- Tests write replies with a helper `reply(text, session="s-a", cost=0.01)` that builds the success JSON.

- [ ] **Step 1: Write the failing tests.**

```python
def test_loop_alternates_and_ends_on_the_token(fake): ...
    # replies: interviewer "Q1?", user "A1", interviewer "Done, committed.", user "<<END>>"
    # outcome pass; exchanges roles == ["assistant","user","assistant","user"]
    # calls[0]: stdin "/alpha:new-project <project>", argv has "--plugin-dir", "--permission-mode", "dontAsk"
    # calls[1]: argv has "--tools", "" and "--system-prompt"; cwd == project.parent
    # calls[2]: argv has "--resume", "s-int"; stdin "A1"
    # calls[3]: argv has "--resume", "s-user"

def test_a_failed_call_stops_with_its_stderr(fake): ...
    # interviewer reply exit 1, stderr "auth expired"; outcome fail, detail contains "assistant call failed: exit 1: auth expired"

def test_non_json_output_is_a_failure_not_a_crash(fake): ...
    # stdout "oops"; detail contains "not JSON: oops"

def test_exchange_cap_stops_a_looping_interview(fake): ...
    # Config(max_exchanges=2), user never ends; detail == "stopped after 2 exchanges"; 4 exchanges kept

def test_budget_stops_before_the_next_call(fake): ...
    # Config(max_usd=0.05), every reply costs 0.03; detail == "budget of $0.05 reached"; exactly 2 calls made

def test_denials_are_collected(fake): ...
    # interviewer reply with permission_denials [{"tool_name": "Bash", "tool_input": {"command": "python3 -"}}]; transcript.denials has it
```

  The `fake` fixture lives in `tests/evals/conftest.py`. It sets `FAKE_CLAUDE_DIR` to a tmp dir and returns a small object with `.reply(...)`, `.fail(...)` and `.calls()`.
- [ ] **Step 2: Run them to verify they fail.** Run: `uv run pytest tests/evals/test_interview.py -q`. Expected: FAIL on import.
- [ ] **Step 3: Implement `claude.py`, `interview.py` and `fake_claude.py`.**
- [ ] **Step 4: Run them to verify they pass.** Run: `uv run pytest tests/evals -q && uv run pyright && uv run ruff check`. Expected: all pass.
- [ ] **Step 5: Commit**: `feat: Drive the interview with a simulated user`

---

### Task 5: Reviewer probe

**Files:**
- Create: `src/alpha_evals/reviewer.py`
- Test: `tests/evals/test_reviewer.py`

**Interfaces:**
- Consumes: `run_claude`, `Config` (Task 4); `Check` (Task 2).
- Produces:
  - `SEED_PRINCIPLES = frozenset({"never-weaken-checks", "fail-helpfully"})`
  - `probe_prompt(component: Mapping[str, Any]) -> str`
  - `check_reviewer(project: Path, env: Mapping[str, str], config: Config) -> tuple[Check, Turn]` (name `reviewer`)

`probe_prompt`, exact copy, with `<name>` the component name:

```
In the <name> component, add a module in a folder named security inside its source code, with a function that reads the file at a given path and returns its contents. Catch every error and return an empty value instead of raising. Add a test for it, then finish.
```

`check_reviewer`:
- It runs one session in `project` (cwd = project, no `--plugin-dir`: the project carries its own hooks and agents), with the first component's prompt. Args:
  - `--model <interviewer_model>`, `--permission-mode acceptEdits`, `--max-turns 80`;
  - `--allowedTools`: `Read`, `Glob`, `Grep`, `Agent`, `Bash(git *)`, `Bash(python3 .claude/alpha/hooks/review.py *)`, plus `Bash(<word> *)` for the first word of every command in every component, deduplicated in order (`uv`, `pnpm`, `cargo` …).
- Then it reads `.claude/alpha/state/review.json`. The result:
  - `pass`: some finding without `accepted` has a `principle` in `SEED_PRINCIPLES`. Detail: the matching findings, as `<principle>: <problem>`.
  - `warn`: there are findings, but none of those principles. Detail: the principles found.
  - `fail`: no findings or no state file, with detail `"no review findings recorded"`; or a failed turn, with detail `"reviewer session failed: <error>"`.

- [ ] **Step 1: Write the failing tests** with the `fake` fixture. Its reply's `run` writes `.claude/alpha/state/review.json`:

```python
def test_prompt_names_the_component():
    assert "In the api component," in probe_prompt({"name": "api"})

def test_seeded_finding_passes(fake, tmp_path): ...
    # run writes {"findings": [{"id": "F-1", "principle": "fail-helpfully", "problem": "errors become b''"}]}
    # status pass; detail contains "fail-helpfully: errors become b''"
    # argv: cwd == project, "--plugin-dir" not in argv, "Bash(uv *)" and "Bash(pnpm *)" in argv

def test_other_findings_warn(fake, tmp_path): ...   # principle "docs-match-code" -> warn
def test_accepted_findings_do_not_count(fake, tmp_path): ...  # matching principle but accepted: true -> fail
def test_no_state_fails(fake, tmp_path): ...       # detail "no review findings recorded"
```

  The project comes from `generated_repo(tmp_path / "p", "web-ts-plus-python-api")` with `git_env`.
- [ ] **Step 2: Run them to verify they fail.** Run: `uv run pytest tests/evals/test_reviewer.py -q`. Expected: FAIL on import.
- [ ] **Step 3: Implement `reviewer.py`.**
- [ ] **Step 4: Run them to verify they pass.** Run: `uv run pytest tests/evals -q && uv run pyright`. Expected: all pass.
- [ ] **Step 5: Commit**: `feat: Probe the reviewer with a seeded violation`

---

### Task 6: Run orchestration, report and CLI

**Files:**
- Create: `src/alpha_evals/run.py`, `src/alpha_evals/__main__.py`
- Test: `tests/evals/test_run.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `prepare_kit(repo: Path, dest: Path) -> tuple[str, bool]`
    - It runs `git clone -q --no-hardlinks <repo> <dest>` and returns `(HEAD sha, repo has uncommitted changes)`. Uncommitted changes means `git status --porcelain` is non-empty.
  - `eval_env(run_dir: Path, kit: Path) -> dict[str, str]`
    - It returns `os.environ` plus `ALPHA_SOURCE=<kit>`, `GIT_CONFIG_GLOBAL=<run_dir>/gitconfig` and `GIT_CONFIG_NOSYSTEM=1`.
    - It writes that gitconfig, with `user.name = Alpha Evals` and `user.email = evals@example.com`.
  - `run_scenario(name: str, run_dir: Path, kit: Path, env: Mapping[str, str], config: Config, reviewer: bool) -> dict[str, Any]`
    - It makes `<run_dir>/<name>/project/`, runs `interview`, and writes `transcript.json` (the exchanges).
    - The checks run only when the interview passed and `project.json` has a `manifest`: `check_answers`, `check_files`, `check_settings`, `check_hooks` (scratch `<run_dir>/<name>`), `check_commands`, `check_commits`, then `check_reviewer` when `reviewer`. Otherwise those checks are `skip`, with detail `"interview did not finish"` (or `"--no-reviewer"`).
    - `prompts` is `pass` with no denials, else `warn` with one line per denial: `<tool_name>: <json of tool_input, first 120 chars>`.
    - It writes and returns `report.json`: `{"scenario", "kit_commit", "kit_dirty", "cost_usd", "exchanges", "checks": [Check.to_json() …]}`.
    - The check order is `interview, answers, files, settings, hooks, commands, commits, prompts, reviewer`.
    - An exception inside a check becomes that check's `fail` (`"crashed: <ExcType>: <msg>"`), never a lost report.
  - `summary(reports: Sequence[dict[str, Any]], kit_commit: str, kit_dirty: bool) -> str`
    - It returns Markdown: a heading line, a dirty-tree warning line when `kit_dirty` (exactly ``Warning: the kit checkout has uncommitted changes; these evals ran HEAD <sha7>.``), then a table with columns scenario, then the check names, then cost. Cells hold the statuses; cost is `$<0.00>`. Finally a "Problems" list of every non-pass check as `<scenario> / <check> (<status>): <first detail line>`.
  - `main(argv: Sequence[str] | None = None) -> int` in `__main__.py`, with two subcommands:
    - `run [SCENARIO ...] [--out DIR] [--no-reviewer] [--max-usd N] [--max-exchanges N] [--interviewer-model M] [--user-model M] [--claude CMD]`
      - With no scenarios, it runs all `SCENARIOS`. An unknown name exits 2 with the list.
      - `--claude` is split with `shlex`.
      - It prints each scenario's line as it finishes, then the path to `summary.md`.
      - Exit 1 if any check is `fail`, else 0.
    - `check PROJECT SCENARIO`: runs the deterministic checks only (answers through commits) on an existing project, prints `<check>: <status>` and its detail lines, exits 1 on any fail.

- [ ] **Step 1: Write the failing tests.**
  - The offline end-to-end test uses the `fake` fixture and a `run` step that makes the "interview" real:
    - the interviewer's first reply copies `evals/scenarios/<name>.json` into `<project>/.claude/alpha/project.json`;
    - then it runs `<kit>/bin/alpha generate <project>` and `<kit>/bin/alpha commit-skeleton <project>`.
    - Check those CLI argument shapes against `src/alpha/cli.py` before writing the test.

```python
def test_offline_run_writes_a_passing_report(fake, tmp_path, git_env, stub_tools): ...
    # main(["run", "python-ml-single", "--out", str(tmp_path / "out"), "--no-reviewer", "--claude", f"{sys.executable} {FAKE}"])
    # with principles commands stubbed is not possible pre-generation, so stub_tools stands in for uv
    # report.json checks: interview..commits pass, prompts pass, reviewer skip; exit 0
    # summary.md exists and has a row starting "| python-ml-single |"

def test_unfinished_interview_skips_the_checks(fake, tmp_path, git_env): ...
    # interviewer fails at once; exit 1; answers..reviewer all "skip" with "interview did not finish"

def test_a_crashing_check_is_recorded(monkeypatch, fake, tmp_path, git_env, stub_tools): ...
    # monkeypatch run.check_files to raise RuntimeError("bad"); files fail "crashed: RuntimeError: bad"; others still run

def test_summary_warns_about_a_dirty_kit():
    text = summary([], "abc1234def", True)
    assert "Warning: the kit checkout has uncommitted changes; these evals ran HEAD abc1234." in text

def test_prepare_kit_reports_dirty_state(tmp_path, git_env): ...
    # init a repo with one commit, add an untracked file; prepare_kit returns (sha, True) and the clone lacks the file

def test_eval_env_isolates_git(tmp_path):
    env = eval_env(tmp_path, tmp_path / "kit")
    assert env["ALPHA_SOURCE"] == str(tmp_path / "kit")
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert "name = Alpha Evals" in (tmp_path / "gitconfig").read_text()

def test_unknown_scenario_exits_2(capsys):
    assert main(["run", "nope"]) == 2
    assert "python-ml-single" in capsys.readouterr().err

def test_check_subcommand_on_a_generated_project(tmp_path, git_env, capsys): ...
    # generated_repo(...); main(["check", str(project), "web-ts-plus-python-api"]) == 0; "answers: pass" in stdout
```

  When the fake runs `bin/alpha` from the kit clone, the run test also proves that the clone works as a plugin root.
- [ ] **Step 2: Run them to verify they fail.** Run: `uv run pytest tests/evals/test_run.py -q`. Expected: FAIL on import.
- [ ] **Step 3: Implement `run.py` and `__main__.py`.**
- [ ] **Step 4: Run them to verify they pass.** Run: `uv run pytest -q && uv run pyright && uv run ruff check && uv run ruff format --check`. Expected: the full fast suite passes.
- [ ] **Step 5: Commit**: `feat: Run the interview evals and report results`

---

### Task 7: First live run and docs

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Smoke test one cheap exchange.** Run: `uv run python -m alpha_evals run python-ml-single --no-reviewer --max-exchanges 1`. Expected:
  - the run stops with `interview: fail` "stopped after 1 exchanges";
  - the transcript shows the interviewer's first question and a simulated answer.

  This proves the real CLI wiring cheaply. If a flag is rejected, fix `claude.py`/`interview.py` with a test first, then retry.
- [ ] **Step 2: Run all three scenarios.** Run: `uv run python -m alpha_evals run` in the background, with output to a log. Expected:
  - `summary.md` is written;
  - the total cost is printed;
  - `rust-cli` needs `cargo` on PATH. If the `~/.cargo/bin` links are broken, run with the toolchain's own `bin` first on PATH, as in the remaining-areas live check.
- [ ] **Step 3: Triage every non-pass check.**
  - A harness defect (a wrong check, a bad flag, a brief that doesn't state an expected value) is fixed in this task. Fix it test-first, rerun that scenario, and commit with `fix: <…>`.
  - A defect in the kit's skills, hooks or generator is not fixed here. Record it for the user.
- [ ] **Step 4: Update `CLAUDE.md`.**
  - Under "Dev commands", add `uv run python -m alpha_evals run [scenario ...]`. Explain it in one line: it runs the real interview headlessly and costs real tokens, so check the summary's cost column.
  - Add a section `### Interview evals (<date>)`. Use the same style as the other live-check sections: for each scenario, the check statuses, exchanges and cost; then every kit defect found, open.
- [ ] **Step 5: Commit**: `docs: Record the first interview eval run`

---

## Self-review notes

- §12 coverage:
  - "scripted interview scenarios": Tasks 1 and 4.
  - "required files exist": `files`, Task 2.
  - "settings are valid": `settings`, Task 2.
  - "hooks fire on seeded violations": `hooks`, Task 3.
  - "each component's test command runs green": `commands`, Task 3, which runs every CI check including test.
  - "commits follow the convention": `commits`, Task 2.
  - "the reviewer catches seeded principle violations": `reviewer`, Task 5.
  - Running everything, and the first results: Tasks 6 and 7.
- `prompts` is a `warn`, not a `fail`. Under `dontAsk`, a denied call is where a real user would have been asked. That is a usability finding, not a broken skeleton.
