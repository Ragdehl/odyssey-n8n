"""Product-boundary E1 coverage for durable hybrid source clarifications."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from odyssey_core.application import ApplicationResult, ApplicationStatus, PendingWorkStatus
from odyssey_core.candidate_pending_state import CandidatePendingRepository
from odyssey_core.clarification import ClarificationOption
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime.delivery_results import DeliveryResultError
from odyssey_runtime.routing import route_execution_id
from tests.runtime.test_candidate_pending_state import NOW, _ready
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA

ACTOR = AuthenticatedActorContext("11111111-1111-4111-8111-111111111111")
OTHER_ACTOR = AuthenticatedActorContext("22222222-2222-4222-8222-222222222222")


class _NewRequestClassifier:
    """Treat one test-only unrelated message as a new request without provider access."""

    def classify(
        self, reply: str, original_request: str, options: tuple[ClarificationOption, ...]
    ) -> str:
        del original_request, options
        return "NEW_REQUEST" if reply == "Una petición distinta" else "UNRESOLVED"


def _runtime(tmp_path: Path, *, classifier: object | None = None, routed: bool = False):
    """Build a production composition with a frozen v2 recorder and disposable vault."""
    fixture_root = tmp_path / "fixture"
    fixture_root.mkdir()
    preview, _unused_pending, vault, _unused_state = _ready(fixture_root)
    resolver = ConversationRootResolver(tmp_path / "state")
    calls: list[tuple[str, str]] = []

    def hybrid(
        source: str, request_id: str, actor: AuthenticatedActorContext, conversation_id: str
    ):
        calls.append((source, request_id))
        if source != preview.original_request:
            return ApplicationResult(request_id, ApplicationStatus.COMPLETED, (), ())
        root = resolver.resolve(actor.stable_user_id) / "pending"
        root.mkdir(parents=True, exist_ok=True)
        pending = CandidatePendingRepository(root)
        pending_id = route_execution_id(request_id, 0) if routed else request_id
        pending.record(
            replace(
                preview,
                request_id=pending_id,
                **(
                    {"physically_verified_fact_count": 0, "completed_fact_markers": ()}
                    if routed
                    else {}
                ),
            ),
            conversation_id=conversation_id,
            created_at=NOW,
            options=(
                ClarificationOption("eric-id", "Eric"),
                ClarificationOption("luis-id", "Luis"),
            ),
            vault=vault,
            schema=SCHEMA,
        )
        return ApplicationResult(
            request_id,
            ApplicationStatus.PARTIAL,
            (),
            (),
            pending_work=PendingWorkStatus(required=True, persisted=True, record_id=pending_id),
            clarification_code="CANDIDATE_AMBIGUITY",
        )

    runtime = RuntimeComposition(
        core_execute=lambda *_args: (_ for _ in ()).throw(AssertionError("v0 must not run")),
        refresh_indexes=lambda: None,
        conversation_root_resolver=resolver,
        vault_repository=vault,
        canonical_schema=SCHEMA,
        clarification_classifier=classifier,
        hybrid_candidate_execute=hybrid,
    )
    return runtime, resolver, vault, calls, preview.original_request, preview.request_id


def test_product_delivers_v2_options_once_and_records_selected_review_without_writing(
    tmp_path: Path,
) -> None:
    """The existing clarification-card JSON carries only Core-proven current choices."""
    runtime, resolver, vault, calls, source, initial_id = _runtime(tmp_path)
    before = {path: vault.read_text(path) for path in vault.list_markdown_paths()}

    initial = runtime.execute_product(source, initial_id, "main", ACTOR)

    assert initial["product_outcome"] == "CLARIFY"
    assert initial["clarification"] == {
        "request_id": initial_id,
        "source_pending": True,
        "requested_reference": "él",
        "explanation": "No puedo identificar con seguridad a «él». Elige una persona o cancela.",
        "options": [{"id": "eric-id", "label": "Eric"}, {"id": "luis-id", "label": "Luis"}],
    }
    assert runtime.execute_product(source, initial_id, "main", ACTOR)["delivery_replayed"]
    assert calls == [(source, initial_id)]

    selected = runtime.execute_product("He elegido a Luis.", "reply-v2", "main", ACTOR)

    assert selected["status"] == "needs_attention"
    assert selected["product_outcome"] == "CANNOT_ANSWER"
    assert selected["product_reason"] == "CONTINUATION_REVIEW_REQUIRED"
    assert selected["product_control"] == "CANDIDATE_SELECTION_RECORDED"
    pending = CandidatePendingRepository(resolver.resolve(ACTOR.stable_user_id) / "pending")
    assert pending.read(initial_id)["status"] == "selected"
    assert (
        pending.selected_for_core_review(
            conversation_id="main", request_id=initial_id, vault=vault, schema=SCHEMA
        ).captured_at
        == NOW
    )
    assert {path: vault.read_text(path) for path in vault.list_markdown_paths()} == before


def test_hybrid_terminal_no_write_failure_is_replayed_only_for_its_actor(tmp_path: Path) -> None:
    """A delivered hybrid failure cannot become a later semantic re-execution."""
    resolver = ConversationRootResolver(tmp_path / "state")
    calls: list[tuple[str, str]] = []

    def hybrid(source: str, request_id: str, actor: AuthenticatedActorContext, _conversation: str):
        calls.append((actor.stable_user_id, request_id))
        return ApplicationResult(
            request_id,
            ApplicationStatus.FAILED,
            (),
            (),
            planning_error="SYNTHETIC_NO_WRITE_FAILURE",
        )

    runtime = RuntimeComposition(
        core_execute=lambda *_args: (_ for _ in ()).throw(AssertionError("v0 must not run")),
        refresh_indexes=lambda: None,
        conversation_root_resolver=resolver,
        hybrid_candidate_execute=hybrid,
    )

    first = runtime.execute_product("Synthetic source.", "same-delivery", "main", ACTOR)
    replay = runtime.execute_product("Synthetic source.", "same-delivery", "main", ACTOR)
    other = runtime.execute_product("Synthetic source.", "same-delivery", "main", OTHER_ACTOR)

    assert first["status"] == "failed"
    assert replay["delivery_replayed"] is True
    assert calls == [
        (ACTOR.stable_user_id, "same-delivery"),
        (OTHER_ACTOR.stable_user_id, "same-delivery"),
    ]
    assert other.get("delivery_replayed") is not True


def test_v2_choice_after_correlated_assistant_turn_uses_original_route_locator(
    tmp_path: Path,
) -> None:
    """Accept the browser's immediate option only after its exact assistant reply."""
    runtime, resolver, vault, _calls, source, initial_id = _runtime(tmp_path, routed=True)
    initial = runtime.execute_product(source, initial_id, "main", ACTOR)
    route_id = route_execution_id(initial_id, 0)
    assert initial["clarification"]["request_id"] == route_id
    runtime._conversation_store(ACTOR.stable_user_id).append_turn(
        request_id=initial_id,
        role="assistant",
        text="No puedo identificar con seguridad a «él». ¿Eric o Luis?",
        created_at=NOW,
    )
    selected = runtime.execute_product("He elegido a Luis.", "reply-after-assistant", "main", ACTOR)
    assert selected["product_control"] == "CANDIDATE_SELECTION_RECORDED"
    assert selected["product_reason"] == "CONTINUATION_REVIEW_REQUIRED"
    repo = CandidatePendingRepository(resolver.resolve(ACTOR.stable_user_id) / "pending")
    assert repo.read(route_id)["status"] == "selected"


