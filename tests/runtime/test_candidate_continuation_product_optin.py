"""Source-isolated product-delivery continuation, ordinary Core/E3 writer.

Uses a synthetic independent reviewer decision, never a fake real-model claim.
The production default is still OFF.
"""

from pathlib import Path

from odyssey_core.application import execute_request
from odyssey_core.candidate_continuation_plan import inspect_selected_candidate_plan
from odyssey_core.candidate_pending_state import CandidatePendingRepository
from odyssey_core.request_planning import RequestPlan
from odyssey_runtime.candidate_continuation_delivery import (
    deliver_reviewed_candidate_continuation,
)
from odyssey_runtime.delivery_results import LocalDeliveryResultStore
from tests.runtime.test_hybrid_product_pending_v2 import ACTOR, _runtime
from tests.runtime.test_temporal_user_path_e2e import SCHEMA, _linked_day_plan


def test_optin_product_reply_runs_one_guarded_core_write_then_replays(tmp_path: Path):
    runtime, resolver, vault, calls, source, initial_id = _runtime(tmp_path)
    prior = vault.read_text("calendar/days/2026-10-03.md")
    original = runtime.execute_product(source, initial_id, "main", ACTOR)
    assert original["status"] == "partial"
    e3_calls: list[str] = []

    def perform(context, actor):
        assert actor == ACTOR.stable_user_id
        plan = _linked_day_plan(
            "2026-10-05",
            "Iré al cine con {{ref:0}}.",
            context.reference_text,
            "2026-10-05",
            target_name=context.selected_name,
        )
        inspection = inspect_selected_candidate_plan(context, plan)
        independent_review = {
            "approved": True,
            "complete": True,
            "reason": None,
            "facts": [
                {
                    "ordinal": 0,
                    "kind": "record",
                    "reviewed_text": inspection.proposed_facts[0].text,
                    "date": "2026-10-05",
                    "reference_names": [context.selected_name],
                    "supported": True,
                }
            ],
        }

        def core(prepared, proposed: RequestPlan, request_id, write_guard):
            e3_calls.append(request_id)
            return execute_request(
                prepared.pending_source,
                planner=type("FixedTestPlanner", (), {"plan": lambda _, __: proposed})(),
                repository=vault,
                schema=SCHEMA,
                context_index=object(),
                semantic_index=object(),
                embedder=object(),
                contextual_reasoner=object(),
                actor="synthetic-optin-only",
                now=prepared.captured_at,
                context_limit=5,
                request_id_factory=lambda: request_id,
                write_preflight_guard=write_guard,
            )

        state = resolver.resolve(actor)
        return deliver_reviewed_candidate_continuation(
            pending=CandidatePendingRepository(state / "pending"),
            deliveries=LocalDeliveryResultStore(state / "delivery-results"),
            conversation_id=context.conversation_id,
            original_request_id=context.original_request_id,
            plan=plan,
            independent_review=independent_review,
            vault=vault,
            schema=SCHEMA,
            run_existing_core=core,
        )

    runtime.candidate_continuation_execute = perform
    delivered = runtime.execute_product("Con Luis", "reply-product-optin", "main", ACTOR)
    assert delivered["status"] == "completed"
    assert delivered["product_control"] == "CANDIDATE_CONTINUATION_SAVED"
    assert delivered["affected_stable_note_ids"] == ["date:2026-10-05"]
    assert len(e3_calls) == 1
    assert vault.read_text("calendar/days/2026-10-03.md") == prior
    day = vault.read_text("calendar/days/2026-10-05.md")
    assert day.count("Iré al cine con [[Luis|Luis]]") == 1
    replay = runtime.execute_product("Con Luis", "reply-product-optin", "main", ACTOR)
    assert replay["delivery_replayed"]
    assert len(e3_calls) == 1
    assert vault.read_text("calendar/days/2026-10-05.md") == day
    assert calls == [(source, initial_id)]


def test_selected_reply_with_failing_optin_does_not_silently_claim_saved(tmp_path: Path):
    runtime, resolver, vault, _calls, source, initial_id = _runtime(tmp_path)
    runtime.execute_product(source, initial_id, "main", ACTOR)
    before = {p: vault.read_text(p) for p in vault.list_markdown_paths()}

    def fail(context, actor):
        assert context.original_request_id == initial_id
        assert actor == ACTOR.stable_user_id
        raise RuntimeError("synthetic provider refusal")

    runtime.candidate_continuation_execute = fail
    result = runtime.execute_product("Con Luis", "reply-product-blocked", "main", ACTOR)
    assert result["status"] == "needs_attention"
    assert result["product_reason"] == "CONTINUATION_REQUIRES_RECONCILIATION"
    assert "saved" not in str(result).lower()
    assert {p: vault.read_text(p) for p in vault.list_markdown_paths()} == before
    assert runtime.execute_product("Con Luis", "reply-product-blocked", "main", ACTOR)[
        "delivery_replayed"
    ]
    assert (
        CandidatePendingRepository(resolver.resolve(ACTOR.stable_user_id) / "pending").read(
            initial_id
        )["status"]
        == "selected"
    )


def test_prewrite_planner_refusal_is_not_falsely_reported_as_postwrite_crash(tmp_path: Path):
    from odyssey_runtime.candidate_continuation_delivery import CandidateContinuationPrewriteError

    runtime, resolver, vault, _calls, source, initial_id = _runtime(tmp_path)
    runtime.execute_product(source, initial_id, "main", ACTOR)
    before = {p: vault.read_text(p) for p in vault.list_markdown_paths()}

    def invalid_plan(_context, _actor):
        raise CandidateContinuationPrewriteError("synthetic planner invalid before claim")

    runtime.candidate_continuation_execute = invalid_plan
    failed = runtime.execute_product("Con Luis", "reply-prewrite-failed", "main", ACTOR)
    assert failed["status"] == "needs_attention"
    assert failed["product_control"] == "CANDIDATE_REVIEW_NOT_APPROVED"
    assert failed["product_reason"] == "CONTINUATION_REVIEW_REQUIRED"
    assert {p: vault.read_text(p) for p in vault.list_markdown_paths()} == before
    assert (
        CandidatePendingRepository(resolver.resolve(ACTOR.stable_user_id) / "pending").read(
            initial_id
        )["status"]
        == "selected"
    )
