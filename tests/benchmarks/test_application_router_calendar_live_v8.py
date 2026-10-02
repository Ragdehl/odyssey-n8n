"""Provider-free guards for the v8 Calendar-focused low-effort live gate."""

from __future__ import annotations

import hashlib
import json

import pytest

from benchmarks.application_router_calendar_live_v8 import run_live
from odyssey_apps.calendar.planning import (
    CALENDAR_PLANNER_REASONING_EFFORT,
    CalendarPlannerError,
    parse_calendar_plan,
)


def test_v8_gate_freezes_calendar_v4_matrix() -> None:
    """Freeze the reviewed Calendar v4 oracle before any provider authority exists."""
    assert (
        hashlib.sha256(run_live.CALENDAR_MATRIX.read_bytes()).hexdigest()
        == run_live.CALENDAR_MATRIX_SHA256
    )


def test_calendar_v4_preserves_consumed_v3_except_clearer_state_start_identity_sentinel() -> None:
    """Do not rewrite old evidence beyond the newly introduced ambiguous place-identity sentinel."""
    v3 = json.loads((run_live.ROOT / "benchmarks/calendar_planner/regression_v3.json").read_text())
    v4 = json.loads(run_live.CALENDAR_MATRIX.read_text())
    assert v4["version"] == 4
    assert v4["current_context"] == v3["current_context"]
    old_by_id = {case["id"]: case for case in v3["cases"]}
    new_by_id = {case["id"]: case for case in v4["cases"]}
    assert set(new_by_id) == set(old_by_id)
    changed = "entity-owned-state-start-exact-date"
    for case_id, old_case in old_by_id.items():
        if case_id != changed:
            assert new_by_id[case_id] == old_case
    assert new_by_id[changed]["request"] == "Lucía empieza mañana a vivir con Daniel."
    assert new_by_id[changed]["expect"]["identity_mentions"] == ["Lucía", "Daniel"]
    assert new_by_id[changed]["expect"]["intent"] == "CORE_SEMANTIC_WRITE"


def test_retained_v8_entity_pass_documents_the_old_executability_oracle_gap() -> None:
    """The retained PASS contained a self-referential scope that current validation rejects."""
    artifact = json.loads((run_live.RESULTS_DIR / "32dce15a4436.json").read_text(encoding="utf-8"))
    row = next(item for item in artifact["rows"] if item["id"] == "entity-owned-exact-date")

    assert row["passed"] is True
    assert row["raw_output"]["semantic_write"]["operations"][0]["target"] == {
        "description": "Marta",
        "binding": "described",
        "direct_name": None,
        "candidate_scope": {
            "source": {"kind": "SOURCE_DESCRIPTION", "description": "Marta"},
            "member_query": "Marta",
            "extent": "one_member",
        },
    }
    with pytest.raises(CalendarPlannerError):
        parse_calendar_plan(row["raw_output"])


def test_v8_router_reuse_is_retired_after_the_successor_boundary_changed() -> None:
    """Consumed v8 evidence must not be reused after Router/Calendar production files change."""
    assert not run_live._router_boundary_unchanged_since_v5()
    assert run_live.ROUTER_V5_PASS_COMMIT == "e186cf48561cfda9097f42268c8efaa82bab18bf"


def test_retained_v8_artifact_records_the_authorized_ten_call_budget() -> None:
    """Judge the consumed experiment from retained usage rather than today's longer prompt."""
    artifact = json.loads((run_live.RESULTS_DIR / "32dce15a4436.json").read_text(encoding="utf-8"))
    assert CALENDAR_PLANNER_REASONING_EFFORT == "low"
    assert artifact["provider_attempts"] == 10
    assert artifact["automatic_retries"] == 0
    assert artifact["estimated_regional_upper_usd"] < run_live.AUTHORIZED_CEILING_USD == 0.012


def test_consumed_v8_preflight_refuses_current_changed_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A historical runner cannot regain provider authority after its boundary changes."""
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
