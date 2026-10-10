"""Provider-free F09/F10 GPT-5.6 Core request review and authorization checks."""

from __future__ import annotations

import json

import pytest

from benchmarks.fact_candidate_core_live import run_live
from tests.runtime.test_fact_candidate_planning_vertical import _sdk_fake


def _fake_client():
    reply = {
        "result": {
            "outcome": "ESCALATE",
            "actions": None,
            "limitations": None,
            "clarification_code": None,
        }
    }
    return _sdk_fake(reply)


def test_gpt56_core_requests_are_exactly_reviewed_and_budgeted() -> None:
    entries, max_cost = run_live.reviewed_requests()
    assert [id for id, _src, _ctx, _req in entries] == ["F09", "F10"]
    assert 0.06 < max_cost < 0.065
    assert run_live.OLDER_ROUTER_ESTIMATED_USD + max_cost < 0.07
    assert all(
        req["model"] == "gpt-5.6-luna"
        and req["reasoning"] == {"effort": "low"}
        and req["store"] is False
        and req["max_output_tokens"] == 2048
        for _, _src, _ctx, req in entries
    )


def test_preflight_refuses_modified_request_snapshot(tmp_path, monkeypatch) -> None:
    frozen = json.loads(run_live.SNAPSHOT.read_text(encoding="utf-8"))
    frozen["sha256"]["F10"] = "0" * 64
    altered = tmp_path / "tampered.json"
    altered.write_text(json.dumps(frozen), encoding="utf-8")
    monkeypatch.setattr(run_live, "SNAPSHOT", altered)
    with pytest.raises(ValueError, match="reviewed contract"):
        run_live.reviewed_requests()


def test_dry_run_never_needs_credentials_or_provider(monkeypatch) -> None:
    monkeypatch.delenv(run_live.RUN_ENV, raising=False)
    result = run_live.run(live=False, client=object())
    assert result["mode"] == "DRY_RUN_NO_PROVIDER"
    assert result["max_calls"] == 2
    assert result["may_authorize_writes"] is False
    assert "results" not in result


def test_live_without_separate_core_spending_authorization_is_rejected(monkeypatch) -> None:
    monkeypatch.delenv(run_live.RUN_ENV, raising=False)
    fake, calls = _fake_client()
    with pytest.raises(ValueError, match="Separate Core-provider spending authorization"):
        run_live.run(live=True, client=fake)
    assert not calls


def test_fake_provider_core_gate_never_materializes_any_notes(monkeypatch) -> None:
    monkeypatch.setenv(run_live.RUN_ENV, "1")
    fake, calls = _fake_client()
    result = run_live.run(live=True, client=fake)
    assert len(calls) == 2
    assert [r["outcome"] for r in result["results"]] == ["ESCALATE", "ESCALATE"]
    assert all(r["validation"] == "source_and_local_plan_valid" for r in result["results"])
    assert all(req["store"] is False for req in calls)
    assert result["may_authorize_writes"] is False
