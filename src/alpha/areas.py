INSTALL_AREAS: tuple[str, ...] = (
    "identity",
    "components",
    "testing",
    "documentation",
    "build",
    "security",
    "dependencies",
    "releases",
    "git",
    "agent_workflow",
)
# The areas that describe the product rather than wire its tooling: install
# leaves them open, and only /alpha:specify settles them.
PRODUCT_AREAS: tuple[str, ...] = (
    "requirements",
    "architecture",
    "errors",
    "design_language",
    "ui",
    "accessibility",
    "observability",
    "data",
    "performance",
    "auth",
)
AREAS: tuple[str, ...] = INSTALL_AREAS + PRODUCT_AREAS
