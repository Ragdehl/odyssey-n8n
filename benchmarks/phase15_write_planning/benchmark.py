"""Frozen artifact loading and strict local output validation for Phase 15."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from benchmarks.phase14_request_plan_v3.benchmark import (
    BenchmarkContractError,
    load_json,
)
from benchmarks.phase14_request_plan_v3.benchmark import (
    validate_output as validate_phase14_output,
)

BENCHMARK_DIR = Path(__file__).resolve().parent
CASES_PATH = BENCHMARK_DIR / "cases.json"
ORACLE_PATH = BENCHMARK_DIR / "oracle.json"
PROMPT_PATH = BENCHMARK_DIR / "prompt.md"
SCHEMA_CONTRACT_PATH = BENCHMARK_DIR / "schema_contract.json"
PHASE14_CAPABILITIES_PATH = (
    BENCHMARK_DIR.parent / "phase14_request_plan_v3" / "planner_capabilities.json"
)
_PLACEHOLDER = "{{RETRIEVAL_CAPABILITIES}}"


def load_contract() -> dict[str, Any]:
    """Load and validate the small frozen Phase 15 vocabulary contract.

    Returns:
        The frozen canonical types, write intents, and prohibited physical fields.

    Raises:
        BenchmarkContractError: If a required closed vocabulary is missing.
    """
    contract = load_json(SCHEMA_CONTRACT_PATH)
    if set(contract) != {"canonical_types", "write_intents", "forbidden_write_fields"} or not all(
        isinstance(value, list) and value for value in contract.values()
    ):
        raise BenchmarkContractError("Phase 15 frozen contract is invalid")
    return contract


def load_cases() -> list[dict[str, str]]:
    """Load the fixed 17-case incremental experiment input.

    Returns:
        Unique non-empty case IDs and requests.

    Raises:
        BenchmarkContractError: If the frozen input is malformed.
    """
    cases = load_json(CASES_PATH).get("cases")
    if not isinstance(cases, list) or len(cases) != 17:
        raise BenchmarkContractError("Phase 15 benchmark must contain exactly 17 cases")
    if any(set(case) != {"id", "request"} for case in cases):
        raise BenchmarkContractError("Phase 15 cases are malformed")
    if len({case["id"] for case in cases}) != len(cases) or any(
        not case["id"].strip() or not case["request"].strip() for case in cases
    ):
        raise BenchmarkContractError("Phase 15 case IDs and requests must be unique and non-empty")
    return cases


def load_oracle() -> dict[str, dict[str, Any]]:
    """Load the deterministic expectation indexed by benchmark case ID.

    Returns:
        Oracle rows keyed by their fixed case identifiers.

    Raises:
        BenchmarkContractError: If oracle coverage differs from the case input.
    """
    rows = load_json(ORACLE_PATH).get("cases")
    if not isinstance(rows, list):
        raise BenchmarkContractError("Phase 15 oracle has no cases")
    indexed = {row.get("id"): row for row in rows if isinstance(row, dict)}
    if set(indexed) != {case["id"] for case in load_cases()}:
        raise BenchmarkContractError("Phase 15 oracle case coverage is invalid")
    return indexed


def render_prompt() -> str:
    """Render the frozen Phase 15 prompt with Phase 14's frozen capabilities.

    Returns:
        A model-ready frozen system prompt.

    Raises:
        BenchmarkContractError: If the prompt placeholder is not exact.
    """
    template = PROMPT_PATH.read_text(encoding="utf-8")
    if template.count(_PLACEHOLDER) != 1:
        raise BenchmarkContractError("Phase 15 prompt placeholder is invalid")
    return template.replace(
        _PLACEHOLDER,
        json.dumps(load_json(PHASE14_CAPABILITIES_PATH), ensure_ascii=False, separators=(",", ":")),
    )


def validate_output(payload: Any) -> dict[str, Any]:
    """Reject malformed planning output and physical write authority.

    Args:
        payload: JSON-decoded model response.

    Returns:
        The validated original JSON payload.

    Raises:
        BenchmarkContractError: If output is not the frozen closed Phase 15 contract.
    """
    contract = load_contract()
    if not isinstance(payload, dict) or set(payload) != {"actions", "limitations"}:
        raise BenchmarkContractError("RequestPlan shape is invalid")
    actions = payload["actions"]
    if not isinstance(actions, list) or not actions:
        raise BenchmarkContractError("RequestPlan actions must be non-empty")
    retrieve_actions = [
        action
        for action in actions
        if isinstance(action, dict) and action.get("kind") == "retrieve"
    ]
    if retrieve_actions:
        validate_phase14_output(
            {"actions": retrieve_actions, "limitations": payload["limitations"]}
        )
    for action in actions:
        if not isinstance(action, dict) or action.get("kind") not in {"retrieve", "write"}:
            raise BenchmarkContractError("RequestPlan action kind is invalid")
        if action["kind"] == "write":
            _validate_write(action, contract)
    return payload


def _validate_write(action: Mapping[str, Any], contract: Mapping[str, list[str]]) -> None:
    """Validate one write action's semantic units without accepting persistence details."""
    units = action.get("units")
    if set(action) != {"kind", "units"} or not isinstance(units, list) or not units:
        raise BenchmarkContractError("WriteAction must contain non-empty units")
    for index, unit in enumerate(units):
        if not isinstance(unit, dict) or set(unit) != {
            "subject",
            "type",
            "intent",
            "facts",
            "references",
        }:
            raise BenchmarkContractError("KnowledgeUnit contains an unsupported physical field")
        if not isinstance(unit["subject"], str) or not unit["subject"].strip():
            raise BenchmarkContractError("KnowledgeUnit subject is invalid")
        if unit["type"] is not None and unit["type"] not in contract["canonical_types"]:
            raise BenchmarkContractError("KnowledgeUnit canonical type is invalid")
        if unit["intent"] not in contract["write_intents"]:
            raise BenchmarkContractError("KnowledgeUnit intent is invalid")
        if (
            not isinstance(unit["facts"], list)
            or not unit["facts"]
            or not all(isinstance(fact, str) and fact.strip() for fact in unit["facts"])
        ):
            raise BenchmarkContractError("KnowledgeUnit facts are invalid")
        if not isinstance(unit["references"], list):
            raise BenchmarkContractError("KnowledgeUnit references are invalid")
        for reference in unit["references"]:
            if (
                not isinstance(reference, dict)
                or set(reference) != {"target_index", "role"}
                or not isinstance(reference["target_index"], int)
                or isinstance(reference["target_index"], bool)
                or reference["target_index"] < 0
                or reference["target_index"] >= len(units)
                or reference["target_index"] == index
                or not isinstance(reference["role"], str)
                or not reference["role"].strip()
            ):
                raise BenchmarkContractError("KnowledgeUnit reference is invalid")
