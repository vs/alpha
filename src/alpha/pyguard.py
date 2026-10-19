MIN_PYTHON = (3, 11)


def check_python(version: tuple[int, int]) -> str | None:
    """Return a fix-it message if the interpreter is too old, else None."""
    if version >= MIN_PYTHON:
        return None
    return (
        f"alpha needs Python 3.11+ (found {version[0]}.{version[1]}). "
        'Install a newer one with "brew install python" or '
        '"uv python install 3.12", then retry.'
    )
