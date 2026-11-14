# Perf

You own the measurement. Every change is tied to a number you measured; reading the source is not measuring.

1. Fix the workload and the metric: a case that reproduces the complaint, the number that counts, which direction is better, and the target. Take the budget from `docs/performance.md` when one is set (`perf-budgets`), the user's number when given, or propose one.
2. Build the measurement as one command anyone can rerun, and vet it before trusting it. It prints a count of the work done and of errors; it runs enough times to see past the noise (a median of several runs, with the spread); it finds what limits the number (CPU, I/O, a lock, a sleep); and it measures the work you think, not a warm cache or a failing request. Record the baseline and a green run of the tests.
3. Ground each hypothesis in what step 2 found ("the list is re-sorted on every keypress"), and try them cheapest first:
   1. Don't do it: stop work whose result nothing uses.
   2. Do it once, not again.
   3. Do it less.
   4. Do it later, or when nobody is waiting.
   5. Do it concurrently.
   6. Do it cheaper.
4. One change, one measurement. Keep a change only when the number moves past the noise and the tests stay green; otherwise revert it in full. Never stack untested changes. Keep a table of attempts: hypothesis, change, before, after, kept or reverted.
5. Stop at the target. For a sustained push on one metric, loop step 4 until the target is met and at least the attempts agreed up front are done; on a run of rejects, change the kind of change before you give up. Correctness and simplicity outrank the number: revert a win that breaks behavior, keep a simplification that holds it.
6. Finish with Done (SKILL.md section 3), one commit per kept change, each with its before and after numbers in the body.

**Reply:** the metric and target, baseline to final with the percent change, the measurement command, each kept change on one line, the attempts reverted, and the next idea you'd try.
