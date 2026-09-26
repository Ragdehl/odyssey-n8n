"""Frozen, provider-free gate for collection, Note-set, and singular planner shapes."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any, TextIO

from benchmarks.luna_first_planner.evaluate import Classification as HistoricalClassification
from benchmarks.luna_first_planner.evaluate_v2 import evaluate_result_v2
from benchmarks.semantic_set_planner.gate import Evaluation, _contains_all_sets
from benchmarks.semantic_set_planner.v3_regression_gate import (
    CASE_IDS as HISTORICAL_CASE_ORDER,
)
from benchmarks.semantic_set_planner.v3_regression_gate import (
    load_v3_regression_registry,
)
from odyssey_core.clarification import ClarificationOption, OpenAILunaClarificationClassifier
from odyssey_core.experimental_luna_planning import (
    LUNA_EXPERIMENT_AUTOMATIC_RETRIES,
    LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    LUNA_EXPERIMENT_MODEL,
    LUNA_EXPERIMENT_REASONING_EFFORT,
    ExperimentalPlannerResult,
    luna_experimental_result_json_schema,
    render_luna_experimental_prompt,
)
from odyssey_core.request_planning import RequestPlan, RetrieveAction, WriteAction

ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = Path(__file__).with_name("v7_cases.json")
ORACLE_PATH = Path(__file__).with_name("v7_oracle.json")
CLASSIFIER_CASES_PATH = Path(__file__).with_name("v7_classifier_cases.json")
PRICING_PATH = ROOT / "benchmarks/phase20_answerer/pricing_snapshot.json"
CASE_ORDER = ("SSET01", "SSET02", "SSET03", "SSET04", "REG01", "REG02", "NOTE01", "SINGLE01")
CLASSIFIER_ORDER = ("CLAR01", "CLAR02", "CLAR03", "CLAR04")
PLANNER_ORDER = CASE_ORDER + HISTORICAL_CASE_ORDER
FINAL_CASE_ORDER = PLANNER_ORDER + CLASSIFIER_ORDER
MAX_PROVIDER_CALLS = len(FINAL_CASE_ORDER)
MAX_PLANNER_CALLS = len(PLANNER_ORDER)
MAX_INPUT_TOKENS = 70_000
MAX_CLASSIFIER_INPUT_TOKENS = 8_192
MAX_COST_USD = Decimal("0.3034048")
_UNSAFE_AUTHORITY = re.compile(
    r"(?:\[\[|\.md\b|[\\/]|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)


def load_v7_registry() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Load the exact ordered frozen cases and aligned meaning oracles."""
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    oracle = json.loads(ORACLE_PATH.read_text(encoding="utf-8"))
    if (
        set(cases) != {"version", "frozen_before_provider_calls", "fixed_context", "cases"}
        or set(oracle) != {"version", "frozen_before_provider_calls", "oracles"}
        or cases["version"] != "7.0.0"
        or oracle["version"] != "7.0.0"
        or cases["frozen_before_provider_calls"] is not True
        or oracle["frozen_before_provider_calls"] is not True
        or tuple(item.get("id") for item in cases["cases"]) != CASE_ORDER
        or tuple(item.get("id") for item in oracle["oracles"]) != CASE_ORDER
        or any(set(item) != {"id", "request"} for item in cases["cases"])
    ):
        raise ValueError("v7 registry is not the reviewed ordered contract")
    return cases, {item["id"]: item for item in oracle["oracles"]}


