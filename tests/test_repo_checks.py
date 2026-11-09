import json
from pathlib import Path
from typing import Any

from helpers import SCENARIOS

from alpha.answers import Answers, load_answers
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source, load_defaults
from alpha.principles import build_principles, render_principles
from alpha.registry import load_registry
from alpha.repo_checks import repo_checks

SOURCE = Source(PLUGIN_ROOT, True, "")
D = load_defaults(SOURCE)
REGISTRY = load_registry(SOURCE)
TABLE = [
    "actions",
    "secrets",
    "vulns",
    "typos",
    "markdown",
    "links",
    "links-online",
    "agent-config",
    "migrations",
    "squawk",
    "review-dates",
    "toolchain",
]


def scenario(tmp_path: Path, name: str, mutate: Any = None) -> tuple[Answers, Any]:
    data = json.loads((SCENARIOS / f"{name}.json").read_text())
    if mutate:
        mutate(data)
    path = tmp_path / ".claude" / "alpha" / "project.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data))
    return load_answers(path), data


def ids(tmp_path: Path, name: str, mutate: Any = None) -> list[str]:
    a, _ = scenario(tmp_path, name, mutate)
    principles = build_principles(D, a, "0.1.0", registry=REGISTRY)
    return [c.id for c in repo_checks(a, principles, REGISTRY)]


def test_catalog_web_api(tmp_path: Path):
    a, data = scenario(tmp_path, "web-ts-plus-python-api")
    principles = build_principles(D, a, "0.1.0", registry=REGISTRY)
    got = [c.id for c in repo_checks(a, principles, REGISTRY)]
    postgres = any(
        "postgres" in store["storage"].lower() for store in data["data"]["components"]
    )
    assert postgres  # the scenario's store is PostgreSQL
    expected = [i for i in TABLE if i != "squawk" or postgres]
    assert got == expected
    assert principles["data"]["squawk_paths"] == ["api/migrations/versions/**"]
    vulns = next(c for c in repo_checks(a, principles, REGISTRY) if c.id == "vulns")
    assert vulns.globs == ("api/uv.lock", "web/pnpm-lock.yaml")


def test_catalog_ml_single(tmp_path: Path):
    got = ids(tmp_path, "python-ml-single")
    assert "migrations" not in got
    assert "squawk" not in got
    assert got == [i for i in TABLE if i not in ("migrations", "squawk")]


def test_no_squawk_for_a_store_that_is_not_postgres(tmp_path: Path):
    def sqlite(data: dict[str, Any]) -> None:
        data["data"]["components"][0]["storage"] = "SQLite"

    got = ids(tmp_path, "web-ts-plus-python-api", sqlite)
    assert "migrations" in got
    assert "squawk" not in got


def test_no_actions_check_without_github(tmp_path: Path):
    def no_ci(data: dict[str, Any]) -> None:
        data["build"]["ci"] = "none"
        data["overrides"].append(
            {
                "principle": "build-hosting-upfront",
                "scope": "project",
                "change": "loosen",
                "params": {},
                "reason": "No CI yet.",
            }
        )

    got = ids(tmp_path, "rust-cli", no_ci)
    assert "actions" not in got
    assert "typos" in got


def test_checks_use_the_registry_commands(tmp_path: Path):
    a, _ = scenario(tmp_path, "web-ts-plus-python-api")
    principles = build_principles(D, a, "0.1.0", registry=REGISTRY)
    checks = {c.id: c for c in repo_checks(a, principles, REGISTRY)}
    for check in checks.values():
        if check.tool and check.id not in ("squawk", "links-online"):
            pin = REGISTRY.tool(check.tool).pin
            assert pin is not None
            assert check.command == pin.command
    assert checks["links-online"].command == "lychee --no-progress ."
    assert checks["squawk"].tool == "squawk"
    assert checks["migrations"].tool is None


def test_principles_carry_stop_checks(tmp_path: Path):
    a, _ = scenario(tmp_path, "web-ts-plus-python-api")
    principles = build_principles(D, a, "0.1.0", registry=REGISTRY)
    checks = repo_checks(a, principles, REGISTRY)
    entries = principles["repo_checks"]
    assert [e["id"] for e in entries] == [c.id for c in checks if c.when != "schedule"]
    for entry in entries:
        assert entry["command"] == f"mise run check:{entry['id']}"
        assert set(entry) == {"id", "command", "globs", "stop"}
    stop = {e["id"] for e in entries if e["stop"]}
    assert stop == {"actions", "typos", "markdown", "links", "agent-config"}


def test_principles_file_round_trips_repo_checks(tmp_path: Path):
    import tomllib

    a, _ = scenario(tmp_path, "web-ts-plus-python-api")
    principles = build_principles(D, a, "0.1.0", registry=REGISTRY)
    read = tomllib.loads(render_principles(principles))
    assert read["repo_checks"] == principles["repo_checks"]
    assert read["data"]["squawk_paths"] == ["api/migrations/versions/**"]
