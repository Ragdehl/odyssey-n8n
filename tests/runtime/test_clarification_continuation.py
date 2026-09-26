"""No-provider tests for one durable, guarded conversation clarification."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from odyssey_core.application import (
    ActionResult,
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
    PendingWorkStatus,
    UnitResult,
    UnitStatus,
)
from odyssey_core.clarification import (
    ClarificationOption,
    LocalClarificationStore,
    PendingClarification,
)
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_core.notes import Note, serialize_note
from odyssey_core.pending_work import PendingWorkRepository
from odyssey_core.request_planning import (
    KnowledgeUnit,
    RequestPlan,
    RetrieveAction,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.storage import VaultRepository
from odyssey_runtime.composition import RuntimeComposition

ROOT = Path(__file__).resolve().parents[2]
ACTOR = AuthenticatedActorContext("11111111-1111-4111-8111-111111111111")
OPTIONS = (
    ClarificationOption("marta-1", "Marta in Lyon"),
    ClarificationOption("marta-2", "Marta in Madrid"),
)


def _pending_runtime(tmp_path: Path, core_execute: object, classifier: object = None):
    """Build only local pending-work and conversation fixtures, with no provider dependency."""
    pending_root = tmp_path / "pending"
    pending_root.mkdir()
    pending_repo = PendingWorkRepository(pending_root)
    original = "Remember that Marta visited Lyon."
    action = WriteAction(
        (
            KnowledgeUnit(
                SelectionCriteria("Marta", "Marta in Lyon", "person", (), None),
                "amend",
                (),
                (),
                ("Marta visited Lyon.",),
                (),
            ),
        )
    )
    original_result = ApplicationResult(
        "request-original",
        ApplicationStatus.NEEDS_ATTENTION,
        (
            ActionResult(
                0,
                "write",
                ActionStatus.DEFERRED,
                unit_results=(
                    UnitResult(
                        0,
                        UnitStatus.DEFERRED,
                        reason="ambiguous_existing_target",
                        candidates=("marta-1", "marta-2"),
                    ),
                ),
            ),
        ),
        (),
    )
    pending_repo.record(
        user_request=original,
        plan=RequestPlan((action,), ()),
        result=original_result,
        created_at="2026-09-26T10:00:00Z",
    )
    resolver = ConversationRootResolver(tmp_path / "state")
    store = LocalClarificationStore(resolver.resolve(ACTOR.stable_user_id), "main")
    store.replace(
        PendingClarification(
            original,
            "request-original",
            "request-original",
            OPTIONS,
            ("a" * 64, "b" * 64),
        )
    )
    runtime = RuntimeComposition(
        core_execute=core_execute,
        refresh_indexes=lambda: None,
        conversation_root_resolver=resolver,
        pending_recorder=pending_repo,
        canonical_schema=json.loads((ROOT / "config/note-schema.json").read_text()),
        clarification_classifier=classifier,
    )
    return runtime, store


def _completed(request_id: str) -> ApplicationResult:
    """Return one non-mutating completed result from the injected Core seam."""
    return ApplicationResult(request_id, ApplicationStatus.COMPLETED, (), ())


def test_numeric_reply_resumes_saved_write_without_replanning(tmp_path: Path) -> None:
    """The reply fixes one supplied decision and preserves original explicit mutation intent."""
    calls = []

    def core(request, request_id, actor, conversation_id, plan, choice):
        calls.append((request, request_id, actor, conversation_id, plan, choice))
        return _completed(request_id)

    runtime, state = _pending_runtime(tmp_path, core)
    response = runtime.execute_product("2", "delivery-2", "main", ACTOR)

    assert response["product_outcome"] == "ANSWER"
    assert state.read() is None
    assert len(calls) == 1
    assert calls[0][0] == "Remember that Marta visited Lyon."
    assert calls[0][4].actions[0].kind == "write"
    assert calls[0][5].stable_id == "marta-2"
    assert calls[0][5].evidence_guard == "b" * 64
    assert runtime.execute_product("2", "delivery-2", "main", ACTOR)["delivery_replayed"] is True
    assert len(calls) == 1


def test_cancel_clears_without_core_execution(tmp_path: Path) -> None:
    """Explicit cancellation forgets the pending decision without a write or new plan."""
    runtime, state = _pending_runtime(
        tmp_path,
        lambda *args: (_ for _ in ()).throw(AssertionError("Core must not execute")),
    )
    response = runtime.execute_product("cancel", "delivery-cancel", "main", ACTOR)
    assert response["product_control"] == "CANCEL"
    assert state.read() is None


def test_unresolved_keeps_same_state_and_options(tmp_path: Path) -> None:
    """A non-decision asks again without losing the original request."""
    runtime, state = _pending_runtime(
        tmp_path,
        lambda *args: (_ for _ in ()).throw(AssertionError("Core must not execute")),
    )
    response = runtime.execute_product("perhaps", "delivery-unknown", "main", ACTOR)
    assert response["product_outcome"] == "CLARIFY"
    assert response["clarification"]["options"] == [
        {"id": option.id, "label": option.label} for option in OPTIONS
    ]
    assert state.read().original_request == "Remember that Marta visited Lyon."


def test_new_request_supersedes_pending_without_cancel_step(tmp_path: Path) -> None:
    """A bounded NEW_REQUEST classification clears state then runs the current text normally."""
    calls = []

    class Classifier:
        """Use an injected deterministic classification, not a live provider."""

        def classify(self, reply, original_request, options):
            """Identify a clearly unrelated request within the allowed result vocabulary."""
            assert original_request == "Remember that Marta visited Lyon."
            return "NEW_REQUEST"

    def core(request, request_id, actor, conversation_id):
        calls.append(request)
        return _completed(request_id)

    runtime, state = _pending_runtime(tmp_path, core, Classifier())
    response = runtime.execute_product("Where is my bike?", "delivery-new", "main", ACTOR)
    assert response["product_outcome"] == "ANSWER"
    assert calls == ["Where is my bike?"]
    assert state.read() is None


def test_ambiguous_write_creates_one_guarded_pending_decision(tmp_path: Path) -> None:
    """Only the complete bounded Core candidate set becomes actor-local continuation state."""
    vault = tmp_path / "vault"
    vault.mkdir()
    for note_id, name in (("marta-1", "Marta in Lyon"), ("marta-2", "Marta in Madrid")):
        note = Note(
            {
                "id": note_id,
                "name": name,
                "type": "person",
                "created_at": "2026-09-26T10:00:00Z",
                "updated_at": "2026-09-26T10:00:00Z",
                "created_by": {"human": None, "app": "test"},
                "updated_by": {"human": None, "app": "test"},
                "revision": 1,
                "schema_version": 3,
            },
            "Known grounded fact.",
        )
        (vault / f"{note_id}.md").write_text(serialize_note(note), encoding="utf-8")

    class Notes:
        """Expose only bounded current labels from the synthetic canonical Notes."""

        def detail(self, note_id):
            """Return the exact displayed label for one supplied ID."""
            label = dict((item.id, item.label) for item in OPTIONS)[note_id]
            return SimpleNamespace(note=SimpleNamespace(id=note_id, name=label))

    runtime, state = _pending_runtime(
        tmp_path,
        lambda *args: (_ for _ in ()).throw(AssertionError("not used")),
    )
    state.clear()
    runtime.vault_repository = VaultRepository(vault)
    runtime.notes_service = Notes()
    result = ApplicationResult(
        "request-original",
        ApplicationStatus.NEEDS_ATTENTION,
        (
            ActionResult(
                0,
                "write",
                ActionStatus.DEFERRED,
                unit_results=(
                    UnitResult(
                        0,
                        UnitStatus.DEFERRED,
                        reason="ambiguous_existing_target",
                        candidates=("marta-1", "marta-2"),
                    ),
                ),
            ),
        ),
        (),
        pending_work=PendingWorkStatus(required=True, persisted=True, record_id="request-original"),
    )
    view = runtime._clarification_view(result)
    pending = runtime._pending_decision(result, view)
    assert pending is not None
    assert pending.options == OPTIONS
    assert all(len(guard) == 64 for guard in pending.evidence_guards)
    runtime.core_execute = lambda *args: result
    response = runtime.execute_product(
        "Remember that Marta visited Lyon.", "request-original", "main", ACTOR
    )
    assert response["product_outcome"] == "CLARIFY"
    assert state.read() == pending


def test_singular_read_resumes_without_replaying_a_note_set(tmp_path: Path) -> None:
    """A chosen one-source read resumes its saved direct plan, not a multi-Note query."""
    pending_root = tmp_path / "pending"
    pending_root.mkdir()
    pending_repo = PendingWorkRepository(pending_root)
    original = "What does my Italy note say?"
    action = RetrieveAction(SelectionCriteria("Italy", original, None, (), None))
    initial = ApplicationResult(
        "read-original",
        ApplicationStatus.NEEDS_ATTENTION,
        (
            ActionResult(
                0,
                "retrieve",
                ActionStatus.DEFERRED,
                reason="ambiguous_existing_target",
                candidate_note_ids=("italy-a", "italy-b"),
            ),
        ),
        (),
    )
    pending_repo.record(
        user_request=original,
        plan=RequestPlan((action,), ()),
        result=initial,
        created_at="2026-09-26T10:00:00Z",
    )
    resolver = ConversationRootResolver(tmp_path / "state")
    state = LocalClarificationStore(resolver.resolve(ACTOR.stable_user_id), "main")
    state.replace(
        PendingClarification(
            original,
            "read-original",
            "read-original",
            (ClarificationOption("italy-a", "Italy A"), ClarificationOption("italy-b", "Italy B")),
            ("a" * 64, "b" * 64),
        )
    )
    calls = []

    def core(request, request_id, actor, conversation_id, plan, choice):
        calls.append((request, plan.actions[0].result_shape, choice.stable_id))
        return _completed(request_id)

    runtime = RuntimeComposition(
        core_execute=core,
        refresh_indexes=lambda: None,
        conversation_root_resolver=resolver,
        pending_recorder=pending_repo,
        canonical_schema=json.loads((ROOT / "config/note-schema.json").read_text()),
    )
    response = runtime.execute_product("1", "read-reply", "main", ACTOR)
    assert response["product_outcome"] == "ANSWER"
    assert calls == [(original, "single", "italy-a")]
    assert state.read() is None
