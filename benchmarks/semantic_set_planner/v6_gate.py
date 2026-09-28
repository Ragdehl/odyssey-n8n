"""Frozen, provider-free v6 semantic-set meaning evaluator."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from benchmarks.semantic_set_planner.gate import Evaluation, conservative_preflight, load_registry
from benchmarks.semantic_set_planner.v4_gate import evaluate_v4_result
from odyssey_core.experimental_luna_planning import ExperimentalPlannerResult

CASES_PATH = Path(__file__).with_name("v6_cases.json")
ORACLE_PATH = Path(__file__).with_name("v6_oracle.json")
TEACHING_EXAMPLES_PATH = Path(__file__).with_name("v6_teaching_examples.json")


def load_v6_registry() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Load the immutable six-case v6 registry before any future provider call."""
    return load_registry(CASES_PATH, ORACLE_PATH)


def evaluate_v6_result(result: ExperimentalPlannerResult, oracle: Mapping[str, Any]) -> Evaluation:
    """Apply the unchanged semantic and regression oracle meaning to a v6 plan."""
    return evaluate_v4_result(result, oracle)


def v6_preflight(schema: Mapping[str, Any], cases_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Calculate the frozen v6 Luna-only ceiling without constructing a provider client."""
    teaching = json.loads(TEACHING_EXAMPLES_PATH.read_text(encoding="utf-8"))
    if set(teaching) != {"version", "examples"} or teaching["version"] != "6.0.0":
        raise ValueError("Semantic-set v6 teaching registry is invalid")
    return conservative_preflight(schema, cases_payload, teaching_examples=teaching["examples"])
