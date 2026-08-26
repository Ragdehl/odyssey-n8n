"""Contracts and local validation for the Phase 14 RequestPlan benchmark."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

from benchmarks.phase14_retrieval_plan.benchmark import (
    BenchmarkContractError,
    extract_schema_contract,
    load_json,
)

BENCHMARK_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = BENCHMARK_DIR.parents[1]
CANONICAL_SCHEMA_PATH = REPOSITORY_ROOT / "config/note-schema.json"
CASES_PATH = BENCHMARK_DIR / "cases.json"
ORACLE_PATH = BENCHMARK_DIR / "oracle.json"
PROMPT_PATH = BENCHMARK_DIR / "prompt.md"
PRICING_PATH = BENCHMARK_DIR / "pricing.json"
SCHEMA_CONTRACT_PATH = BENCHMARK_DIR / "schema_contract.json"
LIMITATION_CODES = ("not_supported", "unsupported_domain_date", "direct_link_not_filterable")
_SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{8,}")
_CAPABILITY_PLACEHOLDER = "{{RETRIEVAL_CAPABILITIES}}"


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one frozen benchmark input."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_schema_alignment() -> dict[str, Any]:
    """Validate that the frozen retrieval values still match the canonical note schema.

    Returns:
        The frozen RequestPlan contract.

    Raises:
        BenchmarkContractError: If a canonical retrieval value changed after the experiment froze.
    """
    frozen = load_json(SCHEMA_CONTRACT_PATH)
    canonical = load_json(CANONICAL_SCHEMA_PATH)
    actual = extract_schema_contract(canonical)
    if (
        canonical.get("schema_version") == 2
        and frozen.get("retrieval_contract", {}).get("schema_version") == 1
    ):
        # Preserve the immutable v1 benchmark contract across the approved name-only schema evolution.
        actual["schema_version"] = 1
    if frozen.get("retrieval_contract") != actual:
        raise BenchmarkContractError("Canonical retrieval schema differs from frozen v2 contract")
    if tuple(frozen.get("limitation_codes", ())) != LIMITATION_CODES:
        raise BenchmarkContractError("Frozen limitation-code vocabulary is invalid")
    if frozen.get("filter_capabilities") != extract_filter_capabilities(canonical):
        raise BenchmarkContractError("Canonical filter capabilities differ from frozen v2 contract")
    return frozen


def extract_filter_capabilities(schema: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Project schema-owned filter scope and description into a compact prompt contract.

    Args:
        schema: Parsed canonical Odyssey note schema.

    Returns:
        Filter capabilities keyed by field, including the types each field may constrain.

    Raises:
        BenchmarkContractError: If filter declarations cannot be safely interpreted.
    """
    try:
        type_ids = [item["id"] for item in schema["types"]]
        universal = [item for item in schema["metadata_fields"] if item.get("filterable")]
        scoped = [
            (note_type["id"], field)
            for note_type in schema["types"]
            for field in note_type["properties"]
            if field.get("filterable")
        ]
    except (KeyError, TypeError) as error:
        raise BenchmarkContractError(
            "Canonical schema has unusable filter capability data"
        ) from error
    capabilities = {
        field["id"]: {"types": type_ids, "description": field["description"]} for field in universal
    }
    for type_id, field in scoped:
        capabilities[field["id"]] = {"types": [type_id], "description": field["description"]}
    return capabilities


def render_prompt() -> str:
    """Render the frozen prompt with schema-derived retrieval capabilities.

    Returns:
        Prompt text ready for a future independent benchmark request.

    Raises:
        BenchmarkContractError: If the frozen prompt omits or duplicates its capability placeholder.
    """
    contract = assert_schema_alignment()
    template = PROMPT_PATH.read_text(encoding="utf-8")
    if template.count(_CAPABILITY_PLACEHOLDER) != 1:
        raise BenchmarkContractError("Prompt must contain exactly one capability placeholder")
    capabilities = contract["filter_capabilities"]
    lines = []
    for field, definition in capabilities.items():
        scope = ", ".join(definition["types"])
        lines.append(f"- `{field}`: {definition['description']} Applies to: {scope}.")
    return template.replace(_CAPABILITY_PLACEHOLDER, "\n".join(lines))


def load_cases() -> list[dict[str, str]]:
    """Load independent RequestPlan requests with unique stable case IDs."""
    cases = load_json(CASES_PATH).get("cases")
    if not isinstance(cases, list) or not cases:
        raise BenchmarkContractError("cases.json must contain non-empty cases")
    if any(set(case) != {"id", "request"} for case in cases):
        raise BenchmarkContractError("Each case must contain only id and request")
    identifiers = [case["id"] for case in cases]
    if len(set(identifiers)) != len(identifiers) or any(
        not case["request"].strip() for case in cases
    ):
        raise BenchmarkContractError("Case IDs and requests must be non-empty and unique")
    return cases


