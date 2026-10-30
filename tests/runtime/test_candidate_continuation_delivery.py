"""Existing actor-local delivery claims + canonical Core/E3 physical readback.

No actual model is called. Source-only coordinator is not product-wired.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from odyssey_core.application import ApplicationStatus
from odyssey_runtime.candidate_continuation_delivery import (
    CandidateContinuationPrewriteError,
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


@pytest.mark.parametrize("selected_identity", ("Luis", "Eric"))
def test_canonical_day_target_without_optional_anchors_reuses_core_e3_and_replay(
    tmp_path: Path, selected_identity: str
) -> None:
    """Ordinary Planner-shaped Day records reuse independent review and E3."""
    from odyssey_core.candidate_continuation_plan import inspect_selected_candidate_plan
    from odyssey_core.candidate_continuation_semantic import (
        validate_independent_continuation_verdict,
    )
    from odyssey_core.request_planning import RequestPlan, WriteAction
    from tests.runtime.test_candidate_continuation_reviewed_core_e3 import _prepared

    preview, pending, vault, context, plan, guard = _prepared(
        tmp_path, chosen_name=selected_identity
    )
    prior = vault.read_text("calendar/days/2026-10-03.md")
    writer, helper = plan.actions[0].units
    # Real Planner output does not always carry optional internal anchor rows.
    # The Day target is canonical Core identity, not an inferred test date.
    plan = RequestPlan((WriteAction((replace(writer, fact_temporal_anchors=()), helper)),), ())
    inspected = inspect_selected_candidate_plan(context, plan)
    assert inspected.proposed_facts[0].temporal_values == ("2026-10-05",)
    validate_independent_continuation_verdict(context, inspected, guard.review)
    store = LocalDeliveryResultStore(tmp_path / "ordinary-delivery-results")
    calls: list[str] = []

    def core(prepared, proposal, request_id, write_guard):
        calls.append(request_id)
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
        run_existing_core=core,
    )
    delivered = deliver_reviewed_candidate_continuation(**kwargs)
    assert delivered["status"] == "completed"
    assert delivered["facts"][0]["note_id"] == "date:2026-10-05"
    assert len(calls) == 1
    day = vault.read_text("calendar/days/2026-10-05.md")
    assert day.count(f"Iré al cine con [[{selected_identity}|{selected_identity}]]") == 1
    assert vault.read_text("calendar/days/2026-10-03.md") == prior
    replay = deliver_reviewed_candidate_continuation(
        **{**kwargs, "run_existing_core": lambda *_: pytest.fail("duplicate E3")}
    )
    assert replay == {**delivered, "delivery_replayed": True}
    assert len(calls) == 1


@pytest.mark.parametrize("selected", ("Luis", "Eric"))
def test_undated_recollection_continuation_writes_one_captured_day_entry_with_e3_replay(
    tmp_path: Path,
    selected: str,
) -> None:
    """Use the existing pending state, selected identity, E3 writer and replay."""
    from odyssey_core.candidate_continuation_context import prepare_selected_candidate_continuation
    from odyssey_core.candidate_continuation_plan import inspect_selected_candidate_plan
    from odyssey_core.candidate_continuation_semantic import (
        validate_independent_continuation_verdict,
    )
    from odyssey_core.candidate_pending_state import CandidatePendingRepository
    from odyssey_core.clarification import ClarificationOption
    from odyssey_core.request_planning import RequestPlan, WriteAction
    from tests.runtime.test_candidate_pending_state import NOW, _ready, _reply
    from tests.runtime.test_temporal_user_path_e2e import _linked_day_plan

    original, _, vault, _ = _ready(tmp_path)
    old_pending = original.pending[0]
    new_clause = "He estado con él en el parque."
    new_source = original.original_request[: old_pending.source_start] + new_clause
    reference_start = old_pending.source_start + new_clause.index("él")
    pending_item = replace(
        old_pending,
        source_text=new_clause,
        source_end=len(new_source),
        reference_start=reference_start,
        reference_end=reference_start + len("él"),
    )
    revised = replace(original, original_request=new_source, pending=(pending_item,))
    pending_root = tmp_path / "independent-no-date-pending"
    pending_root.mkdir()
    pending = CandidatePendingRepository(pending_root)
    pending.record(
        revised,
        conversation_id="chat-1",
        created_at=NOW,
        created_timezone="Europe/Paris",
        options=(ClarificationOption("eric-id", "Eric"), ClarificationOption("luis-id", "Luis")),
        vault=vault,
        schema=SCHEMA,
    )
    assert _reply(pending, vault, f"Con {selected}").outcome == "choice_recorded"
    context = prepare_selected_candidate_continuation(
        pending,
        conversation_id="chat-1",
        request_id=revised.request_id,
        vault=vault,
        schema=SCHEMA,
    )
    initial = _linked_day_plan(
        "2026-10-04",
        "He estado con {{ref:0}} en el parque.",
        "él",
        "2026-10-04",
        target_name=selected,
    )
    writer, helper = initial.actions[0].units
    plan = RequestPlan((WriteAction((replace(writer, fact_temporal_anchors=()), helper)),), ())
    inspection = inspect_selected_candidate_plan(context, plan)
    assert inspection.proposed_facts[0].temporal_values == ()
    review = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": 0,
                "kind": "record",
                "reviewed_text": "He estado con {{ref:0}} en el parque.",
                "date": None,
                "reference_names": [selected],
                "supported": True,
            }
        ],
    }
    validate_independent_continuation_verdict(context, inspection, review)
    before = {path: vault.read_text(path) for path in vault.list_markdown_paths()}
    store = LocalDeliveryResultStore(tmp_path / "no-date-journal-deliveries")
    calls: list[str] = []

    def run_core(prepared, proposal, request_id, guard):
        calls.append(request_id)
        return _execute(vault, prepared, proposal, guard, request_id=request_id)

    kwargs = dict(
        pending=pending,
        deliveries=store,
        conversation_id="chat-1",
        original_request_id=revised.request_id,
        plan=plan,
        independent_review=review,
        vault=vault,
        schema=SCHEMA,
        run_existing_core=run_core,
    )
    delivered = deliver_reviewed_candidate_continuation(**kwargs)
    assert delivered["status"] == "completed"
    assert delivered["facts"][0]["note_id"] == "date:2026-10-04"
    assert len(calls) == 1
    day = vault.read_text("calendar/days/2026-10-04.md")
    assert day.count(f"He estado con [[{selected}|{selected}]] en el parque.") == 1
    assert {
        path for path, original_text in before.items() if vault.read_text(path) != original_text
    } == {"calendar/days/2026-10-04.md"}
    replay = deliver_reviewed_candidate_continuation(
        **{**kwargs, "run_existing_core": lambda *_: pytest.fail("duplicate Core/E3")}
    )
    assert replay == {**delivered, "delivery_replayed": True}
    assert len(calls) == 1


def test_inconsistent_day_and_explicit_anchor_refuse_before_any_e3_claim(
    tmp_path: Path,
) -> None:
    """Conflicting temporal coordinates may not enter the reviewed write path."""
    from odyssey_core.request_planning import RequestPlan, WriteAction

    kwargs, calls = _inputs(tmp_path)
    writer, helper = kwargs["plan"].actions[0].units
    mismatched = replace(writer, target=replace(writer.target, query="2026-10-07"))
    altered = RequestPlan((WriteAction((mismatched, helper)),), ())
    with pytest.raises(CandidateContinuationPrewriteError, match="not current"):
        deliver_reviewed_candidate_continuation(**{**kwargs, "plan": altered})
    assert calls == []
    assert not (kwargs["vault"].root / "calendar/days/2026-10-07.md").exists()


def test_false_empty_temporal_claim_cannot_inherit_a_wrong_day_review(
    tmp_path: Path,
) -> None:
    """No date returned by a model cannot bypass the source-bound reviewer."""
    from odyssey_core.request_planning import RequestPlan, WriteAction
    from odyssey_core.temporal_interpretation import parse_temporal_interpretation
    from odyssey_runtime.composition import _continuation_exact_temporal_evidence

    kwargs, calls = _inputs(tmp_path)
    before = {
        path: kwargs["vault"].read_text(path) for path in kwargs["vault"].list_markdown_paths()
    }
    source = "Mañana iré al cine con él"
    false_empty = parse_temporal_interpretation(
        {"mentions": []},
        source,
        timezone="Europe/Paris",
        allow_empty_mentions=True,
    )
    assert _continuation_exact_temporal_evidence(source, false_empty) == ()
    writer, helper = kwargs["plan"].actions[0].units
    false_day = replace(
        writer,
        target=replace(writer.target, query="2026-10-04"),
        fact_temporal_anchors=(),
    )
    proposed = RequestPlan((WriteAction((false_day, helper)),), ())
    with pytest.raises(CandidateContinuationPrewriteError):
        deliver_reviewed_candidate_continuation(**{**kwargs, "plan": proposed})
    assert calls == []
    assert before == {
        path: kwargs["vault"].read_text(path) for path in kwargs["vault"].list_markdown_paths()
    }


def test_reviewer_rejects_before_claim_or_any_core_write(tmp_path: Path):
    kwargs, calls = _inputs(tmp_path)
    bad = dict(kwargs["independent_review"])
    bad["approved"] = False
    with pytest.raises(CandidateContinuationPrewriteError):
        deliver_reviewed_candidate_continuation(**{**kwargs, "independent_review": bad})
    assert not calls
    assert not (kwargs["vault"].root / "calendar/days/2026-10-05.md").exists()
    # Invalid review must not consume the legitimate delivery's one-time claim.
    completed = deliver_reviewed_candidate_continuation(**kwargs)
    assert completed["status"] == "completed"
    assert len(calls) == 1


def test_stale_preclaim_plan_or_review_is_not_reported_as_uncertain_write(
    tmp_path: Path,
) -> None:
    """Reviewer or stale plan errors are tagged prewrite; E3 is never called."""
    kwargs, calls = _inputs(tmp_path)
    plan = kwargs["plan"]
    writer, helper = plan.actions[0].units
    from odyssey_core.request_planning import RequestPlan, WriteAction

    changed = replace(writer, facts=("Iré al museo con {{ref:0}}.",))
    mutated_plan = RequestPlan((WriteAction((changed, helper)),), ())
    with pytest.raises(CandidateContinuationPrewriteError):
        deliver_reviewed_candidate_continuation(**{**kwargs, "plan": mutated_plan})
    assert calls == []
    assert not (kwargs["vault"].root / "calendar/days/2026-10-05.md").exists()


def test_changed_selected_note_before_claim_rejects_without_touching_e3(
    tmp_path: Path,
) -> None:
    kwargs, calls = _inputs(tmp_path)
    note = kwargs["vault"].root / "Luis.md"
    note.write_text(note.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(CandidateContinuationPrewriteError):
        deliver_reviewed_candidate_continuation(**kwargs)
    assert not calls
    assert not (kwargs["vault"].root / "calendar/days/2026-10-05.md").exists()


def test_missing_or_wrong_conversation_refuses_without_claim(tmp_path: Path):
    kwargs, calls = _inputs(tmp_path)
    with pytest.raises(CandidateContinuationPrewriteError, match="No selected candidate"):
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
