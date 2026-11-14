"""List the colors that aren't in the design language's palette.

Usage, from the repo root: palette.py [--advise] [file ...]
Reads [visuals] in docs/principles.toml: `palette` (the declared colors),
`palette_files` (the globs to read) and `exclude`. With no files, reads every
file git would track; in Markdown, only the diagram blocks. Stdlib only.

It is lenient on purpose: it reads hex, rgb() and hsl() literals, ignores
alpha, and lets a channel differ by a rounding step. Black, white, named
colors, variables and every other notation pass; the reviewer judges those.
Prints one `file:line: color` per finding and exits 1; with --advise, exits 0.
"""

import colorsys
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import _common

PRINCIPLES = "docs/principles.toml"
HEX = re.compile(
    r"(?<![\w&/])#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])"
)
RGB = re.compile(r"rgba?\(\s*([\d.]+%?)[\s,]+([\d.]+%?)[\s,]+([\d.]+%?)", re.I)
HSL = re.compile(r"hsla?\(\s*([\d.]+)(?:deg)?[\s,]+([\d.]+)%[\s,]+([\d.]+)%", re.I)
# `#abc` after these is a link to an element, not a color.
REFERENCES = ("url(", 'href="', "href='")
# In these, `#abc` can be a selector (`#add { ... }`).
SELECTOR_STYLES = {".css", ".scss", ".sass", ".less", ".pcss", ".postcss"}
MARKDOWN = {".md", ".markdown", ".mdx"}
FENCE = re.compile(r"^\s*(```+|~~~+)\s*\{?\.?(\w*)")
DIAGRAMS = {"mermaid", "d2", "plantuml", "puml", "dot", "graphviz"}
ALWAYS = [(0, 0, 0), (255, 255, 255)]
ROUNDING = 2
BLOCK_OR_END = re.compile(r"[{;}]")
# Sass's `#{$name}`: its braces open no block.
INTERPOLATION = re.compile(r"#\{[^}]*\}")
Rgb = tuple[int, int, int]


def _channel(text: str) -> int:
    if text.endswith("%"):
        return round(float(text[:-1]) * 255 / 100)
    return round(float(text))


def _selector(sheet: str, begin: int, end: int) -> bool:
    """Whether the `#abc` at sheet[begin:end] is a selector: its block opens
    before any value ends. A sheet with no braces or semicolons after it (the
    indented Sass syntax) has a selector where no colon precedes it on its line."""
    after = BLOCK_OR_END.search(sheet, end)
    if after is not None:
        return after.group() == "{"
    return ":" not in sheet[sheet.rfind("\n", 0, begin) + 1 : begin]


def colors(line: str, sheet: str = "", start: int = 0) -> list[tuple[str, Rgb]]:
    """Each color literal in the line, with its red, green and blue. `sheet` is
    the stylesheet the line sits in, at `start`: there `#abc` can be a selector."""
    found: list[tuple[str, Rgb]] = []
    for m in HEX.finditer(line):
        before = line[: m.start()]
        if before.endswith(REFERENCES) or (
            sheet and _selector(sheet, start + m.start(), start + m.end())
        ):
            continue
        digits = m.group(1)
        if len(digits) < 6:
            digits = "".join(ch * 2 for ch in digits)
        found.append(
            (
                m.group(0),
                (int(digits[:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)),
            )
        )
    for m in RGB.finditer(line):
        r, g, b = (_channel(part) for part in m.groups())
        found.append((m.group(0) + ")", (r, g, b)))
    for m in HSL.finditer(line):
        hue, sat, light = (float(part) for part in m.groups())
        r, g, b = colorsys.hls_to_rgb(hue % 360 / 360, light / 100, sat / 100)
        found.append(
            (m.group(0) + ")", (round(r * 255), round(g * 255), round(b * 255)))
        )
    return found


def in_palette(color: Rgb, palette: list[Rgb]) -> bool:
    return any(
        all(abs(a - b) <= ROUNDING for a, b in zip(color, known, strict=True))
        for known in palette
    )


def diagram_lines(lines: list[str]) -> list[tuple[int, str]]:
    """The numbered lines inside a Markdown file's diagram blocks."""
    inside: list[tuple[int, str]] = []
    fence = ""
    wanted = False
    for n, line in enumerate(lines, start=1):
        m = FENCE.match(line)
        if m and not fence:
            fence, wanted = m.group(1), m.group(2).lower() in DIAGRAMS
        elif m and m.group(1).startswith(fence):
            fence = ""
        elif fence and wanted:
            inside.append((n, line))
    return inside


def tracked(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        print(f"palette: git ls-files failed: {out.stderr.strip()}")
        sys.exit(2)
    return sorted({p for p in out.stdout.split("\0") if p})


def findings(
    root: Path, files: list[str], visuals: dict[str, Any], palette: list[Rgb]
) -> list[str]:
    def globs(key: str) -> list[str]:
        return [str(g) for g in visuals.get(key, [])]

    out: list[str] = []
    for rel in files:
        if not _common.matches(rel, globs("palette_files")) or _common.matches(
            rel, globs("exclude")
        ):
            continue
        try:
            lines = (root / rel).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        suffix = Path(rel).suffix.lower()
        numbered = (
            diagram_lines(lines) if suffix in MARKDOWN else list(enumerate(lines, 1))
        )
        sheet = (
            INTERPOLATION.sub(lambda m: " " * len(m.group()), "\n".join(lines))
            if suffix in SELECTOR_STYLES
            else ""
        )
        starts = [0]
        for line in lines:
            starts.append(starts[-1] + len(line) + 1)
        for n, line in numbered:
            for literal, rgb in colors(line, sheet, starts[n - 1]):
                if not in_palette(rgb, [*palette, *ALWAYS]):
                    out.append(f"{rel}:{n}: {literal} isn't in the palette")
    return out


def main() -> int:
    args = sys.argv[1:]
    advise = "--advise" in args
    named = [a for a in args if a != "--advise"]
    root = Path.cwd()
    try:
        with (root / PRINCIPLES).open("rb") as f:
            visuals: dict[str, Any] = tomllib.load(f).get("visuals", {})
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(
            f"palette: {PRINCIPLES} can't be read ({e}). Fix it, or restore it "
            f"with git checkout {PRINCIPLES}."
        )
        return 2
    if visuals.get("palette_check", "off") == "off":
        return 0
    declared = [str(value) for value in visuals.get("palette", [])]
    palette = [rgb for value in declared for _, rgb in colors(value)]
    if not palette:
        if advise:
            return 0
        print(
            "palette: the design language's palette holds no hex, rgb() or hsl() "
            "color, so no color can be checked against it. Write the palette's "
            "values in one of those forms (/alpha:extend), or set palette_check "
            f'to "advise" or "off" under [visuals] in {PRINCIPLES}.'
        )
        return 1
    found = findings(root, named or tracked(root), visuals, palette)
    for line in found:
        print(line)
    if not found or advise:
        return 0
    print(
        f"{len(found)} color(s) outside the palette in docs/design-language.md. "
        "For each: use a palette color; or add the color to the design language "
        "with /alpha:extend; or, for a third-party file, add its path to "
        f"exclude under [visuals] in {PRINCIPLES}. To make this check advisory, "
        'set palette_check = "advise" there.'
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
