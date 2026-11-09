from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _common  # noqa: E402


def main() -> None:
    if _common.python_problem():
        sys.exit(0)
    root = _common.project_root(_common.read_input())
    principles = _common.load_principles(root)
    if principles is None:
        sys.exit(0)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SubagentStart",
                    "additionalContext": _common.context_text(root, principles),
                }
            }
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
