"""Provider-free guards for the v6 Router + Calendar live gate."""

from __future__ import annotations

import hashlib

import pytest

from benchmarks.application_router_calendar_live_v6 import run_live
from odyssey_apps.calendar import CALENDAR_DESCRIPTOR


def test_v6_gate_uses_versioned_router_v2_and_calendar_v2_matrices() -> None:
    """Freeze the explicit whitespace-aware Router oracle and unchanged Calendar v2 oracle."""
    assert (
        hashlib.sha256(run_live.ROUTER_MATRIX.read_bytes()).hexdigest()
        == run_live.ROUTER_MATRIX_SHA256
    )
    assert (
        hashlib.sha256(run_live.CALENDAR_MATRIX.read_bytes()).hexdigest()
        == run_live.CALENDAR_MATRIX_SHA256
    )


def test_v6_gate_uses_the_production_calendar_descriptor() -> None:
    """Prevent benchmark routing evidence from drifting away from the real app catalog again."""
    calendar = next(item for item in run_live._catalog().capabilities() if item.id == "calendar")
    assert calendar.routing_description == CALENDAR_DESCRIPTOR.routing_description
    assert "temporal interpretation of date-qualified statements" in calendar.routing_description


def test_v6_gate_ceiling_remains_below_authorized_scale() -> None:
    """Compute the full 8+8 worst-case budget without constructing a provider client."""
    budget = run_live.budget_snapshot()
    assert budget["calls"] == run_live.MAX_CALLS == 16
    assert budget["regional_usd_upper"] < run_live.AUTHORIZED_CEILING_USD == 0.014


def test_v6_gate_has_zero_provider_authority_without_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refuse provider execution before checking credentials or constructing OpenAI."""
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match=run_live.AUTH_ENV):
        run_live._preflight()


def test_router_v2_changes_only_boundary_whitespace_comparison_metadata() -> None:
    """Version the harmless separator-whitespace review without changing routing cases or owners."""
    import json

    v1 = json.loads(
        (run_live.ROOT / "benchmarks/application_router/regression_v1.json").read_text()
    )
    v2 = json.loads(run_live.ROUTER_MATRIX.read_text())
    assert v2["version"] == 2
    assert v2["route_source_comparison"] == (
        "boundary_whitespace_insensitive_after_exact_span_validation"
    )
    assert v2["catalog"] == v1["catalog"]
    assert v2["cases"] == v1["cases"]


def test_router_v6_oracle_accepts_only_boundary_whitespace_after_local_validation() -> None:
    """Do not let the eval reinterpret words, punctuation, ordering, or capability ownership."""
    expected = {
        "outcome": "ROUTE",
        "routes": [["core", "A Cloe le gusta el chocolate."], ["calendar", "Mañana viene."]],
    }
    assert run_live._router_matches(
        {
            "outcome": "ROUTE",
            "routes": [["core", "A Cloe le gusta el chocolate. "], ["calendar", "Mañana viene."]],
        },
        expected,
    )
    assert not run_live._router_matches(
        {
            "outcome": "ROUTE",
            "routes": [["core", "A Cloe le gusta chocolate."], ["calendar", "Mañana viene."]],
        },
        expected,
    )
    assert not run_live._router_matches(
        {
            "outcome": "ROUTE",
            "routes": [["calendar", "A Cloe le gusta el chocolate."], ["core", "Mañana viene."]],
        },
        expected,
    )


def test_recording_transport_counts_failed_attempts_without_retaining_exception_text() -> None:
    """Keep provider-attempt accounting truthful even when no Structured Output is returned."""

    class FailingResponses:
        def create(self, **_kwargs):  # type: ignore[no-untyped-def]
            error = RuntimeError("sensitive provider detail")
            error.status_code = 400  # type: ignore[attr-defined]
            raise error

    recorder = run_live.RecordingResponses(FailingResponses())
    with pytest.raises(RuntimeError):
        recorder.create(model="gpt-6-luna")
    assert recorder.attempts == 1
    assert recorder.records == []
    assert recorder.failures == [{"attempt": 1, "error_type": "RuntimeError", "status_code": 400}]
    assert "sensitive" not in repr(recorder.failures)
