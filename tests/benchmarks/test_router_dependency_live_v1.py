"""Provider-free evidence checks for the bounded Router pronoun dependency gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.router_dependency_live_v1 import run_live as gate
from benchmarks.router_dependency_live_v1.run_live import CASES, MAX_CALLS, MAX_USD

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "benchmarks/router_dependency_live_v1/results/20261008-one-shot.json"


def test_frozen_router_dependency_gate_preserves_historical_contract() -> None:
    """Keep past model evidence without claiming approval for changed source."""
    result = json.loads(RESULTS.read_text())
    assert result["passed"] is True
    assert result["retries"] == 0
    assert result["calls"] == MAX_CALLS == len(CASES) == 6
    assert tuple(result["contract_hashes"]) == gate.FROZEN_CONTRACT_HASHES
    assert result["estimated_usd_with_10pct_margin"] < MAX_USD
    assert [c["id"] for c in result["cases"]] == [case[0] for case in CASES]
    assert all(c["pass"] for c in result["cases"])
    assert result["cases"][0]["routes"][1][2:] == [0, "él"]
    assert (
        result["cases"][3]["routes"][0][1] == "Hoy conocí a Eric. Mañana vendrá conmigo al teatro."
    )


def test_archived_gate_denies_new_model_calls_on_prompt_drift(monkeypatch) -> None:
    """Even an explicit stale benchmark opt-in cannot reach the provider."""
    monkeypatch.setenv(gate.AUTH_ENV, "YES")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-do-not-call")
    with pytest.raises(SystemExit, match="Archived Router contract changed"):
        gate.run()
