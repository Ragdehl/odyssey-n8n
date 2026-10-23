"""C4: post-Core guidance is actor-scoped, read-only and receipt-grounded."""

from __future__ import annotations

from uuid import uuid4

import pytest

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime.conversation_error import explain_trusted_product_failure
from odyssey_runtime.conversation_gateway import OpenAIConversationGateway
from odyssey_runtime.serialization import application_result_to_response
from tests.runtime.test_conversation_gateway import FakeClient


def result(status, *, reason, affected=(), request_id="c4-test"):
    return ApplicationResult(
        request_id=request_id,
        status=ApplicationStatus(status),
        action_results=(),
        affected_stable_note_ids=tuple(affected),
        planning_error=reason,
    )


@pytest.mark.parametrize(
    ("reason", "category", "hint"),
    [
        ("TEMPORAL_COHORT_UNRESOLVED", "SPECIFY_DATE", "ASK_USER"),
        ("AMBIGUOUS_REFERENCE", "SPECIFY_IDENTITY", "ASK_USER"),
        ("ROUTER_NEEDS_CAPABILITY", "UNSUPPORTED", "EXPLAIN"),
        ("OPERATIONAL_FAILURE", "RETRY_LATER", "REVIEW_RETRY"),
        ("UNREPRESENTABLE_REQUEST", "CLARIFY_REQUEST", "ASK_USER"),
        ("NEW_FUTURE_APP_REASON", "UNKNOWN", "EXPLAIN"),
    ],
)
def test_reason_families_have_bounded_nonexecuting_fallback(reason, category, hint):
    typed = result("failed", reason=reason)
    response = application_result_to_response(typed)
    view = explain_trusted_product_failure(typed, response, None)
    assert view == {
        "status": "failed",
        "reason_code": reason,
        "write_evidence": "UNKNOWN",  # empty affected IDs do not prove zero
        "guidance_kind": category,
        "hint": hint,
    }


def test_partial_verified_writes_are_some_not_zero_and_model_cannot_override():
    typed = result("partial", reason="OPERATIONAL_FAILURE", affected=("note-a", "note-b"))
    response = application_result_to_response(typed)
    client = FakeClient([{"guidance_kind": "SPECIFY_IDENTITY", "hint": "ASK_USER"}])
    advice = explain_trusted_product_failure(typed, response, OpenAIConversationGateway(client))
    assert advice["write_evidence"] == "SOME"
    assert advice["guidance_kind"] == "RETRY_LATER"
    assert advice["hint"] == "REVIEW_RETRY"
    sent = client.responses.calls[0]["input"][1]["content"]
    assert '"write_evidence":"SOME"' in sent
    assert "note-a" not in sent and "note-b" not in sent
    assert "request_id" not in sent


def test_model_correct_safe_hint_allowed_and_no_freeform_text():
    typed = result("failed", reason="TEMPORAL_COHORT_UNRESOLVED")
    client = FakeClient([{"guidance_kind": "SPECIFY_DATE", "hint": "ASK_USER"}])
    view = explain_trusted_product_failure(
        typed, application_result_to_response(typed), OpenAIConversationGateway(client)
    )
    assert view["guidance_kind"] == "SPECIFY_DATE"
    assert "message" not in view and "retry_authorized" not in view
    assert len(client.responses.calls) == 1


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("provider down"),
        {"guidance_kind": "RETRY_LATER", "hint": "RETRY_NOW"},
        {"guidance_kind": "UNKNOWN", "hint": "EXPLAIN", "no_writes": True},
    ],
)
def test_provider_failure_or_injection_keeps_fallback_without_changing_result(failure):
    typed = result("failed", reason="OPERATIONAL_FAILURE")
    original = application_result_to_response(typed)
    view = explain_trusted_product_failure(
        typed, original, OpenAIConversationGateway(FakeClient([failure]))
    )
    assert view["guidance_kind"] == "RETRY_LATER"
    assert view["write_evidence"] == "UNKNOWN"
    assert "error_guidance" not in original


def test_model_not_called_on_unknown_code_or_wrong_result():
    client = FakeClient([])
    model = OpenAIConversationGateway(client)
    typed = result("failed", reason="ATTACK_NEW_REASON")
    view = explain_trusted_product_failure(typed, application_result_to_response(typed), model)
    assert view["guidance_kind"] == "UNKNOWN"
    typed = result("completed", reason="OPERATIONAL_FAILURE")
    assert (
        explain_trusted_product_failure(typed, application_result_to_response(typed), model) is None
    )
    assert client.responses.calls == []


def test_forged_response_status_or_id_rejected_as_an_explanation():
    typed = result("failed", reason="OPERATIONAL_FAILURE")
    for alteration in (
        {"request_id": "other"},
        {"status": "partial"},
        {"product_outcome": "ANSWER"},
    ):
        response = {**application_result_to_response(typed), **alteration}
        assert explain_trusted_product_failure(typed, response, None) is None


