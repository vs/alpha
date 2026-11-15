"""What the kit ships, as a whole: features the rewrite dropped stay gone."""

from pathlib import Path

from alpha.cli import PLUGIN_ROOT

# The kit's shipped files, and alpha's own installed copy of them.
SHIPPED = ("src", "project-files", "skills", "recipes", "defaults", "registry", "bin")
SHIPPED_FILES = ("pyproject.toml", ".claude/settings.json")
OWN_COPY = (".claude/alpha", ".claude/skills", ".claude/agents")


def _texts() -> dict[str, str]:
    paths: list[Path] = []
    for folder in (*SHIPPED, *OWN_COPY):
        paths += [p for p in (PLUGIN_ROOT / folder).rglob("*") if p.is_file()]
    paths += [PLUGIN_ROOT / f for f in SHIPPED_FILES]
    texts: dict[str, str] = {}
    for path in paths:
        if "__pycache__" in path.parts or "state" in path.parts:
            continue
        try:
            texts[path.relative_to(PLUGIN_ROOT).as_posix()] = path.read_text("utf-8")
        except UnicodeDecodeError:
            continue
    return texts


def _naming(*words: str) -> list[str]:
    return sorted(
        f"{rel}: {word}"
        for rel, text in _texts().items()
        for word in words
        if word in text
    )


def test_R14_1_dropped_features_are_gone():
    for gone in ("src/alpha_evals", "bin/alpha-evals", "evals"):
        assert not (PLUGIN_ROOT / gone).exists(), gone
    assert _naming("alpha-evals", "alpha_evals") == []
