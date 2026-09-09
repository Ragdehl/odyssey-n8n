"""Canonical few-shot calibration examples for contextual entity resolution."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .contextual import (
    ContextualCandidate,
    ContextualResolutionExample,
    ContextualResolutionRequest,
    validate_contextual_decision,
)

CALIBRATION_PATH = Path(__file__).resolve().parents[1] / "config/contextual-calibration.json"
EXPECTED_CALIBRATION_COUNT = 10


@lru_cache(maxsize=1)
def load_contextual_calibration_examples() -> tuple[ContextualResolutionExample, ...]:
    """Load the immutable ten-example contextual provider calibration prefix.

    Returns:
        Calibration examples in their canonical order, with validated decisions.

    Raises:
        ValueError: If the canonical configuration is malformed or incomplete.
        OSError: If the canonical configuration cannot be read.
    """
    raw = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) != EXPECTED_CALIBRATION_COUNT:
        raise ValueError("Contextual calibration must contain exactly ten examples")
    examples: list[ContextualResolutionExample] = []
    for entry in raw:
        request_data = entry.get("request", {})
        candidates = tuple(
            ContextualCandidate(candidate["id"], candidate["evidence"])
            for candidate in request_data.get("candidates", [])
        )
        request = ContextualResolutionRequest(
            reference=request_data["reference"],
            context=request_data["context"],
            entity_type=request_data["entity_type"],
            candidates=candidates,
        )
        decision_data = entry.get("decision", {})
        decision = validate_contextual_decision(
            decision_data, frozenset(candidate.id for candidate in candidates)
        )
        examples.append(ContextualResolutionExample(request=request, decision=decision))
    return tuple(examples)
