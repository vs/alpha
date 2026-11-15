# Feature

You own the research, the design and the spec. The user settles the design with you, approves the spec and picks how it's built; the tests come from the spec, the code makes them pass.

1. Research the code. Run Investigation steps 1 to 4 over the part of the project the feature touches: how it works today, what the change must reach (callers, tests, fixtures, config, docs), and what it could break for users (`scope-first`).
2. Deep research. Dispatch subagents to find how other projects build this feature: libraries that already do it, products that ship it, write-ups of the trade-offs and the ways it fails. Each returns what it found with its sources. Write their findings to `docs/alpha/features/<YYYY-MM-DD>-<feature-slug>/research.md` (today's date): the options, what each costs and rules out, each claim with its link.
3. Find the product areas the feature needs that are still open (project.json's `areas`): a UI needs ui and accessibility, stored data needs data, a deployed component needs observability, calls between components need architecture, errors users see need errors, a budget needs performance, a visual needs the design language. Name each to the user with its `/alpha:specify` request; don't settle it here. The feature's own choices stay in its spec.
4. Name the data shape before any logic: the types, the states and what moves between them, and the structure that holds them (a typed model, a table, a state machine) rather than scattered conditionals. Keep the structure the codebase already has unless it can't hold the feature.
5. Brainstorm the design with the user. Ask one question at a time (SKILL.md section 3), and for each open decision lay out two or three approaches with their trade-offs from the research, recommending one. Then show the design in sections (the data shape, where the code goes, what changes for callers, the failure paths), and get each section confirmed before the next. A question you could settle by running something goes to the Prototype playbook instead. Recommendations come from the principles, the specification, CONTRIBUTING.md, the code and the research, not the kit defaults.
6. Write `specification.md` beside `research.md`, in the shape below: requirements, an acceptance check per requirement and the test that proves it, the design, the decisions, what's out of scope. When `docs/alpha/specification.md` lists requirements, name the one the feature serves; one it doesn't list yet is the user's to add with `/alpha:specify requirements`, so say so. Then write `plan.md` beside them: ordered tasks, each small enough for one commit that passes the checks, naming its files and the tests from the Requirements table it makes pass. Tasks with disjoint files and no shared interface can run side by side; say which.
7. Get the user's approval of the spec, every time, and their choice of how to build it. Show the folder and a summary of the requirements, checks, decisions and tasks. Ask for the approval first, then how to build it, with your recommendation and one sentence of why (how many tasks, how much they depend on each other's interfaces, what a shipped mistake would cost):
   - **Native**: you build every task yourself in this session. Cheapest and fastest.
   - **Subagents**: a fresh subagent builds each task, and a fresh reviewer subagent checks it against the spec before the next starts. More thorough; costs a fresh context per task and per review.

   And whether to work in a worktree (SKILL.md section 3). On changes to the spec, edit it and ask again. Nothing but the feature folder is written until they approve. Then follow the project's branching in CLAUDE.md: with feature branches, make the feature branch (`git switch -c <branch>`), or the worktree when they chose one, and move the folder there; on trunk, commit on the main branch. Commit the folder as one `docs` commit.
8. Build the tasks in order, without stopping to check in between them. For each task:
   1. Write its tests at the levels the project's testing answers give (CONTRIBUTING.md, Testing), each asserting what a user of the code can observe. Run them and paste the output: each must fail on the missing behavior, not on a typo or an import.
   2. Write the smallest code that makes them pass, keeping the project's principles; delete what the change makes dead first (`subtract-first`).
   3. Run the task's tests and the component's checks, then commit the tests and code together following the commit skill (`clean-history`).

   With subagents, each implementer gets the folder, its task, its files and the brief in SKILL.md section 3; each reviewer gets the spec, the task and the task's diff, and runs the `review-change` skill on that diff. Fix what the reviewer finds before the next task. Tasks marked side by side may run at once, each subagent in its own worktree. Decide what the spec leaves open and record it in the spec's Decisions; stop only for what SKILL.md section 3 says to ask about.
9. Verify. Every test in the spec passes. Exercise each acceptance check on the real thing where you can (run the CLI, the app, the endpoint) and paste what happened. A check you couldn't exercise is reported as unverified, not passed.
10. Bring the spec and the plan in line with what was built. A change to what the feature does goes back to the user for approval; a change to how it's built is recorded in the plan.
11. Finish with Done (SKILL.md section 3). The principles review runs when the branch reaches main, not here.

Spec shape:

<!-- rumdl-disable MD013 -->
<!-- The template's long lines are literal text Claude copies. -->

```markdown
# <Feature>

Date: YYYY-MM-DD
Status: approved by the user on YYYY-MM-DD, built native | with subagents
Serves: R<n> in docs/alpha/specification.md, or none yet
Research: research.md · Plan: plan.md

## Why

<The user's goal and the problem it solves, in two or three sentences.>

## Requirements

| ID | Requirement | Acceptance check | Test |
|---|---|---|---|
| F1 | <what the feature does> | Given <state>, when <action>, then <observable result>. | `<test file>::<test name>` (<level>) |

## Design

<The data shape, where the code goes, what it changes for callers.>

## Decisions

<Each choice settled while brainstorming or building, with its reason.>

## Out of scope

<What the feature deliberately leaves out.>
```

<!-- rumdl-enable MD013 -->

**Reply:** the feature folder, how it was built, each acceptance check with its test and result, the decisions, the open product areas with their `/alpha:specify` requests, and what is left open.
