import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[3] / "project-files" / "checks" / "palette.py"
PRINCIPLES = """\
[visuals]
palette_check = "{mode}"
palette = ["#FFFFFF (light), #0D1117 (dark)", "#0B5FFF", "hsl(355 72% 47%)"]
palette_files = ["**/*.svg", "**/*.css", "**/*.mmd", "**/*.md"]
exclude = ["**/node_modules/**", "docs/partners/**"]
"""


def repo(tmp_path: Path, files: dict[str, str], mode: str = "enforce") -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    files = {"docs/principles.toml": PRINCIPLES.format(mode=mode), **files}
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True
    )


@pytest.mark.parametrize(
    "line",
    [
        "a { color: #0b5fff }",
        "a { color: #0B5FFF80 }",
        "a { color: rgb(11 95 255) }",
        "a { color: rgba(11, 95, 255, 0.5) }",
        "a { color: hsl(219 100% 52%) }",
        "a { color: #fff; background: #000 }",
        "a { color: #0d1117 }",
        "a { color: rgb(206, 33, 47) }",
        "a { color: var(--accent); border-color: currentColor; fill: rebeccapurple }",
        "a { color: oklch(0.55 0.24 262) }",
    ],
)
def test_palette_colors_in_any_notation_pass(tmp_path: Path, line: str) -> None:
    done = run(repo(tmp_path, {"web/app.css": line + "\n"}))
    assert (done.returncode, done.stdout) == (0, "")


def test_a_color_outside_the_palette_fails_and_says_how_to_proceed(
    tmp_path: Path,
) -> None:
    root = repo(
        tmp_path,
        {
            "web/app.css": "a {\n  color: #ff00aa;\n}\n",
            "docs/flow.svg": '<svg><rect fill="rgb(1, 2, 3)"/></svg>\n',
            "docs/flow.mmd": "style A fill:#0B5FFF,stroke:#123456\n",
        },
    )
    done = run(root)
    assert done.returncode == 1
    assert "web/app.css:2: #ff00aa isn't in the palette" in done.stdout
    assert "docs/flow.svg:1: rgb(1, 2, 3) isn't in the palette" in done.stdout
    assert "docs/flow.mmd:1: #123456 isn't in the palette" in done.stdout
    assert "#0B5FFF isn't" not in done.stdout
    assert "3 color(s) outside the palette" in done.stdout
    for way in ("use a palette color", "/alpha:extend", "exclude", '"advise"'):
        assert way in done.stdout


def test_advise_lists_the_same_colors_without_failing(tmp_path: Path) -> None:
    root = repo(tmp_path, {"web/app.css": "a { color: #ff00aa }\n"}, mode="advise")
    done = run(root, "--advise", "web/app.css")
    assert done.returncode == 0
    assert done.stdout == "web/app.css:1: #ff00aa isn't in the palette\n"


def test_off_checks_nothing(tmp_path: Path) -> None:
    root = repo(tmp_path, {"web/app.css": "a { color: #ff00aa }\n"}, mode="off")
    assert (run(root).returncode, run(root).stdout) == (0, "")


def test_excluded_and_unlisted_files_are_not_read(tmp_path: Path) -> None:
    root = repo(
        tmp_path,
        {
            "web/node_modules/lib/theme.css": "a { color: #ff00aa }\n",
            "docs/partners/acme.svg": '<svg fill="#ff00aa"/>\n',
            "web/src/app.tsx": 'const c = "#ff00aa";\n',
        },
    )
    assert (run(root).returncode, run(root).stdout) == (0, "")


def test_things_that_look_like_hex_colors_are_not_colors(tmp_path: Path) -> None:
    root = repo(
        tmp_path,
        {
            "web/app.css": (
                "#add, #cafe { margin: 0 }\na:hover, #add { margin: 0 }\n"
                ".page:not(.x) #feed {\n  top: 0;\n}\n"
                "a{color:#fff}#feed{margin:0}\n#bed,\n.x { top: 0 }\n"
                "a:hover #feed,\n.y { top: 0 }\n"
            ),
            "docs/icon.svg": (
                '<svg><use href="#abc"/><rect fill="url(#fade)"/>'
                "<text>&#123456;</text></svg>\n"
            ),
        },
    )
    assert (run(root).returncode, run(root).stdout) == (0, "")


