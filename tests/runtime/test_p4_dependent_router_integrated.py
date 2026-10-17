"""The actual P4 JOINT router → Core task backlink → typed Tasks → E3.

Only model outputs and Core RequestPlan are frozen; Core execute_request,
Markdown, authenticated SELF, TaskWorkSessionService and outer E3 are real.
No n8n/browser or fresh LLM calls are implied by this suite.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from odyssey_apps.tasks import TaskInterpretation, TaskOperation, TaskWorkSessionService
from odyssey_core import create_entity
from odyssey_core.application import ApplicationResult, ApplicationStatus, execute_request
from odyssey_core.notes import parse_note
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from tests.runtime.test_whole_source_light_product_p4 import (
    SCHEMA,
    RecordedClient,
    _fixture,
)

BEFORE = "Hoy revisé Preparar informe Atlas."
AFTER = " Ahora empieza una sesión de trabajo en esa tarea."
SOURCE = BEFORE + AFTER
CLOCK = "2026-10-16T15:30:00+02:00"


def _route():
    return {
        "capabilities": ["core", "tasks"],
        "self_relation_span": None,
        "interpretation": "joint",
        "reason": "shared_reference",
        "app_scopes": [
            {
                "capability": "core",
                "description": "referenced fact",
                "depends_on_another_scope": False,
            },
            {
                "capability": "tasks",
                "description": "work session",
                "depends_on_another_scope": True,
            },
        ],
    }


def _partition():
    return {
        "full_source_quote": SOURCE,
        "antecedent_quote": BEFORE,
        "dependent_quote": AFTER,
        "dependent_mention": "esa tarea",
    }


def _attestation(**changes):
    return {
        **_partition(),
        "one_target": True,
        "same_target": True,
        "target_type": "task",
        "operation": "START_WORK_SESSION",
        "operation_supported": True,
        **changes,
    }


def _plan(with_task_reference=True):
    if with_task_reference:
        line = "Hoy revisé {{ref:0}}."
        refs = (KnowledgeReference(1, "task", "Preparar informe Atlas"),)
        helper = KnowledgeUnit(
            SelectionCriteria("Preparar informe Atlas", "Preparar informe Atlas", "task", (), None),
            "record",
            (),
            (),
            (),
            (),
            reference_lookup_only=True,
        )
    else:
        line = "Hoy revisé un informe."
        refs = ()
        helper = None
    unit = KnowledgeUnit(
        SelectionCriteria(None, "2026-10-16", "calendar_day", (), None),
        "record",
        (),
        (),
        (line,),
        refs,
    )
    return RequestPlan((WriteAction((unit, helper) if helper else (unit,)),), ())


def _setup(tmp_path, *, existing_type="task", with_task_reference=True):
    repo, actor, executor, runtime = _fixture(tmp_path, incremental_indexes=True)
    create_entity(
        repo,
        SCHEMA,
        path="atlas.md",
        entity_id="atlas-p4-dependent-task",
        metadata={
            "name": "Preparar informe Atlas",
            "type": existing_type,
            **({"status": "pending"} if existing_type == "task" else {}),
        },
        content="- Nota existente.\n",
        actor="fixture",
        now=CLOCK,
    )
    executor.context_index.rebuild(repo, SCHEMA, executor.embedder)
    executor.semantic_index.rebuild(repo, SCHEMA, executor.embedder)
    calls = []

    def core(source, locator, who, instant):
        assert source == BEFORE and who == actor and instant.isoformat() == CLOCK
        calls.append("core")
        return execute_request(
            source,
            planner=SimpleNamespace(plan=lambda *_: _plan(with_task_reference)),
            repository=repo,
            schema=SCHEMA,
            context_index=executor.context_index,
            semantic_index=executor.semantic_index,
            embedder=executor.embedder,
            contextual_reasoner=executor.reasoner,
            authenticated_actor=who,
            self_binding_repository=executor.bindings,
            actor=who.stable_user_id,
            now=CLOCK,
            context_limit=10,
            request_id_factory=lambda: locator,
        )

    domain = TaskWorkSessionService(
        repo, SCHEMA, None, id_allocator=lambda: "p4-dependent-session-1"
    )

    def prepare(text, instant):
        assert text == AFTER.strip() and instant.isoformat() == CLOCK
        calls.append("prepare")
        return TaskInterpretation(
            text, TaskOperation.START_WORK_SESSION, task_reference="esa tarea"
        ), None

    def task(source, locator, who, interpretation, temporal, target, instant):
        assert source == AFTER.strip() and who == actor
        assert interpretation.operation is TaskOperation.START_WORK_SESSION and temporal is None
        assert instant.isoformat() == CLOCK
        calls.append("task")
        task_id = target.require_current(repo, SCHEMA)
        rev, digest = domain.task_mutation_tokens(task_id)
        assert digest == target.source_dependency.evidence.canonical_content_guard
        effect = domain.start(
            task_id=task_id,
            started_at=CLOCK,
            request_id=locator,
            actor=who.stable_user_id,
            now=CLOCK,
            expected_task_revision=rev,
            expected_task_source_hash=digest,
        )
        return ApplicationResult(locator, ApplicationStatus.COMPLETED, (), (effect.session.id,))

    executor.dependent_core_delegate = core
    executor.dependent_task_prepare = prepare
    executor.dependent_task_delegate = task
    executor.client = RecordedClient(
        [
            _route(),
            _partition(),
            {
                "only_task_semantics": True,
                "exactly_one_operation": True,
                "source_quote": AFTER.strip(),
            },
            _attestation(),
            _attestation(),
        ]
    )
    return repo, actor, executor, runtime, calls, domain


def _snapshot(repo):
    return {path: repo.read_text(path) for path in repo.list_markdown_paths()}


def test_real_joined_core_task_target_and_work_session_through_product_e3(tmp_path):
    repo, actor, executor, runtime, calls, domain = _setup(tmp_path)
    status = runtime.execute_product(SOURCE, "p4-dependent-outer", "main", actor)
    assert status["status"] == "completed", status
    assert status["affected_stable_note_ids"] == ["date:2026-10-16", "p4-dependent-session-1"]
    assert len(domain.list_for_task("atlas-p4-dependent-task")) == 1
    day = next(
        parse_note(repo.read_text(p))
        for p in repo.list_markdown_paths()
        if parse_note(repo.read_text(p)).metadata["id"] == "date:2026-10-16"
    )
    assert "[[atlas|Preparar informe Atlas]]" in day.content
    assert calls == ["prepare", "core", "task"]
    assert executor.client.calls == [
        "odyssey_light_capability_route_v1",
        "odyssey_dependent_task_partition_v1",
        "odyssey_task_only_scope_v1",
        "odyssey_dependent_task_review_a_v1",
        "odyssey_dependent_task_review_b_v1",
    ]
    before = _snapshot(repo)
    replay = runtime.execute_product(SOURCE, "p4-dependent-outer", "main", actor)
    assert replay["delivery_replayed"] is True
    assert calls == ["prepare", "core", "task"]
    assert _snapshot(repo) == before


@pytest.mark.parametrize(
    "which,changed",
    [
        ("partition", {"dependent_quote": " Una parte inventada."}),
        ("partition", {"antecedent_quote": BEFORE.replace("revisé", "pensé")}),
        ("partition", {"dependent_mention": "otra tarea"}),
        ("task_scope", {"only_task_semantics": False}),
        ("task_scope", {"exactly_one_operation": False}),
        ("task_scope", {"source_quote": "omitted source"}),
        ("review_a", {"one_target": False}),
        ("review_a", {"target_type": "person"}),
        ("review_b", {"same_target": False}),
        ("review_b", {"operation": "STOP_WORK_SESSION"}),
        ("review_b", {"operation_supported": False}),
        ("review_b", {"note_id": "atlas-p4-dependent-task"}),
    ],
)
def test_bad_partition_or_semantic_reviews_block_before_core_write(tmp_path, which, changed):
    repo, actor, executor, runtime, calls, domain = _setup(tmp_path)
    rows = [
        _route(),
        _partition(),
        {"only_task_semantics": True, "exactly_one_operation": True, "source_quote": AFTER.strip()},
        _attestation(),
        _attestation(),
    ]
    rows[{"partition": 1, "task_scope": 2, "review_a": 3, "review_b": 4}[which]] |= changed
    executor.client = RecordedClient(rows)
    before = _snapshot(repo)
    result = runtime.execute_product(SOURCE, "p4-dependent-bad-proof", "main", actor)
    assert result["status"] == "needs_attention"
    assert _snapshot(repo) == before
    assert "core" not in calls and "task" not in calls
    assert not domain.list_for_task("atlas-p4-dependent-task")
    assert (
        runtime.execute_product(SOURCE, "p4-dependent-bad-proof", "main", actor)[
            "delivery_replayed"
        ]
        is True
    )


def test_core_fails_to_link_task_and_e3_reports_partial_with_no_session(tmp_path):
    repo, actor, executor, runtime, calls, domain = _setup(tmp_path, with_task_reference=False)
    result = runtime.execute_product(SOURCE, "p4-dependent-unlinked", "main", actor)
    assert result["status"] == "partial", result
    assert "core" in calls and "task" not in calls
    assert not domain.list_for_task("atlas-p4-dependent-task")
    assert any(
        parse_note(repo.read_text(p)).metadata["type"] == "calendar_day"
        for p in repo.list_markdown_paths()
    )
    before = _snapshot(repo)
    replay = runtime.execute_product(SOURCE, "p4-dependent-unlinked", "main", actor)
    assert replay["delivery_replayed"] is True
    assert _snapshot(repo) == before


def test_person_note_may_not_be_promoted_to_work_session_task(tmp_path):
    repo, actor, executor, runtime, calls, domain = _setup(tmp_path, existing_type="person")
    result = runtime.execute_product(SOURCE, "p4-dependent-person", "main", actor)
    assert result["status"] != "completed"
    assert "task" not in calls
    assert not any(
        parse_note(repo.read_text(p)).metadata["type"] == "work_session"
        for p in repo.list_markdown_paths()
    )


def test_normal_cross_fact_task_create_does_not_regress_to_dependent_work_session(tmp_path):
    from tests.runtime.test_whole_source_light_product_p4 import (
        _actual_snapshot,
        _speaker,
    )

    source, route, plan, review = _actual_snapshot("maite_cross_app")
    repo, actor, executor, runtime = _fixture(tmp_path)
    core_dependent_calls = []
    executor.dependent_core_delegate = lambda *_: core_dependent_calls.append(True)
    executor.dependent_task_prepare = lambda text, _instant: (
        TaskInterpretation(text, TaskOperation.CREATE),
        None,
    )
    executor.dependent_task_delegate = lambda *_: (_ for _ in ()).throw(
        AssertionError("A new obligation must not become a Work Session")
    )
    first = "Hoy he conocido a Maite,"
    second = " mañana tengo que llamarla."
    assert first + second == source
    executor.client = RecordedClient(
        [
            route,
            {
                "full_source_quote": source,
                "antecedent_quote": first,
                "dependent_quote": second,
                "dependent_mention": "llamarla",
            },
            plan,
            {
                "only_new_task_creations": True,
                "no_work_session_or_lifecycle_transition": True,
                "source_quote": source,
            },
            review,
            _speaker(source, plan, base=1),
            _speaker(source, plan),
        ]
    )
    out = runtime.execute_product(source, "p4-create-fallback", "main", actor)
    assert out["status"] == "completed", out
    assert not core_dependent_calls
    assert executor.client.rows == []


def test_dependent_subtask_without_verified_title_must_block_prewrite(tmp_path):
    from odyssey_apps.tasks import TaskRelationshipMention, TaskRelationshipRole

    repo, actor, executor, runtime, calls, domain = _setup(tmp_path)
    executor.dependent_task_prepare = lambda text, _instant: (
        TaskInterpretation(
            text,
            TaskOperation.CREATE,
            relationship_mentions=(
                TaskRelationshipMention("esa tarea", TaskRelationshipRole.PARENT_TASK),
            ),
        ),
        None,
    )
    snapshot = _snapshot(repo)
    result = runtime.execute_product(SOURCE, "p4-subtask-title-unready", "main", actor)
    assert result["status"] == "needs_attention"
    assert result["product_reason"] == "DEPENDENT_SUBTASK_PLANNER_NOT_READY"
    assert not calls or calls == ["prepare"]
    assert _snapshot(repo) == snapshot


def test_dep_tasks_postwrite_crash_leaves_outer_e3_claim_and_no_duplicate(tmp_path):
    from odyssey_runtime.delivery_results import DeliveryResultError

    repo, actor, executor, runtime, calls, domain = _setup(tmp_path)
    real_delegate = executor.dependent_task_delegate

    def crash_after_write(*args):
        assert real_delegate is not None
        real_delegate(*args)
        raise RuntimeError("synthetic crash after both canonical writes")

    executor.dependent_task_delegate = crash_after_write
    with pytest.raises(RuntimeError, match="synthetic crash"):
        runtime.execute_product(SOURCE, "p4-dep-postwrite-crash", "main", actor)
    assert len(domain.list_for_task("atlas-p4-dependent-task")) == 1
    snapshot = _snapshot(repo)
    with pytest.raises(DeliveryResultError, match="unresolved prior attempt"):
        runtime.execute_product(SOURCE, "p4-dep-postwrite-crash", "main", actor)
    assert _snapshot(repo) == snapshot
    assert calls == ["prepare", "core", "task"]


@pytest.mark.parametrize(
    "failure_kind", ["temporal_provider_error", "missing_temporal", "wrong_source"]
)
def test_dependent_temporal_prewrite_veto_never_persists_core_or_tasks(tmp_path, failure_kind):
    from odyssey_apps.tasks import TaskTemporalMention, TaskTemporalRole
    from odyssey_core.temporal_interpretation import parse_temporal_interpretation

    repo, actor, executor, runtime, calls, domain = _setup(tmp_path)
    request = " Ahora corrige la hora de inicio de la sesión de esa tarea a las 15:10."
    source = BEFORE + request
    fragment = request.strip()
    attempted = TaskInterpretation(
        fragment,
        TaskOperation.EDIT_WORK_SESSION,
        temporal_mentions=(
            TaskTemporalMention("a las 15:10", TaskTemporalRole.WORK_SESSION_START_AT),
        ),
        task_reference="esa tarea",
    )
    if failure_kind == "temporal_provider_error":

        def prepare(_text, _instant):
            raise ValueError("unresolved temporal semantics")
    elif failure_kind == "missing_temporal":

        def prepare(_text, _instant):
            return attempted, None
    else:
        wrong = parse_temporal_interpretation(
            {
                "mentions": [
                    {
                        "temporal_text": "a las 15:10",
                        "temporal": {
                            "kind": "EXACT_DATETIME",
                            "exact_date": None,
                            "exact_datetime": "2026-10-16T15:10:00+02:00",
                            "range_start": None,
                            "range_end_exclusive": None,
                        },
                    }
                ]
            },
            fragment,
            timezone="Europe/Paris",
        )
        wrong = replace(wrong, source_text="untrusted a las 15:10")

        def prepare(_text, _instant):
            return attempted, wrong

    executor.dependent_task_prepare = prepare
    executor.client = RecordedClient(
        [
            _route(),
            {
                "full_source_quote": source,
                "antecedent_quote": BEFORE,
                "dependent_quote": request,
                "dependent_mention": "esa tarea",
            },
        ]
    )
    snapshot = _snapshot(repo)
    result = runtime.execute_product(source, f"p4-pretemporal-{failure_kind}", "main", actor)
    assert result["status"] == "needs_attention", result
    assert result["product_reason"] == "DEPENDENT_TASK_PREWRITE_UNAVAILABLE"
    assert "core" not in calls and "task" not in calls
    assert _snapshot(repo) == snapshot
    replay = runtime.execute_product(source, f"p4-pretemporal-{failure_kind}", "main", actor)
    assert replay["delivery_replayed"] is True
    assert _snapshot(repo) == snapshot
