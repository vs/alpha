# Feature pipeline: research

Date: 2026-11-20

## The case

The user wants `/alpha:do` to work the way the superpowers plugin does: research, a design spec, an implementation plan built from both, then executing that plan, each as its own skill handing off to the next. alpha's principles, hooks, decision skill and principles reviewer stay, and alpha does not depend on superpowers. The pstack playbooks alpha copied are to be kept, reworked onto that pipeline, or dropped.

## How alpha works today

- `skills/do/SKILL.md` routes a task to one of eight playbooks in `skills/do/playbooks/` and holds the rules every playbook keeps (section 3: questions, evidence, subagents, branch, worktrees, done).
- `feature.md` already has the stages, in one 65-line file: research the code (step 1), deep research into `research.md` (2), open product areas (3), data shape (4), a superpowers-style brainstorm (5), `specification.md` and `plan.md` (6), one approval of both plus native or subagents (7), build tests first (8), verify (9), sync the docs (10), done (11).
- The kit spec pins this: `docs/specification.md:44` (R8.1, research, spec and plan in `docs/alpha/features/<date>-<feature>/`), `:45` (R8.2, `do` runs no whole-branch review; the principles review runs at the merge gate), `:176-184`. `tests/unit/test_do_skill.py` checks the playbooks' text: R8.1 step order and phrases, R8.2, the spec template, native and subagents, the router table.
- `.claude/alpha/notes/` is gitignored (`.gitignore:11`) and the only part of `.claude/alpha/` the path guard lets the agent write (`project-files/hooks/_common.py:532-533`); Pause writes its resume note there.

## What superpowers does that alpha lacks

Read from superpowers 7.0.2 (MIT, Jesse Vincent), `skills/`:

| superpowers | Idea | alpha today |
|---|---|---|
| brainstorming | Sizes the work first: a request that says everything is just done; a small change gets a short design; a project gets the full one. Approaches go in a message of their own and the user picks before any doc. Plays the design back in 200-300-word chunks. A fresh "builder check" subagent reads the full design and returns only the questions a builder would still have to guess. Hard gate: nothing is built before the design is approved. Spikes: a throwaway build the user agreed to, no tests, no plan. | One size (always the full folder); approaches and sections are there; no builder check; the Prototype playbook is the spike. |
| writing-plans | A plan for an engineer who hasn't seen the code: header with the spec path, Global Constraints, Review Focus (the five failure modes no task's tests exercise, each then given a test). Each task: Files, Interfaces (consumes/produces, exact signatures), steps with a command and its `Expected:` output. Signatures and test assertions, not bodies. Self-review: spec coverage, step scan, type consistency, Review Focus, proportion to the spec. Then the user reviews the plan and picks the execution mode. | `plan.md` is ordered tasks naming files and tests; approved together with the spec. |
| executing-plans | Inline execution with a ledger (`progress.md`) that survives compaction; every deviation is a `Ruling: <what> — <why> — <cost if wrong>`; four things stop the run (irreversible, security, outside side effect, plan broken beyond guessing); a completion contract per task; one whole-branch review at the end, one fix pass, each fix test-first; the final message lists every ruling and deferred minor. | Build in order without checking in; no ledger, no rulings list; no final review (R8.2). |
| subagent-driven-development | Fresh implementer per task (never two at once), one reviewer giving a spec and a quality verdict, a fix loop capped at five rounds, briefs and diffs passed as files, models picked per role. | A reviewer subagent per task running `review-change`; tasks marked side by side may run in parallel worktrees. |
| scripts (bash) | `sdd-workspace` (a per-plan gitignored folder), `task-brief` (cut one task out of the plan), `task-start`/`task-done` (BASE, run the tests, append the ledger line only on a pass), `review-package` (log, stat and diff of a range in one file). | None. |
| systematic-debugging, TDD, verification-before-completion, using-git-worktrees, dispatching-parallel-agents | Covered in alpha by bug-fix.md, `tests-first-class`, `evidence-before-done` and the Stop hook, the Worktrees and Subagents rules in do/SKILL.md section 3. systematic-debugging adds logging at component boundaries and a test-polluter bisect. | Covered. |
| receiving-code-review | Check each finding against the code, push back with evidence, no performative agreement. | Partly: CLAUDE.md's "say first whether you agree", the decision skill. |
| finishing-a-development-branch | Menu: merge locally, push and open a PR, keep, discard; removes the worktree. | Conflicts: CONTRIBUTING.md allows only pull requests, the merge guard asks for the principles review, alpha leaves worktree removal to the user. |

Conflicts with alpha's rules: superpowers writes `docs/superpowers/{specs,plans}/`, alpha one folder per feature; its plans embed `git commit -m` lines, alpha uses the commit skill and its scopes; its mandatory whole-branch review contradicts R8.2; SDD forbids parallel implementers, alpha allows them in worktrees; SDD always names a model, alpha inherits the chat's; TDD's "delete code written before its test" and "ask the human for exceptions" clash with `untested.py` and `never-block-on-the-human`; using-superpowers' "1% rule" would compete with `do`'s routing.