def test_markdown_is_read_only_inside_diagram_blocks(tmp_path: Path) -> None:
    doc = (
        "# Notes\n\nIssue #123456 and color #ff00aa in prose.\n\n"
        "```python\nc = '#ff00aa'\n```\n\n"
        "```mermaid\nflowchart LR\n  style A fill:#ff00aa\n```\n"
    )
    done = run(repo(tmp_path, {"docs/notes.md": doc}))
    assert done.returncode == 1
    assert done.stdout.startswith("docs/notes.md:11: #ff00aa isn't in the palette\n")
    assert done.stdout.count("isn't in the palette") == 1


def test_an_enforced_palette_with_no_readable_color_fails_with_a_fix(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path, {"web/app.css": "a { color: #ff00aa }\n"})
    (root / "docs/principles.toml").write_text(
        '[visuals]\npalette_check = "enforce"\npalette = ["oklch(0.5 0.2 260)"]\n'
        'palette_files = ["**/*.css"]\n'
    )
    done = run(root)
    assert done.returncode == 1
    assert "holds no hex, rgb() or hsl() color" in done.stdout
    assert "/alpha:extend" in done.stdout and '"advise" or "off"' in done.stdout
    advised = run(root, "--advise")
    assert (advised.returncode, advised.stdout) == (0, "")


def test_colors_in_a_value_that_wraps_across_lines_are_read(tmp_path: Path) -> None:
    sheet = (
        ".card {\n  box-shadow: 0 0 1px #ff00aa,\n    0 1px 2px #123456;\n"
        "  background: linear-gradient(\n    to right,\n    #abcdef,\n    #fedcba\n"
        "  );\n}\n"
    )
    done = run(repo(tmp_path, {"web/app.css": sheet}))
    assert done.returncode == 1
    for line, color in ((2, "#ff00aa"), (3, "#123456"), (6, "#abcdef"), (7, "#fedcba")):
        assert f"web/app.css:{line}: {color} isn't in the palette" in done.stdout


def test_indented_sass_reads_values_and_skips_selectors(tmp_path: Path) -> None:
    sheet = "#feed\n  color: #ff00aa\n  a:hover\n    color: #0b5fff\n"
    files = {"web/app.sass": sheet}
    root = repo(tmp_path, files)
    (root / "docs/principles.toml").write_text(
        PRINCIPLES.format(mode="enforce").replace('"**/*.css"', '"**/*.sass"')
    )
    done = run(root)
    assert done.stdout.startswith("web/app.sass:2: #ff00aa isn't in the palette\n")
    assert done.stdout.count("isn't in the palette") == 1


def test_a_sass_interpolation_opens_no_block(tmp_path: Path) -> None:
    sheet = ".a\n  color: #ff00aa\n.b\n  width: calc(100% - #{$gap})\n"
    scss = ".a { border: 1px solid #123456 #{$style}; }\n"
    root = repo(tmp_path, {"web/app.sass": sheet, "web/app.css": scss})
    (root / "docs/principles.toml").write_text(
        PRINCIPLES.format(mode="enforce").replace(
            '"**/*.css"', '"**/*.css", "**/*.sass"'
        )
    )
    done = run(root)
    assert "web/app.sass:2: #ff00aa isn't in the palette" in done.stdout
    assert "web/app.css:1: #123456 isn't in the palette" in done.stdout


def test_a_value_after_a_selector_on_one_line_is_still_read(tmp_path: Path) -> None:
    done = run(repo(tmp_path, {"web/app.css": "#feed{color:#ff00aa}\n"}))
    assert done.returncode == 1
    assert "web/app.css:1: #ff00aa isn't in the palette" in done.stdout
    assert "#feed" not in done.stdout


def test_an_unreadable_principles_file_stops_with_a_fix(tmp_path: Path) -> None:
    root = repo(tmp_path, {})
    (root / "docs/principles.toml").write_text("[visuals\n")
    done = run(root)
    assert done.returncode == 2
    assert "docs/principles.toml can't be read" in done.stdout
    assert "git checkout docs/principles.toml" in done.stdout
