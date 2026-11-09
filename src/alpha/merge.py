import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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
