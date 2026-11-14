---
name: go
description: Do a task in a project alpha generated or adopted, by a playbook that keeps the project's principles, decisions and checks - investigation, feature (research, grill, spec with its tests, approval, tests first, code), bug fix, refactoring, perf, prototype, session pickup, pause. Use for /alpha:go <task>, or when the user asks for rigorous work on a feature, bug, refactor, slowness or question in such a project.
---

<!--
Adapted from the `poteto-mode` skill and its playbooks in pstack (https://github.com/cursor/plugins/tree/main/pstack).

MIT License

Copyright (c) 2026 Lauren Tan

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

# Go

Do one task in a project alpha generated or adopted, step by step, by the playbook that fits it. The playbooks say how to work; the project says what is right. Its principles, decision records and checks win over anything written here.

Task: `$ARGUMENTS`

## 1. Check the project

`<root>` is the repository root (`git rev-parse --show-toplevel`).

- No `<root>/.claude/alpha/project.json`: alpha hasn't generated or adopted this repo, so there are no principles to follow. Say that `/alpha:adopt` brings an existing repo in, and stop.
- project.json has `adoption` but no `manifest` key: an adoption is under way. Point to `/alpha:adopt`, and stop.
- Otherwise, project.json has no `manifest` key: the interview never finished. Point to `/alpha:new-project`, and stop.
- With a `manifest`, read before the first step:
  - `docs/principles.toml`: the active principles, their parameters and `[review]`. Use the ids it gives (`fix-at-the-root`, `smallest-change`) when you name one.
  - The decision records in `docs/decisions/` that bear on the task (the session start lists them).
  - CLAUDE.md: each component's commands, the definition of done, the commit convention and how to talk to the user.
  - `docs/adoption.md`, when it exists: a task never leaves more findings in a file than its baseline allows; the plan's own steps shrink baselines, not unrelated tasks (`stay-in-scope`).

## 2. Pick the playbook

Match the task to one playbook and read its file in this skill's `playbooks/` folder in full.

| Playbook | File | For |
|---|---|---|
| Investigation | `investigation.md` | A read-only question: how does X work, why is Y built this way, are we sure, X or Y. |
| Feature | `feature.md` | New or changed behavior: research, grill, spec with its tests, approval, tests first, code. |
| Bug fix | `bug-fix.md` | A defect to reproduce, trace to its root cause and fix with a test that fails without the fix. |
| Refactoring | `refactoring.md` | A change to structure that keeps behavior: rename, extract, inline, merge, move. |
| Perf | `perf.md` | A measured slowness, or a push on one metric, against a baseline. |
| Prototype | `prototype.md` | A throwaway sketch to settle a design question by looking at it instead of asking. |
| Session pickup | `session-pickup.md` | Resuming work an earlier session left: a branch, a resume note, a spec. |
| Pause | `pause.md` | Stopping work cleanly so a later session can resume it. |

- Open a todo list whose first items are the playbook's steps, copied in as written, before any task-specific items. A step you skip stays in the list as `skip: <reason>`.
- A bug found in a feature or refactoring, or asked for with one, is fixed on its own first, by the Bug fix playbook. A redesign found during a refactoring is a feature.
- No playbook fits: take the closest one, say which steps you changed and why.

## 3. Rules every playbook keeps

**First message.** Say in your own words the user's goal, the problem behind it and, when the task changes code, the smallest change you expect to meet it. Then go on; don't wait for a confirmation, except where a playbook asks for an approval. When the evidence rules out what the user asked for, show it and stop.

**Facts are yours, decisions are the user's.** Never ask what you can look up or run. A question whose answer you could observe (behavior, output, timing, layout) goes to the Prototype playbook, not to the user. On reversible work, make the reasonable choice, record it with the `decision` skill and say what you chose (`never-block-on-the-human`). Ask first only about product direction or what can't be undone: deleting data, rewriting main, deploys, messages to people. A change that contradicts an accepted record needs a new record that supersedes it, as the `decision` skill says.

**Evidence.** Every claim carries its evidence in the same sentence: you ran it (paste the command and its output), you read it (`file:line`), or it's a guess (say so). Prove a change on the real thing: run the CLI, the test, the app (the component's `run` command in CLAUDE.md), read the actual value. "It compiles" and a subagent's report prove nothing. Never hand the user a check you could run (`evidence-before-done`).

**Two failures, one premise.** When two fixes that share an assumption fail the same check, write the assumption down and test it directly before trying a third.

**Subagents.** Give bulk reading, searching and independent slices of work to subagents; keep their summaries, not their raw output. Each brief restates the user's goal, names the files and the result wanted, and says to follow CLAUDE.md, `docs/principles.toml` and the decision records. A subagent runs on this chat's model unless the user names another. Two subagents never edit the same files at once. You own what they return: read their diff yourself and check its claims before building on it.

**Worktrees.** A feature, a refactoring across many files, or work you'll leave running can go in its own git worktree, so the user's checkout stays untouched. Already in a linked worktree (`git rev-parse --git-dir` differs from `--git-common-dir`, outside a submodule): stay there. Otherwise follow the user's stated preference (CLAUDE.md, memory, this conversation), or offer it once with your recommendation. Create it with the harness's own worktree tool when there is one (`EnterWorktree`); otherwise `git worktree add .claude/worktrees/<branch> -b <branch>` from the default branch (generated projects ignore `.claude/worktrees/`; check with `git check-ignore`). Then run each component's setup command and its tests, so a red baseline is known before you change anything. Subagents running side by side each get their own worktree (the Agent tool's `isolation: "worktree"`). The branch reaches main as CLAUDE.md says; leave removing the worktree to the user.

**Done.** A playbook that changes files finishes with the project's definition of done in CLAUDE.md:

1. The checks of every component you changed pass (the commands in CLAUDE.md, or `mise run check`), and the tests your change touches run green.
2. The docs that move with the changed paths (the table in CONTRIBUTING.md) are updated in the same change.
3. Run the `review-change` skill on your diff and fix what it finds that you agree with; say why you leave the rest.
4. Commit by following the commit skill (`.claude/skills/commit/SKILL.md`; it runs only when the user types it, so read the file), one logical change per commit, each passing the checks on its own.
5. The principles reviewer runs when `[review]` and the hooks ask for it (before main at least); its findings are fixed or accepted as the hooks say.

**Reply.** Follow CLAUDE.md's communication rules and the playbook's reply line. Name each principle that changed a choice, and the choice. End with what you skipped or couldn't check, and any risk the user must know.
