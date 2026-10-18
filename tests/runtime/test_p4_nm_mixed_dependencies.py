"""Any N-scope DAG may mix dependent and independent Task operations.

The production runner uses the existing generic Task prepare/delegate ports and
the same Core writer/E3 manifest for zero-edge scopes. Frozen model responses,
disposable repo; no special task count or source phrase code in the product.
"""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from odyssey_apps.tasks import TaskInterpretation, TaskOperation
from odyssey_core.application import execute_request
from odyssey_core.notes import parse_note
from odyssey_core.request_planning import (
    KnowledgeUnit,
    PropertyChange,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from tests.runtime.test_p4_dependent_n_graph_execution import (
    SOURCE_THREE,
    _physical_runtime,
    _snapshot,
    _three_rows,
)
from tests.runtime.test_p4_dependent_router_integrated import SCHEMA
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient

INDEPENDENT = " Después tengo que limpiar el escritorio."
FULL = SOURCE_THREE + INDEPENDENT


def _rows():
    rows = _three_rows()
    rows[0]["app_scopes"].append(
        {
            "capability": "tasks",
            "description": "Independent task operation",
            "depends_on_another_scope": False,
        }
    )
    rows[1]["full_source_quote"] = FULL
    rows[1]["groups"].append(
        {"capability": "tasks", "source_quote": INDEPENDENT, "dependencies": []}
    )
    rows[2]["full_source_quote"] = FULL
    rows[2]["groups"] = deepcopy(rows[1]["groups"])
    for reviewer in (rows[4], rows[5]):
        reviewer["full_source_quote"] = FULL
    rows.append(
        {
            "only_task_semantics": True,
            "exactly_one_operation": True,
            "source_quote": INDEPENDENT.strip(),
        }
    )
    return rows


def _with_independent_task(repo, actor, executor, calls):
    def prepare(segment, _clock):
        assert segment == INDEPENDENT.strip()
        calls.append("prepare-independent")
        return TaskInterpretation(segment, TaskOperation.CREATE), None

    def delegate(segment, locator, who, task, temporal, instant):
        assert task.operation is TaskOperation.CREATE
        assert temporal is None
        assert segment == INDEPENDENT.strip()
        calls.append("task-independent")
        title = "Limpiar el escritorio"
        action = WriteAction(
            (
                KnowledgeUnit(
                    SelectionCriteria(title, title, "task", (), None),
                    "record",
                    (PropertyChange("status", "set", "pending"),),
                    (),
                    (title + ".",),
                    (),
                    force_create=True,
                ),
            )
        )
        return execute_request(
            segment,
            planner=SimpleNamespace(plan=lambda *_: RequestPlan((action,), ())),
            repository=repo,
            schema=SCHEMA,
            context_index=executor.context_index,
            semantic_index=executor.semantic_index,
            embedder=executor.embedder,
            contextual_reasoner=executor.reasoner,
            authenticated_actor=who,
            self_binding_repository=executor.bindings,
            actor=who.stable_user_id,
            now=instant.isoformat(timespec="seconds"),
            context_limit=10,
            request_id_factory=lambda: locator,
        )

    executor.independent_task_prepare = prepare
    executor.independent_task_delegate = delegate


def test_n_scope_dependent_and_independent_operations_use_existing_writers_and_e3(tmp_path):
    repo, actor, executor, runtime, calls, domain, store = _physical_runtime(tmp_path)
    _with_independent_task(repo, actor, executor, calls)
    executor.client = RecordedClient(_rows())
    before = _snapshot(repo)
    result = runtime.execute_product(FULL, "mixed-dag-dependent-independent", "main", actor)
    assert result["status"] == "completed", result
    assert _snapshot(repo) != before
    assert len(result["execution_flow"]["routes"]) == 4
    assert [scope.get("depends_on") for scope in result["execution_flow"]["routes"]] == [
        None,
        None,
        0,
        None,
    ]
    tasks = [parse_note(repo.read_text(p)) for p in repo.list_markdown_paths()]
    assert any(
        note.metadata.get("type") == "task"
        and note.metadata.get("name") == "Limpiar el escritorio"
        and note.metadata.get("status") == "pending"
        for note in tasks
    )
    assert len(domain.list_for_task("atlas-p4-dependent-task")) == 1
    assert calls == [
        "prepare-a",
        "prepare-independent",
        "core",
        "core2",
        "task-a",
        "task-independent",
    ]
    receipt = store.inspect_operation_manifest(
        "mixed-dag-dependent-independent", store.fingerprint(FULL, "main")
    )
    assert receipt["planned_operations"] == 4 and receipt["observed_operations"] == 4
    persisted = _snapshot(repo)
    replay = runtime.execute_product(FULL, "mixed-dag-dependent-independent", "main", actor)
    assert replay["delivery_replayed"] is True
    assert _snapshot(repo) == persisted
    assert executor.client.rows == []


def test_n_scope_unlinked_task_missing_adapter_refuses_before_any_write(tmp_path):
    repo, actor, executor, runtime, calls, domain, store = _physical_runtime(tmp_path)
    executor.client = RecordedClient(_rows()[:3])
    before = _snapshot(repo)
    result = runtime.execute_product(FULL, "mixed-dag-no-independent-port", "main", actor)
    assert result["status"] == "needs_attention"
    assert result["clarification_code"] == "DEPENDENT_N_INDEPENDENT_TASK_ADAPTER_UNAVAILABLE"
    assert _snapshot(repo) == before
    assert calls == []
    assert not store.inspect_operation_manifest(
        "mixed-dag-no-independent-port", store.fingerprint(FULL, "main")
    )["manifest_present"]


def test_n_scope_bad_last_operation_is_vetoed_before_first_core_write(tmp_path):
    repo, actor, executor, runtime, calls, domain, store = _physical_runtime(tmp_path)
    _with_independent_task(repo, actor, executor, calls)
    rows = _rows()
    rows[-1]["exactly_one_operation"] = False
    executor.client = RecordedClient(rows)
    before = _snapshot(repo)
    result = runtime.execute_product(FULL, "mixed-dag-invalid-final-scope", "main", actor)
    assert result["status"] == "needs_attention"
    assert _snapshot(repo) == before
    assert calls == ["prepare-a", "prepare-independent"]
    assert not store.inspect_operation_manifest(
        "mixed-dag-invalid-final-scope", store.fingerprint(FULL, "main")
    )["manifest_present"]
