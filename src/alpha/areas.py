AREAS: tuple[str, ...] = (
    "identity",
    "components",
    "architecture",
    "errors",
    "testing",
    "design_language",
    "ui",
    "documentation",
    "build",
    "security",
    "dependencies",
    "observability",
    "releases",
    "data",
    "accessibility",
    "performance",
    "git",
    "agent_workflow",
)
# The areas that describe the product rather than wire its tooling: the
# interview leaves them open and /alpha:go settles them.
SPEC_AREAS: tuple[str, ...] = (
    "architecture",
    "errors",
    "design_language",
    "ui",
    "observability",
    "data",
    "accessibility",
    "performance",
)
SETUP_AREAS: tuple[str, ...] = tuple(a for a in AREAS if a not in SPEC_AREAS)
