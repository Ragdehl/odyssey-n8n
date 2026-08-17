"""Tests for Phase 11B.1 benchmark blindness and scoring."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from odyssey_core.contextual import build_openai_payload

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def load_runner():
    """Load the benchmark runner without making benchmarks a production package."""
    path = REPOSITORY_ROOT / "benchmarks/run_phase11b1_openai.py"
    spec = importlib.util.spec_from_file_location("phase11b1_runner", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_blind_projection_excludes_every_frozen_answer_field() -> None:
    """Prove labels and prior answers from both evidence sets cannot reach the API payload."""
    runner = load_runner()
    case = {
        "id": "secret-case",
        "reference": "Beatriz",
        "context": "Dinner with Xavi",
        "type": "person",
        "expected": "RESOLVED",
        "expected_id": "beatriz-costa",
        "returned": "UNRESOLVED",
        "returned_id": None,
        "label_disputed": True,
        "candidates": [
            {"id": "beatriz-costa", "text": "Xavi's partner", "score": 0.99},
            {"id": "beatriz-alonso", "text": "The user's spouse", "score": 0.98},
        ],
    }

    payload = build_openai_payload(runner.blind_request(case), "gpt-5.6-luna")
    serialized = json.dumps(payload)

    for forbidden in (
        "secret-case",
        "expected",
        "returned",
        "label_disputed",
        "0.99",
        "0.98",
    ):
        assert forbidden not in serialized