def load_oracle() -> dict[str, dict[str, Any]]:
    """Load exactly one structural expectation for each frozen benchmark request."""
    rows = load_json(ORACLE_PATH).get("cases")
    if not isinstance(rows, list):
        raise BenchmarkContractError("oracle.json has no cases")
    indexed = {row.get("id"): row for row in rows if isinstance(row, dict)}
    if set(indexed) != {case["id"] for case in load_cases()} or len(indexed) != len(rows):
        raise BenchmarkContractError("oracle cases do not exactly match cases.json")
    return indexed


def structured_output_schema(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Build a conservative strict Structured Outputs schema for one RequestPlan.

    The schema intentionally uses only closed objects, enums, ``anyOf``, required
    properties, and array items. Local validation remains the defense-in-depth
    authority for non-empty strings, filter scope, and semantic constraints.
    """
    retrieval = contract["retrieval_contract"]
    filter_schema = {"anyOf": _field_specific_filter_schemas(retrieval["filterable_fields"])}
    retrieval_plan = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "type": {
                "anyOf": [
                    {"type": "null"},
                    {"type": "string", "enum": retrieval["canonical_types"]},
                ]
            },
            "required_tags": {
                "type": "array",
                "items": {"type": "string", "enum": retrieval["canonical_tags"]},
            },
            "filters": {"type": "array", "items": filter_schema},
        },
        "required": ["query", "type", "required_tags", "filters"],
        "additionalProperties": False,
    }

    return {
        "type": "object",
        "properties": {
            "actions": {
                "type": "array",
                "items": {
                    "anyOf": [
                        {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": ["retrieve"]},
                                "plan": retrieval_plan,
                            },
                            "required": ["kind", "plan"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": ["create_note"]},
                                "content": {"type": "string"},
                            },
                            "required": ["kind", "content"],
                            "additionalProperties": False,
                        },
                    ]
                },
            },
            "limitations": {
                "type": "array",
                "items": {"type": "string", "enum": list(LIMITATION_CODES)},
            },
        },
        "required": ["actions", "limitations"],
        "additionalProperties": False,
    }


def _field_specific_filter_schemas(fields: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build closed field/operator filter alternatives from the frozen schema contract."""
    alternatives = []
    for field, definition in fields.items():
        controlled_values = definition["controlled_values"]
        if field == "subtype" and not controlled_values:
            continue
        scalar = (
            {"type": "string", "enum": controlled_values}
            if controlled_values
            else {"type": "string"}
        )
        for operator in definition["operators"]:
            value = {"type": "array", "items": scalar} if operator == "in" else scalar
            alternatives.append(
                {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string", "enum": [field]},
                        "op": {"type": "string", "enum": [operator]},
                        "value": value,
                    },
                    "required": ["field", "op", "value"],
                    "additionalProperties": False,
                }
            )
    return alternatives


def _validate_filter(item: Any, contract: Mapping[str, Any]) -> None:
    """Validate one Phase 13-compatible deterministic filter."""
    if not isinstance(item, dict) or set(item) != {"field", "op", "value"}:
        raise BenchmarkContractError("Each filter must have exactly field, op, and value")
    definition = contract["retrieval_contract"]["filterable_fields"].get(item["field"])
    if definition is None or item["op"] not in definition["operators"]:
        raise BenchmarkContractError("Unsupported filter field or operator")
    value = item["value"]
    if (
        not isinstance(value, (str, list))
        or isinstance(value, list)
        and (not value or not all(isinstance(v, str) for v in value))
    ):
        raise BenchmarkContractError("Filter values must be a string or non-empty string list")
    if item["op"] == "in" and not isinstance(value, list):
        raise BenchmarkContractError("The in operator requires a string list")
    if item["op"] != "in" and isinstance(value, list):
        raise BenchmarkContractError("Only the in operator accepts a string list")
    controlled = definition["controlled_values"]
    values = value if isinstance(value, list) else [value]
    if (controlled or item["field"] == "subtype") and not set(values) <= set(controlled):
        raise BenchmarkContractError("Filter uses an unregistered controlled value")
    kind = definition["value_type"]
    if kind == "date" and any(_valid_date(v) is False for v in values):
        raise BenchmarkContractError("Date filter value is invalid")
    if kind == "date-time" and any(_valid_datetime(v) is False for v in values):
        raise BenchmarkContractError("Date-time filter value is invalid")


def _valid_date(value: str) -> bool:
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _valid_datetime(value: str) -> bool:
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def _plan_type_candidates(plan: Mapping[str, Any], contract: Mapping[str, Any]) -> set[str]:
    """Return the intersection of all type restrictions in one RetrievalPlan."""
    candidates = set(contract["retrieval_contract"]["canonical_types"])
    if plan["type"] is not None:
        candidates &= {plan["type"]}
    for item in plan["filters"]:
        if item["field"] == "type":
            values = item["value"] if isinstance(item["value"], list) else [item["value"]]
            candidates &= set(values)
    return candidates


