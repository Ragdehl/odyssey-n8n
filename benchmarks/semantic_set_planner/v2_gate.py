"""Frozen future planner gate for the subject-independent semantic-set contract."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from benchmarks.semantic_set_planner.gate import (
    Evaluation,
    _contains_all,
    _contains_all_sets,
    _contains_any,
    _has_unsafe_authority,
    conservative_preflight,
    load_registry,
)
from odyssey_core.experimental_luna_planning import ExperimentalPlannerResult, PlannerEscalation
from odyssey_core.request_planning import PlannerClarification, RequestPlan, RetrieveAction

CASES_PATH = Path(__file__).with_name("v2_cases.json")
ORACLE_PATH = Path(__file__).with_name("v2_oracle.json")
TEACHING_EXAMPLES_PATH = Path(__file__).with_name("v2_teaching_examples.json")


def load_v2_registry() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Load the corrected six-case contract without changing historical gate artifacts."""
    return load_registry(CASES_PATH, ORACLE_PATH)


def evaluate_v2_result(result: ExperimentalPlannerResult, oracle: Mapping[str, Any]) -> Evaluation:
    """Evaluate one locally validated result against the topology-neutral contract."""
    if isinstance(result, (PlannerEscalation, PlannerClarification)):
        return Evaluation("FAIL", ("unexpected_non_plan_outcome",))
    if not isinstance(result, RequestPlan):
        return Evaluation("FAIL_CLOSED", ("unknown_validated_result",))
    if len(result.actions) != 1 or not isinstance(result.actions[0], RetrieveAction):
        return Evaluation("FAIL", ("wrong_action_kind_or_count",))
    if _has_unsafe_authority(result):
        return Evaluation("FAIL", ("unsafe_planner_authority",))
    selection = result.actions[0].plan
    kind = oracle["kind"]
    if kind == "semantic_set":
        return _evaluate_semantic_set(selection, oracle)
    if kind == "singular_relational":
        if selection.semantic_set is not None:
            return Evaluation("FAIL", ("semantic_set_on_relational_regression",))
        relational = selection.relational_reference
        if (
            relational is None
            or relational.source_kind != "self"
            or relational.members != "one"
            or not _contains_any(relational.reference, oracle["reference_terms"])
        ):
            return Evaluation("FAIL", ("singular_relational_contract_missing",))
        return Evaluation("PASS")
    if kind == "ordinary_named":
        if selection.semantic_set is not None:
            return Evaluation("FAIL", ("semantic_set_on_named_regression",))
        if selection.relational_reference is not None:
            return Evaluation("FAIL", ("relational_reference_on_named_regression",))
        if not _contains_all_sets(selection.query, oracle["query_term_sets"]):
            return Evaluation("FAIL", ("ordinary_named_query_dropped",))
        return Evaluation("PASS")
    return Evaluation("FAIL_CLOSED", ("unknown_oracle_kind",))


def _evaluate_semantic_set(selection: Any, oracle: Mapping[str, Any]) -> Evaluation:
    """Check user semantics without assuming the subject is a source Note."""
    intent = selection.semantic_set
    if intent is None:
        return Evaluation("FAIL", ("semantic_set_missing",))
    if selection.relational_reference is not None:
        return Evaluation("FAIL", ("semantic_set_relational_conflict",))
    if intent.subject_kind != oracle["subject_kind"]:
        return Evaluation("FAIL", ("wrong_subject_kind",))
    if intent.subject_kind == "self" and intent.subject_query is not None:
        return Evaluation("FAIL", ("self_subject_query_present",))
    if intent.subject_kind == "query" and (
        intent.subject_query is None
        or not _contains_all(intent.subject_query, oracle["subject_terms"])
    ):
        return Evaluation("FAIL", ("textual_subject_query_missing",))
    if not intent.asks_exhaustive:
        return Evaluation("FAIL", ("exhaustive_intent_dropped",))
    if not _contains_all_sets(intent.member_query, oracle["member_term_sets"]):
        return Evaluation("FAIL", ("member_meaning_dropped",))
    qualifier_text = f"{intent.member_query} {intent.explicit_qualifiers}"
    if not _contains_all_sets(qualifier_text, oracle["qualifier_term_sets"]):
        return Evaluation("FAIL", ("material_qualifier_dropped",))
    return Evaluation("PASS")


def v2_preflight(schema: Mapping[str, Any], cases_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Calculate the reviewed future gate ceiling with its dedicated teaching material."""
    import json

    teaching_payload = json.loads(TEACHING_EXAMPLES_PATH.read_text(encoding="utf-8"))
    if set(teaching_payload) != {"version", "examples"} or teaching_payload["version"] != "2.0.0":
        raise ValueError("Semantic-set v2 teaching registry is invalid")
    return conservative_preflight(
        schema, cases_payload, teaching_examples=teaching_payload["examples"]
    )
