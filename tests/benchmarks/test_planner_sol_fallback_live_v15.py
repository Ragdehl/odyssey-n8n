"""Provider-free guards for the ordinary Core Sol fallback gate v15."""

from __future__ import annotations

import json

import pytest

from benchmarks.planner_sol_fallback_live_v15 import run_live


def test_v15_reuses_one_frozen_non_journal_core_sentinel() -> None:
    case, context = run_live._case_and_context()
    assert case["id"] == run_live.CASE_ID == "SWR01-self-coworkers"
    assert case["request"] == "Axel y Denis son mis compañeros de trabajo."
    assert context == {"date": "2026-09-28", "time": "20:30", "timezone": "Europe/Paris"}


def test_v15_is_retained_historical_sol_evidence() -> None:
    _case, context = run_live._case_and_context()
    schema = run_live._schema()
    historical = (run_live.PROMPT_SHA256, run_live.PROVIDER_SCHEMA_SHA256)
    assert run_live._contract_hashes(schema, context) != historical


def test_v15_preflight_refuses_reuse_after_contract_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match="contract changed"):
        run_live._preflight()


def test_v15_recording_transport_does_not_retain_exception_text() -> None:
    class FailingResponses:
        def create(self, **_kwargs):  # type: ignore[no-untyped-def]
            error = RuntimeError("sensitive provider detail")
            error.status_code = 400  # type: ignore[attr-defined]
            raise error

    recorder = run_live.RecordingResponses(FailingResponses())
    with pytest.raises(RuntimeError):
        recorder.create(model="gpt-5.6-sol")
    assert recorder.attempts == 1
    assert recorder.records == []
    assert recorder.failures == [{"attempt": 1, "error_type": "RuntimeError", "status_code": 400}]
    assert "sensitive" not in repr(recorder.failures)


def test_v15_retains_complete_passing_evidence() -> None:
    artifacts = list(run_live.RESULTS_DIR.glob("*.json"))
    assert len(artifacts) == 1
    artifact = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert artifact["version"] == 15
    assert artifact["provider_attempts"] == artifact["completed_provider_responses"] == 1
    assert artifact["automatic_retries"] == 0
    assert artifact["passed"] is True
    assert artifact["case_id"] == "SWR01-self-coworkers"
