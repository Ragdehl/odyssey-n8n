"""Immutable real GPT-6 F08 Temporal result and provenance regression.

The original live request was source-only and wrote no knowledge notes.
Retain the positive model evidence without assuming all other sentences work.
"""

from __future__ import annotations

import json

from benchmarks.fact_candidate_v2_live import run_temporal_reference as gate


def test_actual_temporal_model_normalized_shared_hour_without_new_rules():
    receipt = json.loads(gate.RECEIPT.read_text(encoding="utf-8"))
    assert receipt["case"] == "F08"
    assert receipt["mode"] == "REAL_TEMPORAL_SINGLE_SHOT"
    assert receipt["model"] == "gpt-6-luna"
    assert receipt["provider_status"] == "completed"
    assert receipt["validation"] == "grounded"
    assert not receipt["may_write_notes"]
    assert receipt["usage"]["input_tokens"] == 366
    assert receipt["usage"]["output_tokens"] == 354
    assert [item["candidate_id"] for item in receipt["bindings"]] == [
        "candidate-1",
        "candidate-1",
        "candidate-2",
        "candidate-2",
    ]
    first, second = (x for x in receipt["bindings"] if x["role"] == "time")
    assert first["source"] == "a las 10"
    assert second["source"] == "a la misma hora"
    assert first["value"] == second["value"] == "2026-10-10T10:00:00+02:00"
    assert first["exact_shape"] and second["exact_shape"]
    assert all(x["status"] == "matched" for x in receipt["bindings"])


def test_actual_temporal_budget_remained_inside_approved_cumulative_ceiling():
    receipt = json.loads(gate.RECEIPT.read_text(encoding="utf-8"))
    prices = json.loads(
        (gate.ROOT / "config/runtime-pricing-snapshot.json").read_text(encoding="utf-8")
    )["models"]["gpt-6-luna"]
    new_cost = (
        receipt["usage"]["input_tokens"] * prices["input_per_million"]
        + receipt["usage"]["output_tokens"] * prices["output_per_million"]
    ) / 1_000_000
    assert 0 < new_cost < receipt["reserved_max_usd"]
    assert receipt["estimated_previous_usd"] + new_cost < receipt["approved_cumulative_usd"]
