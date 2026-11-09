import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from alpha.answers import Answers

_NUMBERED = re.compile(r"\d+")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "decision"


@dataclass(frozen=True)
class Records:
    decisions: tuple[str, ...]
    overrides: tuple[str, ...]

    def to_json(self) -> dict[str, list[str]]:
        return {"decisions": list(self.decisions), "overrides": list(self.overrides)}

    @staticmethod
    def from_json(raw: object) -> "Records | None":
        if not isinstance(raw, dict):
            return None
        out: list[tuple[str, ...]] = []
        for key in ("decisions", "overrides"):
            paths: object = cast(dict[str, object], raw).get(key)
            if not isinstance(paths, list):
                return None
            items = cast(list[object], paths)
            if not all(
                isinstance(p, str) and _NUMBERED.match(Path(p).name) for p in items
            ):
                return None
            out.append(tuple(cast(list[str], items)))
        return Records(out[0], out[1])


def record_number(path: str) -> int:
    return int(re.match(r"\d+", Path(path).name).group())  # type: ignore[union-attr]


def taken_numbers(target: Path) -> set[int]:
    folder = target / "docs" / "decisions"
    return {record_number(p.name) for p in folder.glob("[0-9][0-9][0-9][0-9]-*.md")}


def record_paths(
    a: Answers, known: Records | None = None, taken: Iterable[int] = ()
) -> Records:
    kept_d = known.decisions if known else ()
    kept_o = known.overrides if known else ()
    highest = max(
        [0, *taken, *(record_number(p) for p in (*kept_d, *kept_o))],
    )
    decisions = list(kept_d[: len(a.decisions)])
    for d in a.decisions[len(decisions) :]:
        highest += 1
        decisions.append(f"docs/decisions/{highest:04d}-{slug(d.title)}.md")
    overrides = list(kept_o[: len(a.overrides)])
    for o in a.overrides[len(overrides) :]:
        highest += 1
        overrides.append(f"docs/decisions/{highest:04d}-override-{o.principle}.md")
    return Records(tuple(decisions), tuple(overrides))
