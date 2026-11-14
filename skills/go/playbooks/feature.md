# Feature

You own the design and the spec. The user approves the spec and picks how it's built; the tests come from the spec, the code makes them pass.

1. Research. Run Investigation steps 1 to 4 over the part of the project the feature touches: how it works today, what the change must reach (callers, tests, fixtures, config, docs), and what it could break for users (`scope-first`).
2. Name the data shape before any logic: the types, the states and what moves between them, and the structure that holds them (a typed model, a table, a state machine) rather than scattered conditionals. Keep the structure the codebase already has unless it can't hold the feature.
3. Grill. List the decisions the feature leaves open as a design tree and settle them with the user in rounds, invoking the `alpha:grilling` skill with the Skill tool. For a feature, recommendations come from the principles, the decision records and the code you read, not the kit defaults, and its override protocol doesn't apply. A question you could settle by running something goes to the Prototype playbook instead. Keep each settled choice in the spec's Decisions section; nothing is recorded elsewhere before approval.
4. Write the feature spec to `docs/specs/<YYYY-MM-DD>-<feature-slug>.md`, today's date, in the shape below. Every acceptance check names the test that proves it. Each requirement traces to a row of `docs/product.md`, which alpha generates from the answers: the one it serves, or a new one, written as `new: <requirement>` until approval adds it with `/alpha:extend` (identity area); never edit the file.
5. Plan the build in the spec's Plan section: ordered tasks, each small enough for one commit that passes the checks, naming its files and the tests from the Requirements table it makes pass. Tasks with disjoint files and no shared interface can run side by side; say which.
6. Get the user's approval of the spec, every time, and their choice of how to build it. Show its path, a summary of the requirements, checks, decisions and tasks, and ask both at once, with your recommendation and one sentence of why (how many tasks, how much they depend on each other's interfaces, what a shipped mistake would cost):
   - **Native**: you build every task yourself in this session, then a fresh subagent reviews the whole branch. Cheapest and fastest; no independent review until the end.
   - **Subagents**: a fresh subagent builds each task and a fresh reviewer subagent checks it against the spec and the principles before the next starts, then the whole branch is reviewed. Most thorough; costs a fresh context per task and per review.

   And whether to work in a worktree (SKILL.md section 3). On changes to the spec, edit it and ask again. Nothing but the spec file is written until they approve. Then:
   1. Follow the project's branching in CLAUDE.md: with feature branches, make the feature branch (`git switch -c <branch>`), or the worktree when they chose one, and move the spec file there; on trunk, commit on the main branch.
   2. Add each new requirement with `/alpha:extend` and record each settled choice that later changes must follow with the `decision` skill, then put the requirement ids and record links in the spec.
   3. Commit the spec as one `docs` commit.
7. Build the tasks in order, without stopping to check in between them. For each task:
   1. Write its tests at the levels the project's testing decision gives, each asserting what a user of the code can observe. Run them and paste the output: each must fail on the missing behavior, not on a typo or an import.
   2. Write the smallest code that makes them pass, keeping the project's principles; delete what the change makes dead first (`subtract-first`).
   3. Run the task's tests and the component's checks, then commit the tests and code together following the commit skill (`clean-history`).

   With subagents, each implementer gets the spec path, its task, its files and the brief in SKILL.md section 3; each reviewer gets the spec, the task and the task's diff, and runs the `review-change` skill on it. Fix what the reviewer finds before the next task. Tasks marked side by side may run at once, each subagent in its own worktree. Decide what the spec leaves open and record it in the spec's Decisions; stop only for what SKILL.md section 3 says to ask about.
8. Verify. Every test in the spec passes. Exercise each acceptance check on the real thing where you can (run the CLI, the app, the endpoint) and paste what happened. A check you couldn't exercise is reported as unverified, not passed.
9. Bring the spec in line with what was built. A change to what the feature does goes back to the user for approval; a change to how it's built is recorded in the spec.
10. Finish with Done (SKILL.md section 3), with a fresh subagent's `review-change` of the whole branch.

Spec shape:

<!-- rumdl-disable MD013 -->
<!-- The template's long lines are literal text Claude copies. -->

```markdown
# <Feature>

Date: YYYY-MM-DD
Status: approved by the user on YYYY-MM-DD, built native | with subagents
Serves: R<n> in docs/product.md

## Why

<The user's goal and the problem it solves, in two or three sentences.>

## Requirements

| ID | Requirement | Acceptance check | Test |
|---|---|---|---|
| F1 | <what the feature does> | Given <state>, when <action>, then <observable result>. | `<test file>::<test name>` (<level>) |

## Design

<The data shape, where the code goes, what it changes for callers.>

## Plan

1. <Task>: <files>. Makes F1 pass. <"Side by side with 2" when it can run in parallel.>

## Decisions

<Each choice settled while grilling or building, with its reason, or a link to its record.>

## Out of scope

<What the feature deliberately leaves out.>
```

<!-- rumdl-enable MD013 -->

**Reply:** the spec path, how it was built, each acceptance check with its test and result, the decisions recorded, and what is left open.
