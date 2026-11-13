from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn, cast

sys.path.insert(0, str(Path(__file__).parent))
import _common  # noqa: E402
import review  # noqa: E402

AGENT = "principles-reviewer"
CONTRACT = (
    'End your report with one fenced json block: {"tree": …, "findings": '
    '[{"principle", "file", "line", "problem", "fix"}]}, the tree being '
    "the Tree line of `python3 .claude/alpha/hooks/review.py brief`, line a "
    'number, the other fields non-empty text. Use "findings": [] when the '
    "changes comply."
)
_BLOCK = re.compile(r"```json[ \t]*\n(.*?)```", re.S)
_TREE = re.compile(r"[0-9a-f]{40}")
_TEXT_KEYS = ("principle", "file", "problem", "fix")


def send_back(problem: str) -> NoReturn:
    print(json.dumps({"decision": "block", "reason": f"{problem} {CONTRACT}"}))
    sys.exit(0)


def is_tree(root: Path, sha: str) -> bool:
    try:
        proc = subprocess.run(
            ["git", "cat-file", "-t", sha], cwd=root, capture_output=True, text=True
        )
    except OSError:
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "tree"


def finding_id(f: dict[str, Any]) -> str:
    key = f"{f['principle']}|{f['file']}|{f['problem']}"
    return "F-" + hashlib.sha1(key.encode()).hexdigest()[:6]


def parse(root: Path, message: str) -> tuple[str, list[dict[str, Any]]]:
    blocks = _BLOCK.findall(message)
    if not blocks:
        send_back("Your report has no json block.")
    try:
        data: object = json.loads(blocks[-1])
    except ValueError as e:
        send_back(f"The json block isn't valid JSON ({e}).")
    if not isinstance(data, dict):
        send_back("The json block must be an object.")
    report = cast("dict[str, Any]", data)
    tree = report.get("tree")
    if (
        not isinstance(tree, str)
        or not _TREE.fullmatch(tree)
        or not is_tree(root, tree)
    ):
        send_back(f"{tree!r} isn't the tree from the brief.")
    if tree not in review.load_state(root).get("briefed", []):
        send_back(
            f"{tree} isn't a tree a brief handed out: copy the brief's Tree line, "
            "not its Reviewed line (run the brief first if you haven't)."
        )
    raw = report.get("findings")
    if not isinstance(raw, list):
        send_back('"findings" must be a list.')
    findings: list[dict[str, Any]] = []
    for i, item in enumerate(cast("list[Any]", raw)):
        if not isinstance(item, dict):
            send_back(f"findings[{i}] must be an object.")
        f = cast("dict[str, Any]", item)
        line = f.get("line")
        texts_ok = all(isinstance(f.get(k), str) and f[k].strip() for k in _TEXT_KEYS)
        if not texts_ok or not isinstance(line, int) or isinstance(line, bool):
            send_back(f"findings[{i}] is incomplete.")
        findings.append({k: f[k] for k in (*_TEXT_KEYS[:2], "line", *_TEXT_KEYS[2:])})
    return tree, findings


def main() -> None:
    if _common.python_problem():
        sys.exit(0)
    inp = _common.read_input()
    if inp.get("agent_type") != AGENT:
        sys.exit(0)
    root = _common.project_root(inp)
    if _common.load_principles(root) is None:
        sys.exit(0)
    message = inp.get("last_assistant_message")
    tree, findings = parse(root, message if isinstance(message, str) else "")
    state = review.ensure_state(root)
    accepted = {
        str(f.get("id")) for f in state.get("findings", []) if f.get("accepted")
    }
    recorded = [
        {"id": (fid := finding_id(f)), **f, "accepted": fid in accepted}
        for f in findings
    ]
    if not recorded:
        state["reviewed_tree"] = tree
    state["findings"] = recorded
    state["reviewed_for"] = tree
    review.save_state(root, state)
    sys.exit(0)


if __name__ == "__main__":
    main()
