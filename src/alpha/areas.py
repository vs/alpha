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
# The areas that describe the product rather than wire its tooling: they stay
# open until the user picks one at install or settles it with /alpha:update.
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
