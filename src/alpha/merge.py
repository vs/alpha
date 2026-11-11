import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from alpha.generate import GenerateError

ChangeKind = Literal["new", "change", "merge", "conflict", "stale", "skipped"]


@dataclass(frozen=True)
class Change:
    path: str
    kind: ChangeKind
    text: str | None


def merge3(base: str, ours: str, theirs: str) -> tuple[str, bool]:
    with tempfile.TemporaryDirectory() as tmp:
        paths: dict[str, Path] = {}
        for name, text in (("ours", ours), ("base", base), ("theirs", theirs)):
            paths[name] = Path(tmp) / name
            paths[name].write_text(text, encoding="utf-8", newline="")
        try:
            done = subprocess.run(
                [
                    "git", "merge-file", "-p", "--diff3",
                    "-L", "yours", "-L", "before", "-L", "alpha",
                    str(paths["ours"]), str(paths["base"]), str(paths["theirs"]),
                ],
                capture_output=True,
            )  # fmt: skip
        except OSError as e:
            raise _git_error(str(e)) from e
    if done.returncode < 0 or done.returncode == 255 or done.returncode > 127:
        detail = done.stderr.decode("utf-8", "replace").strip()
        raise _git_error(detail or f"exit {done.returncode}")
    return done.stdout.decode("utf-8"), done.returncode > 0


def _git_error(detail: str) -> GenerateError:
    return GenerateError(
        f"Cannot merge files with git ({detail}). Install git, then rerun "
        'the update ("alpha update").'
    )


def classify(
    path: str, before: str | None, after: str | None, disk: str | None
) -> Change | None:
    if after is None:
        return (
            Change(path, "stale", None)
            if before is not None and disk is not None
            else None
        )
    if before is None:
        if disk is None:
            return Change(path, "new", after)
        if disk == after:
            return None
        return Change(path, "conflict", merge3("", disk, after)[0])
    if after == before:
        return None
    if disk is None:
        return Change(path, "skipped", None)
    if disk == before:
        return Change(path, "change", after)
    text, conflicted = merge3(before, disk, after)
    return Change(path, "conflict" if conflicted else "merge", text)


def union_lines(disk: str, alpha: str, header: str = "# alpha") -> str:
    """`disk` as it is, then alpha's lines it lacks under `header`: for a file
    of independent lines, such as .gitignore."""
    have = {line.strip() for line in disk.splitlines()}
    lines = [line for line in alpha.splitlines() if line.strip()]
    if all(line.strip() in have for line in lines):
        return disk
    # A later line wins in .gitignore, so alpha's negations (!.env.example)
    # follow the patterns it adds, even when the repo has them already.
    missing = [
        line
        for line in lines
        if line.strip() not in have or line.strip().startswith("!")
    ]
    lead = disk if not disk or disk.endswith("\n") else disk + "\n"
    gap = "\n" if lead else ""
    return f"{lead}{gap}{header}\n" + "\n".join(missing) + "\n"


def _union(disk: object, alpha: object, where: str, notes: list[str]) -> object:
    if isinstance(disk, dict) and isinstance(alpha, dict):
        mine = cast("dict[str, object]", disk)
        theirs = cast("dict[str, object]", alpha)
        out = dict(mine)
        for key, value in theirs.items():
            here = f"{where}.{key}" if where else key
            out[key] = _union(mine[key], value, here, notes) if key in mine else value
        return out
    if isinstance(disk, list) and isinstance(alpha, list):
        mine_list = list(cast("list[object]", disk))
        seen = [json.dumps(x, sort_keys=True) for x in mine_list]
        for item in cast("list[object]", alpha):
            if json.dumps(item, sort_keys=True) not in seen:
                mine_list.append(item)
        return mine_list
    if disk != alpha:
        notes.append(
            f"{where}: kept yours ({json.dumps(disk)}), alpha's is {json.dumps(alpha)}"
        )
    return cast(object, disk)


def merge_json(disk: str, alpha: str) -> tuple[str, list[str]] | None:
    """The repo's JSON object with alpha's added: objects merge key by key,
    lists gain alpha's missing items, and a value both set stays the repo's,
    with a note. None when the repo's file isn't a JSON object."""
    try:
        mine: object = json.loads(disk)
    except ValueError:
        return None
    if not isinstance(mine, dict):
        return None
    notes: list[str] = []
    merged = _union(cast("dict[str, object]", mine), json.loads(alpha), "", notes)
    return json.dumps(merged, indent=2) + "\n", notes
