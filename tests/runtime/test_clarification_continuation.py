"""No-provider tests for one durable, guarded conversation clarification."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import odyssey_core.application as core_application
from odyssey_core.application import (
    ActionResult,
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
    PendingWorkStatus,
    UnitResult,
    UnitStatus,
)
from odyssey_core.atomic_facts import render_atomic_facts
from odyssey_core.clarification import (
    ClarificationOption,
    LocalClarificationStore,
    PendingClarification,
)
from odyssey_core.clarification_presentation import (
    ClarificationCandidateEvidence,
    ClarificationPresentation,
)
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_core.notes import Note, serialize_note
from odyssey_core.pending_work import PendingWorkRepository
from odyssey_core.request_planning import (
    KnowledgeUnit,
    RelationalReference,
    RequestPlan,
    RetrieveAction,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.semantic_sets import SetEvidenceSelection, SetMemberOccurrence
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


def test_unresolved_reply_preserves_rich_version_three_presentation(tmp_path: Path) -> None:
    """Re-render the same canonical explanation and evidence without another Core execution."""
    runtime, state = _pending_runtime(
        tmp_path,
        lambda *args: (_ for _ in ()).throw(AssertionError("Core must not execute")),
    )
    rich_options = (
        ClarificationOption("marta-1", "Marta in Lyon", "person", "Vive en Lyon."),
        ClarificationOption("marta-2", "Marta in Madrid", "person", "Vive en Madrid."),
    )
    state.replace(
        PendingClarification(
            "Remember that Marta visited Lyon.",
            "request-original",
            "request-original",
            rich_options,
            ("a" * 64, "b" * 64),
            None,
            "Marta",
            "No puedo identificar con seguridad a “Marta”. He encontrado estas posibilidades en tus notas.",
        )
    )

    response = runtime.execute_product("quizá", "delivery-rich", "main", ACTOR)

    assert response["clarification"]["explanation"].startswith("No puedo identificar")
    assert response["clarification"]["options"] == [
        {
            "id": option.id,
            "label": option.label,
            "note_type": option.note_type,
            "evidence": option.evidence,
        }
        for option in rich_options
    ]
    stored = state.read()
    assert stored is not None
    assert stored.options == rich_options


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


def test_runtime_projects_only_bounded_core_clarification_presentation() -> None:
    """Expose canonical option fields without retrieval rank or model rationale."""
    presentation = ClarificationPresentation(
        "mi descendiente",
        (
            ClarificationCandidateEvidence("cloe", "Cloe", "person", "Mis hijos son Cloe y Bruno."),
            ClarificationCandidateEvidence(
                "bruno", "Bruno", "person", "Mis hijos son Cloe y Bruno."
            ),
        ),
    )
    result = ApplicationResult(
        "relational-rich",
        ApplicationStatus.NEEDS_ATTENTION,
        (
            ActionResult(
                0,
                "write",
                ActionStatus.DEFERRED,
                reason="relational_evidence_ambiguous",
                candidate_note_ids=("cloe", "bruno"),
                clarification=presentation,
            ),
        ),
        (),
    )

    view = RuntimeComposition(
        core_execute=lambda *args: result, refresh_indexes=lambda: None
    )._clarification_view(result)

    assert view == {
        "request_id": "relational-rich",
        "reason": "AMBIGUOUS_REFERENCE",
        "requested_reference": "mi descendiente",
        "explanation": presentation.explanation,
        "options": [
            {
                "id": "cloe",
                "label": "Cloe",
                "note_type": "person",
                "evidence": "Mis hijos son Cloe y Bruno.",
            },
            {
                "id": "bruno",
                "label": "Bruno",
                "note_type": "person",
                "evidence": "Mis hijos son Cloe y Bruno.",
            },
        ],
        "pending_record_id": None,
    }


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


def test_relational_read_pending_keeps_source_guard_in_version_two_state(tmp_path: Path) -> None:
    """Reuse the existing store while binding a relational identity choice to source evidence."""
    pending_root = tmp_path / "pending"
    pending_root.mkdir()
    pending_repo = PendingWorkRepository(pending_root)
    original = "¿Quién es mi hijo?"
    action = RetrieveAction(
        SelectionCriteria(
            None,
            original,
            "person",
            (),
            None,
            relational_reference=RelationalReference("mi hijo", "self", None, "one"),
        )
    )
    source_guard = "c" * 64
    initial = ApplicationResult(
        "relational-original",
        ApplicationStatus.NEEDS_ATTENTION,
        (
            ActionResult(
                0,
                "retrieve",
                ActionStatus.DEFERRED,
                reason="relational_singular_ambiguous",
                candidate_note_ids=("marta-1", "marta-2"),
                relational_evidence_guard=source_guard,
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
    vault = tmp_path / "vault"
    vault.mkdir()
    for note_id, name in (("marta-1", "Cloe"), ("marta-2", "Bruno")):
        (vault / f"{note_id}.md").write_text(
            serialize_note(
                Note(
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
            ),
            encoding="utf-8",
        )

    class Notes:
        """Provide current labels without adding a second semantic authority."""

        def detail(self, note_id):
            return SimpleNamespace(
                note=SimpleNamespace(
                    id=note_id, name={"marta-1": "Cloe", "marta-2": "Bruno"}[note_id]
                )
            )

    resolver = ConversationRootResolver(tmp_path / "state")
    runtime = RuntimeComposition(
        core_execute=lambda *args: _completed(args[1]),
        refresh_indexes=lambda: None,
        conversation_root_resolver=resolver,
        pending_recorder=pending_repo,
        canonical_schema=json.loads((ROOT / "config/note-schema.json").read_text()),
        vault_repository=VaultRepository(vault),
        notes_service=Notes(),
    )
    stored_result = ApplicationResult(
        initial.request_id,
        initial.status,
        initial.action_results,
        (),
        pending_work=PendingWorkStatus(
            required=True, persisted=True, record_id="relational-original"
        ),
    )

    pending = runtime._pending_decision(stored_result, runtime._clarification_view(stored_result))

    assert pending is not None and pending.source_evidence_guard == source_guard
    state = LocalClarificationStore(resolver.resolve(ACTOR.stable_user_id), "main")
    state.replace(pending)
    assert state.read() == pending


def test_ambiguous_relational_write_round_trips_through_core_runtime_and_choice(
    tmp_path: Path,
) -> None:
    """Keep one unknown member as CLARIFY end-to-end, then mutate only the human choice."""
    vault = tmp_path / "vault"
    vault.mkdir()
    schema = json.loads((ROOT / "config/note-schema.json").read_text())

    def write_note(path: str, note_id: str, name: str, body: str) -> None:
        metadata = {
            "id": note_id,
            "name": name,
            "type": "person",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-09-30T12:00:00Z",
            "created_by": {"human": None, "app": "test"},
            "updated_by": {"human": None, "app": "test"},
            "revision": 1,
            "schema_version": 3,
            "aliases": [],
            "tags": [],
        }
        target = vault / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(serialize_note(Note(metadata, body)), encoding="utf-8")

    relation_fact = render_atomic_facts(
        ("Mis hijos son [[people/cloe|Cloe]] y [[people/bruno|Bruno]].",),
        "fixture",
        (0,),
        "2026-09-30T12:00:00Z",
    )
    write_note("people/self.md", "self", "Self", relation_fact)
    write_note("people/cloe.md", "cloe", "Cloe", "")
    write_note("people/bruno.md", "bruno", "Bruno", "")
    before = {path: path.read_bytes() for path in vault.rglob("*.md")}

    selection = SelectionCriteria(
        None,
        "uno de mis hijos",
        "person",
        (),
        None,
        relational_reference=RelationalReference("uno de mis hijos", "self", None, "one"),
    )
    plan = RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        selection,
                        "record",
                        (),
                        (),
                        ("Se ha apuntado a natación.",),
                        (),
                    ),
                )
            ),
        ),
        (),
    )

    class EmptyIndex:
        def find_candidates(self, *_args, **_kwargs):
            return ()

    class Embedder:
        model_name = "tests"
        model_version = "1"

    class AbstainingReasoner:
        def resolve(self, _request):
            return {"outcome": "UNRESOLVED", "id": None, "ambiguous_ids": []}, {}

    class RelationSelector:
        def select(self, request):
            chosen = request.candidates[0]
            return SetEvidenceSelection(
                (chosen.id,),
                (SetMemberOccurrence(chosen.id, "literal", 0, 1),),
            )

    class SelfBinding:
        def resolve(self, stable_user_id):
            assert stable_user_id == ACTOR.stable_user_id
            return SimpleNamespace(person_note_id="self")

    pending_root = tmp_path / "pending"
    pending_root.mkdir()
    pending = PendingWorkRepository(pending_root)
    repository = VaultRepository(vault)

    def execute_core(
        request,
        request_id,
        actor=None,
        _conversation_id=None,
        resume_plan=None,
        clarification_choice=None,
    ):
        active_plan = resume_plan or plan
        return core_application.execute_request(
            request,
            planner=SimpleNamespace(plan=lambda *_args, **_kwargs: active_plan),
            repository=repository,
            schema=schema,
            context_index=object(),
            semantic_index=EmptyIndex(),
            embedder=Embedder(),
            contextual_reasoner=AbstainingReasoner(),
            actor="test",
            now="2026-09-30T12:00:00Z",
            context_limit=5,
            request_id_factory=lambda: request_id,
            authenticated_actor=actor,
            self_binding_repository=SelfBinding(),
            semantic_set_selector=RelationSelector(),
            pending_recorder=pending,
            clarification_choice=clarification_choice,
        )

    resolver = ConversationRootResolver(tmp_path / "state")
    runtime = RuntimeComposition(
        core_execute=execute_core,
        refresh_indexes=lambda: None,
        conversation_root_resolver=resolver,
        pending_recorder=pending,
        vault_repository=repository,
        canonical_schema=schema,
    )

    first = runtime.execute_product(
        "Uno de mis hijos se ha apuntado a natación.", "delivery-ambiguous", "main", ACTOR
    )

    assert first["product_outcome"] == "CLARIFY"
    assert first["product_reason"] == "AMBIGUOUS_REFERENCE"
    assert "product_control" not in first
    assert first["clarification"]["explanation"].startswith("No puedo identificar")
    assert [option["id"] for option in first["clarification"]["options"]] == ["cloe", "bruno"]
    assert [option["label"] for option in first["clarification"]["options"]] == ["Cloe", "Bruno"]
    assert all(path.read_bytes() == content for path, content in before.items())
    second = runtime.execute_product("Bruno", "delivery-choice", "main", ACTOR)

    assert second["product_outcome"] == "ANSWER"
    assert "Se ha apuntado a natación." not in (vault / "people/cloe.md").read_text()
    assert "Se ha apuntado a natación." in (vault / "people/bruno.md").read_text()
