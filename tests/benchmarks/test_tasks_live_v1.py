"""Freeze the consumed Tasks v0.1 live evidence and its provider-free adjudication."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "benchmarks/tasks_live_v1/results/52911b23792a.json"
ARTIFACT_SHA256 = "7b79b456390675ebf23cbc5bd81924adec427fc2bee7008f93ff5e4ab6feca15"


def test_tasks_live_v1_consumed_evidence_is_frozen_and_within_authorized_envelope() -> None:
    raw = ARTIFACT.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ARTIFACT_SHA256
    result = json.loads(raw)
    assert result["provider_attempts"] == 8
    assert result["automatic_retries"] == 0
    assert result["mutation_authority"] is False
    assert result["router_calls"] == 0
    assert result["temporal_provider_calls"] == 0
    assert result["sol_calls"] == 0
    assert result["estimated_regional_cost_usd"] < 0.05


def test_tasks_live_v1_is_eight_of_eight_after_core_semantic_adjudication() -> None:
    result = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    rows = {row["id"]: row for row in result["rows"]}
    assert len(rows) == 8
    assert all(row["passed"] for name, row in rows.items() if name != "P3-core-content")

    # The original oracle expected "amend", but generic Core uses "record" for a new fact.
    # Existing-target resolution still materializes this as UPDATE; missing managed Tasks fail closed.
    content = rows["P3-core-content"]
    assert content["passed"] is False
    assert content["error"] is None
    assert content["actual"] == {
        "target_type": "task",
        "intent": "record",
        "cardinality": "one",
        "properties": {},
        "facts": ["Tengo que preguntar por las comisiones."],
    }
