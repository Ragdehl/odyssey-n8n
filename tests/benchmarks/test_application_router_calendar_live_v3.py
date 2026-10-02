"""Provider-free guards for the v3 Router + Calendar live gate."""

from __future__ import annotations

import hashlib

import pytest

from benchmarks.application_router_calendar_live_v3 import run_live


def test_v3_gate_keeps_router_v1_and_uses_versioned_calendar_v2_matrix() -> None:
    """Keep Attempt-1 evidence immutable while testing the corrected app-boundary contract separately."""
    assert (
        hashlib.sha256(run_live.ROUTER_MATRIX.read_bytes()).hexdigest()
        == run_live.ROUTER_MATRIX_SHA256
    )
    assert (
        hashlib.sha256(run_live.CALENDAR_MATRIX.read_bytes()).hexdigest()
        == run_live.CALENDAR_MATRIX_SHA256
    )


def test_v3_gate_ceiling_remains_below_authorized_scale() -> None:
    """Compute the full 8+8 worst-case budget without constructing a provider client."""
    budget = run_live.budget_snapshot()
    assert budget["calls"] == run_live.MAX_CALLS == 16
    assert budget["regional_usd_upper"] < run_live.AUTHORIZED_CEILING_USD == 0.02


def test_v3_gate_has_zero_provider_authority_without_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refuse provider execution before checking credentials or constructing OpenAI."""
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match=run_live.AUTH_ENV):
        run_live._preflight()
