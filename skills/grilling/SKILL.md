---
name: grilling
description: Interview the user in rounds about a decision tree, recommending an answer for every question from the alpha kit defaults. Use whenever an alpha interview area asks the user to settle decisions, or the user wants their thinking about a project stress-tested.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

<!--
Adapted from the `grilling` skill in mattpocock/skills (https://github.com/mattpocock/skills).

MIT License

Copyright (c) 2026 Matt Pocock

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

# Grilling

Interview the user until you reach a shared understanding. Map the decisions as a **design tree**: every decision branches into the decisions that hang off it.

## Rounds

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. A round is the frontier, asked **one question at a time**: put one question to the user with your recommended answer, wait for the answer, then ask the next. Only when the `AskUserQuestion` tool isn't in your tool list (Claude Code runs headless, and no person is waiting), ask the whole round in one message, each question in the plain-text format below, one blank line between them.

### A choice: in the dialog

When the question has a few fixed answers (a license, a review mode, a yes or no, confirming a summary) and the `AskUserQuestion` tool is in your tool list, ask it there, never as plain text: the user confirms your recommendation with Enter or picks another option.

- One question per call.
- Give it 2 to 4 options, each a few words with a one-line `description` of what it means or costs. Put your recommended option first, its label ending in " (Recommended)", its description saying why when that isn't obvious. Never add an "Other" option: the dialog adds one for a typed answer.
- `header` names the topic in at most 12 characters ("License", "Review mode").
- Set `multiSelect: true` when the user may pick several options (a component's traits).
- The dialog can hide the text above it, so the question names what it's about.
- A yes-or-no question gets the options Yes and No, the recommended one first.

### A draft: in plain text

Ask in plain text when your recommendation is a draft the user would edit rather than pick (a name, the value proposition, the requirements, a sentence per component), when only the user's own words can answer, and for every question when the tool isn't in your tool list (Claude Code runs headless). Format it like so:

<!-- rumdl-disable MD013 -->
<!-- The template's long lines are literal text Claude copies. -->

```text
**Q7. <question title>.** <the question, in one or two sentences> <why you recommend your answer, only if it isn't obvious>
Options: <choice> / <choice> / <choice>
Recommended: <your recommended answer, exactly as the user would send it>
```

<!-- rumdl-enable MD013 -->

- End the question with the `Recommended:` line, holding the answer alone (a list goes on the lines after it), and write nothing after it: Claude Code's prompt suggestion guesses the user's reply from it, so the user can take it into the prompt box with Tab and edit it.
- Add the `Options:` line only when the question has a fixed set of choices, and give each choice in a few words.
- At most one line before the question (the area it's about, at a round's first question). No emoji, horizontal rules, headings or tables, and no blank line inside the question.
- Leave out background the user didn't ask for. If they ask why, explain then.
- Word the question so "yes" accepts your recommended answer. Number questions across the whole interview (Q1, Q2, … keep counting in later rounds).

### Next question

Each answer reshapes the tree: settled decisions push the frontier outward and unblock the questions that depended on them. Ask the round's next question, and when the round is done, recompute the frontier and start the next round. A question whose answer depends on one not yet answered waits for it.

## Where recommendations come from

- Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" defaults show --json` once per session and keep the result. Its `defaults` object holds the kit's preferred answers (the area guide names the key for each question, e.g. `defaults.review.max_lines`).
- Build on the project's earlier answers in `<target>/.claude/alpha/project.json` (`<target>` is the folder the interview is setting up): a later question's recommendation follows from what the user already decided.
- When neither gives you a basis (a product name, say), draft a recommendation from what the user has told you so far, and say it is your suggestion.

## Facts are yours, decisions are the user's

Never ask the user for anything you can look up: installed tool versions, `git config user.name`, whether a folder exists, the latest stable version of a tool. Look it up yourself (dispatch a sub-agent for slow lookups). Only the questions downstream of a running lookup wait for it; ask the frontier's other questions meanwhile. Every _decision_ is the user's: put it to them and wait.

## When the user overrides a default

When the user's answer differs from a kit default:

1. Record it. Ask for the reason if the user hasn't given one. Save with `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '<object>'` (one line, each `'` inside written as `'\''`), sending `overrides` whole.
   - A change to a principle goes in `overrides[]` as `{"principle", "scope", "change", "params", "reason"}`: `principle` is an id from `defaults.principles[].id`; `scope` is `"project"` or `"component:<name>"`; `change` is `"tighten"`, `"loosen"` or `"drop"`; `params` holds any changed parameters (`{}` if none); `reason` is required for `loosen` and `drop`.
   - Any other setting is the area's answer itself; nothing else records it.
2. Ask exactly: "Make this the default for future projects too?"
3. On yes, for a setting, run:
   `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" defaults set --key <dotted key> --value <value> --project <slug> --reason "<user's reason>"`
   - `--key` is the defaults key the recommendation came from, without the `defaults.` prefix (e.g. `review.max_lines`, `identity.license`, `stacks.backend`).
   - `--value` is written as in TOML (`300`, `true`); plain words are stored as text.
   - `--project` is `identity.slug` from project.json.
4. Read the exit code. Never tell the user a default was saved unless the command exits 0.
   - If it exits 0, tell the user the new default is saved with their own defaults (the path it prints), so their next project starts from it.
   - If it exits 3, show the user its message and follow the fix it names, then run it again.
5. On yes for a principle override: the kit can't save principle defaults yet; tell the user so.
6. On no, the override stays in this project only.

## Done

The interview is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Summarize what was settled and wait for the user to confirm you share an understanding before acting on it.
