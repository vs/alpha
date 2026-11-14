# Prototype

You own a decision, not code. The prototype is a throwaway instrument; the real build follows the Feature playbook. It is the one playbook where code quality doesn't matter: speed over polish, no tests, no abstractions. The rigor is in picking the right design cheaply.

1. Name the decision the prototype exists to make: which layout, which interaction, which behavior or approach, what the timing really is. No decision, no prototype.
2. Build it outside the repository, in the session's scratch folder, with the lightest tools that show the idea: a plain HTML page, a short script. It is never committed and never imports secrets.
3. When comparing options, build each one, labeled, behind one switch (a button, a key, a flag), and add an option the user didn't ask for when you see one.
4. Look at the result: screenshot each variant, print the output, log the timing. The observation is the test.
5. Recommend one, with the evidence and the tradeoffs. The user decides when it's a product call; record the choice with the `decision` skill when later work must follow it.

**Reply:** the options tried, the evidence for each, the tradeoffs, your recommendation, the scratch path, and that the prototype is throwaway.
