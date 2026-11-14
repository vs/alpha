---
name: review-change
description: Quality review of a change in plain English - is the logic right, is it safe, does it hold at the project's expected load, is risky code tested, is it fast enough, is every line needed, does it keep the project's principles. Reads the connected code, not only the diff. One-shot report that changes no code. Use for /review-change, "review this", "review the last commit", "review my branch", "is this over-engineered".
---

<!--
Adapted from the `ponytail-review` skill in DietrichGebert/ponytail (https://github.com/DietrichGebert/ponytail).

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

# Review a change

Review a change like the senior developer who will be paged when it breaks. Order of importance: correct, safe, holds under load, tested, fast, lean. Lean still matters: every extra line must be read, tested and fixed later. This is a report the user asked for, so give it in full. It doesn't replace the principles-reviewer agent, which gates what reaches main.

## 1. Understand first

- Review what the user names: uncommitted or staged changes, a branch, or files. Nothing named: the uncommitted changes, or the last commit if there are none.
- Read the diff, then the code it touches: callers of every changed function, the functions it calls, the tests, the docs.
- Trace the real flow: where data comes in, what is stored, what goes out. When a signature, return value or behavior changes, search for every caller.
- Take the expected load from `docs/performance.md`; when it isn't recorded, infer it from the README and deploy config. Judge scale against it, and say which load you used.

## 2. Look for

1. **Bug:** wrong result, crash, missed edge case (empty, zero, last item, rounding, time zones), a caller broken by the change, a fix applied in one caller while the shared function stays broken.
2. **Risk:** security holes (injection, weak randomness, secrets, missing checks on input from users), data loss (errors swallowed, writes in the wrong order, no transaction).
3. **Scale:** fine for one user, wrong at the expected load: check-then-write races, the same work done by every process, memory or lists that only grow, a query per item, O(n^2) on big input, per-process state that must be shared.
4. **Missing test:** risky logic (a branch, a parser, money, security, data writes, a bug fix) with no test that fails when it breaks. One good test, not coverage.
5. **Speed:** big slowdowns are problems; small wins (work repeated in a hot loop) are suggestions, unless a budget in `docs/performance.md` makes them count.
6. **Lean:** code that should not exist or should be smaller: dead code, unused options and config, speculative features; a helper the repo already has (name the path); what the standard library, the platform or an installed dependency already does; an abstraction with one implementation; near-copies that must change together; a function doing several unrelated jobs (split by job, never by line count).
7. **The project's own rules:** anything that breaks a principle in `docs/principles.toml` or an accepted record in `docs/decisions/`; name the principle or the record.

## 3. Check before you report

- Every finding needs a concrete case: "this input or situation leads to this wrong result". No case, no finding.
- A bug finding needs a run: a failing test, a short script that calls the real code, or a command, with the output it printed beside the output it should print. Keep the script out of the change. What you could not run goes under `Not checked:`, not under the findings.
- Find the fact the change is safe because of. Most risky-looking changes are safe because of one fact ("this only drops entries nothing reads any more"). Name it and prove it by running the real code, or say it is unproven.
- Re-read the lines and confirm: the caller exists, the value can really be empty, the code really is unused (search the whole tree, including tests, config and string references).
- A deliberate shortcut marked `shortcut: <the limit>, <when to upgrade>` is a decision, not a finding, unless the expected load already crosses its limit.
- Propose the smallest fix that works; prefer fixes that delete code. Never add layers, frameworks or config the problem does not need.
- No style taste, no "consider", no vague worries.

## 4. Output

Very simple English: short sentences, everyday words. Explain a technical term the first time you use it. The reader may never have seen this code.

Number findings across all groups, so the user can say "fix 2 and 5", and give every finding all four parts, each one or two short sentences; a bug's **Problem** ends with the command you ran and what it printed:

2. **Orders land on the wrong day** (`billing/close_day.py:L40-52`)
   - **What this is:** At midnight this job closes the day and bills all orders of that day.
   - **Problem:** It takes "today" from the server clock, which runs in UTC. An order placed at 00:30 in Berlin is billed on the day before.
   - **Fix:** Compute the day once in the shop's time zone. One line, nothing else changes.
   - **If we skip it:** Late orders show the wrong date, and accounting fixes them by hand.

Start with `What this change does:` in two or three sentences, then `Safe because:` with the fact and its proof, or `unproven`. Then the findings in three groups, skipping empty ones: **Must fix** (bug, security, data loss, breaks at the expected load), **Should fix** (risky code without a test, real slowness, duplication, a function that mixes jobs, code that should not exist, a broken principle), **Nice to have** (small speed-ups, shorter forms).

End with `Verdict: Ship.` or `Verdict: fix 1 and 3 first.`, then `Lean: -<N> lines possible.` when lean findings exist, then `Not checked:` in one line if something mattered that you could not check. Nothing found: `What this change does:` and `Safe because:`, then `Looks good. Ship.` and one line on what you checked.

Lists findings; changes no code.