def test_v2_does_not_accept_a_mismatched_assistant_as_immediate_source(
    tmp_path: Path,
) -> None:
    """An unrelated assistant turn cannot authorize a stale implicit choice."""
    runtime, resolver, _vault, _calls, source, initial_id = _runtime(tmp_path, routed=True)
    runtime.execute_product(source, initial_id, "main", ACTOR)
    runtime._conversation_store(ACTOR.stable_user_id).append_turn(
        request_id="unrelated-assistant",
        role="assistant",
        text="Un mensaje sin correlación con la aclaración.",
        created_at=NOW,
    )
    refusal = runtime.execute_product("Luis", "reply-invalid-assistant", "main", ACTOR)
    assert refusal["product_control"] == "CANDIDATE_EXPLICIT_REQUEST_REQUIRED"
    repo = CandidatePendingRepository(resolver.resolve(ACTOR.stable_user_id) / "pending")
    assert repo.read(route_execution_id(initial_id, 0))["status"] == "open"


def test_v2_cancel_and_unrelated_request_never_route_to_v0(tmp_path: Path) -> None:
    """Cancellation is durable; a classifier-proven new request stays on hybrid routing."""
    runtime, resolver, vault, calls, source, initial_id = _runtime(
        tmp_path, classifier=_NewRequestClassifier()
    )
    runtime.execute_product(source, initial_id, "main", ACTOR)
    cancelled = runtime.execute_product("cancelar", "cancel-v2", "main", ACTOR)
    assert cancelled["product_control"] == "CANDIDATE_CANCELLED"
    pending = CandidatePendingRepository(resolver.resolve(ACTOR.stable_user_id) / "pending")
    assert pending.read(initial_id)["status"] == "cancelled"
    assert not vault.read_text("Eric.md").endswith("cine")

    runtime.execute_product(source, "initial-new", "main", ACTOR)
    unrelated = runtime.execute_product("Una petición distinta", "new-v2", "main", ACTOR)
    assert unrelated["product_outcome"] == "ANSWER"
    assert calls[-1] == ("Una petición distinta", "new-v2")
    assert pending.read("initial-new")["status"] == "open"


