"""PreToolUse hook for Bash: git guardrails. Task 9 fills this in."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _common  # noqa: E402


def main() -> None:
    _common.check_python()
    inp = _common.read_input()
    if _common.load_principles(_common.project_root(inp)) is None:
        sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