def load_classifier_cases() -> list[dict[str, Any]]:
    """Load exactly four bounded synthetic classifier sentinels, without provider use."""
    payload = json.loads(CLASSIFIER_CASES_PATH.read_text(encoding="utf-8"))
    if (
        set(payload) != {"version", "frozen_before_provider_calls", "cases"}
        or payload["version"] != "7.0.0"
        or payload["frozen_before_provider_calls"] is not True
        or tuple(item.get("id") for item in payload["cases"]) != CLASSIFIER_ORDER
    ):
        raise ValueError("v7 classifier registry is invalid")
    for case in payload["cases"]:
        if (
            set(case) != {"id", "original_request", "reply", "options", "expected"}
            or not all(
                isinstance(case[field], str) and case[field]
                for field in ("original_request", "reply", "expected")
            )
            or not isinstance(case["options"], list)
            or len(case["options"]) != 2
            or any(set(item) != {"id", "label"} for item in case["options"])
            or case["expected"]
            not in (
                {item["id"] for item in case["options"]} | {"CANCEL", "NEW_REQUEST", "UNRESOLVED"}
            )
            or len(json.dumps(case, ensure_ascii=False).encode("utf-8")) + 4_096
            > MAX_CLASSIFIER_INPUT_TOKENS
        ):
            raise ValueError("v7 classifier case is invalid")
    return payload["cases"]


