"""The user accepts review findings by replying `accept F-xxxxxx` and nothing
else: the only way to accept a finding on a risk path (rewrite spec, R9.4).

Claude Code runs this hook for every prompt, including subagent reports and
messages from other sessions, with no field telling them apart from the user;
requiring the whole prompt to be the command keeps a report that merely
mentions one from accepting anything.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _common
import review

_COMMAND = re.compile(r"accept\s+(F-[0-9a-f]{6}(?:[\s,]+F-[0-9a-f]{6})*)", re.I)
_ID = re.compile(r"F-[0-9a-f]{6}", re.I)
_NEAR_MISS = 80


def say(text: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": text,
                }
            }
        )
    )


def main() -> None:
    if _common.python_problem():
        sys.exit(0)
    inp = _common.read_input()
    root = _common.project_root(inp)
    if _common.checkout_of(root.resolve()) is None:
        sys.exit(0)
    text = inp.get("prompt")
    text = text.strip() if isinstance(text, str) else ""
    command = _COMMAND.fullmatch(text)
    if command is None:
        near = _ID.findall(text)
        if text[:6].lower() == "accept" and near and len(text) <= _NEAR_MISS:
            ids = " ".join(f"F-{i[2:].lower()}" for i in near)
            say(
                "alpha: this looks like accepting a review finding, but nothing was "
                f'accepted. To accept, the user should reply with exactly "accept '
                f'{ids}", nothing else on the line.'
            )
        sys.exit(0)
    wanted = [f"F-{i[2:].lower()}" for i in _ID.findall(command.group(1))]
    last = review.last_review(root)
    open_ids = [str(f["id"]) for f in review.open_findings(last[1] if last else None)]
    unknown = [i for i in wanted if i not in open_ids]
    if last is None or unknown:
        say(
            f"alpha: {', '.join(unknown or wanted)} isn't an open review finding; "
            f"nothing was accepted. Open findings: {', '.join(open_ids) or 'none'}."
        )
        sys.exit(0)
    tree, note = last
    lines: list[str] = []
    for finding in note.get("findings", []):
        if finding.get("id") in wanted:
            finding["status"] = "accepted"
            finding["accepted_by"] = "user"
            lines.append(f"{finding['id']}: {finding['principle']} {finding['file']}")
    review.write_note(root, tree, note)
    say(f"alpha: the user accepted {'; '.join(lines)}.")
    sys.exit(0)


if __name__ == "__main__":
    main()
