"""Frozen Luna regression gate reusing Phase 20.2E planner contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

from benchmarks.luna_first_planner.evaluate import Classification
from benchmarks.luna_first_planner.evaluate_v2 import evaluate_result_v2, load_frozen_registry_v2
from benchmarks.semantic_set_planner.gate import Evaluation
from odyssey_core.experimental_luna_planning import (
    LUNA_EXPERIMENT_AUTOMATIC_RETRIES,
    LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    LUNA_EXPERIMENT_MODEL,
    LUNA_EXPERIMENT_REASONING_EFFORT,
    ExperimentalPlannerResult,
    luna_experimental_result_json_schema,
    render_luna_experimental_prompt,
)

ROOT = Path(__file__).resolve().parents[2]
CASE_IDS = ("HD03", "HO02", "SP02", "SW01", "SW02", "SD02", "SM01", "SC02", "SE01", "SA02")
MAX_PROVIDER_CALLS = len(CASE_IDS)
MAX_LUNA_INPUT_TOKENS = 70_000
PRICING_PATH = ROOT / "benchmarks/phase20_answerer/pricing_snapshot.json"


def load_v3_regression_registry() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Select exact historical Phase 20.2E contracts without copying their text or oracle."""
    payload, oracles = load_frozen_registry_v2()
    by_id = {case["id"]: case for case in payload["cases"]}
    if any(case_id not in by_id or case_id not in oracles for case_id in CASE_IDS):
        raise ValueError("Frozen historical regression registry drifted")
    return (
        {
            "version": "3.0.0-regression",
            "fixed_context": payload["fixed_context"],
            "cases": [by_id[case_id] for case_id in CASE_IDS],
        },
        {case_id: oracles[case_id] for case_id in CASE_IDS},
    )


def evaluate_v3_regression_result(
    case_id: str, result: ExperimentalPlannerResult, oracle: Mapping[str, Any]
) -> Evaluation:
    """Translate the established historical evaluator into this gate's PASS contract."""
    evaluation = evaluate_result_v2(case_id, result, oracle)
    if evaluation.classification in {
        Classification.SAFE_PLAN,
        Classification.SAFE_CLARIFY,
        Classification.SAFE_ESCALATE,
    }:
        return Evaluation("PASS", evaluation.findings)
    return Evaluation("FAIL", (*evaluation.findings, evaluation.classification.value.lower()))


def v3_regression_preflight(
    schema: Mapping[str, Any], cases_payload: Mapping[str, Any], teaching: list[dict[str, Any]]
) -> dict[str, Any]:
    """Calculate the conservative Luna-only bound before client construction."""
    if (
        LUNA_EXPERIMENT_MODEL != "gpt-5.6-luna"
        or LUNA_EXPERIMENT_REASONING_EFFORT != "low"
        or LUNA_EXPERIMENT_AUTOMATIC_RETRIES != 0
        or len(cases_payload["cases"]) != MAX_PROVIDER_CALLS
    ):
        raise ValueError("Regression gate provider configuration is unsafe")
    prompt = render_luna_experimental_prompt(
        schema, cases_payload["fixed_context"], teaching_examples=teaching
    )
    output_schema = luna_experimental_result_json_schema(schema)
    request_bytes = max(
        len(prompt.encode())
        + len(json.dumps(output_schema, ensure_ascii=False, separators=(",", ":")).encode())
        + len(case["request"].encode())
        for case in cases_payload["cases"]
    )
    if request_bytes > MAX_LUNA_INPUT_TOKENS:
        raise ValueError("Serialized planner input exceeds the reviewed Luna token bound")
    rates = json.loads(PRICING_PATH.read_text())["models"][LUNA_EXPERIMENT_MODEL]
    ceiling = (
        Decimal(MAX_PROVIDER_CALLS)
        * (
            Decimal(MAX_LUNA_INPUT_TOKENS) * Decimal(str(rates["input_per_million"]))
            + Decimal(LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS) * Decimal(str(rates["output_per_million"]))
        )
        / Decimal(1_000_000)
    )
    return {
        "logical_cases": MAX_PROVIDER_CALLS,
        "maximum_provider_calls": MAX_PROVIDER_CALLS,
        "luna_model": LUNA_EXPERIMENT_MODEL,
        "reasoning_effort": LUNA_EXPERIMENT_REASONING_EFFORT,
        "retries": LUNA_EXPERIMENT_AUTOMATIC_RETRIES,
        "serialized_request_bytes": request_bytes,
        "conservative_no_cache_maximum_usd": str(ceiling),
    }
