"""Answers for the areas every project settles, from architecture to observability."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from alpha.validate import (
    NAME,
    as_list,
    choice,
    fail,
    get,
    obj,
    paths,
    per_component,
    relative,
    string,
    strings,
)

if TYPE_CHECKING:
    from alpha.answers import Component

CONTRACT_FORMATS: tuple[str, ...] = (
    "openapi",
    "json-schema",
    "protobuf",
    "graphql",
    "other",
    "none",
)
ERROR_FORMATS: tuple[str, ...] = (
    "problem-json",
    "message-and-exit-code",
    "user-message",
    "exceptions",
    "structured-log",
    "other",
)
TEST_LEVELS: tuple[str, ...] = ("unit", "integration", "end-to-end", "contract")
UPDATE_TOOLS: tuple[str, ...] = ("dependabot", "manual")
SCHEDULES: tuple[str, ...] = ("daily", "weekly", "monthly")
LOG_FORMATS: tuple[str, ...] = ("json", "logfmt")
CORRELATION: tuple[str, ...] = ("traceparent", "request-id", "none")
TELEMETRY: tuple[str, ...] = ("none", "opentelemetry", "other")


@dataclass(frozen=True)
class Responsibility:
    name: str
    responsibility: str
    calls: tuple[str, ...]


@dataclass(frozen=True)
class Contracts:
    format: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class Term:
    term: str
    meaning: str


@dataclass(frozen=True)
class Architecture:
    components: tuple[Responsibility, ...]
    contracts: Contracts
    glossary: tuple[Term, ...]


@dataclass(frozen=True)
class ErrorFormat:
    name: str
    format: str


@dataclass(frozen=True)
class Errors:
    components: tuple[ErrorFormat, ...]
    categories: tuple[str, ...]


@dataclass(frozen=True)
class TestPlan:
    name: str
    levels: tuple[str, ...]


@dataclass(frozen=True)
class Testing:
    components: tuple[TestPlan, ...]


@dataclass(frozen=True)
class Security:
    secret_store: str
    auth: str
    extra_protected: tuple[str, ...]


@dataclass(frozen=True)
class Dependencies:
    updates: str
    schedule: str


@dataclass(frozen=True)
class LogPlan:
    name: str
    log_format: str
    correlation: str
    telemetry: str


@dataclass(frozen=True)
class Observability:
    components: tuple[LogPlan, ...]


def architecture(
    raw: object, comps: "Sequence[Component] | None", talk: bool, jargon: bool
) -> Architecture:
    w = "architecture"
    d = obj(raw, w)
    names = {c.name for c in comps or ()}
    entries: list[Responsibility] = []
    for i, e in enumerate(as_list(get(d, "components", w), f"{w}.components")):
        ew = f"{w}.components[{i}]"
        eo = obj(e, ew)
        name = string(eo, "name", ew)
        calls = strings(eo, "calls", ew)
        for call in calls:
            if comps is not None and (call == name or call not in names):
                raise fail(
                    f"{ew}.calls",
                    f"{call!r} is not another component",
                    f"Use one of: {', '.join(sorted(names - {name})) or '(none)'}",
                )
        if calls and not talk:
            raise fail(
                f"{ew}.calls",
                f"{name!r} calls {', '.join(calls)} but components_talk is false",
                "Set components_talk to true in the components area, or remove "
                "the call",
            )
        entries.append(Responsibility(name, string(eo, "responsibility", ew), calls))
    if comps is not None:
        per_component(entries, comps, f"{w}.components", ("responsibility", "calls"))
    if talk and not any(e.calls for e in entries):
        raise fail(
            f"{w}.components",
            "components_talk is true but no component calls another",
            "Add each component's calls, or set components_talk to false in the "
            "components area",
        )

    cw = f"{w}.contracts"
    co = obj(get(d, "contracts", w), cw)
    fmt = choice(co, "format", cw, CONTRACT_FORMATS)
    if talk:
        if fmt == "none":
            raise fail(
                f"{cw}.format",
                "is none but the components call each other (components_talk is true)",
                "Pick the format their interfaces are defined in, e.g. openapi, or "
                "set components_talk to false in the components area",
            )
        contract_paths = paths(co, "paths", cw)
    else:
        if fmt != "none" or strings(co, "paths", cw):
            raise fail(
                f"{cw}.format",
                f"is {fmt!r} but the components don't call each other",
                'Set format to "none" and paths to []',
            )
        contract_paths = ()

    terms: list[Term] = []
    seen: set[str] = set()
    for i, t in enumerate(as_list(get(d, "glossary", w), f"{w}.glossary")):
        tw = f"{w}.glossary[{i}]"
        to = obj(t, tw)
        term = string(to, "term", tw)
        if term.casefold() in seen:
            raise fail(f"{tw}.term", f"{term!r} is listed twice", "Keep one entry")
        seen.add(term.casefold())
        terms.append(Term(term, string(to, "meaning", tw)))
    if jargon and not terms:
        raise fail(
            f"{w}.glossary",
            "is empty but the domain has its own vocabulary",
            'Add the domain\'s terms, e.g. {"term": "…", "meaning": "…"}',
        )
    return Architecture(tuple(entries), Contracts(fmt, contract_paths), tuple(terms))


def errors(raw: object, comps: "Sequence[Component] | None") -> Errors:
    w = "errors"
    d = obj(raw, w)
    entries: list[ErrorFormat] = []
    for i, e in enumerate(as_list(get(d, "components", w), f"{w}.components")):
        ew = f"{w}.components[{i}]"
        eo = obj(e, ew)
        entries.append(
            ErrorFormat(string(eo, "name", ew), choice(eo, "format", ew, ERROR_FORMATS))
        )
    if comps is not None:
        per_component(entries, comps, f"{w}.components", ("format",))
    categories = strings(d, "categories", w)
    if not categories:
        raise fail(
            f"{w}.categories",
            "is empty",
            'List the kinds of error, e.g. ["validation", "internal"]',
        )
    for i, category in enumerate(categories):
        if not NAME.fullmatch(category):
            raise fail(
                f"{w}.categories[{i}]",
                f"{category!r} is not a valid category name",
                "Use lowercase letters, digits and hyphens, e.g. not-found",
            )
        if categories.index(category) != i:
            raise fail(
                f"{w}.categories[{i}]", f"{category!r} is listed twice", "Keep one"
            )
    return Errors(tuple(entries), categories)


def testing(raw: object, comps: "Sequence[Component] | None", talk: bool) -> Testing:
    w = "testing"
    d = obj(raw, w)
    entries: list[TestPlan] = []
    for i, e in enumerate(as_list(get(d, "components", w), f"{w}.components")):
        ew = f"{w}.components[{i}]"
        eo = obj(e, ew)
        levels = strings(eo, "levels", ew)
        for j, level in enumerate(levels):
            if level not in TEST_LEVELS:
                raise fail(
                    f"{ew}.levels[{j}]",
                    f"{level!r} is not a test level",
                    f"Use one of: {', '.join(TEST_LEVELS)}",
                )
        if "unit" not in levels or len(set(levels)) != len(levels):
            raise fail(
                f"{ew}.levels",
                f"{list(levels)} must include unit, each level once",
                'Use e.g. ["unit", "integration"]',
            )
        if "contract" in levels and not talk:
            raise fail(
                f"{ew}.levels",
                "has contract tests but the components don't call each other",
                "Remove contract",
            )
        entries.append(TestPlan(string(eo, "name", ew), levels))
    if comps is not None:
        per_component(entries, comps, f"{w}.components", ("levels",))
    return Testing(tuple(entries))


def security(raw: object, comps: "Sequence[Component] | None") -> Security:
    w = "security"
    d = obj(raw, w)
    store = string(d, "secret_store", w, blank=True)
    if (
        comps is not None
        and any(c.traits.deployed for c in comps)
        and not store.strip()
    ):
        raise fail(
            f"{w}.secret_store",
            "is empty but a component is deployed",
            "Say where production secrets live, e.g. your host's secret manager",
        )
    protected = strings(d, "extra_protected", w)
    for i, glob in enumerate(protected):
        relative(glob, f"{w}.extra_protected[{i}]")
    return Security(store, string(d, "auth", w), protected)


def dependencies(raw: object) -> Dependencies:
    w = "dependencies"
    d = obj(raw, w)
    return Dependencies(
        choice(d, "updates", w, UPDATE_TOOLS), choice(d, "schedule", w, SCHEDULES)
    )


def observability(raw: object, comps: "Sequence[Component] | None") -> Observability:
    w = "observability"
    d = obj(raw, w)
    entries: list[LogPlan] = []
    for i, e in enumerate(as_list(get(d, "components", w), f"{w}.components")):
        ew = f"{w}.components[{i}]"
        eo = obj(e, ew)
        entries.append(
            LogPlan(
                string(eo, "name", ew),
                choice(eo, "log_format", ew, LOG_FORMATS),
                choice(eo, "correlation", ew, CORRELATION),
                choice(eo, "telemetry", ew, TELEMETRY),
            )
        )
    if comps is not None:
        per_component(
            entries,
            comps,
            f"{w}.components",
            ("log_format", "correlation", "telemetry"),
            only=lambda c: c.traits.deployed,
            reason="isn't deployed",
        )
    if len(entries) > 1:
        for i, e in enumerate(entries):
            if e.correlation == "none":
                raise fail(
                    f"{w}.components[{i}].correlation",
                    "is none but more than one component is deployed",
                    "Use traceparent (or request-id) so a request can be "
                    "followed across components",
                )
    return Observability(tuple(entries))
