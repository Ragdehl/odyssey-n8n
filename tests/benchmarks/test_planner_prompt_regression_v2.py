"""Provider-free guards for the final planner prompt regression v2 gate."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest

from benchmarks.planner_prompt_regression_v1 import run_live as base
from benchmarks.planner_prompt_regression_v2 import run_live


def test_v2_reuses_complete_frozen_matrix() -> None:
    """Keep every inherited regression sentinel and its fixed context."""
    cases, context = base.load_gate_cases()
    assert len(cases) == run_live.MAX_CALLS == 16
    assert (
        hashlib.sha256(run_live._matrix_payload(cases, context)).hexdigest()
        == run_live.MATRIX_SHA256
    )
    assert [case["id"] for case in cases[-3:]] == [
        "PPR14-unknown-self-member-write",
        "PPR15-unknown-self-member-after-related-turn",
        "PPR16-unknown-self-project-member-write",
    ]


def _retained_v2_artifact() -> dict:
    return json.loads((run_live.RESULTS_DIR / "8208d9636c43.json").read_text(encoding="utf-8"))


def test_v2_retained_evidence_matches_its_frozen_historical_contract() -> None:
    """Keep the consumed v2 evidence auditable without making it the current baseline."""
    artifact = _retained_v2_artifact()
    assert artifact["prompt_sha256"] == run_live.PROMPT_SHA256
    assert artifact["provider_schema_sha256"] == run_live.PROVIDER_SCHEMA_SHA256
    assert artifact["teaching_examples_sha256"] == run_live.TEACHING_SHA256
    assert artifact["matrix_sha256"] == run_live.MATRIX_SHA256


def test_v2_retained_execution_was_complete_and_bounded() -> None:
    artifact = _retained_v2_artifact()
    assert artifact["provider_attempts"] == artifact["completed_provider_responses"] == 16
    assert artifact["automatic_retries"] == 0
    assert artifact["acceptable"] is True
    assert Decimal(artifact["estimated_standard_cost_usd"]) < run_live.AUTHORIZED_CEILING_USD


def test_v2_is_consumed_historical_evidence_not_a_rerunnable_current_gate() -> None:
    assert list(run_live.RESULTS_DIR.glob("*.json"))


def test_v2_keeps_prior_reviewed_safe_degradation_policy() -> None:
    """A new regression outside the three inherited reviewed IDs remains blocking."""
    reviewed = [
        {"case_id": case_id, "passed": False} for case_id in sorted(base.ACCEPTED_FAILURE_IDS)
    ]
    assert base._matrix_acceptable(reviewed)
    assert not base._matrix_acceptable(
        reviewed + [{"case_id": "SWR10-relational-target-two-bounded-references", "passed": False}]
    )


def test_v2_recording_transport_does_not_retain_exception_text() -> None:
    """Retain bounded provider failure evidence only."""

    class FailingResponses:
        def create(self, **_kwargs):  # type: ignore[no-untyped-def]
            error = RuntimeError("sensitive provider detail")
            error.status_code = 400  # type: ignore[attr-defined]
            raise error

    recorder = run_live.RecordingResponses(FailingResponses())
    with pytest.raises(RuntimeError):
        recorder.create(model="gpt-5.6-luna")
    assert recorder.attempts == 1
    assert recorder.failures == [{"attempt": 1, "error_type": "RuntimeError", "status_code": 400}]
    assert "sensitive" not in repr(recorder.failures)
