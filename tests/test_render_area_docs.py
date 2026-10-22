import json
from pathlib import Path
from typing import Any

from helpers import SCENARIOS, TODAY, single_component

from alpha.answers import Answers, load_answers
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source, load_defaults
from alpha.principles import build_principles
from alpha.render.docs import render_docs

FIXTURE = Path(__file__).parent / "fixtures" / "answers_valid.json"
D = load_defaults(Source(PLUGIN_ROOT, True, ""))


def load(tmp_path: Path, source: Path = FIXTURE, mutate: Any = None) -> Answers:
    data = json.loads(source.read_text())
    if mutate:
        mutate(data)
    path = tmp_path / ".claude" / "alpha" / "project.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data))
    return load_answers(path)


def render(a: Answers) -> dict[str, str]:
    return render_docs(a, build_principles(D, a, "0.1.0"), 2026, TODAY)


def section(text: str, title: str) -> str:
    return text.split(f"## {title}\n")[1].split("\n## ")[0]


def test_architecture_lists_responsibilities_contracts_and_errors(tmp_path: Path):
    doc = render(load(tmp_path))["docs/architecture.md"]
    resp = section(doc, "Responsibilities")
    assert "| Component | Responsibility | Calls |" in resp
    assert "| api | Embeds and verifies trust payloads in images. | - |" in resp
    assert "| web | Lets users verify an image in the browser. | api |" in resp
    contracts = section(doc, "Contracts")
    assert "openapi" in contracts and "`api/openapi.yaml`" in contracts
    errors = section(doc, "Errors")
    assert "| api | problem-json |" in errors
    assert "| web | user-message |" in errors
    assert "- not-found" in errors
    assert "Every error a user sees says what went wrong and how to fix it." in errors


def test_single_component_has_no_contracts(tmp_path: Path):
    a = load(tmp_path, SCENARIOS / "python-ml-single.json")
    doc = render(a)["docs/architecture.md"]
    assert "No contracts: components don't call each other." in section(
        doc, "Contracts"
    )


def test_glossary_written_when_terms_exist(tmp_path: Path):
    out = render(load(tmp_path))
    glossary = out["docs/glossary.md"]
    assert glossary.startswith("# Glossary\n")
    assert glossary.index("| Intact |") < glossary.index("| Payload |")  # sorted
    assert "- [Glossary](docs/glossary.md)" in out["CLAUDE.md"]


def test_no_glossary_for_one_component_without_jargon(tmp_path: Path):
    def one(data: dict[str, Any]) -> None:
        single_component(data)
        data["architecture"]["glossary"] = []

    out = render(load(tmp_path, mutate=one))
    assert "docs/glossary.md" not in out
    assert "Glossary" not in out["CLAUDE.md"]


def test_glossary_with_two_components_and_no_terms_yet(tmp_path: Path):
    def empty(data: dict[str, Any]) -> None:
        data["architecture"]["glossary"] = []

    glossary = render(load(tmp_path, mutate=empty))["docs/glossary.md"]
    assert "Add terms as they come up" in glossary


def test_contributing_testing_section(tmp_path: Path):
    text = render(load(tmp_path))["CONTRIBUTING.md"]
    testing = section(text, "Testing")
    assert "| api | unit, integration, contract |" in testing
    assert "`tests/<level>/`" in testing
    assert "names its requirement id (e.g. `R1`)" in testing
    order = [text.index(f"## {t}") for t in ("Testing", "Documentation", "Branching")]
    assert order == sorted(order)


def test_security_doc(tmp_path: Path):
    out = render(load(tmp_path))
    doc = out["docs/security.md"]
    assert doc.startswith("# Security\n")
    assert "Production secrets live in: Fly.io secrets." in section(doc, "Secrets")
    assert "`.env` files, which git ignores" in section(doc, "Secrets")
    assert "API keys for publishers" in section(doc, "Auth")
    protected = section(doc, "Protected paths")
    assert "- `api/keys/**`" in protected
    assert "- `api/uv.lock`" in protected
    assert "Claude can't edit these" in protected
    assert "- [Security](docs/security.md)" in out["CLAUDE.md"]


def test_security_doc_with_nothing_deployed(tmp_path: Path):
    a = load(tmp_path, SCENARIOS / "python-ml-single.json")
    assert "Nothing is deployed." in section(render(a)["docs/security.md"], "Secrets")


def test_dependency_policy_precedes_the_log(tmp_path: Path):
    doc = render(load(tmp_path))["docs/dependencies.md"]
    policy = section(doc, "Policy")
    assert "Adding:" in policy and "Pinning:" in policy
    assert "Dependabot opens weekly update pull requests" in policy
    assert doc.index("## Policy") < doc.index("## Log") < doc.index("| Dependency |")


def test_manual_updates_policy(tmp_path: Path):
    def manual(data: dict[str, Any]) -> None:
        data["dependencies"] = {"updates": "manual", "schedule": "monthly"}

    doc = render(load(tmp_path, mutate=manual))["docs/dependencies.md"]
    assert "Upgrades are manual: check for updates monthly." in doc


def test_observability_doc(tmp_path: Path):
    out = render(load(tmp_path))
    doc = out["docs/observability.md"]
    assert doc.startswith("# Observability\n")
    assert "| Component | Logs | Correlation | Telemetry |" in doc
    assert "| api | json | traceparent | none |" in doc
    assert "`info` in deployed environments, `debug` locally" in doc
    assert "- [Observability](docs/observability.md)" in out["CLAUDE.md"]


def test_no_observability_doc_when_nothing_is_deployed(tmp_path: Path):
    out = render(load(tmp_path, SCENARIOS / "python-ml-single.json"))
    assert "docs/observability.md" not in out
    assert "Observability" not in out["CLAUDE.md"].split("## Docs")[1]
