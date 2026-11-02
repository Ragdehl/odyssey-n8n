"""Integrity of retired Router/Core experiments, never current model approval.

No provider-call runner is retained for the unapproved ninth Sol call or
for the eight attempts already consumed on 2026-10-04. Production Router/Core
behavior is checked independently by current tests/apps and tests/runtime.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "benchmarks"
UNAPPROVED = ARCHIVE / "router_core_followup_live_v3"
CONSUMED = ARCHIVE / "router_core_followup_live_v3_8"
CONSUMED_RECEIPT_SHA256 = "d957cd2e072285c88385e651c4fe3784c454f6ef172c38d9f8cb82fa35c8648e"
MATRIX_SHA256 = (
    "17ce0ed065d8eaae861668977b644b43ba0a101fa9b771ca88d3bd1bc0595194",
    "f0f20545880544aa35701c1faa5cf1c644d6b530834d2e61966a1c0f2936e87e",
)


def _authentic_consumed_receipt(path: Path) -> dict:
    """Validate historical bytes, not the current provider or model contract."""
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CONSUMED_RECEIPT_SHA256:
        raise ValueError("Archived provider receipt changed")
    return json.loads(raw)


def test_unapproved_and_consumed_runners_are_retired_but_matrices_preserved() -> None:
    unapproved, consumed = (p / "matrix.json" for p in (UNAPPROVED, CONSUMED))
    for matrix_path, expected in zip((unapproved, consumed), MATRIX_SHA256, strict=True):
        assert hashlib.sha256(matrix_path.read_bytes()).hexdigest() == expected
    original = json.loads(unapproved.read_text(encoding="utf-8"))
    actual = json.loads(consumed.read_text(encoding="utf-8"))
    assert len(original["router_cases"]) == len(actual["router_cases"]) == 5
    assert len(original["core_cases"]) == len(actual["core_cases"]) == 3
    assert len(original["sol_cases"]) == 1
    assert len(actual.get("sol_cases", [])) == 0
    assert not (UNAPPROVED / "results").exists()
    assert not (UNAPPROVED / "run_live.py").exists()
    assert not (CONSUMED / "run_live.py").exists()
    assert len(list((CONSUMED / "results").glob("*.json"))) == 1


def test_consumed_result_retains_two_real_failures_without_new_approval() -> None:
    receipt = _authentic_consumed_receipt(CONSUMED / "results/1ede7c7f9b92.json")
    assert receipt["provider_attempts"] == 8
    assert receipt["automatic_retries"] == 0
    assert receipt["mutation_authority"] is False
    assert receipt["budget_upper_usd"] < 0.05
    assert receipt["estimated_regional_cost_usd"] < 0.05
    assert receipt["matrix_sha256"] == MATRIX_SHA256[1]
    assert receipt["passed"] is False
    assert len(receipt["rows"]) == 8
    assert [row["gate"] for row in receipt["rows"]] == ["router"] * 5 + ["core"] * 3
    assert [row["passed"] for row in receipt["rows"]] == [
        True,
        True,
        True,
        False,
        False,
        True,
        True,
        True,
    ]


def test_modified_historical_receipt_is_rejected(tmp_path: Path) -> None:
    original = CONSUMED / "results/1ede7c7f9b92.json"
    altered = tmp_path / "receipt.json"
    altered.write_bytes(original.read_bytes() + b" ")
    with pytest.raises(ValueError, match="receipt changed"):
        _authentic_consumed_receipt(altered)
