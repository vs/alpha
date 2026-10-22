# Alpha Rules In Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In a generated project, every agent (main session and subagents, after compaction too) works with the project's principles and decision records in view, records new decisions the same way the interview did, and can't slip past the mechanical checks through a subagent or a shell command.

**Architecture:** CLAUDE.md gains short working rules. The SessionStart hook and a new SubagentStart hook inject a live index of decision records and the principle overrides in effect, built from `docs/decisions/` and `docs/principles.toml` each time, so it never goes stale. A `decision` skill copied into the project writes new records in the interview's format. The post-edit hook records which files each subagent edits, and `stop_checks.py` runs on SubagentStop over that subagent's files. `guard_bash.py` blocks shell writes to protected paths.

**Tech Stack:** Python stdlib hooks (3.9-parseable, 3.11 runtime), Claude Code hooks (SessionStart, SubagentStart, PostToolUse, SubagentStop, PreToolUse), pytest, ruff, pyright.

**Spec:** `docs/superpowers/specs/2026-10-19-project-kit-design.md` (§2 anti-goals, §4 decisions "recorded as they're made… and for each decision made later in the project's life", §6 "Ask when ambiguous… record the answer in the decision log", §7, §8)

**Plan series:** inserted after 2b, before plan 3 (reviewer). 2c–2e and plan 4 follow plan 3.

## Global Constraints

- Hooks stay stdlib-only, parse on Python 3.9 (`from __future__ import annotations`, no `X | Y` at runtime), follow `_common.py` conventions, and fail helpfully; a hook problem never bricks a session (exit 0 with a message).
- Facts verified in the Claude Code docs (2026-10-23): SessionStart fires with `source` in `startup`, `resume`, `clear`, `compact`; SessionStart and SubagentStart accept `hookSpecificOutput.additionalContext`; SubagentStop accepts the Stop output (`decision: "block"` + `reason`), receives `agent_id`, `agent_type`, `stop_hook_active`; PreToolUse/PostToolUse inside a subagent receive `agent_id` and `agent_type`; subagents load CLAUDE.md except the built-in Explore and Plan agents; Claude Code caps consecutive Stop/SubagentStop continuations at 8.
- The injected context stays short: at most 40 decision lines (the most recent ones, plus "N older records in docs/decisions/"), then the overrides.
- Decision record format, as the interview writes it (`render/docs.py` `_decision`): file `docs/decisions/NNNN-<slug>.md`; `# NNNN. <Title>`, `Date: YYYY-MM-DD`, `Status: accepted` (or `superseded by NNNN`), optional extra header lines, then `## Context`, `## Decision`, `## Consequences`.
- Nothing kit-specific at the root; new files live under `.claude/`.

## Review Focus

1. **A project with many decision records** (60+). The injected index must stay within the cap and say where the rest are. (Test in Task 3.)
2. **A malformed or hand-renamed decision file** (no `# NNNN.` heading, no Status). The index skips it with a one-line warning instead of crashing or hiding the others. (Test in Task 3.)
3. **A read-only subagent** (Explore, a researcher) stopping while the main agent has failing work in progress. SubagentStop must not block it: it judges only files that subagent edited. (Test in Task 4.)
4. **Shell writes that look like writes but aren't** (`cat docs/x > /dev/null`, `grep '>' file`, a `>` inside quotes). No false block. (Test in Task 5.)
5. **Superseded decisions.** The index shows a superseded record as superseded, so agents follow the newer one. (Test in Task 3.)

---

## File Structure

```
src/alpha/render/docs.py                 CLAUDE.md working rules; overridden principles name their record
project-files/skills/decision/SKILL.md   NEW: record a decision in the project's log
project-files/hooks/_common.py           + decision_index(root), overrides_in_effect(principles), context_text(...)
project-files/hooks/session_start.py     always injects the index (plus any warnings)
project-files/hooks/subagent_start.py    NEW: injects the same index into subagents
project-files/hooks/post_edit.py         records files edited by each subagent
project-files/hooks/stop_checks.py       SubagentStop mode over the subagent's own files
project-files/hooks/guard_bash.py        blocks shell writes to protected paths
src/alpha/render/claude_settings.py      wires SubagentStart and SubagentStop
src/alpha/generate.py                    copies the decision skill
```

---

### Task 1: CLAUDE.md working rules

**Files:** Modify `src/alpha/render/docs.py`. Test: `tests/test_render_docs.py`.

**Interfaces:** `_claude_md` gains a `## Working rules` section right after `## Principles` (and its source-of-truth line), and each principle with an override gets ` (overridden: see <record path>)` after its statement.

Exact rules text:

```
## Working rules

- Before you change code, docs or config, read the decision records in docs/decisions/ that bear on the change (an index is added to your context at the start of each session) and the principle's parameters in docs/principles.toml. Follow them.
- A change that contradicts an accepted decision needs a new decision that supersedes it. Ask the user first, then record it with the decision skill.
- When a requirement is ambiguous, ask the user, then record the answer with the decision skill.
- Subagents work under the same principles, decisions and checks.
```

