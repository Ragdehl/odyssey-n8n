"""Frozen focused inputs and production-parity request construction for Phase 15.2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from odyssey_core.planner_capabilities import build_planner_capabilities, build_write_capabilities
from odyssey_core.request_planning import (
    PLANNER_MODEL,
    PLANNER_REASONING_EFFORT,
    render_request_planner_prompt,
    request_plan_json_schema,
)

BENCHMARK_DIR = Path(__file__).resolve().parent
ROOT = BENCHMARK_DIR.parents[1]
CONTEXT = {"date": "2026-08-23", "time": "10:00", "timezone": "Europe/Paris"}


class BenchmarkContractError(ValueError):
    """Indicate malformed frozen Phase 15.2 benchmark inputs or evidence state."""


def load_cases() -> list[dict[str, str]]:
    """Load the focused immutable acceptance cases exactly once each."""
    try:
        cases = json.loads((BENCHMARK_DIR / "cases.json").read_text(encoding="utf-8"))["cases"]
    except (OSError, KeyError, json.JSONDecodeError) as error:
        raise BenchmarkContractError("Cannot load Phase 15.2 benchmark cases") from error
    required = {"id", "request", "expect"}
    if (
        not isinstance(cases, list)
        or len(cases) != 15
        or any(not isinstance(case, dict) or set(case) != required for case in cases)
        or len({case["id"] for case in cases}) != len(cases)
    ):
        raise BenchmarkContractError("Phase 15.2 cases must be fifteen unique complete rows")
    return cases


def production_request(
    case: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    """Build the exact production Sol/low request plus reproducibility digests for one case."""
    try:
        schema_bytes = (ROOT / "config/note-schema.json").read_bytes()
        schema = json.loads(schema_bytes)
    except (OSError, json.JSONDecodeError) as error:
        raise BenchmarkContractError("Cannot load canonical schema") from error
    prompt = render_request_planner_prompt(schema, CONTEXT)
    structured_schema = request_plan_json_schema(schema)
    capabilities = {
        "selection": build_planner_capabilities(schema, current_context=CONTEXT),
        "write": build_write_capabilities(schema),
    }
    digests = {
        "canonical_schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "structured_output_schema_sha256": hashlib.sha256(
            json.dumps(structured_schema, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    request = {
        "model": PLANNER_MODEL,
        "reasoning": {"effort": PLANNER_REASONING_EFFORT},
        "store": False,
        "input": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": case["request"]},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "odyssey_request_plan",
                "strict": True,
                "schema": structured_schema,
            }
        },
    }
    return request, {"schema": schema, "capabilities": capabilities}, digests
