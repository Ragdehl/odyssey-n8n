"""Provider-free guards for the Journal-converged Router + Calendar live gate v11."""

from __future__ import annotations

import hashlib
import json

import pytest

from benchmarks.application_router_calendar_live_v11 import run_live


def test_v11_frozen_matrices_cover_journal_convergence_and_prior_routes() -> None:
    assert hashlib.sha256(run_live.ROUTER_MATRIX.read_bytes()).hexdigest() == (
        run_live.ROUTER_MATRIX_SHA256
    )
    assert hashlib.sha256(run_live.CALENDAR_MATRIX.read_bytes()).hexdigest() == (
        run_live.CALENDAR_MATRIX_SHA256
    )
    router = json.loads(run_live.ROUTER_MATRIX.read_text(encoding="utf-8"))
    calendar = json.loads(run_live.CALENDAR_MATRIX.read_text(encoding="utf-8"))
    assert router["version"] == 3 and len(router["cases"]) == 9
    assert calendar["version"] == 7 and len(calendar["cases"]) == 9
    assert {case["id"] for case in router["cases"]} >= {
        "journal-to-calendar",
        "journal-implicit-today-to-calendar",
        "tasks-disabled",
    }
    assert {case["id"] for case in calendar["cases"]} >= {
        "journal-explicit-day-capture",
        "journal-implicit-current-day-capture",
        "task-lifecycle-not-calendar-literal",
    }


def test_v11_pins_exact_candidate_contract_and_budget() -> None:
    assert run_live._contract_hashes() == (
        run_live.ROUTER_PROMPT_SHA256,
        run_live.ROUTER_SCHEMA_SHA256,
        run_live.CALENDAR_PROMPT_SHA256,
        run_live.CALENDAR_SCHEMA_SHA256,
    )
    budget = run_live.budget_snapshot()
    assert budget == {
        "calls": 18,
        "input_bytes_upper": 55623,
        "max_output_tokens": 9216,
        "standard_usd_upper": 0.0101703,
        "regional_usd_upper": 0.01118733,
    }
    assert budget["regional_usd_upper"] < run_live.AUTHORIZED_CEILING_USD == 0.013


def test_v11_has_zero_provider_authority_without_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match=run_live.AUTH_ENV):
        run_live._preflight()


def test_v11_calendar_oracle_requires_exact_capture_text() -> None:
    actual = {
        "outcome": "PLAN",
        "intent": "DAY_LITERAL_CAPTURE",
        "temporal_kind": "EXACT_DATE",
        "exact_date": "2026-10-02",
        "temporal_text": None,
        "capture_text": "he tenido un día tranquilo.",
        "failure_code": None,
    }
    expected = {
        "outcome": "PLAN",
        "intent": "DAY_LITERAL_CAPTURE",
        "temporal_kind": "EXACT_DATE",
        "exact_date": "2026-10-02",
        "temporal_text": None,
        "capture_text": "he tenido un día tranquilo.",
    }
    assert run_live._expected_subset(actual, expected)
    actual["capture_text"] = "Fue un día tranquilo."
    assert not run_live._expected_subset(actual, expected)
