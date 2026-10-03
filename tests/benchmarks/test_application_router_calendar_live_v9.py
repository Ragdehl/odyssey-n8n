"""Provider-free guards for the unexecuted Router + Calendar executability gate v9."""

from __future__ import annotations

import hashlib
import json

import pytest

from benchmarks.application_router_calendar_live_v9 import run_live


def test_v9_freezes_calendar_v5_matrix() -> None:
    assert (
        hashlib.sha256(run_live.CALENDAR_MATRIX.read_bytes()).hexdigest()
        == run_live.CALENDAR_MATRIX_SHA256
    )
    matrix = json.loads(run_live.CALENDAR_MATRIX.read_text(encoding="utf-8"))
    assert matrix["version"] == 5
    assert len(matrix["cases"]) == 12


def test_calendar_v5_preserves_v4_and_adds_only_two_dev_reproductions() -> None:
    v4 = json.loads((run_live.ROOT / "benchmarks/calendar_planner/regression_v4.json").read_text())
    v5 = json.loads(run_live.CALENDAR_MATRIX.read_text())
    old = {case["id"]: case for case in v4["cases"]}
    new = {case["id"]: case for case in v5["cases"]}
    added = {"dev-explicit-start-direct-identities", "dev-explicit-end-direct-identities"}
    assert set(new) == set(old) | added
    for case_id, old_case in old.items():
        if case_id.startswith("entity-owned-"):
            assert new[case_id]["request"] == old_case["request"]
            assert new[case_id]["expect"] | old_case["expect"] == new[case_id]["expect"]
        else:
            assert new[case_id] == old_case


def test_v5_entity_cases_require_executable_direct_identity_selection() -> None:
    matrix = json.loads(run_live.CALENDAR_MATRIX.read_text())
    cases = {case["id"]: case for case in matrix["cases"]}
    expected = {
        "entity-owned-exact-date": [["Marta", "direct_name"], ["Airbus", "direct_name"]],
        "entity-owned-ending-exact-date": [["Bruno", "direct_name"], ["Renault", "direct_name"]],
        "entity-owned-state-start-exact-date": [
            ["Lucía", "direct_name"],
            ["Daniel", "direct_name"],
        ],
        "dev-explicit-start-direct-identities": [
            ["Marta Test", "direct_name"],
            ["Airbus Test", "direct_name"],
        ],
        "dev-explicit-end-direct-identities": [
            ["Bruno Test", "direct_name"],
            ["Airbus Test", "direct_name"],
        ],
    }
    for case_id, modes in expected.items():
        assert cases[case_id]["expect"]["identity_selection_modes"] == modes
        assert cases[case_id]["expect"]["core_compile"] == "ok"


def test_v9_is_retired_unexecuted_after_app_to_core_boundary_redesign() -> None:
    """The discarded mini-Core Calendar gate can never regain provider authority."""
    assert run_live.RETIRED is True
    assert run_live.MAX_CALLS == 20


def test_v9_preflight_always_refuses_provider_use(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(run_live.AUTH_ENV, "1")
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match="retired"):
        run_live._preflight()


def test_v9_recording_transport_counts_failures_without_exception_text() -> None:
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
