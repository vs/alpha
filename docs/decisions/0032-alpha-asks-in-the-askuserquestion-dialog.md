# 0032. alpha asks in the AskUserQuestion dialog

Date: 2026-11-14
Status: superseded by 0033
Kind: product

## Context

The user asked: "I wonder if it's possible to force using the TUI dialogues whenever alpha asks me something to choose from a few options. Research if that is possible and if so update alpha so it uses the TUI dialogues rather than plain text questions."

The grilling skill told Claude to ask every round as numbered plain text (spec §4, user decision 2026-11-11), so the user had to type replies. Claude sometimes picked the `AskUserQuestion` tool anyway, so some questions showed the dialog and others didn't.

What Claude Code allows: no setting or skill frontmatter makes Claude call a tool (`allowed-tools` only skips permission prompts), so the skills' instructions are the lever. The tool takes 1 to 4 questions per call, 2 to 4 options per question, a header of at most 12 characters, and adds "Other" for a typed answer. In headless `claude -p` (Claude Code 2.1.325, checked 2026-11-14) the tool is absent: not in the tool list, and `ToolSearch` finds no deferred tool of that name.

## Decision

When `AskUserQuestion` is in Claude's tool list, every question with answers alpha can offer goes through the dialog: interview rounds, confirmations, saving a default or a recipe, a spec's approval. The recommended option comes first and its label ends in "(Recommended)". A question with no fixed choices offers Claude's draft as the recommended option, and the user types their own through "Other". Only a question Claude can't draft an answer to is asked in plain text. Without the tool, rounds stay the compact plain text of spec §4.

The rule lives in the grilling skill's "Rounds" section; `/alpha:new-project`, `/alpha:adopt`, `/alpha:extend` and `/alpha:go` each point to it for the questions they ask directly.

## Consequences

- The evals run headless, so they still exercise the plain-text path; the dialog path is checked only by hand in an interactive session.
- A frontier bigger than 4 questions takes several dialog calls in one round.
- If Claude Code later offers the tool in `claude -p`, the evals' simulated user, which reads only the final text, would stop seeing the questions; the evals would then need `--disallowedTools AskUserQuestion`.
