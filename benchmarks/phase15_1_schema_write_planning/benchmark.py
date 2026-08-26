"""Frozen inputs and production-parity construction for Phase 15.1 evidence."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from odyssey_core.request_planning import (
    PLANNER_MODEL,
    PLANNER_REASONING_EFFORT,
    render_request_planner_prompt,
    request_plan_json_schema,
)

BENCHMARK_DIR = Path(__file__).resolve().parent
ROOT = BENCHMARK_DIR.parents[1]
CASES_PATH = BENCHMARK_DIR / "cases.json"
SNAPSHOT_PATH = BENCHMARK_DIR / "schema_snapshot.json"
_PHASE16_5B_CANONICAL_SCHEMA_SHA256 = (
    "419871146d1496286ef91d55cbbd00a4f9b59465297fd707bb69b6b0381e133c"
)


class BenchmarkContractError(ValueError):
    """Indicate malformed frozen benchmark inputs or drift from the approved contract."""


def load_json(path: Path) -> dict[str, Any]:
    """Load one benchmark JSON object.

    Args:
        path: UTF-8 JSON object artifact.

    Returns:
        Parsed JSON object.

    Raises:
        BenchmarkContractError: If the artifact is not a JSON object.
    """
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BenchmarkContractError(f"Cannot load {path.name}") from error
    if not isinstance(value, dict):
        raise BenchmarkContractError(f"{path.name} must contain a JSON object")
    return value


def load_cases() -> list[dict[str, Any]]:
    """Load the exact focused Phase 15.1 case set.

    Returns:
        Fifteen unique model inputs with schema selectors and fixed current context.

    Raises:
        BenchmarkContractError: If the case set is incomplete or malformed.
    """
    cases = load_json(CASES_PATH).get("cases")
    required = {"id", "schema", "current_context", "request"}
    if (
        not isinstance(cases, list)
        or len(cases) != 15
        or any(set(case) != required for case in cases)
    ):
        raise BenchmarkContractError("Phase 15.1 cases must contain exactly fifteen complete rows")
    if len({case["id"] for case in cases}) != len(cases) or any(
        not isinstance(case["request"], str) or not case["request"].strip() for case in cases
    ):
        raise BenchmarkContractError(
            "Phase 15.1 case IDs and requests must be unique and non-empty"
        )
    return cases


def schema_for(case: dict[str, Any]) -> dict[str, Any]:
    """Return the frozen canonical or synthetic schema selected by one case.

    Args:
        case: Valid frozen case row.

    Returns:
        A deep-copy-safe schema passed directly to production prompt/schema builders.

    Raises:
        BenchmarkContractError: If the canonical schema drifted or the selector is unknown.
    """
    snapshot = load_json(SNAPSHOT_PATH)
    canonical_path = ROOT / snapshot["canonical_schema_path"]
    canonical_bytes = canonical_path.read_bytes()
    canonical_hash = hashlib.sha256(canonical_bytes).hexdigest()
    approved_hashes = {
        snapshot["canonical_schema_sha256"],
        _PHASE16_5B_CANONICAL_SCHEMA_SHA256,
    }
    if canonical_hash not in approved_hashes:
        raise BenchmarkContractError("Canonical schema drifted from the frozen Phase 15.1 snapshot")
    schema = json.loads(canonical_bytes)
    if case["schema"] == "canonical":
        return schema
    variant = snapshot.get("synthetic_variants", {}).get(case["schema"])
    if not isinstance(variant, dict):
        raise BenchmarkContractError("Unknown schema snapshot selector")
    changed = deepcopy(schema)
    changed["types"].append(deepcopy(variant))
    return changed


def production_request(case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build one exact production Responses request and its active schema.

    Args:
        case: Valid frozen case row.

    Returns:
        Pair of Responses API payload and the schema from which it was derived.
    """
    schema = schema_for(case)
    current_context = case["current_context"]
    return (
        {
            "model": PLANNER_MODEL,
            "reasoning": {"effort": PLANNER_REASONING_EFFORT},
            "store": False,
            "input": [
                {
                    "role": "system",
                    "content": render_request_planner_prompt(schema, current_context),
                },
                {"role": "user", "content": case["request"]},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "odyssey_request_plan",
                    "strict": True,
                    "schema": request_plan_json_schema(schema),
                }
            },
        },
        schema,
    )