def test_v2_rejects_stale_or_multiple_choice_without_cross_actor_access(tmp_path: Path) -> None:
    """Choice delivery fails closed for changed evidence, multiple records, and other roots."""
    runtime, resolver, vault, calls, source, initial_id = _runtime(tmp_path)
    runtime.execute_product(source, initial_id, "main", ACTOR)
    pending = CandidatePendingRepository(resolver.resolve(ACTOR.stable_user_id) / "pending")
    record = pending.read(initial_id)
    another_root = tmp_path / "another"
    another_root.mkdir()
    second = replace(
        _ready(another_root)[0],
        request_id="second-v2",
        physically_verified_fact_count=0,
        completed_fact_markers=(),
    )
    pending.record(
        second,
        conversation_id="main",
        created_at=NOW,
        options=(ClarificationOption("eric-id", "Eric"), ClarificationOption("luis-id", "Luis")),
        vault=vault,
        schema=SCHEMA,
    )
    multiple = runtime.execute_product("Luis", "multiple-v2", "main", ACTOR)
    assert multiple["product_control"] == "CANDIDATE_AMBIGUOUS_PENDING"
    assert pending.read(initial_id)["status"] == "open"

    # A second actor has no visibility into this root and reaches only its own hybrid request.
    other = runtime.execute_product("Luis", "other-v2", "main", OTHER_ACTOR)
    assert other["product_outcome"] == "ANSWER"
    assert calls[-1] == ("Luis", "other-v2")
    assert record["conversation_id"] == "main"


