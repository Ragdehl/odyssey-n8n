"""Generic structural evaluator for current bounded-existing-source WRITE semantics."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from odyssey_core.request_planning import KnowledgeUnit, RequestPlan, WriteAction

REGISTRY = Path(__file__).with_name("cases.json")


@dataclass(frozen=True, slots=True)
class Evaluation:
    """Return the bounded structural verdict for one current-schema successor case."""

    passed: bool
    findings: tuple[str, ...]


def load_registry() -> dict[str, Any]:
    """Load the closed current-schema registry without consulting historical v1 assets."""
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {
        "version",
        "schema_contract",
        "fixed_context",
        "cases",
    }:
        raise ValueError("current semantic WRITE registry shape is invalid")
    return payload


def evaluate(result: Any, expected: str) -> Evaluation:
    """Evaluate bounded-source semantics without depending on a concrete source note type."""
    action = _single_write(result)
    if action is None:
        return Evaluation(False, ("not_single_write",))
    material = tuple(unit for unit in action.units if not unit.reference_lookup_only)
    lookups = tuple(unit for unit in action.units if unit.reference_lookup_only)
    checks: list[tuple[bool, str]] = [(len(material) == 1, "one_material_unit")]
    if len(material) != 1:
        return _verdict(checks)
    source = material[0]
    if expected == "qualified_bounded_source_target":
        checks.extend(
            [
                (_is_bounded_existing_one(source), "bounded_existing_source"),
                (
                    _contains(source.target.query, "directorio", "faro", "airbus"),
                    "qualified_target",
                ),
                (_facts_contain(source, "paraguas", "rojo"), "target_fact"),
                (not source.references and not lookups, "no_spurious_references"),
            ]
        )
    elif expected == "relational_target_and_one_bounded_reference":
        checks.extend(
            [
                (_is_self_bounded_one(source), "self_bounded_target"),
                (_contains(source.target.query, "hija", "mayor"), "target_qualifier"),
                (_facts_contain(source, "cenar"), "dinner_fact"),
                (len(source.references) == 1 and len(lookups) == 1, "one_reference"),
                (
                    len(lookups) == 1
                    and _is_bounded_existing_one(lookups[0])
                    and _contains(lookups[0].target.query, "directorio", "faro", "airbus"),
                    "bounded_qualified_reference",
                ),
            ]
        )
    elif expected == "relational_target_and_two_bounded_references":
        checks.extend(
            [
                (_is_self_bounded_one(source), "self_bounded_target"),
                (_facts_contain(source, "parque", "sabado"), "literal_saturday_fact"),
                (len(source.references) == 2 and len(lookups) == 2, "two_references"),
                (
                    len(lookups) == 2
                    and all(_is_bounded_existing_one(unit) for unit in lookups)
                    and any(_contains(unit.target.query, "airbus") for unit in lookups)
                    and any(_contains(unit.target.query, "italiano") for unit in lookups),
                    "separately_qualified_bounded_references",
                ),
                (
                    all(not _contains(unit.target.query, "sabado") for unit in lookups),
                    "saturday_not_identity",
                ),
            ]
        )
    else:
        return Evaluation(False, ("unknown_expectation",))
    return _verdict(checks)


def _single_write(result: Any) -> WriteAction | None:
    if not isinstance(result, RequestPlan) or len(result.actions) != 1:
        return None
    action = result.actions[0]
    return action if isinstance(action, WriteAction) else None


def _is_bounded_existing_one(unit: KnowledgeUnit) -> bool:
    relation = unit.target.relational_reference
    return bool(
        relation is not None
        and relation.source_kind == "existing"
        and relation.source_query
        and relation.members == "one"
    )


def _is_self_bounded_one(unit: KnowledgeUnit) -> bool:
    relation = unit.target.relational_reference
    return bool(
        relation is not None
        and relation.source_kind == "self"
        and relation.source_query is None
        and relation.members == "one"
    )


def _normalize(value: str) -> str:
    return re.sub(
        r"[^a-z0-9 ]",
        "",
        value.casefold()
        .replace("ú", "u")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("é", "e")
        .replace("á", "a"),
    )


def _contains(value: str, *needles: str) -> bool:
    normalized = _normalize(value)
    return all(_normalize(needle) in normalized for needle in needles)


def _facts_contain(unit: KnowledgeUnit, *needles: str) -> bool:
    return any(_contains(fact, *needles) for fact in unit.facts)


def _verdict(checks: list[tuple[bool, str]]) -> Evaluation:
    failed = tuple(label for passed, label in checks if not passed)
    return Evaluation(not failed, failed or ("all_checks_passed",))