def _validate_filter_scopes(plan: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    """Reject type-specific filters that would silently constrain unrelated note types."""
    candidates = _plan_type_candidates(plan, contract)
    if not candidates:
        raise BenchmarkContractError("RetrievalPlan type restrictions are contradictory")
    for item in plan["filters"]:
        allowed = set(contract["filter_capabilities"][item["field"]]["types"])
        if not candidates <= allowed:
            raise BenchmarkContractError(
                f"Filter {item['field']!r} requires candidates within {sorted(allowed)!r}"
            )


def validate_output(payload: Any) -> dict[str, Any]:
    """Strictly validate a generated RequestPlan without executing any action."""
    contract = assert_schema_alignment()
    if not isinstance(payload, dict) or set(payload) != {"actions", "limitations"}:
        raise BenchmarkContractError("Output must contain exactly actions and limitations")
    actions = payload["actions"]
    if not isinstance(actions, list) or not actions:
        raise BenchmarkContractError("actions must be a non-empty list")
    for action in actions:
        if not isinstance(action, dict) or action.get("kind") not in {"retrieve", "create_note"}:
            raise BenchmarkContractError("Action kind is invalid")
        if action["kind"] == "create_note":
            if (
                set(action) != {"kind", "content"}
                or not isinstance(action["content"], str)
                or not action["content"].strip()
            ):
                raise BenchmarkContractError("CreateNoteAction must contain only non-empty content")
            continue
        if set(action) != {"kind", "plan"} or not isinstance(action["plan"], dict):
            raise BenchmarkContractError("RetrieveAction must contain exactly one plan")
        plan = action["plan"]
        if (
            set(plan) != {"query", "type", "required_tags", "filters"}
            or not isinstance(plan["query"], str)
            or not plan["query"].strip()
        ):
            raise BenchmarkContractError("RetrievalPlan shape is invalid")
        if (
            plan["type"] is not None
            and plan["type"] not in contract["retrieval_contract"]["canonical_types"]
        ):
            raise BenchmarkContractError("RetrievalPlan type is invalid")
        if not isinstance(plan["required_tags"], list) or not set(plan["required_tags"]) <= set(
            contract["retrieval_contract"]["canonical_tags"]
        ):
            raise BenchmarkContractError("RetrievalPlan tags are invalid")
        if not isinstance(plan["filters"], list):
            raise BenchmarkContractError("RetrievalPlan filters are invalid")
        for item in plan["filters"]:
            _validate_filter(item, contract)
        _validate_filter_scopes(plan, contract)
    if (
        not isinstance(payload["limitations"], list)
        or len(payload["limitations"]) != len(set(payload["limitations"]))
        or not set(payload["limitations"]) <= set(LIMITATION_CODES)
    ):
        raise BenchmarkContractError("limitations are invalid")
    return payload


def build_api_payload(model: str, effort: str, prompt: str, request: str) -> dict[str, Any]:
    """Build one independent, cache-stable future Responses API request."""
    if model not in {"gpt-5.6-terra", "gpt-5.6-sol"} or effort != "low":
        raise BenchmarkContractError("Only approved v2 staged configurations are allowed")
    return {
        "model": model,
        "store": False,
        "prompt_cache_key": "odyssey-phase14-request-plan-v2",
        "prompt_cache_options": {"mode": "explicit"},
        "reasoning": {"effort": effort},
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                        "prompt_cache_breakpoint": {"mode": "explicit"},
                    }
                ],
            },
            {"role": "user", "content": [{"type": "input_text", "text": request}]},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "odyssey_request_plan_v2",
                "strict": True,
                "schema": structured_output_schema(assert_schema_alignment()),
            }
        },
    }


def estimated_cost(model: str, usage: Mapping[str, int], pricing: Mapping[str, Any]) -> float:
    """Estimate cost from actual provider counters and a locked pricing snapshot.

    ``input_tokens`` is normalized as the total input counter: cached reads and
    cache writes are separately billed subsets, so ordinary input is their remainder.
    A malformed overlapping total fails rather than silently double charging.
    """
    rates = pricing["models"][model]
    ordinary_input = (
        usage["input_tokens"] - usage["cached_input_tokens"] - usage["cache_write_tokens"]
    )
    if ordinary_input < 0:
        raise BenchmarkContractError("Provider usage counters overlap beyond input_tokens")
    return (
        ordinary_input * rates["input"]
        + usage["cached_input_tokens"] * rates["cached_input"]
        + usage["cache_write_tokens"] * rates["cache_write"]
        + usage["output_tokens"] * rates["output"]
    ) / 1_000_000


def finite_latency(value: float) -> float:
    """Return a finite non-negative latency suitable for append-only evidence."""
    if not math.isfinite(value) or value < 0:
        raise BenchmarkContractError("Latency is invalid")
    return value


def sanitize_error(error: Exception) -> str:
    """Return non-secret diagnostic text for raw benchmark evidence."""
    return _SECRET_PATTERN.sub("[redacted]", str(error))[:500]
