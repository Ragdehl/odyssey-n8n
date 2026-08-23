"""Frozen inputs and production-parity construction for Phase 15.3 evidence."""

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
CONTEXT = {"date": "2026-08-24", "time": "10:00", "timezone": "Europe/Paris"}


class BenchmarkContractError(ValueError):
    """Indicate malformed Phase 15.3 benchmark inputs or append-only evidence."""


def load_cases() -> list[dict[str, str]]:
    """Load the eighteen frozen Phase 15.3 boundary cases."""
    try:
        cases = json.loads((BENCHMARK_DIR / "cases.json").read_text(encoding="utf-8"))["cases"]
    except (OSError, KeyError, json.JSONDecodeError) as error:
        raise BenchmarkContractError("Cannot load Phase 15.3 benchmark cases") from error
    if (
        not isinstance(cases, list)
        or len(cases) != 18
        or any(set(case) != {"id", "request", "expect"} for case in cases)
        or len({case["id"] for case in cases}) != len(cases)
    ):
        raise BenchmarkContractError("Phase 15.3 cases must be eighteen complete rows")
    return cases


def production_request(
    case: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    """Build production Sol/low request, active schema/capabilities, and reproducibility digests."""
    schema_bytes = (ROOT / "config/note-schema.json").read_bytes()
    schema = json.loads(schema_bytes)
    prompt = render_request_planner_prompt(schema, CONTEXT)
    structured = request_plan_json_schema(schema)
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
                "schema": structured,
            }
        },
    }
    effective = {
        "schema": schema,
        "capabilities": {
            "selection": build_planner_capabilities(schema, current_context=CONTEXT),
            "write": build_write_capabilities(schema),
        },
    }
    digests = {
        "canonical_schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "structured_output_schema_sha256": hashlib.sha256(
            json.dumps(structured, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    return request, effective, digests