def load_historical_registry() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Reuse the immutable historical requests and oracle meanings verbatim."""
    payload, oracles = load_v3_regression_registry()
    cases = [{"id": case["id"], "request": case["request"]} for case in payload["cases"]]
    if (
        tuple(case["id"] for case in cases) != HISTORICAL_CASE_ORDER
        or tuple(oracles) != HISTORICAL_CASE_ORDER
    ):
        raise ValueError("v7 historical regression registry drifted")
    return cases, oracles


def v7_preflight(schema: Mapping[str, Any], cases: Mapping[str, Any]) -> dict[str, Any]:
    """Bound the one-call-per-case Luna-only experiment before provider construction."""
    if (
        LUNA_EXPERIMENT_MODEL != "gpt-5.6-luna"
        or LUNA_EXPERIMENT_REASONING_EFFORT != "low"
        or LUNA_EXPERIMENT_AUTOMATIC_RETRIES != 0
        or tuple(case["id"] for case in cases["cases"]) != CASE_ORDER
        or OpenAILunaClarificationClassifier.model != "gpt-5.6-luna"
        or OpenAILunaClarificationClassifier.reasoning_effort != "low"
    ):
        raise ValueError("v7 provider configuration is unsafe")
    historical_cases, _ = load_historical_registry()
    load_classifier_cases()
    prompt = render_luna_experimental_prompt(schema, cases["fixed_context"])
    output_schema = luna_experimental_result_json_schema(schema)
    maximum_bytes = max(
        len(prompt.encode("utf-8"))
        + len(json.dumps(output_schema, ensure_ascii=False, separators=(",", ":")).encode())
        + len(case["request"].encode("utf-8"))
        for case in [*cases["cases"], *historical_cases]
    )
    if maximum_bytes > MAX_INPUT_TOKENS:
        raise ValueError("v7 serialized input exceeds conservative bound")
    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    rates = pricing["models"][LUNA_EXPERIMENT_MODEL]
    planner_bound = Decimal(MAX_PLANNER_CALLS) * (
        Decimal(MAX_INPUT_TOKENS) * Decimal(str(rates["input_per_million"]))
        + Decimal(LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS) * Decimal(str(rates["output_per_million"]))
    )
    classifier_bound = Decimal(len(CLASSIFIER_ORDER)) * (
        Decimal(MAX_CLASSIFIER_INPUT_TOKENS) * Decimal(str(rates["input_per_million"]))
        + Decimal(128) * Decimal(str(rates["output_per_million"]))
    )
    ceiling = (planner_bound + classifier_bound) / Decimal(1_000_000)
    if ceiling > MAX_COST_USD:
        raise ValueError("v7 conservative ceiling exceeds reviewed bound")
    return {
        "case_order": FINAL_CASE_ORDER,
        "maximum_provider_calls": MAX_PROVIDER_CALLS,
        "model": LUNA_EXPERIMENT_MODEL,
        "reasoning": LUNA_EXPERIMENT_REASONING_EFFORT,
        "retries": LUNA_EXPERIMENT_AUTOMATIC_RETRIES,
        "serialized_request_bytes": maximum_bytes,
        "classifier_maximum_input_tokens": MAX_CLASSIFIER_INPUT_TOKENS,
        "conservative_no_cache_maximum_usd": str(ceiling),
    }


def run_classifier_cases(
    classifier: OpenAILunaClarificationClassifier,
    cases: list[dict[str, Any]],
    evidence: TextIO,
) -> list[dict[str, Any]]:
    """Continue after safe oracle mismatches; stop on provider or bounded-output failures."""
    rows: list[dict[str, Any]] = []
    for case in cases:
        options = tuple(ClarificationOption(**item) for item in case["options"])
        started = perf_counter()
        try:
            decision = classifier.classify(case["reply"], case["original_request"], options)
        except Exception as error:
            decision = "UNRESOLVED"
            unexpected_error = type(error).__name__[:120]
        else:
            unexpected_error = None
        allowed = {item.id for item in options} | {"CANCEL", "NEW_REQUEST", "UNRESOLVED"}
        error_category = unexpected_error or classifier.last_error_category
        valid_decision = isinstance(decision, str) and decision in allowed
        classification = _classify_bounded_decision(
            classifier.last_called,
            error_category,
            valid_decision,
            decision,
            case["expected"],
        )
        row = {
            "case_id": case["id"],
            "classification": classification,
            "decision": decision if valid_decision else "INVALID",
            "model": classifier.model,
            "reasoning_effort": classifier.reasoning_effort,
            "max_retries": 0,
            "usage": classifier.last_usage,
            "duration_ms": round((perf_counter() - started) * 1000, 3),
            "response_id": classifier.last_response_id,
            "error_category": error_category,
        }
        rows.append(row)
        evidence.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        evidence.flush()
        if classification == "FAIL_CLOSED":
            break
    return rows


def _classify_bounded_decision(
    called: bool,
    error_category: str | None,
    valid_decision: bool,
    decision: str,
    expected: str,
) -> str:
    """Classify valid oracle mismatches separately from invalid or uncertain decisions."""
    if not called or error_category is not None or not valid_decision:
        return "FAIL_CLOSED"
    if decision != expected:
        return "FAIL"
    return "PASS"


def evaluate_v7_result(result: ExperimentalPlannerResult, oracle: Mapping[str, Any]) -> Evaluation:
    """Check only planner-owned shape and complete query meaning, never Core evidence."""
    if not isinstance(result, RequestPlan):
        return Evaluation("FAIL", ("unexpected_non_plan_outcome",))
    if any(isinstance(action, WriteAction) for action in result.actions):
        return Evaluation("FAIL_CLOSED", ("unsafe_action_authority",))
    if _UNSAFE_AUTHORITY.search(json.dumps(asdict(result), ensure_ascii=False)):
        return Evaluation("FAIL_CLOSED", ("unsafe_planner_authority",))
    if len(result.actions) != 1 or not isinstance(result.actions[0], RetrieveAction):
        return Evaluation("FAIL", ("wrong_action_kind_or_count",))
    action = result.actions[0]
    selection = action.plan
    shape_evaluation = _evaluate_result_shape(result, action, oracle)
    if shape_evaluation is not None:
        return shape_evaluation
    if not _contains_all_sets(selection.query, oracle["query_term_sets"]):
        return Evaluation("FAIL", ("lossless_query_meaning_dropped",))
    return Evaluation("PASS")


def _evaluate_result_shape(
    result: RequestPlan, action: RetrieveAction, oracle: Mapping[str, Any]
) -> Evaluation | None:
    """Return a bounded shape mismatch, or None when the requested retrieval shape matches."""
    kind = oracle["kind"]
    if kind == "collection":
        return _evaluate_collection_shape(result, action)
    if kind == "note_set":
        if result.presentation_intent != "note_set" or action.result_shape != "single":
            return Evaluation("FAIL", ("note_set_shape_missing",))
        return None
    if kind in {"ordinary_named", "single"}:
        return _evaluate_single_shape(result, action, oracle)
    if kind == "singular_relational":
        return _evaluate_relational_shape(result, action, oracle)
    return Evaluation("FAIL_CLOSED", ("unknown_oracle_kind",))


def _evaluate_collection_shape(result: RequestPlan, action: RetrieveAction) -> Evaluation | None:
    """Require a collection mode with no competing direct-selection authority."""
    selection = action.plan
    if action.result_shape != "collection" or result.presentation_intent != "answer":
        return Evaluation("FAIL", ("collection_shape_missing",))
    if any(
        (
            selection.entity is not None,
            selection.type is not None,
            bool(selection.filters),
            selection.link_scope is not None,
            selection.self_target is not None,
            selection.relational_reference is not None,
            selection.semantic_set is not None,
        )
    ):
        return Evaluation("FAIL", ("collection_direct_selection_conflict",))
    return None


def _evaluate_single_shape(
    result: RequestPlan, action: RetrieveAction, oracle: Mapping[str, Any]
) -> Evaluation | None:
    """Check ordinary single-result mode and any frozen source-identity requirement."""
    selection = action.plan
    if action.result_shape != "single" or result.presentation_intent != "answer":
        return Evaluation("FAIL", ("single_shape_missing",))
    if selection.relational_reference is not None:
        return Evaluation("FAIL", ("unexpected_relational_reference",))
    if oracle.get("requires_entity") and selection.entity is None:
        return Evaluation("FAIL", ("singular_source_identity_missing",))
    return None


def _evaluate_relational_shape(
    result: RequestPlan, action: RetrieveAction, oracle: Mapping[str, Any]
) -> Evaluation:
    """Require one self-rooted relational reference using a frozen meaning term."""
    reference = action.plan.relational_reference
    if action.result_shape != "single" or result.presentation_intent != "answer":
        return Evaluation("FAIL", ("singular_relational_contract_missing",))
    if reference is None or reference.source_kind != "self" or reference.members != "one":
        return Evaluation("FAIL", ("singular_relational_contract_missing",))
    if not any(term in reference.reference.casefold() for term in oracle["reference_terms"]):
        return Evaluation("FAIL", ("singular_relational_contract_missing",))
    return Evaluation("PASS")


def evaluate_historical_result(
    case_id: str, result: ExperimentalPlannerResult, oracle: Mapping[str, Any]
) -> Evaluation:
    """Preserve historical oracle semantics while separating safe mismatch from unsafe plans."""
    evaluation = evaluate_result_v2(case_id, result, oracle)
    if evaluation.classification in {
        HistoricalClassification.SAFE_PLAN,
        HistoricalClassification.SAFE_CLARIFY,
        HistoricalClassification.SAFE_ESCALATE,
    }:
        return Evaluation("PASS", evaluation.findings)
    if evaluation.classification == HistoricalClassification.INVALID_FAIL_CLOSED:
        return Evaluation("FAIL_CLOSED", (*evaluation.findings, "invalid_historical_result"))
    if isinstance(result, RequestPlan) and "PLAN" not in oracle.get("allowed_outcomes", []):
        return Evaluation("FAIL_CLOSED", (*evaluation.findings, "unsafe_historical_plan"))
    if _UNSAFE_AUTHORITY.search(json.dumps(asdict(result), ensure_ascii=False)):
        return Evaluation("FAIL_CLOSED", (*evaluation.findings, "unsafe_planner_authority"))
    expected_kinds = oracle.get("plan", {}).get("action_kinds", [])
    if (
        isinstance(result, RequestPlan)
        and any(action.kind == "write" for action in result.actions)
        and "write" not in expected_kinds
    ):
        return Evaluation("FAIL_CLOSED", (*evaluation.findings, "unsafe_action_authority"))
    if (
        isinstance(result, RequestPlan)
        and evaluation.classification == HistoricalClassification.UNSAFE_NON_ESCALATION
        and "write" in expected_kinds
        and any(action.kind == "write" for action in result.actions)
    ):
        return Evaluation("FAIL_CLOSED", (*evaluation.findings, "unsafe_write_scope"))
    return Evaluation("FAIL", evaluation.findings)
