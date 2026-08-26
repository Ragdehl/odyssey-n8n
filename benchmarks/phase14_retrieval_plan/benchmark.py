"""Shared contracts for the reproducible Phase 14 retrieval-plan benchmark."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

BENCHMARK_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = BENCHMARK_DIR.parents[1]
CANONICAL_SCHEMA_PATH = REPOSITORY_ROOT / "config/note-schema.json"
CASES_PATH = BENCHMARK_DIR / "cases.json"
ORACLE_PATH = BENCHMARK_DIR / "oracle.json"
PROMPT_PATH = BENCHMARK_DIR / "prompt.md"
PRICING_PATH = BENCHMARK_DIR / "pricing.json"
SCHEMA_CONTRACT_PATH = BENCHMARK_DIR / "schema_contract.json"

_ALLOWED_OPERATORS = {
    "string": ("eq", "in"),
    "integer": ("eq", "in", "gt", "gte", "lt", "lte"),
    "date": ("eq", "in", "gt", "gte", "lt", "lte"),
    "array[string]": ("contains",),
}
_SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{8,}")


class BenchmarkContractError(ValueError):
    """Indicate that benchmark data or a generated plan violates a locked contract."""


def load_json(path: Path) -> Any:
    """Load one UTF-8 JSON benchmark artifact.

    Args:
        path: JSON file to parse.

    Returns:
        Parsed JSON-compatible data.

    Raises:
        BenchmarkContractError: If the file is missing or invalid JSON.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BenchmarkContractError(f"Unable to load benchmark JSON: {path}") from error


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one versioned benchmark input."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_ids(schema: Mapping[str, Any], registry: str) -> list[str]:
    """Extract ordered IDs from one canonical schema registry."""
    try:
        values = [item["id"] for item in schema[registry]]
    except (KeyError, TypeError) as error:
        raise BenchmarkContractError(
            f"Canonical schema has no usable {registry!r} registry"
        ) from error
    if not values or not all(isinstance(value, str) and value for value in values):
        raise BenchmarkContractError(f"Canonical schema has an invalid {registry!r} registry")
    return values


