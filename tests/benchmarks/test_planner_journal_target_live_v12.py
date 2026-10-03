"""Historical guards for the retained Journal target live gate v12."""

from __future__ import annotations

import hashlib
import json

import pytest

from benchmarks.planner_journal_target_live_v12 import run_live


def test_v12_matrix_is_frozen_and_journal_specific() -> None:
    assert hashlib.sha256(run_live.MATRIX.read_bytes()).hexdigest() == run_live.MATRIX_SHA256
    matrix = json.loads(run_live.MATRIX.read_text(encoding="utf-8"))
    assert matrix["version"] == 12
    assert len(matrix["cases"]) == run_live.MAX_CALLS == 2


def test_v12_retained_evidence_records_partial_failure_without_rerun() -> None:
    artifacts = list(run_live.RESULTS_DIR.glob("*.json"))
    assert len(artifacts) == 1
    artifact = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert artifact["version"] == 12
    assert artifact["provider_attempts"] == artifact["completed_provider_responses"] == 2
    assert artifact["automatic_retries"] == 0
    assert artifact["passed"] is False
    rows = {row["id"]: row for row in artifact["rows"]}
    today = rows["journal-today-target-date"]
    yesterday = rows["journal-yesterday-target-date"]
    assert today["actual"]["filters"] == [
        {"field": "entry_date", "op": "eq", "value": "2026-10-03"}
    ]
    assert today["actual"]["properties"] == []
    assert yesterday["passed"] is True
    assert artifact["estimated_regional_upper_usd"] < run_live.AUTHORIZED_CEILING_USD


def test_v12_frozen_candidate_is_not_the_current_contract() -> None:
    matrix = json.loads(run_live.MATRIX.read_text(encoding="utf-8"))
    schema = json.loads(run_live.SCHEMA_PATH.read_text(encoding="utf-8"))
    prompt_hash, schema_hash = run_live._contract_hashes(schema, matrix["current_context"])
    assert prompt_hash != run_live.PROMPT_SHA256
    assert schema_hash == run_live.PROVIDER_SCHEMA_SHA256


def test_v12_preflight_refuses_current_contract_before_provider_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(run_live.AUTH_ENV, "1")
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match="candidate model-facing contract changed"):
        run_live._preflight()


def test_v12_oracle_requires_date_filter_property_and_fact() -> None:
    expected = {"date": "2026-10-03", "fact_contains": "tranquilo"}
    actual = {
        "target_type": "journal_entry",
        "filters": [{"field": "entry_date", "op": "eq", "value": "2026-10-03"}],
        "properties": [{"field": "entry_date", "op": "set", "value": "2026-10-03"}],
        "facts": ["Hoy he tenido un día muy tranquilo."],
    }
    assert run_live._matches(actual, expected)
    actual["filters"] = []
    assert not run_live._matches(actual, expected)