def test_v2_refuses_a_changed_canonical_option_without_writing(tmp_path: Path) -> None:
    """A source-backed button is not a valid choice after its canonical guard changes."""
    runtime, resolver, vault, _calls, source, initial_id = _runtime(tmp_path)
    runtime.execute_product(source, initial_id, "main", ACTOR)
    luis = vault.root / "Luis.md"
    luis.write_text(luis.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    before = {path: vault.read_text(path) for path in vault.list_markdown_paths()}

    stale = runtime.execute_product("Luis", "stale-v2", "main", ACTOR)

    assert stale["product_outcome"] == "CANNOT_ANSWER"
    assert stale["product_reason"] == "STALE_EVIDENCE"
    assert stale["product_control"] == "STALE_CANDIDATE_SELECTION"
    pending = CandidatePendingRepository(resolver.resolve(ACTOR.stable_user_id) / "pending")
    assert pending.read(initial_id)["status"] == "open"
    assert {path: vault.read_text(path) for path in vault.list_markdown_paths()} == before


def test_durable_option_can_be_selected_after_unrelated_turn_using_exact_pending_id(
    tmp_path: Path,
) -> None:
    """An older card addresses its own actor-scoped, source-exact v2 record."""
    runtime, resolver, vault, calls, source, initial_id = _runtime(tmp_path, routed=True)
    runtime.execute_product(source, initial_id, "main", ACTOR)
    route_id = route_execution_id(initial_id, 0)
    pending = CandidatePendingRepository(resolver.resolve(ACTOR.stable_user_id) / "pending")
    original = pending.read(route_id)
    original_notes = {p: vault.read_text(p) for p in vault.list_markdown_paths()}
    runtime._conversation_store(ACTOR.stable_user_id).append_turn(
        request_id="another-turn",
        role="assistant",
        text="Una respuesta diferente.",
        created_at=NOW,
    )
    # The former implicit path refuses a stale reply, as before.
    stale = runtime.execute_product("Luis", "stale-implicit-v2", "main", ACTOR)
    assert stale["product_control"] == "CANDIDATE_EXPLICIT_REQUEST_REQUIRED"
    # The explicit card ID is not an identity selector: Core validates the
    # chosen label and current canonical revision before recording a choice.
    selected = runtime.execute_product(
        "He elegido a Luis.",
        "explicit-v2",
        "main",
        ACTOR,
        reply_to_request_id=route_id,
    )
    assert selected["product_reason"] == "CONTINUATION_REVIEW_REQUIRED"
    assert selected["selected_pending_request_id"] == route_id
    assert selected["product_control"] == "CANDIDATE_SELECTION_RECORDED"
    assert pending.read(route_id)["original_request"] == original["original_request"]
    assert pending.read(route_id)["created_at"] == original["created_at"]
    assert pending.read(route_id)["selected_note_id"] == "luis-id"
    assert (
        runtime.execute_product(
            "He elegido a Luis.",
            "explicit-v2",
            "main",
            ACTOR,
            reply_to_request_id=route_id,
        )["delivery_replayed"]
        is True
    )
    assert len(calls) == 1
    assert {p: vault.read_text(p) for p in vault.list_markdown_paths()} == original_notes


def test_explicit_candidate_id_cannot_select_other_actor_or_unknown_record(tmp_path: Path) -> None:
    runtime, resolver, vault, calls, source, initial_id = _runtime(tmp_path)
    runtime.execute_product(source, initial_id, "main", ACTOR)
    pending = CandidatePendingRepository(resolver.resolve(ACTOR.stable_user_id) / "pending")
    original_notes = {p: vault.read_text(p) for p in vault.list_markdown_paths()}
    # Actor B must never use actor A's existing source record as a write or
    # identity authority, regardless of the supplied source identifier.
    foreign = runtime.execute_product(
        "Con Luis",
        "actor-b-cross",
        "main",
        OTHER_ACTOR,
        reply_to_request_id=initial_id,
    )
    assert foreign["product_control"] == "CANDIDATE_UNAVAILABLE"
    unknown = runtime.execute_product(
        "Con Luis",
        "wrong-v2",
        "main",
        ACTOR,
        reply_to_request_id="nonexistent-v2",
    )
    assert unknown["product_control"] == "CANDIDATE_UNAVAILABLE"
    assert pending.read(initial_id)["status"] == "open"
    assert {p: vault.read_text(p) for p in vault.list_markdown_paths()} == original_notes
    assert calls == [(source, initial_id)]


def test_reloaded_main_conversation_restores_only_live_actor_verified_pending_cards(
    tmp_path: Path,
) -> None:
    """Read-only restart projection does not grant identity or write authority."""
    from odyssey_runtime.composition import RuntimeComposition

    runtime, resolver, vault, calls, source, first_id = _runtime(tmp_path, routed=True)
    result = runtime.execute_product(source, first_id, "main", ACTOR)
    pending_id = route_execution_id(first_id, 0)
    assert result["clarification"]["request_id"] == pending_id
    original = {p: vault.read_text(p) for p in vault.list_markdown_paths()}
    # A new Runtime composition reads the same actor-local disk state after restart.
    rebooted = RuntimeComposition(
        core_execute=lambda *_: (_ for _ in ()).throw(AssertionError("No writes allowed")),
        refresh_indexes=lambda: None,
        conversation_root_resolver=resolver,
        vault_repository=vault,
        canonical_schema=SCHEMA,
        hybrid_candidate_execute=runtime.hybrid_candidate_execute,
    )
    page = rebooted.main_conversation(ACTOR)
    assert page["pending_clarifications"] == [
        {
            "request_id": pending_id,
            "source_pending": True,
            "requested_reference": "él",
            "explanation": "No puedo identificar con seguridad a «él». Elige una persona o cancela.",
            "options": [{"id": "eric-id", "label": "Eric"}, {"id": "luis-id", "label": "Luis"}],
        }
    ]
    assert (
        "pending_clarifications" not in rebooted.main_conversation(ACTOR, before=page["before"])
        if page["before"] is not None
        else True
    )
    other_page = rebooted.main_conversation(OTHER_ACTOR)
    assert not other_page.get("pending_clarifications")
    assert {p: vault.read_text(p) for p in vault.list_markdown_paths()} == original
    assert calls == [(source, first_id)]

    answer = rebooted.execute_product(
        "Con Luis",
        "from-reloaded-card",
        "main",
        ACTOR,
        reply_to_request_id=pending_id,
    )
    assert answer["product_control"] == "CANDIDATE_SELECTION_RECORDED"
    assert rebooted.main_conversation(ACTOR).get("pending_clarifications") == []
    assert {p: vault.read_text(p) for p in vault.list_markdown_paths()} == original


def test_stale_identity_cannot_be_redisplayed_as_current_pending_card(tmp_path: Path) -> None:
    runtime, _resolver, vault, _calls, source, first_id = _runtime(tmp_path, routed=True)
    runtime.execute_product(source, first_id, "main", ACTOR)
    note = vault.root / "Luis.md"
    note.write_text(note.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert runtime.main_conversation(ACTOR)["pending_clarifications"] == []
    # The pending source is not destroyed by stale evidence, so explicit
    # recovery remains possible only after another Core-supported review.
    assert (
        runtime.execute_product(
            "Con Luis",
            "stale-after-reload",
            "main",
            ACTOR,
            reply_to_request_id=route_execution_id(first_id, 0),
        )["product_control"]
        == "STALE_CANDIDATE_SELECTION"
    )


def test_same_delivery_id_cannot_switch_to_other_pending_record(tmp_path: Path) -> None:
    """A retry cannot silently switch the user's old-card target."""
    runtime, resolver, _vault, calls, source, initial_id = _runtime(tmp_path, routed=True)
    runtime.execute_product(source, initial_id, "main", ACTOR)
    route_id = route_execution_id(initial_id, 0)
    first = runtime.execute_product(
        "Con Luis",
        "same-target-delivery",
        "main",
        ACTOR,
        reply_to_request_id=route_id,
    )
    assert first["product_control"] == "CANDIDATE_SELECTION_RECORDED"
    with pytest.raises(DeliveryResultError):
        runtime.execute_product(
            "Con Luis",
            "same-target-delivery",
            "main",
            ACTOR,
            reply_to_request_id="another-pending-id",
        )
    with pytest.raises(DeliveryResultError):
        runtime.execute_product(
            "Con Luis",
            "same-target-delivery",
            "main",
            ACTOR,
        )
    repo = CandidatePendingRepository(resolver.resolve(ACTOR.stable_user_id) / "pending")
    assert repo.read(route_id)["selected_note_id"] == "luis-id"
    assert calls == [(source, initial_id)]


def test_missing_candidate_seam_never_routes_explicit_reply_into_legacy_writer(tmp_path):
    resolver = ConversationRootResolver(tmp_path / "state")

    def forbidden(*_args):
        pytest.fail("Explicit pending response must not become a normal write")

    runtime = RuntimeComposition(
        core_execute=forbidden,
        refresh_indexes=lambda: None,
        conversation_root_resolver=resolver,
    )
    result = runtime.execute_product(
        "Con Luis",
        "missing-v2-seam",
        "main",
        ACTOR,
        reply_to_request_id="absent-pending",
    )
    assert result["product_control"] == "CANDIDATE_UNAVAILABLE"
    assert (
        runtime.execute_product(
            "Con Luis",
            "missing-v2-seam",
            "main",
            ACTOR,
            reply_to_request_id="absent-pending",
        )["delivery_replayed"]
        is True
    )