def extract_schema_contract(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Project the canonical note schema into the retrieval contract used by the benchmark.

    Args:
        schema: Parsed canonical Odyssey note schema.

    Returns:
        Stable types, tags, subtypes, filter fields, operators, and controlled values.

    Raises:
        BenchmarkContractError: If filter declarations conflict or are unusable.
    """
    types = _canonical_ids(schema, "types")
    tags = _canonical_ids(schema, "tags")
    subtypes: list[str] = []
    definitions: dict[str, Mapping[str, Any]] = {}
    try:
        for note_type in schema["types"]:
            subtypes.extend(item["id"] for item in note_type["subtypes"])
        declarations = [
            item for item in schema["metadata_fields"] if item.get("filterable") is True
        ]
        declarations.extend(
            property_definition
            for note_type in schema["types"]
            for property_definition in note_type["properties"]
            if property_definition.get("filterable") is True
        )
    except (KeyError, TypeError) as error:
        raise BenchmarkContractError(
            "Canonical schema has unusable retrieval declarations"
        ) from error
    for definition in declarations:
        field = definition.get("id")
        if not isinstance(field, str) or not field:
            raise BenchmarkContractError("Canonical schema declares an invalid filter field")
        existing = definitions.get(field)
        if existing is not None and existing != definition:
            raise BenchmarkContractError(f"Canonical schema conflicts on filter field {field!r}")
        definitions[field] = definition

    fields: dict[str, Any] = {}
    for field, definition in definitions.items():
        raw_type = definition.get("value_type")
        constraints = definition.get("constraints", {})
        value_type = "date-time" if constraints.get("format") == "date-time" else raw_type
        operator_key = "string" if value_type == "date-time" else value_type
        operators = list(_ALLOWED_OPERATORS.get(operator_key, ()))
        if value_type == "date-time":
            operators.extend(("gt", "gte", "lt", "lte"))
        if not operators:
            raise BenchmarkContractError(
                f"Canonical schema exposes unsupported filter value type {raw_type!r}"
            )
        registry = constraints.get("registry")
        controlled_values: list[str] = []
        if registry == "types":
            controlled_values = types
        elif registry == "tags":
            controlled_values = tags
        elif registry == "types[].subtypes":
            controlled_values = subtypes
        fields[field] = {
            "value_type": value_type,
            "operators": operators,
            "controlled_values": controlled_values,
        }
    return {
        "schema_version": schema.get("schema_version"),
        "canonical_types": types,
        "canonical_tags": tags,
        "canonical_subtypes": subtypes,
        "filterable_fields": fields,
    }


def assert_schema_alignment() -> dict[str, Any]:
    """Fail before API use unless the live repository matches the frozen prompt contract.

    Returns:
        The verified frozen retrieval contract.

    Raises:
        BenchmarkContractError: If the canonical repository schema has changed.
    """
    canonical = load_json(CANONICAL_SCHEMA_PATH)
    frozen = load_json(SCHEMA_CONTRACT_PATH)
    actual = extract_schema_contract(canonical)
    if canonical.get("schema_version") == 2 and frozen.get("schema_version") == 1:
        # Phase 16.5B adds required canonical name metadata. Historical retrieval evidence keeps
        # its v1 contract; its filter/type/tag projection remains unchanged.
        actual["schema_version"] = 1
    if actual != frozen:
        raise BenchmarkContractError(
            "Canonical retrieval schema differs from schema_contract.json; review the benchmark "
            "specification before any paid API calls"
        )
    return frozen


def load_cases() -> list[dict[str, str]]:
    """Load and validate exactly the independent T01-T45 benchmark requests."""
    document = load_json(CASES_PATH)
    cases = document.get("cases") if isinstance(document, dict) else None
    expected_ids = [f"T{index:02d}" for index in range(1, 46)]
    if not isinstance(cases, list) or [item.get("id") for item in cases] != expected_ids:
        raise BenchmarkContractError("cases.json must contain ordered independent cases T01-T45")
    if any(set(item) != {"id", "request"} or not item["request"].strip() for item in cases):
        raise BenchmarkContractError("Each benchmark case must contain only a non-empty id/request")
    return cases


def load_oracle() -> dict[str, dict[str, Any]]:
    """Load the deterministic oracle and verify one expectation per frozen case."""
    document = load_json(ORACLE_PATH)
    rows = document.get("cases") if isinstance(document, dict) else None
    if not isinstance(rows, list):
        raise BenchmarkContractError("oracle.json has no cases")
    indexed = {row.get("id"): row for row in rows if isinstance(row, dict)}
    case_ids = {case["id"] for case in load_cases()}
    if set(indexed) != case_ids or len(indexed) != len(rows):
        raise BenchmarkContractError("oracle.json must define exactly one expectation for T01-T45")
    return indexed


def structured_output_schema(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Build the strict Responses API JSON Schema for one RetrievalPlan output."""
    fields = list(contract["filterable_fields"])
    operators = sorted(
        {
            operator
            for definition in contract["filterable_fields"].values()
            for operator in definition["operators"]
        }
    )
    return {
        "type": "object",
        "properties": {
            "plan": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "type": {
                        "type": ["string", "null"],
                        "enum": [None, *contract["canonical_types"]],
                    },
                    "required_tags": {
                        "type": "array",
                        "items": {"type": "string", "enum": contract["canonical_tags"]},
                    },
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string", "enum": fields},
                                "op": {"type": "string", "enum": operators},
                                "value": {
                                    "anyOf": [
                                        {"type": "string"},
                                        {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "minItems": 1,
                                        },
                                    ]
                                },
                            },
                            "required": ["field", "op", "value"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["query", "type", "required_tags", "filters"],
                "additionalProperties": False,
            },
            "unrepresented_constraints": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["plan", "unrepresented_constraints"],
        "additionalProperties": False,
    }


def build_api_payload(model: str, effort: str, prompt: str, request: str) -> dict[str, Any]:
    """Build one production-like, cache-stable Responses API request.

    Args:
        model: Exact requested OpenAI model ID.
        effort: Supported reasoning effort for the selected model.
        prompt: Byte-stable common prompt text.
        request: One and only one benchmark user request.

    Returns:
        Official Responses API keyword arguments with strict Structured Outputs.
    """
    contract = assert_schema_alignment()
    if model not in load_json(PRICING_PATH)["models"]:
        raise BenchmarkContractError(f"Unapproved benchmark model: {model}")
    if effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
        raise BenchmarkContractError(f"Unsupported benchmark reasoning effort: {effort}")
    return {
        "model": model,
        "store": False,
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
            {"role": "user", "content": request},
        ],
        "prompt_cache_key": "odyssey-phase14-retrieval-plan-v1",
        "prompt_cache_options": {"mode": "explicit"},
        "text": {
            "format": {
                "type": "json_schema",
                "name": "odyssey_retrieval_plan",
                "strict": True,
                "schema": structured_output_schema(contract),
            }
        },
    }