- [ ] **Step 1: Write failing tests**: `test_claude_md_has_working_rules` (the four bullets, between `## Principles` and `## Commands`) and `test_overridden_principle_names_its_record` (fixture: the Observability line ends with `(overridden: see docs/decisions/<NNNN>-override-observability.md)`, the number from `helpers.override_record`).
- [ ] **Step 2: Run** `uv run pytest tests/test_render_docs.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** Keep CLAUDE.md under 150 lines (`test_claude_md_two_components_under_limit`).
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: Tell agents to follow decisions and principles`

---

### Task 2: Decision skill in generated projects

**Files:** Create `project-files/skills/decision/SKILL.md`. Modify `src/alpha/generate.py` (`_copies`). Test: `tests/test_generate.py`, `tests/test_project_skills.py` (new).

**Interfaces:** `.claude/skills/decision/SKILL.md` in every generated project. Frontmatter: `name: decision`, a description that triggers when the user settles a question, an ambiguity is resolved, a principle is loosened, or a decision record must change; no `allowed-tools` (it writes one Markdown file). Body, in order:
1. Find the next number: the highest `NNNN` in `docs/decisions/` plus one, four digits.
2. Write `docs/decisions/NNNN-<slug>.md` (slug: lowercase words joined by `-`) in the exact format of Global Constraints, `Date:` today, `Status: accepted`.
3. When it replaces an earlier record, add `Supersedes: NNNN` under Status, and change the earlier record's `Status:` line to `superseded by NNNN` (the only edit ever made to an old record).
4. Loosening or dropping a principle also needs `docs/principles.toml` updated (the principle's `active`, `components` or `params`, and `override_decision` set to the new record's path); editing that file asks the user, which is intended.
5. Commit the record with the change it explains, per the commit convention.

