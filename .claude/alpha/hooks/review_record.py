from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, NoReturn, cast

sys.path.insert(0, str(Path(__file__).parent))
import _common
import review

AGENT = "principles-reviewer"
CONTRACT = (
    'End your report with one fenced json block: {"tree": …, "checked": '
    '[{"id", "status"}], "findings": [{"principle", "file", "line", "problem", '
    '"fix"}]}, the tree being the Tree line of `python3 '
    ".claude/alpha/hooks/review.py brief`, each checked finding's status "
    '"fixed", "accepted" or "open", line a number, the other fields non-empty '
    'text. Use "findings": [] when the changes comply.'
)
_BLOCK = re.compile(r"```json[ \t]*\n(.*?)```", re.S)
_TREE = re.compile(r"[0-9a-f]{40}")
_TEXT_KEYS = ("principle", "file", "problem", "fix")
# Claude Code may still be appending the reviewer's last entry to its
# transcript when the hook starts, so a report not there yet is looked for
# again this many times, this many seconds apart.
TRANSCRIPT_TRIES = 5
TRANSCRIPT_WAIT = 0.25


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


def _is_prompt(entry: dict[str, Any]) -> bool:
    """A message the reviewer was sent: its task, or a later request."""
    if entry.get("type") != "user" or entry.get("isMeta"):
        return False
    content: object = cast("dict[str, Any]", entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    blocks = cast("list[object]", content) if isinstance(content, list) else []
    return not any(
        cast("dict[str, Any]", b).get("type") == "tool_result"
        for b in blocks
        if isinstance(b, dict)
    )


def _said(entry: dict[str, Any]) -> list[str]:
    """What an assistant entry says: its text, and the text its tool calls
    carry, such as the report of a hand-back."""
    content: object = cast("dict[str, Any]", entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return [content]
    said: list[str] = []
    for raw in cast("list[object]", content) if isinstance(content, list) else []:
        block = cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
        if block.get("type") == "text":
            said.append(str(block.get("text", "")))
        elif block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
            values = cast("dict[str, object]", block["input"]).values()
            said += [v for v in values if isinstance(v, str)]
    return said


def latest_turn(path: object) -> str:
    """What the reviewer said since it was last asked, from its transcript:
    the report can end in a hand-back instead of a last message."""
    if not isinstance(path, str):
        return ""
    try:
        # A line still being written may end mid-character, and won't parse.
        lines = Path(path).read_bytes().decode("utf-8", "replace").splitlines()
    except OSError:
        return ""
    said: list[str] = []
    for line in lines:
        try:
            raw: object = json.loads(line)
        except ValueError:
            continue
        entry = cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
        if _is_prompt(entry):
            said = []
        elif entry.get("type") == "assistant":
            said += _said(entry)
    return "\n".join(said)


def parse(root: Path, message: str) -> dict[str, Any]:
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
    brief = next(
        (b for b in reversed(review.briefs(root)) if b.get("tree") == tree), None
    )
    if brief is None:
        send_back(
            f"{tree} isn't a tree a brief handed out: copy the brief's Tree line, "
            "not its Base line (run the brief first if you haven't)."
        )
    raw = report.get("findings")
    if not isinstance(raw, list):
        send_back('"findings" must be a list.')
    findings: list[dict[str, Any]] = []
    fresh = {str(f) for f in brief.get("fresh", [])}
    for i, item in enumerate(cast("list[Any]", raw)):
        if not isinstance(item, dict):
            send_back(f"findings[{i}] must be an object.")
        f = cast("dict[str, Any]", item)
        line = f.get("line")
        texts_ok = all(isinstance(f.get(k), str) and f[k].strip() for k in _TEXT_KEYS)
        if not texts_ok or not isinstance(line, int) or isinstance(line, bool):
            send_back(f"findings[{i}] is incomplete.")
        if brief.get("kind") == "fix-check" and f["file"] not in fresh:
            send_back(
                f"findings[{i}] is on {f['file']}, which this fix check doesn't review "
                f"afresh: report on its findings in checked, and raise new findings "
                f"only on {', '.join(sorted(fresh)) or 'no file'}."
            )
        findings.append({k: f[k] for k in (*_TEXT_KEYS[:2], "line", *_TEXT_KEYS[2:])})
    checked: dict[str, str] = {}
    for i, item in enumerate(cast("list[Any]", report.get("checked", []) or [])):
        c = cast("dict[str, Any]", item) if isinstance(item, dict) else {}
        if c.get("status") not in review.STATUSES or not isinstance(c.get("id"), str):
            send_back(
                f'checked[{i}] needs an id and a status: "fixed", "accepted" or "open".'
            )
        checked[str(c["id"])] = str(c["status"])
    return {"tree": tree, "brief": brief, "findings": findings, "checked": checked}


def record(root: Path, report: dict[str, Any], principles: dict[str, Any]) -> None:
    """Write the review as a note on its tree. A finding the fix check was given
    keeps its id and gets the status reported for it; only the user accepts
    one on a risk path."""
    brief: dict[str, Any] = report["brief"]
    previous = [cast("dict[str, Any]", f) for f in brief.get("findings", [])]
    carried: list[dict[str, Any]] = []
    for f in previous:
        status = report["checked"].get(str(f["id"]), "open")
        if status == "accepted" and review.on_risk_path(principles, str(f["file"])):
            status = "open"
        carried.append({**f, "status": status})
    new = [{"id": finding_id(f), **f, "status": "open"} for f in report["findings"]]
    review.write_note(
        root,
        report["tree"],
        {
            "kind": brief.get("kind", "review"),
            "branch": brief.get("branch", ""),
            "base": brief.get("base", ""),
            "recorded": int(time.time()),
            "findings": carried + new,
        },
    )


def main() -> None:
    if _common.python_problem():
        sys.exit(0)
    inp = _common.read_input()
    if inp.get("agent_type") != AGENT:
        sys.exit(0)
    root = _common.project_root(inp)
    if _common.checkout_of(root.resolve()) is None:
        sys.exit(0)
    message = inp.get("last_assistant_message")
    text = message if isinstance(message, str) else ""
    for attempt in range(TRANSCRIPT_TRIES):
        if _BLOCK.search(text):
            break
        if attempt:
            time.sleep(TRANSCRIPT_WAIT)
        text = latest_turn(inp.get("agent_transcript_path")) or text
    report = parse(root, text)
    try:
        record(root, report, _common.load_principles(root) or {})
    except review.ReviewError as e:
        send_back(f"{e}.")
    sys.exit(0)


if __name__ == "__main__":
    main()
