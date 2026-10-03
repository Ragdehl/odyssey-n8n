"""Provider-free guards for the focused Journal target live gate v13."""

from __future__ import annotations

import hashlib
import json

import pytest

from benchmarks.planner_journal_target_live_v13 import run_live


def test_v13_matrix_is_frozen_and_create_safe_specific() -> None:
    assert hashlib.sha256(run_live.MATRIX.read_bytes()).hexdigest() == run_live.MATRIX_SHA256
    matrix = json.loads(run_live.MATRIX.read_text(encoding="utf-8"))
    assert matrix["version"] == 13
    assert len(matrix["cases"]) == run_live.MAX_CALLS == 2
    assert [case["id"] for case in matrix["cases"]] == [
        "journal-today-create-safe",
        "journal-yesterday-create-safe",
    ]


def test_v13_retained_evidence_is_historical_and_complete() -> None:
    artifacts = list(run_live.RESULTS_DIR.glob("*.json"))
    assert len(artifacts) == 1
    artifact = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert artifact["version"] == 13
    assert artifact["provider_attempts"] == artifact["completed_provider_responses"] == 2
    assert artifact["automatic_retries"] == 0
    assert artifact["passed"] is True
    assert artifact["estimated_regional_upper_usd"] < run_live.AUTHORIZED_CEILING_USD


def test_v13_historical_contract_is_not_current_and_cannot_rerun(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matrix = json.loads(run_live.MATRIX.read_text(encoding="utf-8"))
    schema = json.loads(run_live.SCHEMA_PATH.read_text(encoding="utf-8"))
    prompt_hash, schema_hash = run_live._contract_hashes(schema, matrix["current_context"])
    assert prompt_hash != run_live.PROMPT_SHA256
    assert schema_hash != run_live.PROVIDER_SCHEMA_SHA256
    monkeypatch.setenv(run_live.AUTH_ENV, "1")
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match="candidate model-facing contract changed"):
        run_live._preflight()


def test_v13_oracle_requires_date_filter_property_and_fact() -> None:
    expected = {"date": "2026-10-03", "fact_contains": "tranquilo"}
    actual = {
        "target_type": "journal_entry",
        "filters": [{"field": "entry_date", "op": "eq", "value": "2026-10-03"}],
        "properties": [{"field": "entry_date", "op": "set", "value": "2026-10-03"}],
        "facts": ["Hoy he tenido un día muy tranquilo."],
    }
    assert run_live._matches(actual, expected)
    actual["properties"] = []
    assert not run_live._matches(actual, expected)


def test_v13_recording_transport_does_not_retain_exception_text() -> None:
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
