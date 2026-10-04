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


def test_v11_is_retained_historical_evidence_not_the_current_contract() -> None:
    """Keep the consumed v11 hashes immutable while proving Calendar chat routing is retired."""
    historical = (
        run_live.ROUTER_PROMPT_SHA256,
        run_live.ROUTER_SCHEMA_SHA256,
        run_live.CALENDAR_PROMPT_SHA256,
        run_live.CALENDAR_SCHEMA_SHA256,
    )
    assert historical == (
        "1140626c2c05ec02d33aebc96456e4dc7387a8cab6340b18427c8fb8843d06d6",
        "86ddd47fd22d1e6f3496d784679f6e71ac0b44a89b16d6d487a3298ea162908e",
        "ecdfd472ef2a51ab32dd9512132bc77d77462e8fef81444971da844d2d6ab711",
        "2230bfa0bf885b0c97e5bd458cebda6d38ebca8ec555fdbb72736fbc911f7e3c",
    )
    assert run_live._contract_hashes() != historical


def test_v11_preflight_refuses_reuse_after_contract_retirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A historical authorization can never be reused against the new Router/Temporal contract."""
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match="contract changed"):
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


def test_v11_retained_summary_records_consumed_pass_without_inventing_rows() -> None:
    artifacts = list(run_live.RESULTS_DIR.glob("*.reconstructed.json"))
    assert len(artifacts) == 1
    artifact = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert artifact["version"] == 11
    assert artifact["reconstructed_from_runner_stdout"] is True
    assert artifact["full_row_artifact_available"] is False
    assert artifact["provider_attempts"] == artifact["completed_provider_responses"] == 18
    assert artifact["automatic_retries"] == 0
    assert artifact["passed"] is True
