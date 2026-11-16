import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from alpha.generate import GenerateError
from alpha.shell import GitError, git

ChangeKind = Literal[
    "new", "change", "merge", "conflict", "stale", "skipped", "deleted"
]


@dataclass(frozen=True)
class Change:
    path: str
    kind: ChangeKind
    text: str | None


def merge3(base: str, ours: str, theirs: str) -> tuple[str, bool]:
    """git merge-file of the three texts. The result is read back from the
    file git writes, as bytes: captured output would have its CRLFs turned
    into LFs."""
    with tempfile.TemporaryDirectory() as tmp:
        paths: dict[str, Path] = {}
        for name, text in (("ours", ours), ("base", base), ("theirs", theirs)):
            paths[name] = Path(tmp) / name
            paths[name].write_text(text, encoding="utf-8", newline="")
        try:
            done = git(
                Path(tmp),
                "merge-file", "--diff3",
                "-L", "yours", "-L", "before", "-L", "alpha",
                str(paths["ours"]), str(paths["base"]), str(paths["theirs"]),
            )  # fmt: skip
        except GitError as e:
            raise _git_error(str(e)) from e
        if done.returncode < 0 or done.returncode == 255 or done.returncode > 127:
            raise _git_error(done.stderr.strip() or f"exit {done.returncode}")
        return paths["ours"].read_bytes().decode("utf-8"), done.returncode > 0


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


ALPHA_HOOKS = ".claude/alpha/hooks/"


def is_alpha_hook(entry: object) -> bool:
    """Whether a Claude Code hook entry runs one of alpha's hook scripts."""
    return isinstance(entry, dict) and ALPHA_HOOKS in str(
        cast("dict[str, object]", entry).get("command", "")
    )


def strip_alpha_hooks(hooks: object) -> dict[str, object]:
    """Claude Code's hooks table without alpha's entries, and without a group
    or event that only held them."""
    if not isinstance(hooks, dict):
        return {}
    kept: dict[str, object] = {}
    for event, groups in cast("dict[str, object]", hooks).items():
        if not isinstance(groups, list):
            kept[event] = groups
            continue
        new_groups: list[object] = []
        for raw in cast("list[object]", groups):
            if not isinstance(raw, dict):
                new_groups.append(raw)
                continue
            group = cast("dict[str, object]", raw)
            entries: object = group.get("hooks")
            if not isinstance(entries, list):
                new_groups.append(group)
                continue
            listed = cast("list[object]", entries)
            mine = [h for h in listed if not is_alpha_hook(h)]
            if mine:
                new_groups.append({**group, "hooks": mine})
        if new_groups:
            kept[event] = new_groups
    return kept


def _permissions(settings: object) -> dict[str, set[str]]:
    perms: object = (
        cast("dict[str, object]", settings).get("permissions")
        if isinstance(settings, dict)
        else None
    )
    if not isinstance(perms, dict):
        return {}
    return {
        kind: {str(r) for r in cast("list[object]", rules)}
        for kind, rules in cast("dict[str, object]", perms).items()
        if isinstance(rules, list)
    }


def merge_settings(
    disk: str, alpha: str, base: str | None
) -> tuple[str, list[str]] | None:
    """The repo's .claude/settings.json with alpha's entries brought to alpha's
    render: alpha's hook entries are replaced, a permission rule alpha's last
    render had and this one doesn't is dropped, and the user's own entries
    stay (a value both set stays the user's, with a note). None when the
    repo's file isn't a JSON object."""
    try:
        mine: object = json.loads(disk)
    except ValueError:
        return None
    if not isinstance(mine, dict):
        return None
    current = dict(cast("dict[str, object]", mine))
    theirs: object = json.loads(alpha)
    gone = {
        kind: rules - _permissions(theirs).get(kind, set())
        for kind, rules in _permissions(json.loads(base) if base else {}).items()
    }
    perms: object = current.get("permissions")
    if isinstance(perms, dict):
        current["permissions"] = {
            kind: [
                r for r in cast("list[object]", rules) if r not in gone.get(kind, ())
            ]
            if isinstance(rules, list)
            else rules
            for kind, rules in cast("dict[str, object]", perms).items()
        }
    if "hooks" in current:
        current["hooks"] = strip_alpha_hooks(current["hooks"])
    notes: list[str] = []
    merged = _union(current, theirs, "", notes)
    return json.dumps(merged, indent=2) + "\n", notes
