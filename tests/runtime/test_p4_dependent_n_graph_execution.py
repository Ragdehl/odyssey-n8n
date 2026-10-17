"""P4 true multi-scope DAG: original Core Writer, Tasks domain sessions and E3."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from odyssey_apps.tasks import TaskInterpretation, TaskOperation, TaskWorkSessionService
from odyssey_core import create_entity
from odyssey_core.application import ApplicationResult, ApplicationStatus, execute_request
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_runtime.delivery_results import LocalDeliveryResultStore
from tests.runtime.test_p4_dependent_router_integrated import (
    BEFORE,
    CLOCK,
    SCHEMA,
    _setup,
    _snapshot,
)
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient

SECOND = " Ayer revisé Revisar contratos."
FIRST_TASK = " Ahora empieza una sesión de trabajo en Preparar informe Atlas."
SECOND_TASK = " Después termina la sesión de Preparar informe Atlas."
PARTS = (BEFORE, SECOND, FIRST_TASK, SECOND_TASK)
SOURCE = "".join(PARTS)


def _scopes():
    return [
        {
            "capability": cap,
            "description": "Core source" if cap == "core" else "Tasks action",
            "depends_on_another_scope": i >= 2,
        }
        for i, cap in enumerate(("core", "core", "tasks", "tasks"))
    ]


def _partition():
    return {
        "full_source_quote": SOURCE,
        "groups": [
            {"capability": "core", "source_quote": BEFORE, "dependencies": []},
            {"capability": "core", "source_quote": SECOND, "dependencies": []},
            {
                "capability": "tasks",
                "source_quote": FIRST_TASK,
                "dependencies": [
                    {
                        "predecessor_index": 0,
                        "antecedent_mention": "Preparar informe Atlas",
                        "mention": "Preparar informe Atlas",
                    }
                ],
            },
            {
                "capability": "tasks",
                "source_quote": SECOND_TASK,
                "dependencies": [
                    {
                        "predecessor_index": 0,
                        "antecedent_mention": "Preparar informe Atlas",
                        "mention": "Preparar informe Atlas",
                    }
                ],
            },
        ],
    }


def _route():
    return {
        "capabilities": ["core", "tasks"],
        "self_relation_span": None,
        "interpretation": "joint",
        "reason": "shared_reference",
        "app_scopes": _scopes(),
    }


def _reviewed():
    proposal = _partition()
    return {
        "full_source_quote": SOURCE,
        "complete": True,
        "dependency_edges_verified": True,
        "groups": deepcopy(proposal["groups"]),
    }


def _semantic(scope_index):
    mention = "Preparar informe Atlas"
    fragment = PARTS[scope_index]
    source = PARTS[0]
    return {
        "full_source_quote": SOURCE,
        "antecedent_quote": source,
        "dependent_quote": fragment,
        "dependent_mention": mention,
        "one_target": True,
        "same_target": True,
        "target_type": "task",
        "operation": "START_WORK_SESSION" if scope_index == 2 else "STOP_WORK_SESSION",
        "operation_supported": True,
    }


def _rows():
    return [
        _route(),
        _partition(),
        _reviewed(),
        {
            "only_task_semantics": True,
            "exactly_one_operation": True,
            "source_quote": FIRST_TASK.strip(),
        },
        _semantic(2),
        _semantic(2),
        {
            "only_task_semantics": True,
            "exactly_one_operation": True,
            "source_quote": SECOND_TASK.strip(),
        },
        _semantic(3),
        _semantic(3),
    ]


def _three_rows():
    rows = _rows()
    rows[0]["app_scopes"] = rows[0]["app_scopes"][:3]
    rows[1]["groups"] = rows[1]["groups"][:3]
    rows[1]["full_source_quote"] = SOURCE_THREE
    rows[2]["groups"] = deepcopy(rows[1]["groups"])
    rows[2]["full_source_quote"] = SOURCE_THREE
    for index in (4, 5):
        rows[index]["full_source_quote"] = SOURCE_THREE
    return rows[:6]


SOURCE_THREE = BEFORE + SECOND + FIRST_TASK


def _physical_runtime(tmp_path):
    repo, actor, executor, runtime, calls, _previous_domain = _setup(tmp_path)
    create_entity(
        repo,
        SCHEMA,
        path="second-task.md",
        entity_id="second-task-id",
        metadata={"name": "Revisar contratos", "type": "task", "status": "pending"},
        content="- Tarea de prueba.\n",
        actor="fixture",
        now=CLOCK,
    )
    executor.context_index.rebuild(repo, SCHEMA, executor.embedder)
    executor.semantic_index.rebuild(repo, SCHEMA, executor.embedder)
    original_core = executor.dependent_core_delegate
    assert original_core is not None

    def core(text, locator, who, instant):
        if text == BEFORE:
            return original_core(text, locator, who, instant)
        assert text == SECOND.strip()
        calls.append("core2")
        primary = KnowledgeUnit(
            SelectionCriteria(None, "2026-10-15", "calendar_day", (), None),
            "record",
            (),
            (),
            ("Ayer revisé {{ref:0}}.",),
            (KnowledgeReference(1, "task", "Revisar contratos"),),
        )
        helper = KnowledgeUnit(
            SelectionCriteria("Revisar contratos", "Revisar contratos", "task", (), None),
            "record",
            (),
            (),
            (),
            (),
            reference_lookup_only=True,
        )
        return execute_request(
            text,
            planner=SimpleNamespace(
                plan=lambda *_: RequestPlan((WriteAction((primary, helper)),), ())
            ),
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

    executor.dependent_core_delegate = core

    def prepare(text, _instant):
        assert text in (FIRST_TASK.strip(), SECOND_TASK.strip())
        calls.append("prepare-a" if text == FIRST_TASK.strip() else "prepare-b")
        operation = (
            TaskOperation.START_WORK_SESSION
            if text == FIRST_TASK.strip()
            else TaskOperation.STOP_WORK_SESSION
        )
        return TaskInterpretation(text, operation, task_reference="Preparar informe Atlas"), None

    executor.dependent_task_prepare = prepare
    session_ids = iter(("first-n-session", "second-n-session"))
    domain = TaskWorkSessionService(repo, SCHEMA, None, id_allocator=lambda: next(session_ids))

    def task(text, locator, who, interpretation, temporal, target, instant):
        assert temporal is None
        calls.append("task-a" if text == FIRST_TASK.strip() else "task-b")
        note_id = target.require_current(repo, SCHEMA)
        if interpretation.operation is TaskOperation.START_WORK_SESSION:
            revision, digest = domain.task_mutation_tokens(note_id)
            effect = domain.start(
                task_id=note_id,
                started_at=instant.isoformat(),
                request_id=locator,
                actor=who.stable_user_id,
                now=instant.isoformat(),
                expected_task_revision=revision,
                expected_task_source_hash=digest,
            )
        else:
            assert interpretation.operation is TaskOperation.STOP_WORK_SESSION
            effect = domain.stop_for_task(
                task_id=note_id,
                ended_at=instant.isoformat(),
                request_id=locator,
                actor=who.stable_user_id,
                now=instant.isoformat(),
            )
        return ApplicationResult(locator, ApplicationStatus.COMPLETED, (), (effect.session.id,))

    executor.dependent_task_delegate = task
    executor.client = RecordedClient(_rows())
    store = LocalDeliveryResultStore(
        runtime.conversation_root_resolver.resolve(actor.stable_user_id) / "delivery-results"
    )

    def manifest_begin(delivery, text, _who, groups):
        store.begin_operation_manifest(delivery, store.fingerprint(text, "main"), text, groups)

    def manifest_observe(delivery, text, _who, ordinal, capability, outcome):
        store.observe_operation_manifest(
            delivery,
            store.fingerprint(text, "main"),
            ordinal,
            capability,
            outcome.status.value,
            outcome.affected_stable_note_ids,
        )

    executor.operation_manifest_begin = manifest_begin
    executor.operation_manifest_observe = manifest_observe
    executor.refresh_between_independent_scopes = executor.refresh_affected_indexes
    return repo, actor, executor, runtime, calls, domain, store


def test_n_dependent_three_groups_have_real_core_writers_session_manifest_and_replay(tmp_path):
    repo, actor, executor, runtime, calls, domain, store = _physical_runtime(tmp_path)
    executor.client = RecordedClient(_three_rows())
    delivery = "p4-n3-real-dag"
    result = runtime.execute_product(SOURCE_THREE, delivery, "main", actor)
    assert result["status"] == "completed", result
    assert [entry["capability"] for entry in result["execution_flow"]["routes"]] == [
        "core",
        "core",
        "tasks",
    ]
    assert [entry["depends_on"] for entry in result["execution_flow"]["routes"]] == [None, None, 0]
    assert len(domain.list_for_task("atlas-p4-dependent-task")) == 1
    assert len(domain.list_for_task("second-task-id")) == 0
    assert domain.list_for_task("atlas-p4-dependent-task")[0].ended_at is None
    assert "first-n-session" in result["affected_stable_note_ids"]
    assert calls == ["prepare-a", "core", "core2", "task-a"]
    manifest = store.inspect_operation_manifest(delivery, store.fingerprint(SOURCE_THREE, "main"))
    assert manifest["planned_operations"] == 3
    assert manifest["observed_operations"] == 3
    assert manifest["recovery_authorized"] is False
    before = _snapshot(repo)
    replay = runtime.execute_product(SOURCE_THREE, delivery, "main", actor)
    assert replay["delivery_replayed"] is True
    assert _snapshot(repo) == before
    assert calls == ["prepare-a", "core", "core2", "task-a"]
    assert executor.client.rows == []


@pytest.mark.parametrize(
    "bad",
    [
        "partition_missing_group",
        "route_reordered",
        "two_task_parents",
        "task_scope_extra_operation",
        "last_semantic_wrong_target",
        "last_source_no_antecedent",
    ],
)
def test_n_graph_all_unrepresentable_semantics_abort_before_first_write(tmp_path, bad):
    repo, actor, executor, runtime, calls, domain, store = _physical_runtime(tmp_path)
    rows = _rows()
    if bad == "partition_missing_group":
        rows[1]["groups"] = rows[1]["groups"][:3]
    elif bad == "route_reordered":
        rows[0]["app_scopes"][1]["capability"] = "tasks"
    elif bad == "two_task_parents":
        rows[1]["groups"][3]["dependencies"].append(
            {
                "predecessor_index": 0,
                "antecedent_mention": "Preparar informe Atlas",
                "mention": "Preparar informe Atlas",
            }
        )
        rows[2]["groups"] = deepcopy(rows[1]["groups"])
    elif bad == "task_scope_extra_operation":
        rows[6]["exactly_one_operation"] = False
    elif bad == "last_semantic_wrong_target":
        rows[8]["target_type"] = "person"
    else:
        rows[1]["groups"][3]["dependencies"][0]["antecedent_mention"] = "Nadie"
        rows[2]["groups"] = deepcopy(rows[1]["groups"])
    executor.client = RecordedClient(rows)
    before = _snapshot(repo)
    result = runtime.execute_product(SOURCE, f"p4-n4-deny-{bad}", "main", actor)
    assert result["status"] == "needs_attention", result
    assert before == _snapshot(repo)
    assert not domain.list_for_task("atlas-p4-dependent-task")
    assert not domain.list_for_task("second-task-id")
    assert "core" not in calls and "task-a" not in calls
    assert not store.inspect_operation_manifest(
        f"p4-n4-deny-{bad}", store.fingerprint(SOURCE, "main")
    )["manifest_present"]


def test_n_graph_stale_predecessor_after_second_core_leaves_partial_and_replay(tmp_path):
    from dataclasses import replace

    from odyssey_core.notes import parse_note, serialize_note

    repo, actor, executor, runtime, calls, domain, store = _physical_runtime(tmp_path)
    executor.client = RecordedClient(_three_rows())
    real_core = executor.dependent_core_delegate
    assert real_core is not None

    def changed_between_groups(text, locator, who, instant):
        receipt = real_core(text, locator, who, instant)
        if text == SECOND.strip():
            # Simulates non-cooperating external Markdown edit after earlier
            # Core backlink but before dependent Task target proof.
            for path in repo.list_markdown_paths():
                note = parse_note(repo.read_text(path))
                if note.metadata.get("id") == "atlas-p4-dependent-task":
                    repo.replace_text(
                        path, serialize_note(replace(note, content=note.content + "\n- changed\n"))
                    )
                    break
        return receipt

    executor.dependent_core_delegate = changed_between_groups
    result = runtime.execute_product(SOURCE_THREE, "p4-n3-stale-after-write", "main", actor)
    assert result["status"] == "partial", result
    assert len(domain.list_for_task("atlas-p4-dependent-task")) == 0
    assert len(domain.list_for_task("second-task-id")) == 0
    manifest = store.inspect_operation_manifest(
        "p4-n3-stale-after-write", store.fingerprint(SOURCE_THREE, "main")
    )
    assert manifest["planned_operations"] == 3
    assert manifest["observed_operations"] == 3
    assert [item["status"] for item in result["execution_flow"]["routes"]] == [
        "completed",
        "completed",
        "needs_attention",
    ]
    before = _snapshot(repo)
    assert (
        runtime.execute_product(SOURCE_THREE, "p4-n3-stale-after-write", "main", actor)[
            "delivery_replayed"
        ]
        is True
    )
    assert _snapshot(repo) == before


def test_n_graph_two_global_session_starts_vetoed_before_any_core_write(tmp_path):
    """Task domain compatibility is prechecked for ALL ops before first Core fact."""
    repo, actor, executor, runtime, calls, domain, store = _physical_runtime(tmp_path)
    from dataclasses import replace

    original_prepare = executor.dependent_task_prepare
    assert original_prepare is not None

    def two_starts(text, instant):
        op, temporal = original_prepare(text, instant)
        return replace(op, operation=TaskOperation.START_WORK_SESSION), temporal

    executor.dependent_task_prepare = two_starts
    rows = _rows()
    rows[7]["operation"] = "START_WORK_SESSION"
    rows[8]["operation"] = "START_WORK_SESSION"
    executor.client = RecordedClient(rows)
    before = _snapshot(repo)
    result = runtime.execute_product(SOURCE, "p4-n4-double-session-veto", "main", actor)
    assert result["status"] == "needs_attention", result
    assert result["clarification_code"] == "DEPENDENT_N_TASK_BATCH_INCOMPATIBLE"
    assert calls == ["prepare-a", "prepare-b"]
    assert before == _snapshot(repo)
    assert not store.inspect_operation_manifest(
        "p4-n4-double-session-veto", store.fingerprint(SOURCE, "main")
    )["manifest_present"]
    assert not domain.list_for_task("atlas-p4-dependent-task")


def test_n_graph_crash_after_physical_session_write_retains_e3_and_no_duplicate(tmp_path):
    from odyssey_runtime.delivery_results import DeliveryResultError

    repo, actor, executor, runtime, calls, domain, store = _physical_runtime(tmp_path)
    executor.client = RecordedClient(_three_rows())
    delegate = executor.dependent_task_delegate
    assert delegate is not None

    def fail_after_first_task(*args):
        delegate(*args)
        raise RuntimeError("synthetic postwrite crash after first session")

    executor.dependent_task_delegate = fail_after_first_task
    with pytest.raises(RuntimeError, match="synthetic postwrite crash"):
        runtime.execute_product(SOURCE_THREE, "p4-n3-crash-after-session", "main", actor)
    assert len(domain.list_for_task("atlas-p4-dependent-task")) == 1
    assert domain.list_for_task("atlas-p4-dependent-task")[0].ended_at is None
    observed = store.inspect_operation_manifest(
        "p4-n3-crash-after-session", store.fingerprint(SOURCE_THREE, "main")
    )
    assert observed == {
        "manifest_present": True,
        "planned_operations": 3,
        "observed_operations": 2,
        "claim_state": "unresolved_attempt",
        "recovery_authorized": False,
    }
    snapshot = _snapshot(repo)
    with pytest.raises(DeliveryResultError, match="unresolved prior attempt"):
        runtime.execute_product(SOURCE_THREE, "p4-n3-crash-after-session", "main", actor)
    assert _snapshot(repo) == snapshot
    assert calls == ["prepare-a", "core", "core2", "task-a"]


def test_n_graph_start_then_stop_without_session_edge_is_rejected_prewrite(tmp_path):
    repo, actor, executor, runtime, calls, domain, store = _physical_runtime(tmp_path)
    before = _snapshot(repo)
    result = runtime.execute_product(SOURCE, "p4-n4-no-session-provenance", "main", actor)
    assert result["status"] == "needs_attention"
    assert result["clarification_code"] == "DEPENDENT_N_TASK_BATCH_INCOMPATIBLE"
    assert calls == ["prepare-a", "prepare-b"]
    assert _snapshot(repo) == before
    assert not domain.list_for_task("atlas-p4-dependent-task")
    assert not store.inspect_operation_manifest(
        "p4-n4-no-session-provenance", store.fingerprint(SOURCE, "main")
    )["manifest_present"]


def test_n_graph_missing_tasks_capability_adapter_cannot_fall_through_to_core(tmp_path):
    repo, actor, executor, runtime, calls, domain, store = _physical_runtime(tmp_path)
    executor.dependent_task_delegate = None
    executor.client = RecordedClient([_route()])
    before = _snapshot(repo)
    result = runtime.execute_product(SOURCE, "p4-n4-no-tasks-adapter", "main", actor)
    assert result["status"] == "needs_attention"
    assert result["clarification_code"] == "DEPENDENT_N_GRAPH_ADAPTER_UNAVAILABLE"
    assert _snapshot(repo) == before
    assert executor.client.rows == []
    assert calls == []
