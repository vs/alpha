# 0033. alpha asks one question at a time

Date: 2026-11-15
Status: accepted
Kind: product
Supersedes: 0032

## Context

After decision 0032, the user asked: "right now I can get a few questions in a row and I have to answer all of them at once. But I'd prefer to get one questions at a time with recommendation prefiled in the prompt text area, so I can easily confirm or adjust the recommendation".

No skill, hook or plugin can put text into Claude Code's prompt box: the hook outputs have no such field, and the request for a plugin API (anthropics/claude-code#88368) was closed as not planned. The closest feature is Claude Code's prompt suggestions: after a turn, the session's model guesses the user's next message and shows it as grey text, which Tab or Right arrow places in the prompt box. They don't appear while an `AskUserQuestion` dialog is open, are skipped on some turns (a cold prompt cache, after an error, in plan mode), and may be off.

Asked how alpha should ask its one question at a time, the user chose "Mixed": a choice in the dialog, a draft in plain text so the suggestion can offer it. Asked whether the README should tell users to turn prompt suggestions on, they said no.

Without the dialog tool (headless `claude -p`, as in the evals) no person is waiting, and asking one question per exchange would multiply the evals' cost: every resumed call carries the whole interview, and the November 2026 eval run already cost $2 to 3 per exchange by the 17th exchange, about $50 for an interview of 20 to 25 exchanges. One question per exchange would take 70 or more, past the 60-exchange cap. So, Claude's choice: headless runs keep asking a whole round in one message.

## Decision

The grilling skill asks a round's questions one at a time and waits for each answer.

- A question with a few fixed answers (a license, a review mode, a yes or no, confirming a summary) goes in the `AskUserQuestion` dialog, one question per call, the recommended option first and labeled "(Recommended)", when the tool is in Claude's tool list.
- A question whose recommendation is a draft the user would edit (a name, the value proposition, the requirements), or that only the user's own words can answer, is asked in plain text. The message ends with a `Recommended:` line holding the answer alone, exactly as the user would send it, so the prompt suggestion is likely to offer it.
- When the tool is absent (Claude Code runs headless), the whole round goes in one plain-text message, as before.

`/alpha:new-project`, `/alpha:adopt`, `/alpha:extend` and `/alpha:go` point to that rule, and the feature playbook asks for the spec's approval before asking how to build it.

## Consequences

- An interactive interview takes more turns: one per question instead of one per round.
- The prefill is a likely guess, not a guarantee: it depends on the user's prompt-suggestion setting and on Claude Code generating one that turn. When none appears, the user answers "yes" or types their own.
- The area skills keep "round" as a group of independent questions; only how a round is asked changed.
- The evals run headless, so they still ask a round per message and keep their cost and exchange cap; one question at a time, the dialog and the prompt suggestion are checked only by hand.
