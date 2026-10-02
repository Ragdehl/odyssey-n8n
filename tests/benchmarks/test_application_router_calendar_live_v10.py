"""Provider-free guards for the minimal app-to-Core live gate v10."""

from __future__ import annotations

import hashlib
import json

import pytest

from benchmarks.application_router_calendar_live_v10 import run_live


def test_v10_freezes_minimal_calendar_and_core_handoff_matrices() -> None:
    assert (
        hashlib.sha256(run_live.CALENDAR_MATRIX.read_bytes()).hexdigest()
        == run_live.CALENDAR_MATRIX_SHA256
    )
    assert (
        hashlib.sha256(run_live.CORE_MATRIX.read_bytes()).hexdigest() == run_live.CORE_MATRIX_SHA256
    )
    calendar = json.loads(run_live.CALENDAR_MATRIX.read_text(encoding="utf-8"))
    core = json.loads(run_live.CORE_MATRIX.read_text(encoding="utf-8"))
    assert len(calendar["cases"]) == 8
    assert len(core["cases"]) == 2
    assert {case["id"] for case in core["cases"]} == {
        "dev-explicit-start-direct-identities",
        "dev-explicit-end-direct-identities",
    }


def test_calendar_v10_oracle_contains_no_core_semantic_planning_surface() -> None:
    calendar = json.loads(run_live.CALENDAR_MATRIX.read_text(encoding="utf-8"))
    serialized = json.dumps(calendar)
    for forbidden in (
        "CORE_SEMANTIC_WRITE",
        "direct_name",
        "candidate_scope",
        "identity_mentions",
        "target_entity",
        "reference_entity",
        "core_compile",
    ):
        assert forbidden not in serialized
    intents = {case["expect"].get("intent") for case in calendar["cases"]}
    assert intents <= {None, "DAY_LITERAL_CAPTURE", "DELEGATE_TO_CORE"}


def test_core_handoff_matrix_contains_only_bounded_domain_evidence() -> None:
    core = json.loads(run_live.CORE_MATRIX.read_text(encoding="utf-8"))
    for case in core["cases"]:
        interpretation = case["domain_interpretation"]
        assert set(interpretation) == {"capability_id", "intent", "evidence"}
        assert interpretation["capability_id"] == "calendar"
        assert interpretation["intent"] == "TEMPORAL_ANNOTATION"
        assert len(interpretation["evidence"]) == 1
        assert set(interpretation["evidence"][0]) == {"kind", "source_text", "value"}
        assert interpretation["evidence"][0]["kind"] == "temporal_reference"


def test_v10_budget_is_ten_zero_retry_calls_below_hard_ceiling() -> None:
    budget = run_live.budget_snapshot()
    assert budget["calls"] == run_live.MAX_CALLS == 10
    assert budget["regional_usd_upper"] < run_live.AUTHORIZED_CEILING_USD == 0.034


def test_v10_has_no_provider_authority_without_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match=run_live.AUTH_ENV):
        run_live._preflight()


def test_v10_recording_transport_counts_failures_without_exception_text() -> None:
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
    assert recorder.failures == [
        {
            "attempt": 1,
            "model": "gpt-6-luna",
            "error_type": "RuntimeError",
            "status_code": 400,
        }
    ]
    assert "sensitive" not in repr(recorder.failures)
