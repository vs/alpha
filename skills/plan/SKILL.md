---
name: plan
description: Write the implementation plan of an approved full-track spec in a project alpha installed - tasks an engineer who hasn't seen the code can build, each with its files, interfaces, test-first steps and expected output - self-review it, get it approved with the choice of native or subagent execution, then hand off to /alpha:execute. Use for /alpha:plan [folder], after /alpha:brainstorm, or when the user asks to plan a spec they approved.
---

<!--
Adapted from the `writing-plans` skill in superpowers (https://github.com/obra/superpowers).

MIT License

Copyright (c) 2025 Jesse Vincent

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
-->

# Plan

The second of the full track's three skills: `/alpha:brainstorm` wrote the research and the spec, this skill writes `plan.md` beside them, `/alpha:execute` builds it. A plan is the set of decisions the builder can't make alone: which files, which names and signatures, which values from the spec, which tests prove each task. Write it for an engineer who hasn't seen this code or this spec and writes idiomatic code once they know the exact interface and the exact test.

Folder: `$ARGUMENTS`

## 1. Check the project and the spec

Run section 1 of `${CLAUDE_PLUGIN_ROOT}/skills/do/SKILL.md`, and keep its section 3 rules throughout. The folder is the one named, else the newest under `docs/alpha/{features,bug-fixes,refactorings,perf}/` whose `specification.md` has no `plan.md` beside it. With no `specification.md`, or one whose Status isn't `approved by the user on <date>`, say which file is missing or unapproved and that `/alpha:brainstorm` makes it, and stop; a spec the user wrote by hand is planned once they approve it. Read the spec, `research.md` and the task's playbook in `${CLAUDE_PLUGIN_ROOT}/skills/do/playbooks/` in full.

## 2. Write the plan

1. Map the files first: which are created or changed and what each is responsible for. Keep the structure the codebase has; files that change together live together.
2. Cut the tasks. A task is the smallest unit with its own test cycle that a reviewer could reject while approving its neighbor, and it ends in one commit that passes the checks (`clean-history`). Fold setup, config and the docs that move with its paths (CONTRIBUTING.md, Documentation) into the task that needs them (`docs-with-code`).
   - Bug fix: one task, the test and the fix in one `fix` commit (the Bug fix playbook), unless the spec says otherwise.
   - Refactoring: the subtraction commit first (`subtract-first`), then small reshapes that each keep the pin green.
   - Perf: one task per hypothesis, cheapest first in the playbook's order, each with its keep rule: kept only when the number moves past the noise with the tests green, else reverted in full.
3. Write each step so the builder can write exactly one reasonable thing from it. A test step: the test's name, as CONTRIBUTING.md's Testing names tests (`R<n>` when the work serves a product requirement), and its assertions, with the spec's exact values. A code step: the signature (name, parameters, return type), its file, and the values the spec pins; a body only for an algorithm the signature and tests don't determine. A verification step: the command and the `Expected:` output that means it passed; a test step's run is expected to fail on the missing behavior. A step that uses another task's work points to that task's Interfaces instead of repeating it.
4. Write Global constraints: the spec's project-wide requirements (versions, limits, naming, copy), one line each, values verbatim. Every task includes them.
5. Write Review Focus: the five inputs or failure modes the spec implies but no task's tests exercise that are likeliest to bite a user, most likely first, each with what a reasonable user expects. Then add each one's test to the task that owns the code.

Plan shape:

<!-- rumdl-disable MD013 -->
<!-- The template's long lines are literal text Claude copies. -->

```markdown
# <Title>: plan

Status: draft | approved by the user on YYYY-MM-DD, built native | with subagents
Spec: specification.md · Research: research.md

<Goal in one sentence; the approach in two or three. Which tasks depend on which.>

## Global constraints

- <constraint, value verbatim from the spec>

## Review Focus

1. <input or condition>: <what a reasonable user expects>. Test: <task, test name>.

## Task <N>: <name>

`<type>(<scope>): <commit subject>`

- Files: create `<path>`; change `<path>`; test `<path>`.
- Interfaces: consumes <exact names and types from earlier tasks>; produces <exact names and types later tasks use>.
- Steps:
  1. Write `<test name>`: <assertions with the spec's values>. Run `<command>`. Expected: fails with <the missing behavior>.
  2. Write `<signature>` in `<path>`: <one line on the approach when the test leaves a choice>.
  3. Run `<command>`. Expected: <passing output>.
  4. Commit by the commit skill.
```

<!-- rumdl-enable MD013 -->

## 3. Self-review

Read the spec again with fresh eyes and check the plan against it; fix what you find in place.

1. **Spec coverage.** Every requirement and acceptance check has a task whose tests prove it; add a task for one that doesn't.
2. **Step scan.** No step decides nothing ("handle edge cases", "add validation", "TBD", a name no task defines), and none carries a body the signature and tests already determine.
3. **Consistency.** Names, signatures and types match across tasks: a function called one thing in task 3 and another in task 7 is a bug.
4. **Review Focus.** Each line has its test in the owning task; an empty section means you looked and found none.
5. **Proportion.** A plan several times longer than its spec has written the code instead: replace bodies with signatures and assertions.

## 4. Approval and the mode

1. Get the user's approval of the plan, every time, and their choice of how to build it. Show the plan's path and its tasks in one line each, then ask for the approval and the mode, with your recommendation and one sentence of why (how many tasks, how much they depend on each other's interfaces, what a shipped mistake would cost):
   - **Native**: you build every task yourself in this session, test-first, with a ledger. Cheapest and fastest.
   - **Subagents**: a fresh subagent builds each task, one at a time, and a fresh reviewer checks it against the spec before the next starts. More thorough; costs a fresh context per task and per review.

   On changes, edit the plan and ask again.
2. Set its Status, and commit `plan.md` as one `docs` commit by the commit skill (`.claude/skills/commit/SKILL.md`).
3. Hand off to `/alpha:execute` with the folder: invoke the `alpha:execute` skill, and no other.

**Reply:** the plan's path, its tasks in one line each, the Review Focus, the mode the user chose, and the hand-off to `/alpha:execute`.
