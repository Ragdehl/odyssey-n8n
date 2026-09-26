"""Frozen, provider-free v4 semantic-set meaning evaluator."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from benchmarks.semantic_set_planner.gate import (
    Evaluation,
    _contains_all_sets,
    conservative_preflight,
    evaluate_planner_result,
    load_registry,
)
from odyssey_core.experimental_luna_planning import ExperimentalPlannerResult

CASES_PATH = Path(__file__).with_name("v4_cases.json")
ORACLE_PATH = Path(__file__).with_name("v4_oracle.json")
TEACHING_EXAMPLES_PATH = Path(__file__).with_name("v4_teaching_examples.json")


def load_v4_registry() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Load the immutable six-case v4 registry before any future provider call."""
    return load_registry(CASES_PATH, ORACLE_PATH)


def evaluate_v4_result(result: ExperimentalPlannerResult, oracle: Mapping[str, Any]) -> Evaluation:
    """Validate complete consumed semantic fields against the frozen v4 contract."""
    return evaluate_planner_result(result, oracle, semantic_evaluator=_evaluate_semantic_set)


def v4_preflight(schema: Mapping[str, Any], cases_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Calculate the frozen v4 Luna-only ceiling without constructing a provider client."""
    teaching = json.loads(TEACHING_EXAMPLES_PATH.read_text(encoding="utf-8"))
    if set(teaching) != {"version", "examples"} or teaching["version"] != "4.0.0":
        raise ValueError("Semantic-set v4 teaching registry is invalid")
    return conservative_preflight(schema, cases_payload, teaching_examples=teaching["examples"])


def _evaluate_semantic_set(selection: Any, oracle: Mapping[str, Any]) -> Evaluation:
    """Require complete query meaning, safe type hints, and exhaustive intent."""
    intent = selection.semantic_set
    if intent is None or selection.relational_reference is not None:
        return Evaluation("FAIL", ("semantic_set_missing_or_conflicting",))
    if intent.subject_kind != oracle["subject_kind"] or intent.asks_exhaustive is not True:
        return Evaluation("FAIL", ("subject_or_exhaustiveness_dropped",))
    if intent.member_type != oracle["member_type"]:
        return Evaluation("FAIL", ("member_type_missing_or_wrong",))
    effective = " ".join(
        (
            selection.query,
            intent.member_query,
            intent.explicit_qualifiers,
            intent.subject_query or "",
        )
    )
    if not _contains_all_sets(effective, oracle["terms"]):
        return Evaluation("FAIL", ("material_semantics_dropped",))
    return Evaluation("PASS")