def _is_date(value: Any) -> bool:
    """Return whether a value is a normalized ISO calendar date."""
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _is_date_time(value: Any) -> bool:
    """Return whether a value is timezone-aware ISO date-time text."""
    if not isinstance(value, str) or "T" not in value:
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def _validate_filter_value(field: str, op: str, value: Any, definition: Mapping[str, Any]) -> None:
    """Validate one generated filter value against the frozen Phase 13 contract."""
    values: Sequence[Any]
    if op == "in":
        if isinstance(value, (str, bytes)) or not isinstance(value, list) or not value:
            raise BenchmarkContractError(f"Filter {field!r} with 'in' needs a non-empty array")
        values = value
    else:
        values = [value]
    value_type = definition["value_type"]
    for item in values:
        if not isinstance(item, str):
            raise BenchmarkContractError(f"Filter {field!r} requires string values")
        if value_type == "date" and not _is_date(item):
            raise BenchmarkContractError(f"Filter {field!r} requires YYYY-MM-DD values")
        if value_type == "date-time":
            date_boundary = op in {"gt", "gte", "lt", "lte"} and _is_date(item)
            if not date_boundary and not _is_date_time(item):
                raise BenchmarkContractError(
                    f"Filter {field!r} requires timezone-aware ISO date-time values"
                )
    controlled = definition["controlled_values"]
    if field == "subtype" and not controlled:
        raise BenchmarkContractError("No canonical subtype value currently exists")
    if controlled and any(item not in controlled for item in values):
        raise BenchmarkContractError(f"Filter {field!r} contains a non-canonical value")