- [ ] **Step 1: Write failing tests**: `test_copies_the_decision_skill` (generated file list includes `.claude/skills/decision/SKILL.md`); `test_decision_skill_states_the_record_format` (the skill text contains `# NNNN. `, `Status: accepted`, `superseded by NNNN`, `## Context`, `## Decision`, `## Consequences`, and stays ≤ 120 lines); `test_decision_skill_matches_the_interview_format` (render one decision with `render.docs._decision` and assert each header line the skill names appears in it, so the two can't drift).
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Write** the skill and add it to `_copies`. It lands in the `chore:` commit with the rest of `.claude/`.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS (update `test_scenario_skeleton`'s file list if it enumerates `.claude/skills`).
- [ ] **Step 5: Commit** `feat: Add a decision skill to generated projects`

---

### Task 3: Decision index injected at session and subagent start

**Files:** Modify `project-files/hooks/_common.py`, `project-files/hooks/session_start.py`, `src/alpha/render/claude_settings.py`. Create `project-files/hooks/subagent_start.py`. Test: `tests/hooks/test_decision_index.py` (new), `tests/hooks/test_session_start.py`, `tests/test_claude_settings.py`.

**Interfaces** (in `_common.py`):
- `DecisionRecord` as a plain tuple `(number: int, title: str, status: str, path: str)`.
- `decision_index(root: Path) -> tuple[list[tuple[int, str, str, str]], list[str]]`: records sorted by number, and warnings for files under `docs/decisions/` named `*.md` whose first line isn't `# NNNN. Title` or that lack a `Status:` line (`docs/decisions/x.md: no "# NNNN. Title" heading; fix it or rename it`).
- `overrides_in_effect(principles: dict) -> list[str]`: one line per principle with a non-empty `override_decision`: `<id>: <active/inactive>, components <list> (<record path>)`.
- `context_text(root: Path, principles: dict) -> str`: `alpha: decisions in effect (read the ones that bear on your change before changing anything):` then up to 40 lines `- NNNN <title> [<status>] <path>` (the newest 40 when there are more, followed by `- … N older records in docs/decisions/`), then, when any, `Principle overrides:` and those lines, then the warnings.
- `session_start.py`: always prints `additionalContext` = `context_text(...)` plus any existing warnings (so far it printed only on warnings).
- `subagent_start.py`: SubagentStart hook printing `{"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": context_text(...)}}`; exits 0 silently outside an alpha project or on old Python.
- `render_settings` adds `"SubagentStart": [entry(subagent_start.py)]`.

- [ ] **Step 1: Write failing tests**

```python
def test_index_lists_records_with_status(project): ...           # fixture project: numbers 1..N in order, titles, "accepted"
def test_superseded_record_shows_its_status(project): ...         # edit 0003 Status → "superseded by 0012" → "[superseded by 0012]"
def test_malformed_record_is_skipped_with_a_warning(project): ... # docs/decisions/notes.md without heading → warning names it; others still listed
def test_index_caps_at_40_lines(project): ...                     # write 60 records → 40 lines + "… 20 older records"
def test_overrides_in_effect(project): ...                         # observability override line with its record path
def test_session_start_always_injects_the_index(project): ...      # no warnings → additionalContext starts with "alpha: decisions in effect"
def test_subagent_start_injects_the_same_index(project): ...
def test_settings_wire_subagent_start(): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/hooks/test_decision_index.py tests/hooks/test_session_start.py tests/test_claude_settings.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** Add `subagent_start.py` to the 3.9-parse test list automatically (it globs `*.py`).
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hooks): Inject the decision index into every session`

---

### Task 4: Stop checks for subagents

**Files:** Modify `project-files/hooks/post_edit.py`, `project-files/hooks/stop_checks.py`, `src/alpha/render/claude_settings.py`. Test: `tests/hooks/test_stop_checks.py`, `tests/hooks/test_post_edit.py`, `tests/test_claude_settings.py`.

**Interfaces:**
- `post_edit.py`: when the input has a non-empty `agent_id`, append the edited file's project-relative path to `state/agent-<agent_id>.json` (`{"files": [...]}`, deduplicated).
- `stop_checks.py` on `hook_event_name == "SubagentStop"`: read that file; no file or no files → exit 0 silently. Otherwise run `find_problems` and `secret_problems` over those files only (still against the session baseline), block with `decision: "block"` and the same listing, counting in `state/agent-<agent_id>-blocks` with the same three-strike rule (secrets never give up). On a clean result, delete the agent's state files.
- `render_settings` adds `"SubagentStop": [entry(stop_checks.py, timeout=_STOP_TIMEOUT_SECONDS)]`.

- [ ] **Step 1: Write failing tests**

```python
def test_post_edit_records_subagent_files(project): ...                # agent_id "a1" edit api/src/x.py → state/agent-a1.json lists it
def test_subagent_without_edits_stops_freely(project): ...             # main work has a source change without tests; SubagentStop for "r1" → no output
def test_subagent_is_blocked_on_its_own_untested_source(project): ...  # agent-a1.json lists api/src/x.py → block naming it
def test_subagent_secret_blocks_every_time(project): ...
def test_clean_subagent_stop_clears_its_state(project): ...
def test_settings_wire_subagent_stop(): ...
```

- [ ] **Step 2: Run** the three test files. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hooks): Run the stop checks on subagents' own work`

---

### Task 5: Shell writes to protected paths

**Files:** Modify `project-files/hooks/guard_bash.py`. Test: `tests/hooks/test_guard_bash.py`.

**Interfaces:** `write_targets(segment: list[str]) -> list[str]` over the existing `split_segments` output: the token after `>`, `>>`, `>|`, `&>`, `1>`/`2>` (and the rest of a token that starts with one of them, e.g. `>out`); every non-option argument of `tee`; the last argument of `cp`, `mv`, `install`, `ln`; every non-option argument of `rm`, `truncate`; the file arguments of `sed -i`/`sed --in-place` and `perl -i`/`-pi` (every argument after the script). `/dev/null` and paths outside the project are ignored. Each target, resolved against the command's cwd and made project-relative, is checked against `protected.paths`; a match blocks with `guard_paths.protected_message`'s text (move that function to `_common.py` so both hooks share it). Commands inside `bash -c`/`sh -c` are already recursed by `check_command`.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.parametrize("command", [
    "echo x > api/uv.lock", "echo k >> .env", "cat x | tee api/keys/a.txt",
    "sed -i '' 's/a/b/' api/uv.lock", "cp /tmp/x web/pnpm-lock.yaml", "rm api/keys/old.txt",
    "bash -c 'echo x >.env.local'",
])
def test_shell_writes_to_protected_paths_are_blocked(project, command): ...
@pytest.mark.parametrize("command", [
    "cat api/uv.lock > /dev/null", "grep '>' api/uv.lock", "echo '> api/uv.lock'",
    "uv sync", "cp api/uv.lock /tmp/backup.lock", "echo x > api/src/app.py",
])
def test_reads_and_unprotected_writes_pass(project, command): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/hooks/test_guard_bash.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(hooks): Block shell writes to protected paths`

---

### Task 6: Live check in Claude Code

**Files:** Modify `CLAUDE.md` (kit live-run notes).

- [ ] **Step 1:** Generate, bootstrap and commit the web+API scenario in a scratch folder.
- [ ] **Step 2:** In it, run `claude -p "List the decision records you were given at the start of this session, with their numbers." --output-format text`. Expected: the answer lists the records by number and title (the index reached the session).
- [ ] **Step 3:** Run `claude -p "Use a general-purpose subagent to add api/app/routes/ping.py with a function ping() returning 'pong'. Don't add tests. Report what the subagent said." --output-format text`. Expected: the subagent is blocked at least once with the tests-first-class problem (visible in its report), and the main session's Stop also flags it.
- [ ] **Step 4:** Record what was verified, and anything that behaved differently, under the live-run notes in the kit's `CLAUDE.md`.
- [ ] **Step 5: Commit** `docs: Record the rules-in-context live check`