## The pstack playbooks alpha copied

From pstack 0.15.36 `skills/poteto-mode/playbooks/`: investigation, feature (rewritten almost entirely, already superpowers-like), bug-fix, perf-issue and hillclimb (merged into perf.md), prototype, refactoring, session-pickup, pause-safely. Fourteen others (forensics, shipping, opening-a-pr, autopilot, orchestrate and more) were never copied; they need Cursor, cloud agents or PR tooling. pstack's helper skills (how, why, architect, tdd, benchmark-checklist) are folded into alpha's playbook steps; arena, interrogate, swarm and reflect have no alpha equivalent.

## Prior art

| Tool | Stages and artifacts | Small work | Bugs |
|---|---|---|---|
| superpowers | brainstorm → design doc → plan → execute → finish ([repo](https://github.com/obra/superpowers)) | A clear request is just done; a small change gets a short doc; v6.3 added a no-spec path; skipping approval for "mechanical" work was refused on purpose ([#2076](https://github.com/obra/superpowers/issues/2076)) | systematic-debugging, not brainstorming |
| GitHub spec-kit | constitution → specify → plan → tasks → implement → converge, in a feature folder ([quickstart](https://github.com/github/spec-kit/blob/main/docs/quickstart.md)) | "Shorter path" skips clarify, checklist, analyze | Separate extension: assess → fix → test, a verdict ([repo](https://github.com/github/spec-kit)) |
| Kiro | requirements (EARS) → design → tasks, each reviewed ([docs](https://kiro.dev/docs/specs/)) | Quick Spec: all three without gates | Bugfix spec: current, expected, unchanged behavior, root cause ([docs](https://kiro.dev/docs/specs/bugfix-specs/)) |
| BMAD | Sized by intent: trivial needs nothing, one session goes to `bmad-build`, epics get PRD and architecture ([docs](https://github.com/bmad-code-org/BMAD-METHOD/blob/main/docs/plan/choose-a-planning-path.md)) | `bmad-build` takes a light path when intent, irreversibility and footprint are all clean ([docs](https://github.com/bmad-code-org/BMAD-METHOD/blob/main/docs/build/build-a-change.md)) | A ticket or a direct build |

## Failure modes

1. Ceremony on small work. Every tool added a light path after complaints; Böckeler found Kiro on a small bug "a sledgehammer to crack a nut" and would "rather review code than all these markdown files" ([martinfowler.com](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html)). Superpowers: 15 of 26 sessions started brainstorming unasked ([#2000](https://github.com/obra/superpowers/issues/2000)); a 5-line file cost 10-15x through per-task review ([#1120](https://github.com/obra/superpowers/issues/1120)).
2. Letting the agent judge the effort made it skip steps; superpowers keeps the gate and makes it cheaper instead ([#1120](https://github.com/obra/superpowers/issues/1120)).
3. Long specs are hard to review; code in a spec is reviewed twice ([Thoughtworks Radar](https://www.thoughtworks.com/radar/techniques/spec-driven-development), [Marmelab](https://marmelab.com/blog/2025/11/12/spec-driven-development-waterfall-strikes-back.html): 1,300 lines of spec for a date display).
4. Plans become transcripts of the code; superpowers answers with signatures-not-bodies and a proportion check ([writing-plans](https://github.com/obra/superpowers/blob/main/skills/writing-plans/SKILL.md), [#512](https://github.com/obra/superpowers/issues/512)).
5. Spec drift: spec-kit has no reconciliation ([evolving specs](https://github.com/github/spec-kit/blob/main/docs/how-to/evolving-specs.md)); specs heavy with implementation detail decay ([arXiv 2608.25202](https://arxiv.org/abs/2608.25202), abstract only).
6. Agents ignore plans; a bad plan hurts more than none, reminders reduce violations ([arXiv 2604.12147](https://arxiv.org/abs/2604.12147), abstract only).
7. Losing place after compaction and redoing finished tasks is superpowers' "single most expensive failure" ([SDD](https://github.com/obra/superpowers/blob/main/skills/subagent-driven-development/SKILL.md)); the ledger answers it.
8. Forced questioning annoys users who arrive with a finished spec ([#2530](https://github.com/obra/superpowers/issues/2530)).
9. No tool runs bugs through the feature flow: root cause, failing test, regression guard.

## What this means for alpha

- The pipeline is the Feature playbook split at its natural seams, each a skill with one job: design (research, brainstorm, spec), plan, execute. alpha keeps its feature folder, the Requirements table with a test per check, the approval gate, and the decision skill instead of a ledger-only record of rulings.
- Bug fix, Perf and Investigation keep their own short flows, as every tool does. Refactoring's "target shape" is a design; a multi-commit refactoring can use the plan and execute stages.
- The ledger belongs in `.claude/alpha/notes/`, where Pause's note already lives, which also gives Session pickup something exact to resume from.
- The whole-branch review superpowers ends with is what alpha's principles reviewer already is at the merge gate; moving it into execution changes R8.2 and needs the user's yes.