def validate_output(output: Any, contract: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Validate a Structured Output again locally against the complete retrieval contract.

    Args:
        output: Parsed model response.
        contract: Verified frozen retrieval contract, loaded when omitted.

    Returns:
        The original validated output mapping.

    Raises:
        BenchmarkContractError: If any shape, value, field, operator, or date is unsafe.
    """
    contract = contract or assert_schema_alignment()
    if not isinstance(output, dict) or set(output) != {"plan", "unrepresented_constraints"}:
        raise BenchmarkContractError(
            "Output must contain exactly plan and unrepresented_constraints"
        )
    plan = output["plan"]
    if not isinstance(plan, dict) or set(plan) != {"query", "type", "required_tags", "filters"}:
        raise BenchmarkContractError("RetrievalPlan has an invalid shape")
    if not isinstance(plan["query"], str) or not plan["query"].strip():
        raise BenchmarkContractError("RetrievalPlan query must be non-empty")
    if plan["type"] is not None and plan["type"] not in contract["canonical_types"]:
        raise BenchmarkContractError("RetrievalPlan type is not canonical")
    tags = plan["required_tags"]
    if not isinstance(tags, list) or any(tag not in contract["canonical_tags"] for tag in tags):
        raise BenchmarkContractError("RetrievalPlan required_tags are not canonical")
    if len(tags) != len(set(tags)):
        raise BenchmarkContractError("RetrievalPlan required_tags contain duplicates")
    filters = plan["filters"]
    if not isinstance(filters, list):
        raise BenchmarkContractError("RetrievalPlan filters must be an array")
    for item in filters:
        if not isinstance(item, dict) or set(item) != {"field", "op", "value"}:
            raise BenchmarkContractError("Every filter must contain exactly field, op, and value")
        definition = contract["filterable_fields"].get(item["field"])
        if definition is None:
            raise BenchmarkContractError(f"Unknown filter field: {item['field']!r}")
        if item["op"] not in definition["operators"]:
            raise BenchmarkContractError(
                f"Unsupported operator {item['op']!r} for field {item['field']!r}"
            )
        _validate_filter_value(item["field"], item["op"], item["value"], definition)
    unrepresented = output["unrepresented_constraints"]
    if not isinstance(unrepresented, list) or any(
        not isinstance(item, str) or not item.strip() for item in unrepresented
    ):
        raise BenchmarkContractError("unrepresented_constraints must contain non-empty strings")
    return output


def effective_types(plan: Mapping[str, Any]) -> set[str] | None:
    """Return the candidate-type restriction produced by all ANDed type constraints."""
    constraints: list[set[str]] = []
    if plan["type"] is not None:
        constraints.append({plan["type"]})
    for item in plan["filters"]:
        if item["field"] == "type":
            constraints.append({item["value"]} if item["op"] == "eq" else set(item["value"]))
    if not constraints:
        return None
    result = constraints[0]
    for constraint in constraints[1:]:
        result &= constraint
    return result


def effective_required_tags(plan: Mapping[str, Any]) -> set[str]:
    """Return all tags the plan deterministically requires with AND semantics."""
    result = set(plan["required_tags"])
    result.update(
        item["value"]
        for item in plan["filters"]
        if item["field"] == "tags" and item["op"] == "contains"
    )
    return result


def regular_filters(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return hard filters other than equivalent type and required-tag representations."""
    return [item for item in plan["filters"] if item["field"] not in {"type", "tags"}]


def canonical_filter(item: Mapping[str, Any]) -> tuple[str, str, Any]:
    """Return an order-insensitive identity for one oracle or generated filter."""
    value = item["value"]
    if item["op"] == "in" and isinstance(value, list):
        value = tuple(sorted(value))
    return item["field"], item["op"], value


def normalized_text(value: str) -> str:
    """Normalize user-facing text for robust concept-preservation checks."""
    return unicodedata.normalize("NFC", value).casefold()


def concepts_present(text: str, groups: Sequence[Sequence[str]]) -> list[list[str]]:
    """Return concept groups for which none of the accepted phrases appears."""
    normalized = normalized_text(text)
    return [
        list(group)
        for group in groups
        if not any(normalized_text(term) in normalized for term in group)
    ]


def sanitize_error(error: BaseException) -> str:
    """Render a provider error without allowing an API-key-shaped token into artifacts."""
    rendered = f"{type(error).__name__}: {error}"
    return _SECRET_PATTERN.sub("[REDACTED_API_KEY]", rendered)


def finite_latency(value: float) -> float:
    """Validate and round one measured request latency for durable results."""
    if not math.isfinite(value) or value < 0:
        raise BenchmarkContractError("Measured request latency is invalid")
    return round(value, 6)


def estimated_cost(model: str, usage: Mapping[str, int], pricing: Mapping[str, Any]) -> float:
    """Calculate standard API cost from actual token counters and dated official rates."""
    rates = pricing["models"][model]
    cached = usage.get("cached_input_tokens", 0)
    cache_write = usage.get("cache_write_tokens", 0)
    ordinary = max(0, usage.get("input_tokens", 0) - cached - cache_write)
    dollars = (
        ordinary * rates["input"]
        + cached * rates["cached_input"]
        + cache_write * rates["input"] * 1.25
        + usage.get("output_tokens", 0) * rates["output"]
    ) / 1_000_000
    return round(dollars, 9)
