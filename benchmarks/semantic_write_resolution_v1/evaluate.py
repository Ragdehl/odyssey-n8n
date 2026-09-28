"""Structural evaluator for the semantic WRITE-resolution Luna gate."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from odyssey_core.experimental_luna_planning import PlannerEscalation
from odyssey_core.request_planning import KnowledgeUnit, RequestPlan, WriteAction

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = Path(__file__).with_name("cases.json")


@dataclass(frozen=True, slots=True)
class Evaluation:
    """Bounded local verdict for one planner-only case."""

    passed: bool
    findings: tuple[str, ...]


def load_registry() -> dict[str, Any]:
    """Load the closed focused-case registry."""
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"version", "fixed_context", "cases"}:
        raise ValueError("semantic WRITE registry shape is invalid")
    return payload


def evaluate(result: Any, expected: str) -> Evaluation:
    """Evaluate only the semantic distinctions this revision intentionally changes."""
    if expected == "fail_closed_ambiguous_pronoun":
        return Evaluation(isinstance(result, PlannerEscalation), ("expected_escalation",))
    action = _single_write(result)
    if action is None:
        return Evaluation(False, ("not_single_write",))
    material = tuple(unit for unit in action.units if not unit.reference_lookup_only)
    lookups = tuple(unit for unit in action.units if unit.reference_lookup_only)
    checks: list[tuple[bool, str]] = [(len(material) == 1, "one_material_unit")]
    if len(material) != 1:
        return _verdict(checks)
    source = material[0]
    if expected == "self_relationship_references":
        checks.extend(
            [
                (source.target.self_target == "self", "self_target"),
                (len(source.references) == 2, "two_references"),
                (len(lookups) == 2, "two_lookup_only_units"),
                (_mentions(source) == {"axel", "denis"}, "coworker_mentions"),
                (_queries(lookups) == {"axel", "denis"}, "coworker_queries"),
            ]
        )
    elif expected == "descriptive_child_target":
        checks.extend(
            [
                (source.target.self_target is None, "not_self"),
                (source.target.relational_reference is None, "ordinary_semantic_target"),
                (_contains(source.target.query, "hijo", "futbol"), "child_query_preserved"),
                (_facts_contain(source, "chocolate"), "chocolate_fact"),
                (not source.references and not lookups, "no_spurious_references"),
            ]
        )
    elif expected == "descriptive_daughter_target":
        relation = source.target.relational_reference
        checks.extend(
            [
                (source.target.self_target is None, "not_self"),
                (relation is not None, "relational_anchor"),
                (relation is not None and relation.source_kind == "self", "self_relation_source"),
                (relation is not None and relation.members == "one", "singular_relation"),
                (
                    relation is not None and _contains(relation.reference, "hija"),
                    "daughter_relation_preserved",
                ),
                (
                    _contains(source.target.query, "hija", "detectives", "animales"),
                    "daughter_query_preserved",
                ),
                (_facts_contain(source, "chocolate"), "chocolate_fact"),
                (not source.references and not lookups, "no_spurious_references"),
            ]
        )
    elif expected == "descriptive_friend_target":
        checks.extend(
            [
                (source.target.self_target is None, "not_self"),
                (source.target.relational_reference is None, "ordinary_semantic_target"),
                (_contains(source.target.query, "amiga", "cen", "ayer"), "friend_query_preserved"),
                (_facts_contain(source, "paris"), "paris_fact"),
                (not source.references and not lookups, "no_spurious_references"),
            ]
        )
    elif expected == "descriptive_target_and_reference":
        relation = source.target.relational_reference
        checks.extend(
            [
                (source.target.self_target is None, "not_self"),
                (relation is not None, "relational_anchor"),
                (relation is not None and relation.source_kind == "self", "self_relation_source"),
                (relation is not None and relation.members == "one", "singular_relation"),
                (
                    relation is not None and _contains(relation.reference, "hijo"),
                    "child_relation_preserved",
                ),
                (_contains(source.target.query, "hijo", "mayor"), "older_child_query"),
                (_facts_contain(source, "cine"), "cinema_fact"),
                (len(source.references) == 1, "one_reference"),
                (len(lookups) == 1, "one_lookup_only_unit"),
                (
                    len(lookups) == 1
                    and _contains(lookups[0].target.query, "amiga", "vive", "lyon"),
                    "friend_reference_query",
                ),
            ]
        )
    elif expected == "qualified_existing_relation_target":
        relation = source.target.relational_reference
        checks.extend(
            [
                (source.target.self_target is None, "not_self"),
                (relation is not None, "relational_anchor"),
                (relation is not None and relation.source_kind == "existing", "existing_source"),
                (
                    relation is not None
                    and relation.source_query is not None
                    and _contains(relation.source_query, "bruno"),
                    "source_query",
                ),
                (
                    relation is not None and _contains(relation.reference, "amigo"),
                    "friend_relation",
                ),
                (
                    _contains(source.target.query, "amigo", "bruno", "lyon"),
                    "full_query_preserved",
                ),
                (_facts_contain(source, "toulouse"), "destination_fact"),
                (not source.references and not lookups, "no_spurious_references"),
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


def _normalize(value: str) -> str:
    return re.sub(
        r"[^a-z0-9 ]",
        "",
        value.lower()
        .replace("ú", "u")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("é", "e")
        .replace("á", "a"),
    )


def _contains(value: str, *needles: str) -> bool:
    normalized = _normalize(value)
    return all(_normalize(needle) in normalized for needle in needles)


def _facts_contain(unit: KnowledgeUnit, needle: str) -> bool:
    return any(_contains(fact, needle) for fact in unit.facts)


def _mentions(unit: KnowledgeUnit) -> set[str]:
    return {_normalize(reference.mention) for reference in unit.references}


def _queries(units: tuple[KnowledgeUnit, ...]) -> set[str]:
    return {_normalize(unit.target.query) for unit in units}


def _verdict(checks: list[tuple[bool, str]]) -> Evaluation:
    failed = tuple(label for passed, label in checks if not passed)
    return Evaluation(not failed, failed or ("all_checks_passed",))
