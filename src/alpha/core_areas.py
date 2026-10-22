"""Answers for the areas every project settles: architecture, errors, testing."""

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

    cw = f"{w}.contracts"
    co = obj(get(d, "contracts", w), cw)
    fmt = choice(co, "format", cw, CONTRACT_FORMATS)
    if talk:
        if fmt == "none":
            raise fail(
                f"{cw}.format",
                "is none but the components call each other",
                "Pick the format their interfaces are defined in, e.g. openapi",
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
