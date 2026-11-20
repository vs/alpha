---
name: brainstorm
description: Start the full track of a task in a project alpha installed - research the code and how others solve it, brainstorm the design with the user one question at a time, write research.md and a design spec in docs/alpha/<features|bug-fixes|refactorings|perf>/<date>-<slug>/, get it approved, then hand off to /alpha:plan. Use for /alpha:brainstorm <task>, or when the user asks to brainstorm, research or spec a feature, bug fix, refactoring or perf change before building it.
---

<!--
Adapted from the `brainstorming` skill in superpowers (https://github.com/obra/superpowers).

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

# Brainstorm

The first of the full track's three skills: `/alpha:brainstorm` writes the research and the design, `/alpha:plan` the plan, `/alpha:execute` builds it. `/alpha:do <task>` is the light track, straight into the work with no files. You own the research and the design; the user decides what they want and approves the spec.

Task: `$ARGUMENTS`

## 1. Check the project and pick the playbook

Run section 1 of `${CLAUDE_PLUGIN_ROOT}/skills/do/SKILL.md`, and keep its section 3 rules throughout (first message, facts and decisions, questions, evidence, subagents, branch, worktrees). Open a todo list with this skill's steps.

Match the task to a playbook in `${CLAUDE_PLUGIN_ROOT}/skills/do/playbooks/` and read it in full: it says what research and design mean for this kind of task. The folder is `docs/alpha/<folder>/<YYYY-MM-DD>-<slug>/`, today's date and a short slug:

| Playbook | Folder |
|---|---|
| Feature | `docs/alpha/features/` |
| Bug fix | `docs/alpha/bug-fixes/` |
| Refactoring | `docs/alpha/refactorings/` |
| Perf | `docs/alpha/perf/` |

An investigation, a prototype, a pause or a session pickup has no full track: say so, point to `/alpha:do <task>`, and stop.

## 2. Research and design

1. Research the code. Run Investigation steps 1 to 4 over the part of the project the task touches: how it works today, what the change must reach (callers, tests, fixtures, config, docs), and what it could break for users (`scope-first`). Never ask what the project already answers.
2. Run the playbook's research steps. Bug fix: reproduce it and find the root cause (steps 1 to 3). Perf: fix the workload and the metric, build the measurement and record the baseline (steps 1 and 2). Refactoring: pin the behavior and sketch the target shape (steps 1 and 2). Feature: name the open product areas it needs and the data shape (the types, the states, the structure that holds them), keeping the structure the codebase has unless it can't hold the feature. An open area is named to the user with its `/alpha:update <area>` request, not settled here.
3. Deep research. Dispatch subagents to find how other projects solve this: libraries that already do it, products that ship it, write-ups of the trade-offs and the ways it fails. Each returns what it found with its sources. Write their findings and steps 1 and 2's to `research.md` in the folder: the options, what each costs and rules out, each claim with its link or `file:line`.
4. Ask what the user wants before how, one question at a time (`do`'s section 3, Questions), and only where the answer changes what gets built and neither the request nor the research answers it. Until you know why they want it, ask open questions with no options attached; say what the answer would change. Otherwise make the call, say it as a proposal they can correct, and go on. A question you could settle by running something is a spike: build it by the Prototype playbook, with the user's yes.
5. Lay out the approaches in a message of their own, before anything is written: two or three real ways to build it, grounded in what the project does and the research, each with what it trades off; recommend one and ask which way they want to go. When there is one sensible way, say so and why the others don't fit. Recommendations come from the principles, the specification, CONTRIBUTING.md, the code and the research, not the kit defaults.
6. Play the design back in sections, a few hundred words each: the data shape, where the code goes, what changes for callers, the failure paths. Mark what they said as theirs and what you filled in as your proposal with its reason, and end each section by asking what's wrong or missing. Get each confirmed before the next.
7. Write `specification.md` beside `research.md`, in the shape below. When `docs/alpha/specification.md` lists requirements, name the one the task serves; one it doesn't list yet is the user's to add with `/alpha:update requirements`, so say so. A bug fix's Requirements hold the fixed behavior and the behavior that must not change, and its Design the root cause with its `file:line`; perf's hold the metric, the target and the measurement command; a refactoring's hold the pin and the target shape.
8. Builder check. Dispatch a fresh subagent with this brief: "You are an engineer handed `<folder>/specification.md` and `research.md` to plan from, and you can't talk to the author. Read them, then report only the questions you would still have to guess at where a wrong guess changes the plan, each with why, most important first. Skip what the spec leaves to the builder and wording nits. If nothing important is left, say so." Sort its questions: answered by the conversation or the project goes into the spec; minor, a sensible builder could settle it, you settle and mark as your call in Decisions; only the user can answer it, ask in one message, most important first.
9. Get the user's approval of the spec, every time. Show the folder and a summary of the requirements, checks and decisions, and the calls you made so they can check those. On changes, edit the spec and ask again. Nothing but the folder is written until the user approves. Then set its Status, take the branch or the worktree (`do`'s section 3), and commit the folder as one `docs` commit by the commit skill (`.claude/skills/commit/SKILL.md`).
10. Hand off to `/alpha:plan` with the folder: invoke the `alpha:plan` skill, and no other.

Spec shape:

<!-- rumdl-disable MD013 -->
<!-- The template's long lines are literal text Claude copies. -->

```markdown
# <Title>

Date: YYYY-MM-DD
Status: draft | approved by the user on YYYY-MM-DD
Serves: R<n> in docs/alpha/specification.md, or none yet
Research: research.md · Plan: plan.md

## Why

<The user's goal and the problem it solves, in two or three sentences.>

## Requirements

| ID | Requirement | Acceptance check | Test |
|---|---|---|---|
| F1 | <what the change does> | Given <state>, when <action>, then <observable result>. | `<test file>::<test name>` (<level>) |

## Design

<The data shape, where the code goes, what it changes for callers, the failure paths.>

## Decisions

<The approaches considered and the one picked, and each choice settled while brainstorming, with its reason and whose call it was.>

## Out of scope

<What the change deliberately leaves out.>
```

<!-- rumdl-enable MD013 -->

**Reply:** the folder, the approved spec's requirements and decisions, the open product areas with their `/alpha:update <area>` requests, and the hand-off to `/alpha:plan`.
