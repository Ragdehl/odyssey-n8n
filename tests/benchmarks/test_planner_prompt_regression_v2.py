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


def test_v2_pins_exact_current_candidate_contract() -> None:
    """Refuse evidence from any prompt/schema/examples contract other than this candidate."""
    _cases, context = base.load_gate_cases()
    schema = json.loads(run_live.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert run_live._contract_hashes(schema, context) == (
        run_live.PROMPT_SHA256,
        run_live.PROVIDER_SCHEMA_SHA256,
        run_live.TEACHING_SHA256,
    )


def test_v2_budget_is_complete_and_bounded() -> None:
    """Bound all 16 zero-retry production-model calls before provider authority exists."""
    budget = run_live.budget_snapshot()
    assert budget["calls"] == 16
    assert budget["conservative_usd_upper"] == Decimal("0.214944")
    assert budget["conservative_usd_upper"] <= run_live.AUTHORIZED_CEILING_USD == Decimal("0.215")


def test_v2_has_zero_provider_authority_without_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not permit provider access until the exact bounded gate is human-authorized."""
    monkeypatch.delenv(run_live.AUTH_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "presence-only")
    with pytest.raises(SystemExit, match=run_live.AUTH_ENV):
        run_live._preflight()


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
