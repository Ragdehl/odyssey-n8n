"""Provider-free guards for the v7 Calendar-focused low-effort live gate."""

from __future__ import annotations

import hashlib
import json

import pytest

from benchmarks.application_router_calendar_live_v7 import run_live
from odyssey_apps.calendar.planning import CALENDAR_PLANNER_REASONING_EFFORT


def test_v7_gate_freezes_calendar_v3_matrix() -> None:
    """Freeze the widened Calendar oracle before any provider authority exists."""
    assert (
        hashlib.sha256(run_live.CALENDAR_MATRIX.read_bytes()).hexdigest()
        == run_live.CALENDAR_MATRIX_SHA256
    )


def test_calendar_v3_retains_v2_and_adds_only_generic_transition_sentinels() -> None:
    """Widen transition coverage without rewriting any previously consumed expectation."""
    v2 = json.loads((run_live.ROOT / "benchmarks/calendar_planner/regression_v2.json").read_text())
    v3 = json.loads(run_live.CALENDAR_MATRIX.read_text())
    assert v3["version"] == 3
    assert v3["current_context"] == v2["current_context"]
    old_by_id = {case["id"]: case for case in v2["cases"]}
    new_by_id = {case["id"]: case for case in v3["cases"]}
    assert all(new_by_id[case_id] == case for case_id, case in old_by_id.items())
    assert set(new_by_id) - set(old_by_id) == {
        "entity-owned-ending-exact-date",
        "entity-owned-state-start-exact-date",
    }
    for case_id in set(new_by_id) - set(old_by_id):
        assert new_by_id[case_id]["expect"]["intent"] == "CORE_SEMANTIC_WRITE"


def test_v7_router_reuse_is_retired_after_the_successor_boundary_changed() -> None:
    """Consumed v7 evidence cannot reuse Router after current production files change."""
    assert not run_live._router_boundary_unchanged_since_v5()
    assert run_live.ROUTER_V5_PASS_COMMIT == "e186cf48561cfda9097f42268c8efaa82bab18bf"


def test_retained_v7_artifact_records_the_authorized_ten_call_budget() -> None:
    """Judge the consumed experiment from retained usage rather than today's longer prompt."""
    artifact = json.loads((run_live.RESULTS_DIR / "727da0223703.json").read_text(encoding="utf-8"))
    assert CALENDAR_PLANNER_REASONING_EFFORT == "low"
    assert artifact["provider_attempts"] == run_live.MAX_CALLS == 10
    assert artifact["automatic_retries"] == 0
    assert artifact["estimated_regional_upper_usd"] < run_live.AUTHORIZED_CEILING_USD == 0.012


def test_consumed_v7_preflight_refuses_current_changed_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Historical v7 cannot regain provider authority after Router/Calendar files change."""
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match="Router boundary changed"):
        run_live._preflight()


def test_recording_transport_counts_failed_attempts_without_retaining_exception_text() -> None:
    """Keep provider-attempt accounting truthful without retaining sensitive exception text."""

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
