"""Verified source-relative clock references with the existing Temporal adapter."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from benchmarks.fact_candidate_v2_live import run_temporal_reference as gate
from odyssey_apps.fact_temporal import bind_temporal_to_fact_candidates
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from tests.runtime.test_fact_candidate_planning_vertical import _sdk_fake


def _part(text, kind, date=None, instant=None):
    return {
        "temporal_text": text,
        "temporal": {
            "kind": kind,
            "exact_date": date,
            "exact_datetime": instant,
            "range_start": None,
            "range_end_exclusive": None,
        },
    }


def _result(shared_clock: str):
    return {
        "mentions": [
            _part("Mañana", "EXACT_DATE", date="2026-10-10"),
            _part("a las 10", "EXACT_DATETIME", instant="2026-10-10T10:00:00+02:00"),
            _part("a la misma hora", "EXACT_DATETIME", instant=shared_clock),
        ]
    }


def test_temporal_already_can_bind_same_explicit_clock_to_two_source_units():
    source, proposal = gate.original()
    fake, calls = _sdk_fake(_result("2026-10-10T10:00:00+02:00"))
    interpretation = OpenAITemporalInterpreter(fake, gate.CLOCK).interpret(source)
    scopes = bind_temporal_to_fact_candidates(proposal, interpretation)
    assert len(calls) == 1
    first = next(e for e in scopes if e.candidate_id == "candidate-1" and e.role == "time")
    second = next(e for e in scopes if e.candidate_id == "candidate-2" and e.role == "time")
    assert first.temporal_text == "a las 10"
    assert second.temporal_text == "a la misma hora"
    assert first.resolution.exact_datetime == second.resolution.exact_datetime
    assert first.has_exact_source_shape and second.has_exact_source_shape
    assert second.origin == "explicit"


def test_temporal_must_not_treat_missing_shared_hour_as_proven():
    source, proposal = gate.original()
    fake, _ = _sdk_fake(
        {
            "mentions": [
                _part("Mañana", "EXACT_DATE", date="2026-10-10"),
                _part("a las 10", "EXACT_DATETIME", instant="2026-10-10T10:00:00+02:00"),
            ]
        }
    )
    scopes = bind_temporal_to_fact_candidates(
        proposal, OpenAITemporalInterpreter(fake, gate.CLOCK).interpret(source)
    )
    later = next(e for e in scopes if e.candidate_id == "candidate-2" and e.role == "time")
    assert later.status == "missing"
    assert not later.has_exact_source_shape
    assert later.resolution is None


def test_temporal_source_shape_cannot_fake_exact_clock_with_date_only():
    source, proposal = gate.original()
    fake, _ = _sdk_fake(
        {
            "mentions": [
                _part("Mañana", "EXACT_DATE", date="2026-10-10"),
                _part("a las 10", "EXACT_DATE", date="2026-10-10"),
                _part("a la misma hora", "EXACT_DATE", date="2026-10-10"),
            ]
        }
    )
    scopes = bind_temporal_to_fact_candidates(
        proposal, OpenAITemporalInterpreter(fake, gate.CLOCK).interpret(source)
    )
    assert all(not e.has_exact_source_shape for e in scopes if e.role == "time")


def test_bound_budget_and_provider_flag(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "RECEIPT", tmp_path / "not-yet-run.json")
    monkeypatch.delenv(gate.FLAG, raising=False)
    dry = gate.run()
    assert dry["mode"] == "DRY_RUN_NO_PROVIDER"
    assert 0 < dry["reserved_max_usd"] < 0.002
    assert dry["reserved_max_usd"] + dry["estimated_previous_usd"] < 0.07
    fake = SimpleNamespace(responses=SimpleNamespace(create=lambda **_: None))
    with pytest.raises(ValueError, match="flag"):
        gate.run(live=True, client=fake)


def test_single_live_stub_persists_receipt_and_never_calls_again(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "RECEIPT", tmp_path / "temporal.json")
    monkeypatch.setenv(gate.FLAG, "1")
    raw = _result("2026-10-10T10:00:00+02:00")
    attempts = []

    def respond(**payload):
        attempts.append(payload)
        return SimpleNamespace(
            status="completed",
            output_text=json.dumps(raw, ensure_ascii=False),
            usage=SimpleNamespace(input_tokens=1100, output_tokens=275),
        )

    fake = SimpleNamespace(responses=SimpleNamespace(create=respond))
    result = gate.run(live=True, client=fake)
    assert len(attempts) == 1
    assert result["validation"] == "grounded"
    assert result["may_write_notes"] is False
    assert len(result["bindings"]) >= 4
    with pytest.raises(ValueError, match="already exists"):
        gate.run(live=True, client=fake)
    assert len(attempts) == 1
