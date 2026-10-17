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
        "review_reason": "APPROVED",
        "failing_group_index": None,
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
    assert [entry.get("depends_on") for entry in result["execution_flow"]["routes"]] == [
        None,
        None,
        0,
    ]
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


@pytest.mark.parametrize(
    "reason,index",
    [
        ("SOURCE_COVERAGE", None),
        ("GROUP_CLASSIFICATION", 0),
        ("DEPENDENCY_AMBIGUOUS", 2),
        ("DEPENDENCY_MISSING", 2),
    ],
)
def test_n_graph_review_reason_is_visible_but_never_allows_a_write(tmp_path, reason, index):
    repo, actor, executor, runtime, calls, domain, store = _physical_runtime(tmp_path)
    rows = _three_rows()
    rows[2] = {
        "full_source_quote": SOURCE_THREE,
        "complete": False,
        "dependency_edges_verified": False,
        "review_reason": reason,
        "failing_group_index": index,
        "groups": [],
    }
    executor.client = RecordedClient(rows[:3])
    before = _snapshot(repo)
    locator = f"n-review-{reason.lower()}"
    response = runtime.execute_product(SOURCE_THREE, locator, "main", actor)
    assert response["status"] == "needs_attention"
    assert response["clarification_code"] == f"DEPENDENT_N_GRAPH_REVIEW_{reason}"
    assert _snapshot(repo) == before
    assert calls == []
    assert not domain.list_for_task("atlas-p4-dependent-task")
    assert not store.inspect_operation_manifest(locator, store.fingerprint(SOURCE_THREE, "main"))[
        "manifest_present"
    ]
    replay = runtime.execute_product(SOURCE_THREE, locator, "main", actor)
    assert replay["delivery_replayed"] is True
    assert replay["clarification_code"] == response["clarification_code"]


def _session_link_rows():
    """Explicitly reviewed Task→WorkSession edge alongside the Core→Task edge."""
    rows = _rows()
    rows[1]["groups"][3]["dependencies"].append(
        {
            "predecessor_index": 2,
            "antecedent_mention": "una sesión de trabajo",
            "mention": "la sesión",
        }
    )
    rows[2]["groups"] = deepcopy(rows[1]["groups"])
    review = {
        "full_source_quote": SOURCE,
        "producer_quote": FIRST_TASK,
        "consumer_quote": SECOND_TASK,
        "source_mention": "una sesión de trabajo",
        "dependent_mention": "la sesión",
        "producer_operation": "START_WORK_SESSION",
        "consumer_operation": "STOP_WORK_SESSION",
        "one_session": True,
        "same_session": True,
        "operation_supported": True,
    }
    return [*rows, deepcopy(review), deepcopy(review)]


def _linked_session_runtime(tmp_path):
    from odyssey_apps.tasks import prove_created_session

    repo, actor, executor, runtime, calls, domain, store = _physical_runtime(tmp_path)
    executor.client = RecordedClient(_session_link_rows())

    def execute_proven_step(text, locator, who, task, temporal, target, instant, prior_session):
        assert temporal is None
        task_id = target.require_current(repo, SCHEMA)
        if task.operation is TaskOperation.START_WORK_SESSION:
            assert prior_session is None
            calls.append("typed-start")
            revision, digest = domain.task_mutation_tokens(task_id)
            mutation = domain.start(
                task_id=task_id,
                started_at=instant.isoformat(),
                request_id=locator,
                actor=who.stable_user_id,
                now=instant.isoformat(),
                expected_task_revision=revision,
                expected_task_source_hash=digest,
            )
            evidence = prove_created_session(
                result=mutation,
                expected_task_id=task_id,
                creator_delivery_step=locator,
                service=domain,
            )
        else:
            assert task.operation is TaskOperation.STOP_WORK_SESSION
            assert prior_session is not None and prior_session.task_id == task_id
            calls.append("typed-stop")
            revision, digest = prior_session.require_current(domain)
            mutation = domain.stop(
                session_id=prior_session.session_id,
                ended_at=instant.isoformat(),
                expected_revision=revision,
                expected_source_hash=digest,
                request_id=locator,
                actor=who.stable_user_id,
                now=instant.isoformat(),
            )
            evidence = None
        return (
            ApplicationResult(locator, ApplicationStatus.COMPLETED, (), (mutation.session.id,)),
            evidence,
        )

    executor.dependent_session_delegate = execute_proven_step
    return repo, actor, executor, runtime, calls, domain, store


