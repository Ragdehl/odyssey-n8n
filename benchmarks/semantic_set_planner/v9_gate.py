"""Frozen successor gate for the collection membership-anchor prompt correction."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

from benchmarks.semantic_set_planner.v8_gate import (
    CASE_ORDER,
    MAX_INPUT_TOKENS,
    PLANNER_ORDER,
    SELECTOR_ORDER,
    evaluate_v8_result,
    evaluate_v8_selector_result,
    load_historical_registry,
    load_v8_registry,
    load_v8_selector_registry,
)
from odyssey_core.experimental_luna_planning import (
    LUNA_EXPERIMENT_AUTOMATIC_RETRIES,
    LUNA_EXPERIMENT_MAX_OUTPUT_TOKENS,
    LUNA_EXPERIMENT_MODEL,
    LUNA_EXPERIMENT_REASONING_EFFORT,
    luna_experimental_result_json_schema,
    render_luna_experimental_prompt,
)

ROOT = Path(__file__).resolve().parents[2]
PRICING_PATH = ROOT / "benchmarks/phase20_answerer/pricing_snapshot.json"
VERSION = "9.0.0"
MAX_PROVIDER_CALLS = len(PLANNER_ORDER) + len(SELECTOR_ORDER)
MAX_COST_USD = Decimal("0.41144")
_V8_REGISTRY_HASHES = {
    "v8_cases.json": "a0fb44ddec219208d41713fc758ed4d571ea23607795974ffb9bb62d03fe1a0c",
    "v8_oracle.json": "fae747ede457c2119bf56c76615df1c28dd8d77289c72163af9f3ecd192a244c",
    "v8_selector_cases.json": "dcf405994b9a37b0d30751f66cfd17cb9b90e7f391ed05a79d1d9a2fb35b62cb",
    "v8_selector_oracle.json": "0577b259b02eae5d130e72b1617c01346308014a1b91b231c376c554bbc01342",
}


def load_v9_registry() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Reuse v8's immutable planner cases and oracles after checking their exact bytes."""
    _verify_reused_v8_registry()
    return load_v8_registry()


def load_v9_selector_registry() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Reuse v8's immutable selector cases and oracles after checking their exact bytes."""
    _verify_reused_v8_registry()
    return load_v8_selector_registry()


def _verify_reused_v8_registry() -> None:
    """Reject a successor run if its inherited frozen v8 inputs have changed."""
    for filename, expected in _V8_REGISTRY_HASHES.items():
        actual = hashlib.sha256((Path(__file__).parent / filename).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("v9 inherited v8 registry drifted")


def v9_preflight(schema: Mapping[str, Any], cases: Mapping[str, Any]) -> dict[str, Any]:
    """Recalculate the successor Luna ceiling against the corrected inherited prompt."""
    if (
        LUNA_EXPERIMENT_MODEL != "gpt-5.6-luna"
        or LUNA_EXPERIMENT_REASONING_EFFORT != "low"
        or LUNA_EXPERIMENT_AUTOMATIC_RETRIES != 0
        or tuple(case["id"] for case in cases["cases"]) != CASE_ORDER
    ):
        raise ValueError("v9 provider configuration is unsafe")
    _verify_reused_v8_registry()
    historical_cases, _ = load_historical_registry()
    selector_cases, _ = load_v9_selector_registry()
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
        for case in [*cases["cases"], *historical_cases, *selector_cases["cases"]]
    )
    if maximum_bytes > MAX_INPUT_TOKENS:
        raise ValueError("v9 serialized input exceeds conservative bound")
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
        raise ValueError("v9 conservative ceiling changed")
    return {
        "gate_version": VERSION,
        "planner_case_order": PLANNER_ORDER,
        "selector_case_order": SELECTOR_ORDER,
        "maximum_provider_calls": MAX_PROVIDER_CALLS,
        "model": LUNA_EXPERIMENT_MODEL,
        "reasoning": LUNA_EXPERIMENT_REASONING_EFFORT,
        "retries": LUNA_EXPERIMENT_AUTOMATIC_RETRIES,
        "serialized_request_bytes": maximum_bytes,
        "conservative_no_cache_maximum_usd": str(ceiling),
        "reused_v8_registry_sha256": dict(_V8_REGISTRY_HASHES),
    }


__all__ = [
    "CASE_ORDER",
    "MAX_COST_USD",
    "MAX_PROVIDER_CALLS",
    "PLANNER_ORDER",
    "SELECTOR_ORDER",
    "evaluate_v8_result",
    "evaluate_v8_selector_result",
    "load_historical_registry",
    "load_v9_registry",
    "load_v9_selector_registry",
    "v9_preflight",
]
