"""UserPromptSubmit hook: the user accepts a review finding.

Only a prompt that is exactly "accept F-xxxxxx" (several ids allowed) counts.
Claude Code also runs this hook for subagent reports and messages from other
sessions, and gives no field to tell them apart, so anything more than the bare
command is ignored.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _common  # noqa: E402
import review  # noqa: E402

_COMMAND = re.compile(r"accept\s+(F-[0-9a-f]{6}(?:[\s,]+F-[0-9a-f]{6})*)", re.I)
_ID = re.compile(r"F-[0-9a-f]{6}")


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
    text = inp.get("prompt")
    command = _COMMAND.fullmatch(text.strip()) if isinstance(text, str) else None
    if command is None:
        sys.exit(0)
    root = _common.project_root(inp)
    if _common.load_principles(root) is None:
        sys.exit(0)
    wanted = _ID.findall(command.group(1))
    state = review.ensure_state(root)
    findings = list(state.get("findings", []))
    open_ids = [str(f["id"]) for f in findings if not f.get("accepted")]
    unknown = [i for i in wanted if i not in open_ids]
    if unknown:
        say(
            f"alpha: {', '.join(unknown)} isn't an open review finding; nothing was "
            f"accepted. Current open findings: {', '.join(open_ids) or 'none'}."
        )
        sys.exit(0)
    lines: list[str] = []
    for f in findings:
        if f["id"] in wanted:
            f["accepted"] = True
            lines.append(f"{f['id']}: {f['principle']} {f['file']}: {f['problem']}")
    state["findings"] = findings
    review.save_state(root, state)
    ids = ", ".join(f'"Accepts: {i}"' for i in wanted)
    say(
        f"alpha: the user accepted {'; '.join(lines)}. Record each with the decision "
        f"skill (an {ids} header line; context: the finding; decision: why it "
        "stands)."
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
