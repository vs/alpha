import re

_BREAK = re.compile(r"\s*[\r\n]+\s*")


def row(*cells: str) -> str:
    """A table row. A | or line break in an answer would end the cell or the
    table, so pipes are escaped and line breaks become spaces."""
    return (
        "| " + " | ".join(_BREAK.sub(" ", c).replace("|", "\\|") for c in cells) + " |"
    )