def test_composition_opt_in_preserves_durable_failing_receipt_and_replay(tmp_path):
    """The production-equivalent guarded E3 seam must NEVER execute again."""
    calls = []

    def hybrid(source, request_id, actor, conversation_id):
        calls.append((source, request_id, actor.stable_user_id, conversation_id))
        return result("failed", reason="TEMPORAL_COHORT_UNRESOLVED", request_id=request_id)

    actor = AuthenticatedActorContext(str(uuid4()))
    runtime = RuntimeComposition(
        core_execute=lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("wrong route")),
        hybrid_candidate_execute=hybrid,
        full_source_mutation_guard=True,
        refresh_indexes=lambda: None,
        conversation_root_resolver=ConversationRootResolver(tmp_path / "synthetic"),
        conversation_error_guidance_enabled=True,
    )
    first = runtime.execute_product("A date was ambiguous", "c4-replay", "main", actor)
    assert first["error_guidance"]["guidance_kind"] == "SPECIFY_DATE"
    assert first["error_guidance"]["write_evidence"] == "UNKNOWN"
    assert first["status"] == "failed"
    again = runtime.execute_product("A date was ambiguous", "c4-replay", "main", actor)
    assert again["delivery_replayed"] is True
    assert {k: v for k, v in again.items() if k != "delivery_replayed"} == first
    assert calls == [("A date was ambiguous", "c4-replay", actor.stable_user_id, "main")]
    assert "retry_authorized" not in first["error_guidance"]
    assert first["affected_stable_note_ids"] == []


def test_many_verified_writes_preserve_positive_evidence_without_exact_count():
    """A bulk write never degrades to UNKNOWN merely because it exceeds 64."""
    typed = result(
        "partial",
        reason="OPERATIONAL_FAILURE",
        affected=tuple(f"synthetic-{i}" for i in range(70)),
    )
    client = FakeClient([{"guidance_kind": "RETRY_LATER", "hint": "REVIEW_RETRY"}])
    view = explain_trusted_product_failure(
        typed, application_result_to_response(typed), OpenAIConversationGateway(client)
    )
    assert view["write_evidence"] == "SOME"
    assert view["guidance_kind"] == "RETRY_LATER"
    sent = client.responses.calls[0]["input"][1]["content"]
    assert '"write_evidence":"SOME"' in sent
    assert "synthetic-69" not in sent


def test_generic_identity_request_handles_future_app_entity_types():
    """C4 may identify any registered App target, not only people/tasks."""
    typed = result("failed", reason="AMBIGUOUS_REFERENCE")
    view = explain_trusted_product_failure(typed, application_result_to_response(typed), None)
    from odyssey_runtime.conversation_gateway import (
        ErrorAdvice,
        GuidanceKind,
        RecoveryHint,
        VerifiedFailure,
    )

    user_text = ErrorAdvice(
        GuidanceKind(view["guidance_kind"]), RecoveryHint(view["hint"])
    ).user_message(VerifiedFailure("c4-test", "failed", "AMBIGUOUS_REFERENCE", None))
    assert "elemento" in user_text
    assert "persona o la tarea" not in user_text


def test_c4_receipts_are_isolated_by_authenticated_actor(tmp_path):
    """Identical request IDs may carry different guidance in different actors."""
    first_actor = AuthenticatedActorContext(str(uuid4()))
    second_actor = AuthenticatedActorContext(str(uuid4()))
    calls = []

    def hybrid(source, request_id, actor, conversation_id):
        calls.append((actor.stable_user_id, request_id))
        reason = (
            "TEMPORAL_COHORT_UNRESOLVED"
            if actor.stable_user_id == first_actor.stable_user_id
            else "OPERATIONAL_FAILURE"
        )
        return result("failed", reason=reason, request_id=request_id)

    runtime = RuntimeComposition(
        core_execute=lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("wrong path")),
        hybrid_candidate_execute=hybrid,
        full_source_mutation_guard=True,
        refresh_indexes=lambda: None,
        conversation_root_resolver=ConversationRootResolver(tmp_path / "actor-scoped"),
        conversation_error_guidance_enabled=True,
    )
    first = runtime.execute_product("A synthetic failure", "same-id", "main", first_actor)
    second = runtime.execute_product("A synthetic failure", "same-id", "main", second_actor)
    assert first["error_guidance"]["guidance_kind"] == "SPECIFY_DATE"
    assert second["error_guidance"]["guidance_kind"] == "RETRY_LATER"
    assert first["error_guidance"]["reason_code"] != second["error_guidance"]["reason_code"]
    assert (
        runtime.execute_product("A synthetic failure", "same-id", "main", first_actor)[
            "delivery_replayed"
        ]
        is True
    )
    assert (
        runtime.execute_product("A synthetic failure", "same-id", "main", second_actor)[
            "delivery_replayed"
        ]
        is True
    )
    assert calls == [
        (first_actor.stable_user_id, "same-id"),
        (second_actor.stable_user_id, "same-id"),
    ]
