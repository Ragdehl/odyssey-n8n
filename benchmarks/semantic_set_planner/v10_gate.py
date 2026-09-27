"""Frozen successor gate for the single-versus-collection schema partition."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from benchmarks.semantic_set_planner.v9_gate import (
    CASE_ORDER,
    MAX_COST_USD,
    MAX_PROVIDER_CALLS,
    PLANNER_ORDER,
    SELECTOR_ORDER,
    evaluate_v8_result,
    evaluate_v8_selector_result,
    load_historical_registry,
    load_v9_registry,
    load_v9_selector_registry,
    v9_preflight,
)

VERSION = "10.0.0"


def load_v10_registry() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Reuse the byte-checked frozen v8 planner inputs through v9's verifier."""
    return load_v9_registry()


def load_v10_selector_registry() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Reuse the byte-checked frozen v8 selector inputs through v9's verifier."""
    return load_v9_selector_registry()


def v10_preflight(schema: Mapping[str, Any], cases: Mapping[str, Any]) -> dict[str, Any]:
    """Recalculate the reviewed bound against the single/collection partition prompt and schema."""
    details = v9_preflight(schema, cases)
    return {**details, "gate_version": VERSION}


__all__ = [
    "CASE_ORDER",
    "MAX_COST_USD",
    "MAX_PROVIDER_CALLS",
    "PLANNER_ORDER",
    "SELECTOR_ORDER",
    "evaluate_v8_result",
    "evaluate_v8_selector_result",
    "load_historical_registry",
    "load_v10_registry",
    "load_v10_selector_registry",
    "v10_preflight",
]
