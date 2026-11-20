---
name: execute
description: Build an approved full-track plan in a project alpha installed - task by task, test-first, natively or with a fresh subagent and reviewer per task - keeping a ledger it resumes from and ruling on every deviation without checking in, then run the principles review once, fix its findings and run the fix check. Use for /alpha:execute [folder], after /alpha:plan, or to resume a full-track build after a pause or compaction.
---

<!--
Adapted from the `executing-plans` and `subagent-driven-development` skills in superpowers (https://github.com/obra/superpowers).

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

# Execute

The last of the full track's three skills: `/alpha:brainstorm` wrote the spec, `/alpha:plan` the plan, this skill builds it. The plan already did the thinking: build it exactly, prove each step with a test you watched fail and then pass, and leave a record that survives your own forgetting.

Folder: `$ARGUMENTS`

## 1. Check the project, the plan and the ledger

Run section 1 of `${CLAUDE_PLUGIN_ROOT}/skills/do/SKILL.md`, and keep its section 3 rules throughout; section 4 here replaces Done's step 4. The folder is the one named, else the newest under `docs/alpha/{features,bug-fixes,refactorings,perf}/` with an approved `plan.md`. With no `plan.md`, or one whose Status isn't `approved by the user on <date>`, say which and that `/alpha:plan` makes it, and stop. Work on the branch the spec was committed on (`do`'s section 3, Branch).

The ledger is `.claude/alpha/notes/<slug>/progress.md`, `<slug>` the folder's name: gitignored, and the one place under `.claude/alpha/` the hooks let you write. Your conversation doesn't survive compaction; the ledger and `git log` do, so trust them over what you remember.

- No ledger: create it with `# Ledger: <plan path>` as its first line.
- A ledger whose first line names this plan: a task with a `Task <N>: complete` line is done and never redone, even when you don't remember it; resume at the first task without one.
- A ledger whose first line names another plan isn't yours: leave it, tell the user, and stop.

Read the plan and the spec once and open a todo per task. The spec is the authority the plan argues from. Then the pre-flight: for each task that consumes what an earlier one produces (their Interfaces), one ledger line naming both and whether they match, or `Pre-flight: no shared interfaces`. Rule on each mismatch before task 1.

## 2. Rulings, not stalls

Build every task without stopping to check in: the user chose the mode at the plan's approval. Conflicts, ambiguities and plan defects are yours to decide, the spec binding and your judgment settling what neither answers. Write each as `Task <N>: Ruling: <what you decided> — <why> — <cost if wrong>` in the ledger, in the same step as the work it changes; a deviation with no ruling is a decision made in secret. A ruling that changes what the spec says gets built goes back to the user at the end (section 5).

Four things stop you, and only these: an irreversible or destructive operation; a security-sensitive action; a side effect outside the checkout that needs asking first (a push, a merge, a deploy, a message to people); a plan so broken that every path forward is a guess. Ask about those, as `do`'s section 3 says.

## 3. Each task

**Native.**

1. Read the task's section in `plan.md` again, even one you remember: the plan has the exact names and values, your memory a summary. Mark its todo in progress and note BASE, `git rev-parse HEAD`.
2. Work its steps in order. A test step's test is written and run first: watch it fail on the missing behavior; a test that passes before the code exists is a finding about the test. Compare every command's output with its `Expected:` line. It matches: next step. The code is wrong: find the cause as Bug fix steps 2 and 3 do; never patch the symptom to match. The plan is wrong (it contradicts the spec, an interface doesn't match, a command can't work): take the smallest change that satisfies the spec and write the ruling.
3. Update the docs the task's paths move (CONTRIBUTING.md, Documentation), run the task's tests and the component's checks, and commit by the commit skill (`.claude/skills/commit/SKILL.md`; `clean-history`).
4. Complete it only when every test it names exists and ran, the last run passed, every `Expected:` was compared with real output, and every deviation has a ruling (`evidence-before-done`). Then, with the commit, append `Task <N>: complete (commits <base>..<head>, tests: <command> → <result>)` and mark the todo done.

**Subagents.** You are the controller: one task at a time, never two at once. Give a fresh implementer subagent the folder, the task's section from `plan.md` verbatim, the rulings that touch its Interfaces, BASE, and `do`'s section 3 brief; it works the task as Native steps 2 and 3 say, asks you instead of guessing (your answers are rulings), and reports its commits and test output. Then give a fresh reviewer subagent the spec, the task's section and `git diff <BASE>..HEAD`; it runs the `review-change` skill on that diff and says whether the task meets the spec, nothing missing and nothing extra, and what it found. Send the findings back to the same implementer; after five fix rounds, rule on what is still open and go on. Run the task's tests yourself and read its diff before Native step 4's ledger line: a subagent's report proves nothing.

## 4. The principles review, once

After the last task, the review the merge guard asks for runs here, once (`docs/alpha/specification.md`, Review), not again at the push.

1. Run the full suites: `python3 .claude/alpha/hooks/stop_checks.py tests`. Fix what fails as section 3 does.
2. Run the principles-reviewer agent once over the branch: a fresh one, from a session started in the checkout that holds the branch, since the hook records only such a run.
3. Fix its findings in one pass. Re-grade each by what a user gets if it ships, not by its label. Each fix gets a test written to fail first, then the fix, then the component's checks, then a commit; write `Final: fixed <id> — <test>` in the ledger. A finding that stands gets a commit trailer `Accepts: <id> <reason>` and a ruling; only the user accepts one on a risk path, by replying `accept <id>`.
4. Run a fresh principles-reviewer as the fix check: it judges those findings and the files changed since. What it leaves open goes to the user in the reply, with its fix or the case for accepting it; never start a third review yourself.

## 5. Finish

1. Bring the spec and the plan in line with what was built. A ruling that changes how it's built goes into `plan.md`; one that changes what it does is recorded in the spec's Decisions with the `decision` skill and needs the user's yes, asked in the reply. Commit both as one `docs` commit.
2. Verify: every test in the spec passes, and each acceptance check is exercised on the real thing where you can (run the CLI, the app, the endpoint) with what happened pasted. A check you couldn't exercise is unverified, not passed.
3. Finish with Done (`do`'s section 3) steps 1 to 3.
4. Copy every `Ruling:` and `Final:` line into the reply, then delete the ledger's folder: the git history is the record now.

**Reply:** the folder and the mode, each acceptance check with its test and result, every ruling with what it costs if wrong, the findings fixed and the deferred ones, what the fix check left open, the rulings that change the spec and wait for the user's yes, and what is still ahead before main (the push or pull request).
