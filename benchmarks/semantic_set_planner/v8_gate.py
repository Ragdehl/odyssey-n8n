"""Frozen preflight and oracles for the corrective self/query Luna planner gate."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from benchmarks.semantic_set_planner.gate import Evaluation, _contains_all_sets
from benchmarks.semantic_set_planner.v7_gate import (
    _UNSAFE_AUTHORITY,
    HISTORICAL_CASE_ORDER,
    evaluate_v7_result,
    load_historical_registry,
)
from odyssey_core.experimental_luna_planning import (
    LUNA_EXPERIMENT_AUTOMATIC_RETRIES,
    LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    LUNA_EXPERIMENT_MODEL,
    LUNA_EXPERIMENT_REASONING_EFFORT,
    ExperimentalPlannerResult,
    PlannerEscalation,
    luna_experimental_result_json_schema,
    render_luna_experimental_prompt,
)
from odyssey_core.request_planning import RequestPlan, RetrieveAction, WriteAction
from odyssey_core.semantic_sets import SetEvidenceSelection

ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = Path(__file__).with_name("v8_cases.json")
ORACLE_PATH = Path(__file__).with_name("v8_oracle.json")
SELECTOR_CASES_PATH = Path(__file__).with_name("v8_selector_cases.json")
SELECTOR_ORACLE_PATH = Path(__file__).with_name("v8_selector_oracle.json")
PRICING_PATH = ROOT / "benchmarks/phase20_answerer/pricing_snapshot.json"
CASE_ORDER = (
    "SSET01",
    "SSET02",
    "SSET03",
    "SSET04",
    "REG01",
    "REG02",
    "NOTE01",
    "SINGLE01",
    "CORR01",
    "MULTI01",
    "ESC01",
)
PLANNER_ORDER = CASE_ORDER + HISTORICAL_CASE_ORDER
SELECTOR_ORDER = ("RELSEL_CORROBORATE", "RELSEL_CONFLICT", "RELSEL_MULTI_TARGET", "RELSEL_SEMANTIC")
PLANNER_PROVIDER_CALLS = len(PLANNER_ORDER)
SELECTOR_PROVIDER_CALLS = len(SELECTOR_ORDER)
MAX_PROVIDER_CALLS = PLANNER_PROVIDER_CALLS + SELECTOR_PROVIDER_CALLS
MAX_INPUT_TOKENS = 70_000
MAX_COST_USD = Decimal("0.41144")


def load_v8_registry() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Load the exact frozen corrective cases before any provider is constructed."""
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    oracle = json.loads(ORACLE_PATH.read_text(encoding="utf-8"))
    if (
        set(cases) != {"version", "frozen_before_provider_calls", "fixed_context", "cases"}
        or set(oracle) != {"version", "frozen_before_provider_calls", "oracles"}
        or cases["version"] != "8.1.0"
        or oracle["version"] != "8.1.0"
        or cases["frozen_before_provider_calls"] is not True
        or oracle["frozen_before_provider_calls"] is not True
        or tuple(item.get("id") for item in cases["cases"]) != CASE_ORDER
        or tuple(item.get("id") for item in oracle["oracles"]) != CASE_ORDER
        or any(set(item) != {"id", "request"} for item in cases["cases"])
    ):
        raise ValueError("v8 registry is not the reviewed ordered contract")
    by_id = {item["id"]: item for item in oracle["oracles"]}
    for item in by_id.values():
        if item.get("kind") == "collection" and item.get("collection_subject") not in {
            "self",
            "query",
        }:
            raise ValueError("v8 collection oracle lacks subject scope")
    return cases, by_id


