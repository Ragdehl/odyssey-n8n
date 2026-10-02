"""Provider-free guards for the Core-only app handoff live gate v11."""

from __future__ import annotations

import hashlib
import json

import pytest

from benchmarks.application_core_handoff_live_v11 import run_live


def test_v11_retains_historical_matrix_but_flags_invalid_employment_oracle() -> None:
    assert hashlib.sha256(run_live.MATRIX.read_bytes()).hexdigest() == run_live.MATRIX_SHA256
    matrix = json.loads(run_live.MATRIX.read_text(encoding="utf-8"))
    assert matrix["version"] == 11
    assert len(matrix["cases"]) == run_live.MAX_CALLS == 2
    assert {case["id"] for case in matrix["cases"]} == {
        "dev-end-employment-participant",
        "end-person-relation-participant",
    }
    readme = (run_live.ROOT / "benchmarks/application_core_handoff_live_v11/README.md").read_text(
        encoding="utf-8"
    )
    assert "Invalidated acceptance gate" in readme
    assert "no company/organization type" in readme


def test_v11_handoff_contains_only_bounded_temporal_evidence() -> None:
    matrix = json.loads(run_live.MATRIX.read_text(encoding="utf-8"))
    serialized = json.dumps(matrix)
    for forbidden in ("candidate_scope", "semantic_write", "CORE_SEMANTIC_WRITE"):
        assert forbidden not in serialized
    for case in matrix["cases"]:
        interpretation = case["domain_interpretation"]
        assert interpretation["capability_id"] == "calendar"
        assert interpretation["intent"] == "TEMPORAL_ANNOTATION"
        assert interpretation["evidence"] == [
            {"kind": "temporal_reference", "source_text": "mañana", "value": "2026-10-03"}
        ]


def test_v11_budget_is_two_zero_retry_calls_below_hard_ceiling() -> None:
    budget = run_live.budget_snapshot()
    assert budget["calls"] == run_live.MAX_CALLS == 2
    assert budget["regional_usd_upper"] < run_live.AUTHORIZED_CEILING_USD == 0.030


def test_v11_has_no_provider_authority_without_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match=run_live.AUTH_ENV):
        run_live._preflight()


def test_v10_retained_evidence_allows_reusing_calendar_without_new_calls() -> None:
    artifact = json.loads(
        (
            run_live.ROOT
            / "benchmarks/application_router_calendar_live_v10/results/ed5ddf437611.json"
        ).read_text(encoding="utf-8")
    )
    calendar = [row for row in artifact["rows"] if row["gate"] == "calendar"]
    assert len(calendar) == 8
    assert all(row["passed"] for row in calendar)
    assert artifact["automatic_retries"] == 0


def test_v11_recording_transport_counts_failure_without_exception_text() -> None:
    class FailingResponses:
        def create(self, **_kwargs):  # type: ignore[no-untyped-def]
            error = RuntimeError("sensitive provider detail")
            error.status_code = 400  # type: ignore[attr-defined]
            raise error

    recorder = run_live.RecordingResponses(FailingResponses())
    with pytest.raises(RuntimeError):
        recorder.create(model="gpt-5.6-luna")
    assert recorder.attempts == 1
    assert recorder.records == []
    assert recorder.failures == [{"attempt": 1, "error_type": "RuntimeError", "status_code": 400}]
    assert "sensitive" not in repr(recorder.failures)
