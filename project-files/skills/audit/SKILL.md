---
name: audit
description: Quality audit of the whole repo in plain English - bugs, security holes, what breaks at the project's expected load, risky code without tests, slow paths, broken principles, and what to delete, merge or split. Ranked; one-shot report that changes no code. Use for /audit, "audit this codebase", "review the whole repo", "find bloat", "what can I delete".
---

<!--
Adapted from the `ponytail-audit` skill in DietrichGebert/ponytail (https://github.com/DietrichGebert/ponytail).

MIT License

Copyright (c) 2026 DietrichGebert

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

# Audit the repo

Audit the repo like the senior developer who just inherited it and will be paged when it breaks. Order of importance: correct, safe, holds under load, tested, fast, lean. This is a report the user asked for, so give it in full.

## 1. Map first

- Audit what the user names: a folder, a component, or the whole repo. Nothing named: the whole repo.
- Read the README, `docs/` (architecture, principles, decisions, performance), the build and deploy config, the dependency list, the entry points (main, routes, handlers, jobs, CLI commands) and the tests.
- Take the expected load from `docs/performance.md`; when it isn't recorded, infer it from the README and deploy config, and say which load you assumed.
- Trace the main flows end to end and read those paths fully: input from users, money, auth, data writes, background jobs, anything shared between processes. In a big repo, go deep where a mistake costs the most, and say which parts you did not read.

## 2. Look for

1. **Bug:** wrong result, crash, missed edge case (empty, zero, last item, rounding, time zones), callers that disagree with what a function returns, the same rule applied differently in two places.
2. **Risk:** security holes (injection, weak randomness, secrets, missing checks on input from users), data loss (errors swallowed, writes in the wrong order, no transaction).
3. **Scale:** fine for one user, wrong at the expected load: check-then-write races, the same work done by every process, memory or lists that only grow, a query per item, O(n^2) on big input, per-process state that must be shared.
4. **Missing test:** risky logic (a branch, a parser, money, security, data writes, a bug fix) with no test that fails when it breaks. One good test, not coverage.
5. **Speed:** big slowdowns are problems; small wins (work repeated in a hot loop) are suggestions, unless a budget in `docs/performance.md` makes them count.
6. **Lean:** code that should not exist or should be smaller: dead code, unused options and config, speculative features; a helper the repo already has (name the path); what the standard library, the platform or an installed dependency already does; an abstraction with one implementation; near-copies that must change together; a function doing several unrelated jobs (split by job, never by line count).
7. **The project's own rules:** anything that breaks a principle in `docs/principles.toml` or an accepted record in `docs/decisions/`; name the principle or the record.

## 3. Check before you report

- Every finding needs a concrete case: "this input or situation leads to this wrong result". No case, no finding.
- Re-read the lines and confirm: the caller exists, the value can really be empty, the code really is unused (search the whole tree, including tests, config and string references).
- A deliberate shortcut marked `shortcut: <the limit>, <when to upgrade>` is a decision, not a finding, unless the expected load already crosses its limit.
- Propose the smallest fix that works; prefer fixes that delete code. Never add layers, frameworks or config the problem does not need.
- No style taste, no "consider", no vague worries.

## 4. Output

Very simple English: short sentences, everyday words. Explain a technical term the first time you use it. The reader may never have seen this code.

Number findings across all groups, so the user can say "fix 2 and 5", and give every finding all four parts, each one or two short sentences:

2. **Orders land on the wrong day** (`billing/close_day.py:L40-52`)
   - **What this is:** At midnight this job closes the day and bills all orders of that day.
   - **Problem:** It takes "today" from the server clock, which runs in UTC. An order placed at 00:30 in Berlin is billed on the day before.
   - **Fix:** Compute the day once in the shop's time zone. One line, nothing else changes.
   - **If we skip it:** Late orders show the wrong date, and accounting fixes them by hand.

Start with `What this repo does:` in two or three sentences, and the load you assumed. Then at most 20 findings, most important first, in three groups, skipping empty ones: **Must fix**, **Should fix**, **Nice to have** (as in the `review-change` skill); if you left smaller ones out, say how many.

End with `Verdict:` in one line (healthy, or what to fix first), `Lean: -<N> lines, -<M> dependencies possible.` when lean findings exist, and `Not checked:` for the parts you did not read or could not run. Nothing found: `What this repo does:`, then `Healthy. Nothing to fix.` and one line on what you checked.

One-shot report; changes no code.