def load_v8_selector_registry() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Load frozen selector-only rows with opaque fact IDs before provider construction."""
    cases = json.loads(SELECTOR_CASES_PATH.read_text(encoding="utf-8"))
    oracle = json.loads(SELECTOR_ORACLE_PATH.read_text(encoding="utf-8"))
    if (
        set(cases) != {"version", "frozen_before_provider_calls", "cases"}
        or set(oracle) != {"version", "frozen_before_provider_calls", "oracles"}
        or cases["version"] != "8.1.0"
        or oracle["version"] != "8.1.0"
        or cases["frozen_before_provider_calls"] is not True
        or oracle["frozen_before_provider_calls"] is not True
        or tuple(item.get("id") for item in cases["cases"]) != SELECTOR_ORDER
        or tuple(item.get("id") for item in oracle["oracles"]) != SELECTOR_ORDER
        or any(set(item) != {"id", "query", "candidates"} for item in cases["cases"])
    ):
        raise ValueError("v8 selector registry is not the reviewed ordered contract")
    for case in cases["cases"]:
        if (
            not isinstance(case["query"], str)
            or not case["query"].strip()
            or not isinstance(case["candidates"], list)
        ):
            raise ValueError("v8 selector case is invalid")
        ids = [item.get("id") for item in case["candidates"] if isinstance(item, dict)]
        if (
            not ids
            or len(ids) != len(set(ids))
            or any(set(item) != {"id", "text"} for item in case["candidates"])
        ):
            raise ValueError("v8 selector candidates are invalid")
    return cases, {item["id"]: item for item in oracle["oracles"]}


def v8_preflight(schema: Mapping[str, Any], cases: Mapping[str, Any]) -> dict[str, Any]:
    """Calculate the reviewed no-cache Luna ceiling without making provider calls."""
    if (
        LUNA_EXPERIMENT_MODEL != "gpt-5.6-luna"
        or LUNA_EXPERIMENT_REASONING_EFFORT != "low"
        or LUNA_EXPERIMENT_AUTOMATIC_RETRIES != 0
        or tuple(item["id"] for item in cases["cases"]) != CASE_ORDER
    ):
        raise ValueError("v8 provider configuration is unsafe")
    historical, _ = load_historical_registry()
    selector_cases, _ = load_v8_selector_registry()
    prompt = render_luna_experimental_prompt(schema, cases["fixed_context"])
    output_schema = luna_experimental_result_json_schema(schema)
    maximum_bytes = max(
        len(prompt.encode("utf-8"))
        + len(json.dumps(output_schema, ensure_ascii=False, separators=(",", ":")).encode())
        + len(
            (case["request"] if "request" in case else json.dumps(case, ensure_ascii=False)).encode(
                "utf-8"
            )
        )
        for case in [*cases["cases"], *historical, *selector_cases["cases"]]
    )
    if maximum_bytes > MAX_INPUT_TOKENS:
        raise ValueError("v8 serialized input exceeds conservative bound")
    rates = json.loads(PRICING_PATH.read_text(encoding="utf-8"))["models"][LUNA_EXPERIMENT_MODEL]
    ceiling = (
        Decimal(MAX_PROVIDER_CALLS)
        * (
            Decimal(MAX_INPUT_TOKENS) * Decimal(str(rates["input_per_million"]))
            + Decimal(LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS) * Decimal(str(rates["output_per_million"]))
        )
        / Decimal(1_000_000)
    )
    if ceiling != MAX_COST_USD:
        raise ValueError("v8 conservative ceiling changed")
    return {
        "planner_case_order": PLANNER_ORDER,
        "selector_case_order": SELECTOR_ORDER,
        "maximum_provider_calls": MAX_PROVIDER_CALLS,
        "model": LUNA_EXPERIMENT_MODEL,
        "reasoning": LUNA_EXPERIMENT_REASONING_EFFORT,
        "retries": LUNA_EXPERIMENT_AUTOMATIC_RETRIES,
        "serialized_request_bytes": maximum_bytes,
        "conservative_no_cache_maximum_usd": str(ceiling),
    }


def evaluate_v8_selector_result(
    result: SetEvidenceSelection, case: Mapping[str, Any], oracle: Mapping[str, Any]
) -> Evaluation:
    """Require every expected relevant opaque fact to carry direct supplied-text evidence."""
    if not isinstance(result, SetEvidenceSelection) or result.scope_uncertain:
        return Evaluation("FAIL", ("selector_scope_uncertain_or_invalid",))
    supplied = tuple(result.supplied_fact_ids)
    expected = tuple(oracle["selected_fact_ids"])
    candidate_text = {item["id"]: item["text"] for item in case["candidates"]}
    if set(supplied) != set(expected) or any(item not in candidate_text for item in supplied):
        return Evaluation("FAIL", ("relevant_fact_set_missing_or_extra",))
    supported: set[str] = set()
    for occurrence in result.member_occurrences:
        text = candidate_text.get(occurrence.candidate_id)
        if (
            text is None
            or occurrence.kind not in {"literal", "link"}
            or occurrence.start < 0
            or occurrence.end <= occurrence.start
            or occurrence.end > len(text)
        ):
            return Evaluation("FAIL_CLOSED", ("invalid_direct_occurrence",))
        supported.add(occurrence.candidate_id)
    if supported != set(expected):
        return Evaluation("FAIL", ("selected_fact_lacks_direct_evidence",))
    return Evaluation("PASS")


def evaluate_v8_result(result: ExperimentalPlannerResult, oracle: Mapping[str, Any]) -> Evaluation:
    """Check new collection scope without granting the planner canonical identity authority."""
    if oracle["kind"] == "escalation":
        return evaluate_v8_escalation(result)
    if oracle["kind"] != "collection":
        return evaluate_v7_result(result, oracle)
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
    if (
        action.result_shape != "collection"
        or result.presentation_intent != "answer"
        or selection.collection_subject != oracle["collection_subject"]
    ):
        return Evaluation("FAIL", ("collection_shape_or_subject_missing",))
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
    if not _contains_all_sets(selection.query, oracle["query_term_sets"]):
        return Evaluation("FAIL", ("lossless_query_meaning_dropped",))
    return Evaluation("PASS")


def evaluate_v8_escalation(result: ExperimentalPlannerResult) -> Evaluation:
    """Retain the established understood-but-unrepresentable planner regression oracle."""
    return (
        Evaluation("PASS")
        if isinstance(result, PlannerEscalation)
        else Evaluation("FAIL", ("understood_request_did_not_escalate",))
    )
