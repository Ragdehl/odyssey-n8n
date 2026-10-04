"""Provider-free guards for the final planner prompt regression v3 gate."""

from __future__ import annotations

import hashlib
import json

import pytest

from benchmarks.planner_prompt_regression_v1 import run_live as base
from benchmarks.planner_prompt_regression_v3 import run_live


def test_v3_reuses_complete_frozen_matrix() -> None:
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


def test_v3_is_retained_historical_core_evidence() -> None:
    """Keep the consumed v3 hashes immutable while the current Core contract moves on."""
    _cases, context = base.load_gate_cases()
    schema = json.loads(run_live.SCHEMA_PATH.read_text(encoding="utf-8"))
    historical = (run_live.PROMPT_SHA256, run_live.PROVIDER_SCHEMA_SHA256, run_live.TEACHING_SHA256)
    assert historical == (
        "3825f67eb4a209d709193cb1d928b94d7cd1a8b1035bba78f2f54f2b7275f143",
        "d336432ba67b471030ac67eed11bb389065d5832d4032906774bbef52e84cb23",
        "e3ad1321ab56fb0ce0a3b587a73c07f282c748ec6ae0f203bb50ca13d1d3f5c0",
    )
    assert run_live._contract_hashes(schema, context) != historical


def test_v3_preflight_refuses_reuse_after_current_contract_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match="contract changed"):
        run_live._preflight()


def test_v3_keeps_prior_reviewed_safe_degradation_policy() -> None:
    """A new regression outside the three inherited reviewed IDs remains blocking."""
    reviewed = [
        {"case_id": case_id, "passed": False} for case_id in sorted(base.ACCEPTED_FAILURE_IDS)
    ]
    assert base._matrix_acceptable(reviewed)
    assert not base._matrix_acceptable(
        reviewed + [{"case_id": "SWR10-relational-target-two-bounded-references", "passed": False}]
    )


def test_v3_recording_transport_does_not_retain_exception_text() -> None:
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


def test_v3_retained_summary_records_blocking_live_result_without_inventing_rows() -> None:
    artifacts = list(run_live.RESULTS_DIR.glob("*.reconstructed.json"))
    assert len(artifacts) == 1
    artifact = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert artifact["version"] == 3
    assert artifact["reconstructed_from_runner_stdout"] is True
    assert artifact["full_row_artifact_available"] is False
    assert artifact["provider_attempts"] == artifact["completed_provider_responses"] == 16
    assert artifact["automatic_retries"] == artifact["sol_calls"] == 0
    assert artifact["acceptable"] is False
    assert artifact["failed_case_ids"] == [
        "SWR07-qualified-event-member",
        "SWR08-relational-target-described-reference",
        "SWR10-relational-target-two-bounded-references",
        "SWF-MIXED-ORDER-01",
    ]