def test_n_graph_four_groups_start_stop_same_canonical_session_with_e3_replay(tmp_path):
    repo, actor, executor, runtime, calls, domain, store = _linked_session_runtime(tmp_path)
    delivery = "p4-n4-typed-session-edge"
    result = runtime.execute_product(SOURCE, delivery, "main", actor)
    assert result["status"] == "completed", result
    assert [entry.get("depends_on") for entry in result["execution_flow"]["routes"]] == [
        None,
        None,
        0,
        2,
    ]
    assert result["execution_flow"]["routes"][3]["dependency_indices"] == [0, 2]
    # Pass the REAL product result through the deployed n8n source's
    # sanitizer and the actual browser graph validator (no network/deploy).
    import json
    import subprocess
    from pathlib import Path

    bridge = subprocess.run(
        ["node", str(Path(__file__).resolve().parents[1] / "p4_n4_n8n_flow_contract.mjs")],
        input=json.dumps(result, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert bridge.returncode == 0, bridge.stderr or bridge.stdout
    assert json.loads(bridge.stdout)["verified_dependencies"] == 2
    assert not any("depends_on" in part for part in result["execution_flow"]["routes"][:2])
    assert calls == ["prepare-a", "prepare-b", "core", "core2", "typed-start", "typed-stop"]
    sessions = domain.list_for_task("atlas-p4-dependent-task")
    assert len(sessions) == 1
    assert sessions[0].id == "first-n-session"
    assert sessions[0].ended_at == sessions[0].started_at
    manifest = store.inspect_operation_manifest(delivery, store.fingerprint(SOURCE, "main"))
    assert manifest["planned_operations"] == 4
    assert manifest["observed_operations"] == 4
    assert manifest["recovery_authorized"] is False
    before = _snapshot(repo)
    replay = runtime.execute_product(SOURCE, delivery, "main", actor)
    assert replay["delivery_replayed"] is True
    assert _snapshot(repo) == before
    assert executor.client.rows == []
    assert calls == ["prepare-a", "prepare-b", "core", "core2", "typed-start", "typed-stop"]


@pytest.mark.parametrize(
    "tamper",
    [
        "no_session_review",
        "review_wrong_parent",
        "review_ambiguous",
        "review_wrong_mention",
        "review_wrong_scope",
        "no_typed_adapter",
    ],
)
def test_n_graph_session_link_rejected_before_first_core_write(tmp_path, tamper):
    repo, actor, executor, runtime, calls, domain, store = _linked_session_runtime(tmp_path)
    rows = _session_link_rows()
    if tamper == "no_session_review":
        rows[10]["same_session"] = False
    elif tamper == "review_wrong_parent":
        rows[1]["groups"][3]["dependencies"][1]["predecessor_index"] = 1
        rows[2]["groups"] = deepcopy(rows[1]["groups"])
    elif tamper == "review_ambiguous":
        rows[9]["one_session"] = False
    elif tamper == "review_wrong_mention":
        rows[9]["dependent_mention"] = "otras sesiones"
    elif tamper == "review_wrong_scope":
        rows[10]["consumer_quote"] = "otro texto"
    elif tamper == "no_typed_adapter":
        executor.dependent_session_delegate = None
        rows = rows[:3]
    executor.client = RecordedClient(rows)
    before = _snapshot(repo)
    delivery = f"p4-n4-typed-veto-{tamper}"
    outcome = runtime.execute_product(SOURCE, delivery, "main", actor)
    assert outcome["status"] == "needs_attention", outcome
    assert _snapshot(repo) == before
    assert not domain.list_for_task("atlas-p4-dependent-task")
    assert "core" not in calls
    assert not store.inspect_operation_manifest(delivery, store.fingerprint(SOURCE, "main"))[
        "manifest_present"
    ]


def test_n_graph_start_physical_then_stale_session_stops_with_partial(tmp_path):
    from dataclasses import replace

    from odyssey_apps.tasks import CanonicalSessionEvidenceError
    from odyssey_core.notes import parse_note, serialize_note

    repo, actor, executor, runtime, calls, domain, store = _linked_session_runtime(tmp_path)
    original = executor.dependent_session_delegate
    assert original is not None

    def mutate_session_between_steps(*args):
        if args[3].operation is TaskOperation.STOP_WORK_SESSION:
            # Non-cooperating actor changes same physical session between
            # START receipt and dependent STOP. No second writer is allowed.
            for path in repo.list_markdown_paths():
                note = parse_note(repo.read_text(path))
                if note.metadata.get("id") == "first-n-session":
                    repo.replace_text(
                        path,
                        serialize_note(
                            replace(note, metadata={**note.metadata, "name": "Edited outside"})
                        ),
                    )
                    break
            try:
                args[7].require_current(domain)
            except CanonicalSessionEvidenceError:
                return (
                    ApplicationResult(
                        args[1],
                        ApplicationStatus.NEEDS_ATTENTION,
                        (),
                        (),
                        planning_error="SESSION_DEPENDENCY_STALE",
                    ),
                    None,
                )
            raise AssertionError("Tampered session proof should be stale")
        return original(*args)

    executor.dependent_session_delegate = mutate_session_between_steps
    delivery = "p4-n4-session-stale"
    result = runtime.execute_product(SOURCE, delivery, "main", actor)
    assert result["status"] == "partial", result
    assert len(domain.list_for_task("atlas-p4-dependent-task")) == 1
    assert domain.list_for_task("atlas-p4-dependent-task")[0].ended_at is None
    manifest = store.inspect_operation_manifest(delivery, store.fingerprint(SOURCE, "main"))
    assert manifest["planned_operations"] == 4
    assert manifest["observed_operations"] == 4
    before = _snapshot(repo)
    assert runtime.execute_product(SOURCE, delivery, "main", actor)["delivery_replayed"] is True
    assert _snapshot(repo) == before


def test_n_graph_crash_after_physical_stop_leaves_uncertain_e3_no_replay(tmp_path):
    from odyssey_runtime.delivery_results import DeliveryResultError

    repo, actor, executor, runtime, calls, domain, store = _linked_session_runtime(tmp_path)
    original = executor.dependent_session_delegate
    assert original is not None

    def crash_after_stop(*args):
        outcome = original(*args)
        if args[3].operation is TaskOperation.STOP_WORK_SESSION:
            raise RuntimeError("crash after physical Work Session STOP")
        return outcome

    executor.dependent_session_delegate = crash_after_stop
    delivery = "p4-n4-crash-after-stop"
    with pytest.raises(RuntimeError, match="crash after physical"):
        runtime.execute_product(SOURCE, delivery, "main", actor)
    sessions = domain.list_for_task("atlas-p4-dependent-task")
    assert len(sessions) == 1 and sessions[0].ended_at is not None
    report = store.inspect_operation_manifest(delivery, store.fingerprint(SOURCE, "main"))
    assert report["observed_operations"] == 3
    assert report["claim_state"] == "unresolved_attempt"
    before = _snapshot(repo)
    with pytest.raises(DeliveryResultError, match="unresolved prior attempt"):
        runtime.execute_product(SOURCE, delivery, "main", actor)
    assert _snapshot(repo) == before
