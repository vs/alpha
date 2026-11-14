# Specify

You own one part of the specification, settled when the work needs it. The user decides; you bring the options and the evidence.

1. Name what to settle and why now: a spec area left open (architecture, errors, design language, UI, observability, data, accessibility, performance) or the target users, and the task that needs it or the user's request. A spec area already settled is changed with `/alpha:extend` directly, not here.
2. Research before asking. Run Investigation steps 1 to 3 over what the project's code and docs already imply for it, read the kit's default, and when the choice is open, lay out two or three options with what each costs and rules out. Give a slow lookup (a library's limits, a standard's level) to a subagent. A choice you could settle by running something goes to the Prototype playbook first.
3. Settle it through `/alpha:extend settle the <area>`, with your findings as the recommendations. It runs the area's questions with the user, records the decision, and `alpha update` writes the area's doc and switches on the principles it gates.
4. Verify on the real files: docs/product.md no longer lists it under "Not settled yet", its doc exists where the area applies, and docs/principles.toml shows its principles active where they apply. Run the project's checks: a principle that just switched on can flag code written before it; fix that, or record why not with the `decision` skill.
5. Finish with Done (SKILL.md section 3).

**Reply:** what was settled and why now, the options weighed, the choice and its decision record, the principles it switched on and what they now check.
