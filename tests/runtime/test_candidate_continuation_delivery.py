"""Existing actor-local delivery claims + canonical Core/E3 physical readback.

No actual model is called. Source-only coordinator is not product-wired.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_continuation_semantic import CandidateContinuationSemanticError
from odyssey_runtime.candidate_continuation_delivery import (
    deliver_reviewed_candidate_continuation,
)
from odyssey_runtime.delivery_results import DeliveryResultError, LocalDeliveryResultStore
from tests.runtime.test_candidate_continuation_reviewed_core_e3 import _execute, _prepared
from tests.runtime.test_temporal_user_path_e2e import SCHEMA


def _inputs(tmp_path: Path):
    preview, pending, vault, context, plan, guard = _prepared(tmp_path)
    store = LocalDeliveryResultStore(tmp_path / "delivery-results")
    calls: list[str] = []

    def existing_core(prepared, proposal, request_id, write_guard):
        calls.append(request_id)
        assert prepared == context
        assert proposal == plan
        return _execute(vault, prepared, proposal, write_guard, request_id=request_id)

    kwargs = dict(
        pending=pending,
        deliveries=store,
        conversation_id=context.conversation_id,
        original_request_id=preview.request_id,
        plan=plan,
        independent_review=guard.review,
        vault=vault,
        schema=SCHEMA,
        run_existing_core=existing_core,
        completed_at="2026-10-30T11:00:00+00:00",
    )
    return kwargs, calls


def test_reviewed_continuation_reuses_delivery_receipt_with_no_second_writer(
    tmp_path: Path,
):
    kwargs, calls = _inputs(tmp_path)
    original_day = kwargs["vault"].read_text("calendar/days/2026-10-03.md")
    first = deliver_reviewed_candidate_continuation(**kwargs)
    assert first["status"] == "completed"
    assert first["kind"] == "reviewed_candidate_continuation"
    assert len(first["facts"]) == 1
    assert first["facts"][0]["status"] == "verified_in_markdown"
    assert first["facts"][0]["note_id"] == "date:2026-10-05"
    assert len(calls) == 1
    assert kwargs["vault"].read_text("calendar/days/2026-10-03.md") == original_day
    assert kwargs["pending"].read(kwargs["original_request_id"])["status"] == "selected"
    reread = LocalDeliveryResultStore(tmp_path / "delivery-results")
    replay = deliver_reviewed_candidate_continuation(
        **{
            **kwargs,
            "deliveries": reread,
            "run_existing_core": lambda *_: pytest.fail("replayed E3"),
        }
    )
    assert replay == {**first, "delivery_replayed": True}
    assert len(calls) == 1
    day = kwargs["vault"].read_text("calendar/days/2026-10-05.md")
    assert day.count("Iré al cine con [[Luis|Luis]]") == 1


def test_reviewer_rejects_before_claim_or_any_core_write(tmp_path: Path):
    kwargs, calls = _inputs(tmp_path)
    bad = dict(kwargs["independent_review"])
    bad["approved"] = False
    with pytest.raises(CandidateContinuationSemanticError):
        deliver_reviewed_candidate_continuation(**{**kwargs, "independent_review": bad})
    assert not calls
    assert not (kwargs["vault"].root / "calendar/days/2026-10-05.md").exists()
    # Invalid review must not consume the legitimate delivery's one-time claim.
    completed = deliver_reviewed_candidate_continuation(**kwargs)
    assert completed["status"] == "completed"
    assert len(calls) == 1


def test_missing_or_wrong_conversation_refuses_without_claim(tmp_path: Path):
    kwargs, calls = _inputs(tmp_path)
    with pytest.raises(ValueError, match="No selected candidate"):
        deliver_reviewed_candidate_continuation(
            **{**kwargs, "conversation_id": "another-conversation"}
        )
    assert not calls


@pytest.mark.parametrize("failure", ["crash_after_write", "tamper_after_write", "bad_core_status"])
def test_postwrite_failure_preserves_existing_unresolved_claim_and_blocks_reexecution(
    tmp_path: Path, failure: str
):
    kwargs, calls = _inputs(tmp_path)
    original_run = kwargs["run_existing_core"]

    def failing_core(prepared, proposal, request_id, write_guard):
        outcome = original_run(prepared, proposal, request_id, write_guard)
        if failure == "crash_after_write":
            raise RuntimeError("synthetic network/worker crash after E3")
        if failure == "tamper_after_write":
            path = kwargs["vault"].root / "calendar/days/2026-10-05.md"
            path.write_text(
                path.read_text(encoding="utf-8").replace("Iré al cine", "Iré al teatro"),
                encoding="utf-8",
            )
        if failure == "bad_core_status":
            return replace(outcome, status=ApplicationStatus.NEEDS_ATTENTION)
        return outcome

    kwargs["run_existing_core"] = failing_core
    with pytest.raises((RuntimeError, DeliveryResultError)):
        deliver_reviewed_candidate_continuation(**kwargs)
    assert len(calls) == 1
    with pytest.raises(DeliveryResultError, match="unresolved prior E3 attempt"):
        deliver_reviewed_candidate_continuation(
            **{**kwargs, "run_existing_core": lambda *_: pytest.fail("unsafe second E3")}
        )
    assert len(calls) == 1
    assert kwargs["pending"].read(kwargs["original_request_id"])["status"] == "selected"


def test_corrupt_selected_identity_receipt_cannot_be_reported_complete(tmp_path: Path):
    """Readback cannot claim the user's chosen person from a different helper ID."""
    kwargs, calls = _inputs(tmp_path)
    original = kwargs["run_existing_core"]

    def mismatched_result(prepared, proposal, request_id, write_guard):
        completed = original(prepared, proposal, request_id, write_guard)
        first = completed.action_results[0]
        altered_helper = replace(first.unit_results[1], stable_note_id="eric-id")
        return replace(
            completed,
            action_results=(replace(first, unit_results=(first.unit_results[0], altered_helper)),),
        )

    with pytest.raises(DeliveryResultError, match="selected identity receipt"):
        deliver_reviewed_candidate_continuation(
            **{**kwargs, "run_existing_core": mismatched_result}
        )
    assert len(calls) == 1
    assert kwargs["pending"].read(kwargs["original_request_id"])["status"] == "selected"
