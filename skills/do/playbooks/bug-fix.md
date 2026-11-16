# Bug fix

You own the diagnosis. Every line that ships traces to evidence; a change that "might help" is a guess, and guesses don't ship.

1. Reproduce it yourself on the surface where it was reported: run the command, call the endpoint, drive the app. When it won't reproduce, narrow the conditions, build the trigger by hand, or add logging until it fires. Ask the user only after that, with the specific reason you can't reach it.
2. Find the cause. List the hypotheses, then rule them out with evidence until one survives: logging read while the code runs, a smaller input, `git bisect` between a good and a bad commit. Take the test that rules out the most at once. Investigation step 3 finds when and why the code got this way.
3. Find the root. Trace the symptom back to the first place the system went wrong, then find every caller of the function you'll change, and fix it once there, in the shared code (`fix-at-the-root`). A guard is a fix only when the state it handles is legitimate.
4. Write the test that reproduces it, at the cheapest level that shows the bug: one good test. Run it and paste the output; it must fail with the bug's symptom. Don't commit it on its own; a commit passes the checks (`clean-history`).
5. Fix it with the smallest change the evidence supports. Revert anything a ruled-out hypothesis put in.
6. Verify. The test passes, and the original repro passes on the same surface. "Inconclusive" or a different surface is not a pass; say so.
7. Finish with Done (SKILL.md section 3). The test and the fix go in one `fix` commit whose body names the symptom and the root cause.

**Reply:** what was broken, the root cause with its `file:line`, the fix, and the repro and test output before and after, pasted as they printed.
