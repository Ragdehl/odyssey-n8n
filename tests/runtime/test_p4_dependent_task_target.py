"""E2 target binding: actual Core Task backlink → existing Work Session service.

All Notes and Core writes are physical. Model attestations are frozen, not live
LLM outcomes. P4 still needs an independent real-model partition/reviewer and
product coordinator wiring before this may run from a chat message.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from odyssey_apps.tasks import (
    TaskDependentTargetError,
    prove_dependent_task_target,
)
from odyssey_apps.tasks.interpretation import (
    TaskActivityTarget,
    TaskInterpretation,
    TaskOperation,
    TaskQueryScope,
)
from odyssey_apps.tasks.work_sessions import TaskWorkSessionService, WorkSessionError
from odyssey_core import create_entity
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.notes import parse_note, serialize_note
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from tests.runtime.test_whole_source_light_product_p4 import SCHEMA, _fixture

BEFORE = "Hoy revisé Preparar informe Atlas."
AFTER = " Ahora empieza una sesión de trabajo en esa tarea."
SOURCE = BEFORE + AFTER
NOW = "2026-10-16T19:00:00+02:00"


@pytest.fixture
def bound_task(tmp_path):
    repo, actor, executor, runtime = _fixture(tmp_path, incremental_indexes=True)
    create_entity(
        repo,
        SCHEMA,
        path="atlas.md",
        entity_id="atlas-proven-task",
        metadata={"name": "Preparar informe Atlas", "type": "task", "status": "pending"},
        content="- Una tarea existente.\n",
        actor="fixture",
        now=NOW,
    )
    executor.context_index.rebuild(repo, SCHEMA, executor.embedder)
    executor.semantic_index.rebuild(repo, SCHEMA, executor.embedder)
    unit = KnowledgeUnit(
        SelectionCriteria(None, "2026-10-16", "calendar_day", (), None),
        "record",
        (),
        (),
        ("Hoy revisé {{ref:0}}.",),
        (KnowledgeReference(1, "task", "Preparar informe Atlas"),),
    )
    helper = KnowledgeUnit(
        SelectionCriteria("Preparar informe Atlas", "Preparar informe Atlas", "task", (), None),
        "record",
        (),
        (),
        (),
        (),
        reference_lookup_only=True,
    )
    plan = RequestPlan((WriteAction((unit, helper)),), ())
    receipt = execute_request(
        BEFORE,
        planner=SimpleNamespace(plan=lambda *_args: plan),
        repository=repo,
        schema=SCHEMA,
        context_index=executor.context_index,
        semantic_index=executor.semantic_index,
        embedder=executor.embedder,
        contextual_reasoner=executor.reasoner,
        authenticated_actor=actor,
        self_binding_repository=executor.bindings,
        actor=actor.stable_user_id,
        now=NOW,
        context_limit=10,
        request_id_factory=lambda: "p4-predecessor-proven-task",
    )
    assert receipt.status is ApplicationStatus.COMPLETED
    assert [proof.note_type for proof in receipt.canonical_reference_evidence] == ["task"]
    task_request = TaskInterpretation(
        AFTER.strip(), TaskOperation.START_WORK_SESSION, task_reference="esa tarea"
    )
    attested = {
        "full_source_quote": SOURCE,
        "antecedent_quote": BEFORE,
        "dependent_quote": AFTER,
        "dependent_mention": "esa tarea",
        "one_target": True,
        "same_target": True,
        "target_type": "task",
        "operation": "START_WORK_SESSION",
        "operation_supported": True,
    }
    return repo, actor, executor, runtime, receipt, task_request, attested


def _prove(fixture, **overrides):
    repo, _actor, _executor, _runtime, receipt, request, attested = fixture
    params = {
        "full_source": SOURCE,
        "antecedent_source": BEFORE,
        "dependent_source": AFTER,
        "dependent_mention": "esa tarea",
        "core_predecessor": receipt,
        "interpretation": request,
        "attestations": (attested, dict(attested)),
        "repository": repo,
        "schema": SCHEMA,
    }
    return prove_dependent_task_target(**(params | overrides))


def test_real_core_task_reference_proof_then_real_work_session_mutation_same_ui_service(bound_task):
    repo, actor, executor, runtime, receipt, request, attested = bound_task
    target = _prove(bound_task)
    assert target.operation is TaskOperation.START_WORK_SESSION
    assert target.require_current(repo, SCHEMA) == "atlas-proven-task"
    domain = TaskWorkSessionService(repo, SCHEMA, None, id_allocator=lambda: "bound-session")
    from hashlib import sha256

    task_raw = repo.read_text("atlas.md")
    task_revision = parse_note(task_raw).metadata["revision"]
    effect = domain.start(
        task_id=target.require_current(repo, SCHEMA),
        expected_task_revision=task_revision,
        expected_task_source_hash=sha256(task_raw.encode()).hexdigest(),
        started_at=NOW,
        request_id="p4-bound-domain-operation",
        actor=actor.stable_user_id,
        now=NOW,
    )
    assert effect.session.id == "bound-session"
    assert (
        len(
            [
                p
                for p in repo.list_markdown_paths()
                if parse_note(repo.read_text(p)).metadata["type"] == "work_session"
            ]
        )
        == 1
    )
    from odyssey_core.note_queries import NotesQueryService

    runtime.notes_service = NotesQueryService(repo, SCHEMA, executor.context_index)
    runtime.work_session_service = domain
    runtime.vault_repository = repo
    runtime.canonical_schema = SCHEMA
    runtime.notes_mutation_actor = lambda *_: actor.stable_user_id
    detail = runtime.notes("detail", {"note_id": "atlas-proven-task"}, actor)
    assert len(detail["work_sessions"]) == 1
    session = detail["work_sessions"][0]
    activity = runtime.notes(
        "work_session_activity_add",
        {
            "session_id": session["id"],
            "text": "Trabajo revisado en UI.",
            "request_id": "p4-bound-ui-activity",
            "expected_revision": session["mutation"]["revision"],
            "expected_source_hash": session["mutation"]["source_hash"],
        },
        actor,
    )
    assert len(activity["work_sessions"][0]["activity"]) == 1
    with pytest.raises(WorkSessionError, match="ALREADY_ACTIVE"):
        domain.start(
            task_id=target.require_current(repo, SCHEMA),
            started_at=NOW,
            request_id="p4-second-session-rejected",
            actor=actor.stable_user_id,
            now=NOW,
        )


@pytest.mark.parametrize(
    "field,wrong",
    [
        ("full_source", BEFORE + " Otro texto."),
        ("dependent_source", AFTER.replace("esa tarea", "otra tarea")),
        ("dependent_mention", "otra tarea"),
        (
            "interpretation",
            TaskInterpretation(
                "Empieza una sesión en el informe.",
                TaskOperation.START_WORK_SESSION,
                task_reference="el informe",
            ),
        ),
        (
            "interpretation",
            TaskInterpretation(
                AFTER.strip(), TaskOperation.STOP_WORK_SESSION, task_reference="esa tarea"
            ),
        ),
    ],
)
def test_altered_or_mismatched_scope_and_task_interpretation_fails_closed(bound_task, field, wrong):
    with pytest.raises(TaskDependentTargetError):
        _prove(bound_task, **{field: wrong})


@pytest.mark.parametrize(
    "attestation_change",
    [
        {"one_target": False},
        {"same_target": False},
        {"target_type": "person"},
        {"dependent_mention": "la"},
        {"full_source_quote": "other text"},
        {"invented_note_id": "atlas-proven-task"},
        {"operation": "STOP_WORK_SESSION"},
        {"operation_supported": False},
    ],
)
def test_reviewer_disagreement_or_injected_identity_is_never_authority(
    bound_task, attestation_change
):
    first = bound_task[-1]
    with pytest.raises(TaskDependentTargetError):
        _prove(bound_task, attestations=(first, first | attestation_change))


def test_unsupported_create_query_or_active_session_activity_never_gets_target(bound_task):
    interpretations = (
        TaskInterpretation("Crear otra tarea", TaskOperation.CREATE),
        TaskInterpretation("Consultar tareas", TaskOperation.QUERY, query_scope=TaskQueryScope.ALL),
    )
    with pytest.raises(TaskDependentTargetError):
        _prove(bound_task, interpretation=interpretations[0])
    with pytest.raises(TaskDependentTargetError):
        _prove(bound_task, interpretation=interpretations[1])
    activity = TaskInterpretation(
        "Escribí algo",
        TaskOperation.ADD_WORK_SESSION_ACTIVITY,
        activity_text="Escribí algo",
        activity_target=TaskActivityTarget.ACTIVE,
    )
    with pytest.raises(TaskDependentTargetError):
        _prove(bound_task, interpretation=activity)


def test_current_task_target_and_canonical_source_both_require_freshness(bound_task):
    repo, actor, executor, runtime, receipt, request, attested = bound_task
    target = _prove(bound_task)
    for stable_id in ("atlas-proven-task", target.source_dependency.evidence.source_note_id):
        for path in repo.list_markdown_paths():
            note = parse_note(repo.read_text(path))
            if note.metadata["id"] != stable_id:
                continue
            repo.replace_text(
                path, serialize_note(replace(note, content=note.content + "\n- external edit\n"))
            )
            break
        else:
            raise AssertionError("Verified Note cannot disappear")
        with pytest.raises(TaskDependentTargetError, match="expired"):
            target.require_current(repo, SCHEMA)
        with pytest.raises(TaskDependentTargetError):
            _prove(bound_task)


def test_predecessor_person_note_may_never_select_a_task(bound_task):
    repo, actor, executor, runtime, receipt, request, attested = bound_task
    forged = replace(receipt.canonical_reference_evidence[0], note_type="person")
    fake_action = replace(receipt.action_results[0], canonical_reference_evidence=(forged,))
    fake = replace(receipt, canonical_reference_evidence=(forged,), action_results=(fake_action,))
    with pytest.raises(TaskDependentTargetError):
        _prove(bound_task, core_predecessor=fake)


def test_bound_task_consumer_uses_existing_e3_outer_claim_and_http_replay(bound_task):
    """Guarded domain consumer, NOT the still-unwired dependent P4 Router.

    Proves a later adapter can consume this typed proof through existing E3
    and HTTP without creating another Work Session writer or retry scheme.
    """
    import json
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer
    from threading import Thread

    from odyssey_core.application import (
        ActionResult,
        ActionStatus,
        ApplicationResult,
        UnitResult,
        UnitStatus,
    )
    from odyssey_runtime.server import _handler_for

    repo, actor, executor, runtime, receipt, request, attested = bound_task
    domain = TaskWorkSessionService(
        repo, SCHEMA, None, id_allocator=lambda: "e3-bound-task-session"
    )
    calls: list[str] = []

    def checked_consumer(full_source, delivery, identity, conversation):
        assert full_source == SOURCE and conversation == "main"
        assert identity.stable_user_id == actor.stable_user_id
        target = _prove(bound_task)
        calls.append(delivery)
        mutation = domain.start(
            task_id=target.require_current(repo, SCHEMA),
            started_at=NOW,
            request_id=delivery,
            actor=identity.stable_user_id,
            now=NOW,
        )
        return ApplicationResult(
            delivery,
            ApplicationStatus.COMPLETED,
            (
                ActionResult(
                    0,
                    "write",
                    ActionStatus.COMPLETED,
                    unit_results=(
                        UnitResult(
                            0, UnitStatus.SUCCEEDED, mutation.operation, mutation.session.id
                        ),
                    ),
                ),
            ),
            (mutation.session.id,),
        )

    runtime.hybrid_candidate_execute = checked_consumer
    runtime.notes_mutation_actor = lambda *_: actor.stable_user_id
    runtime.vault_repository = repo
    runtime.canonical_schema = SCHEMA
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(runtime))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def post(source=SOURCE, request_id="e3-bound-dependent-outer"):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=15)
        connection.request(
            "POST",
            "/execute",
            json.dumps(
                {
                    "request": source,
                    "request_id": request_id,
                    "conversation_id": "main",
                    "authenticated_actor": {"stable_user_id": actor.stable_user_id},
                }
            ),
            {"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        status = response.status
        payload = json.loads(response.read())
        connection.close()
        return status, payload

    try:
        status, first = post()
        assert status == 200 and first["status"] == "completed"
        assert first["affected_stable_note_ids"] == ["e3-bound-task-session"]
        assert len(calls) == 1
        original_files = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
        status, replay = post()
        assert status == 200 and replay["delivery_replayed"] is True
        assert len(calls) == 1
        assert original_files == {path: repo.read_text(path) for path in repo.list_markdown_paths()}
        assert len(domain.list_for_task("atlas-proven-task")) == 1
        # Same id with changed original source has a conflicting immutable E3
        # fingerprint. It must not be reinterpreted as another authorized Task.
        conflicting_status, _ = post(source=SOURCE + " Otra tarea.")
        assert conflicting_status >= 400
        assert len(calls) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_bound_task_consumer_crash_postwrite_retains_e3_claim_and_no_reexecution(bound_task):
    repo, actor, executor, runtime, receipt, request, attested = bound_task
    domain = TaskWorkSessionService(
        repo, SCHEMA, None, id_allocator=lambda: "e3-crash-task-session"
    )
    calls = []

    def crash_consumer(_source, delivery, identity, _conversation):
        target = _prove(bound_task)
        calls.append(delivery)
        domain.start(
            task_id=target.require_current(repo, SCHEMA),
            started_at=NOW,
            request_id=delivery,
            actor=identity.stable_user_id,
            now=NOW,
        )
        raise RuntimeError("synthetic crash after Work Session write, before receipt")

    runtime.hybrid_candidate_execute = crash_consumer
    with pytest.raises(RuntimeError, match="synthetic crash"):
        runtime.execute_product(SOURCE, "e3-bound-task-crash", "main", actor)
    assert len(domain.list_for_task("atlas-proven-task")) == 1
    after = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    from odyssey_runtime.delivery_results import DeliveryResultError

    with pytest.raises(DeliveryResultError, match="unresolved prior attempt"):
        runtime.execute_product(SOURCE, "e3-bound-task-crash", "main", actor)
    assert calls == ["e3-bound-task-crash"]
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == after


def test_tasks_standard_cas_refuses_change_between_verified_target_and_write(bound_task):
    from hashlib import sha256

    repo, actor, executor, runtime, receipt, request, attested = bound_task
    target = _prove(bound_task)
    task_id = target.require_current(repo, SCHEMA)
    original = repo.read_text("atlas.md")
    revision = parse_note(original).metadata["revision"]
    token = sha256(original.encode()).hexdigest()
    # Concurrent update after the E2 review and before the domain command.
    note = parse_note(original)
    repo.replace_text(
        "atlas.md", serialize_note(replace(note, content=note.content + "\n- newer data\n"))
    )
    with pytest.raises(TaskDependentTargetError, match="expired"):
        target.require_current(repo, SCHEMA)
    domain = TaskWorkSessionService(repo, SCHEMA, None, id_allocator=lambda: "must-not-create")
    with pytest.raises(WorkSessionError, match="STALE_NOTE"):
        domain.start(
            task_id=task_id,
            started_at=NOW,
            request_id="stale-target-refused",
            actor=actor.stable_user_id,
            now=NOW,
            expected_task_revision=revision,
            expected_task_source_hash=token,
        )
    assert domain.list_for_task(task_id) == ()


def test_core_proven_parent_task_is_usable_by_existing_subtask_ui_service(bound_task):
    """Tests the target handoff and real E3 subtask writer, not title inference."""
    from hashlib import sha256

    from odyssey_apps.tasks.interpretation import TaskRelationshipMention, TaskRelationshipRole
    from odyssey_apps.tasks.mutations import TaskDirectMutationService

    repo, actor, executor, runtime, receipt, request, attested = bound_task
    fragment = " Ahora crea la subtarea Preparar el índice dentro de esa tarea."
    full = BEFORE + fragment
    interpretation = TaskInterpretation(
        fragment.strip(),
        TaskOperation.CREATE,
        relationship_mentions=(
            TaskRelationshipMention("esa tarea", TaskRelationshipRole.PARENT_TASK),
        ),
    )
    review = {
        "full_source_quote": full,
        "antecedent_quote": BEFORE,
        "dependent_quote": fragment,
        "dependent_mention": "esa tarea",
        "one_target": True,
        "same_target": True,
        "target_type": "task",
        "operation": "CREATE_SUBTASK",
        "operation_supported": True,
    }
    target = prove_dependent_task_target(
        full_source=full,
        antecedent_source=BEFORE,
        dependent_source=fragment,
        dependent_mention="esa tarea",
        core_predecessor=receipt,
        interpretation=interpretation,
        attestations=(review, dict(review)),
        repository=repo,
        schema=SCHEMA,
    )
    assert target.operation is TaskOperation.CREATE
    assert target.require_current(repo, SCHEMA) == "atlas-proven-task"
    before = repo.read_text("atlas.md")
    revision = parse_note(before).metadata["revision"]
    service = TaskDirectMutationService(
        repo,
        SCHEMA,
        None,
        semantic_index=executor.semantic_index,
        embedder=executor.embedder,
        contextual_reasoner=executor.reasoner,
        semantic_limit=10,
    )
    result = service.create_subtask(
        parent_note_id=target.require_current(repo, SCHEMA),
        # User-authored child title must come from the regular Core planner or
        # UI's explicit title field; the handoff never invents it.
        title="Preparar el índice",
        expected_revision=revision,
        expected_source_hash=sha256(before.encode()).hexdigest(),
        request_id="p4-dependent-real-subtask",
        actor=actor.stable_user_id,
        now=NOW,
    )
    child = parse_note(repo.read_text(result.path))
    assert child.metadata["type"] == "task"
    assert child.metadata["status"] == "pending"
    assert child.metadata["name"] == "Preparar el índice"
    assert child.content.count("Tarea superior:") == 1
    assert "Preparar informe Atlas" in child.content
    assert "[[atlas|Preparar informe Atlas]]" in child.content


@pytest.mark.parametrize(
    "bad",
    [
        {"operation": "CREATE"},
        {"operation_supported": False},
        {"target_type": "person"},
        {"same_target": False},
    ],
)
def test_dependent_subtask_rejects_uncertain_parent_or_operation(bound_task, bad):
    from odyssey_apps.tasks.interpretation import TaskRelationshipMention, TaskRelationshipRole

    repo, actor, executor, runtime, receipt, request, attested = bound_task
    fragment = " Ahora crea una subtarea dentro de esa tarea."
    review = {
        "full_source_quote": BEFORE + fragment,
        "antecedent_quote": BEFORE,
        "dependent_quote": fragment,
        "dependent_mention": "esa tarea",
        "one_target": True,
        "same_target": True,
        "target_type": "task",
        "operation": "CREATE_SUBTASK",
        "operation_supported": True,
    }
    plan = TaskInterpretation(
        fragment.strip(),
        TaskOperation.CREATE,
        relationship_mentions=(
            TaskRelationshipMention("esa tarea", TaskRelationshipRole.PARENT_TASK),
        ),
    )
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    with pytest.raises(TaskDependentTargetError):
        prove_dependent_task_target(
            full_source=BEFORE + fragment,
            antecedent_source=BEFORE,
            dependent_source=fragment,
            dependent_mention="esa tarea",
            core_predecessor=receipt,
            interpretation=plan,
            attestations=(review, review | bad),
            repository=repo,
            schema=SCHEMA,
        )
    assert before == {path: repo.read_text(path) for path in repo.list_markdown_paths()}


def test_update_without_parent_and_multi_relationship_create_do_not_inherit_task_target(bound_task):
    from odyssey_apps.tasks.interpretation import TaskRelationshipMention, TaskRelationshipRole

    repo, actor, executor, runtime, receipt, request, attested = bound_task
    update = TaskInterpretation(
        "Actualizar asignación a Marta",
        TaskOperation.UPDATE,
        relationship_mentions=(TaskRelationshipMention("Marta", TaskRelationshipRole.ASSIGNEE),),
    )
    with pytest.raises(TaskDependentTargetError):
        _prove(bound_task, interpretation=update)
    standalone_create = TaskInterpretation("Crear una tarea", TaskOperation.CREATE)
    with pytest.raises(TaskDependentTargetError):
        _prove(bound_task, interpretation=standalone_create)
    # A child with a second assignee/reference needs its own reviewed Core
    # plan; this narrow parent-carrier cannot silently validate the extra role.
    fragment = " Crea una subtarea dentro de esa tarea y asígnala a Marta."
    multiple = TaskInterpretation(
        fragment.strip(),
        TaskOperation.CREATE,
        relationship_mentions=(
            TaskRelationshipMention("esa tarea", TaskRelationshipRole.PARENT_TASK),
            TaskRelationshipMention("Marta", TaskRelationshipRole.ASSIGNEE),
        ),
    )
    with pytest.raises(TaskDependentTargetError):
        _prove(
            bound_task,
            dependent_source=fragment,
            full_source=BEFORE + fragment,
            interpretation=multiple,
        )
