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


def test_v13_pins_exact_candidate_prompt_and_provider_schema() -> None:
    matrix = json.loads(run_live.MATRIX.read_text(encoding="utf-8"))
    schema = json.loads(run_live.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert run_live._contract_hashes(schema, matrix["current_context"]) == (
        run_live.PROMPT_SHA256,
        run_live.PROVIDER_SCHEMA_SHA256,
    )


def test_v13_budget_is_two_zero_retry_calls_below_hard_ceiling() -> None:
    budget = run_live.budget_snapshot()
    assert budget["calls"] == run_live.MAX_CALLS == 2
    assert budget["regional_usd_upper"] < run_live.AUTHORIZED_CEILING_USD == 0.030


def test_v13_has_no_provider_authority_without_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match=run_live.AUTH_ENV):
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
