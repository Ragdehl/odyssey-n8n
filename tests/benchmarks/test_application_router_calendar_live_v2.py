"""Provider-free guards for the successor Router + Calendar live gate."""

from __future__ import annotations

import hashlib

import pytest

from benchmarks.application_router_calendar_live_v2 import run_live


def test_successor_gate_reuses_frozen_attempt_one_matrices() -> None:
    """Keep the failed Attempt-1 oracles immutable while only prompts evolve."""
    assert (
        hashlib.sha256(run_live.ROUTER_MATRIX.read_bytes()).hexdigest()
        == run_live.ROUTER_MATRIX_SHA256
    )
    assert (
        hashlib.sha256(run_live.CALENDAR_MATRIX.read_bytes()).hexdigest()
        == run_live.CALENDAR_MATRIX_SHA256
    )


def test_successor_gate_ceiling_remains_below_authorized_scale() -> None:
    """Compute the full 8+8 worst-case budget without constructing a provider client."""
    budget = run_live.budget_snapshot()
    assert budget["calls"] == run_live.MAX_CALLS == 16
    assert budget["regional_usd_upper"] < run_live.AUTHORIZED_CEILING_USD == 0.02


def test_successor_gate_has_zero_provider_authority_without_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refuse provider execution before checking credentials or constructing OpenAI."""
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match=run_live.AUTH_ENV):
        run_live._preflight()
