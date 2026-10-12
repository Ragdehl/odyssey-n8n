"""Opt-in hybrid Task route delegates to real Tasks Core lifecycle, never Day facts.

The hybrid compiler does not create or label Tasks. Registered Tasks alone
owns its schema, lifecycle and Core writer. No DEV/PROD registration occurs.
"""

from __future__ import annotations

from functools import partial
from types import SimpleNamespace

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TASK_SCHEMA_EXTENSION,
    TaskCorePlanner,
    TaskInterpretation,
    TaskLifecycleGuard,
    TaskOperation,
)
from odyssey_core.application import ApplicationResult, ApplicationStatus, execute_request
from odyssey_core.notes import parse_note, validate_note
from odyssey_core.request_planning import (
    KnowledgeUnit,
    PropertyChange,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import RecordedRouter
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault


def _source(case_id):
    return next(c["source"] for c in CASES if c["id"] == case_id)


def _enabled_compiler():
    return partial(compile_hybrid_candidate_bundle, enable_tasks=True)


def test_tasks_use_registered_app_only_when_explicitly_enabled():
    source = _source("F22")
    normal = compile_hybrid_candidate_bundle(RecordedRouter("F22").propose(source))
    enabled = _enabled_compiler()(RecordedRouter("F22").propose(source))
    assert len(normal.units) == len(enabled.units) == 3
    assert [x.route.capability_id for x in normal.units] == ["temporal", "core", "temporal"]
    assert [x.route.capability_id for x in enabled.units] == ["tasks"] * 3
    assert [x.context.source for x in enabled.units] == [x.context.source for x in normal.units]
    assert all(x.context.hybrid_interpretation_mode for x in enabled.units)
    mixed = _enabled_compiler()(RecordedRouter("F25").propose(_source("F25")))
    assert len(mixed.units) == 1
    assert mixed.units[0].route.capability_id == "core"


def test_enabled_tasks_without_app_executor_fail_closed_on_each_route(tmp_path):
    source = _source("F22")
    repo, ctx, semantic, embedder = fresh_corpus_vault(tmp_path)
    originals = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    result = execute_candidate_routed_message(
        source,
        router=RecordedRouter("F22"),
        temporal=None,
        core_planner_factory=lambda *_: (_ for _ in ()).throw(AssertionError("Core fallback")),
        candidate_coverage_factory=lambda *_: (_ for _ in ()).throw(AssertionError("No write")),
        repository=repo,
        schema=SCHEMA,
        context_index=ctx,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="tasks-unavailable",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "tasks-unavailable-test",
        bundle_compiler=_enabled_compiler(),
    )
    assert result.status is not ApplicationStatus.COMPLETED
    assert [r["status"] for r in result.execution_flow["routes"]] == ["failed"] * 3
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == originals


def test_hybrid_task_app_can_create_real_pending_task_via_existing_core_lifecycle(tmp_path):
    source = _source("F22")
    repo, ctx, semantic, embedder = fresh_corpus_vault(tmp_path)
    task_schema = compose_application_schema(SCHEMA, (TASK_SCHEMA_EXTENSION,))
    ctx.rebuild(repo, task_schema, embedder)
    semantic.rebuild(repo, task_schema, embedder)
    visited = []

    def tasks_execute(fragment, locator, _actor, _prior):
        visited.append(fragment)
        assert fragment in (
            "Hoy tengo que llamar a Ana",
            " y escribir a Luis",
            "; mañana preparar la factura.",
        )
        if fragment != "; mañana preparar la factura.":
            return ApplicationResult(
                locator,
                ApplicationStatus.NEEDS_ATTENTION,
                (),
                (),
                planning_error="TASK_CAPABILITY_PENDING_EVIDENCE",
            )
        task = TaskInterpretation(fragment, TaskOperation.CREATE)
        plan = RequestPlan(
            (
                WriteAction(
                    (
                        KnowledgeUnit(
                            SelectionCriteria(
                                "Preparar la factura", "preparar la factura", "task", (), None
                            ),
                            "record",
                            (
                                PropertyChange("status", "set", "pending"),
                                PropertyChange("target_date", "set", "2026-10-05"),
                            ),
                            (),
                            ("Preparar la factura.",),
                            (),
                        ),
                    )
                ),
            ),
            (),
        )
        planner = TaskCorePlanner(
            SimpleNamespace(plan=lambda _request, _context=(): plan, is_local_replay=True),
            task,
        )
        return execute_request(
            fragment,
            planner=planner,
            repository=repo,
            schema=task_schema,
            context_index=ctx,
            semantic_index=semantic,
            embedder=embedder,
            contextual_reasoner=object(),
            actor="hybrid-real-task-create",
            now=NOW,
            context_limit=5,
            request_id_factory=lambda: locator,
            preflight_id_allocator=lambda: "test-hybrid-task-f22",
            write_preflight_guard=TaskLifecycleGuard(TaskOperation.CREATE),
        )

    result = execute_candidate_routed_message(
        source,
        router=RecordedRouter("F22"),
        temporal=None,
        core_planner_factory=lambda *_: (_ for _ in ()).throw(AssertionError("Core fallback")),
        candidate_coverage_factory=lambda *_: (_ for _ in ()).throw(AssertionError("No Core path")),
        repository=repo,
        schema=SCHEMA,
        context_index=ctx,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="test-hybrid-task",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "hybrid-tasks-v1",
        bundle_compiler=_enabled_compiler(),
        task_route_executor=tasks_execute,
    )
    assert len(visited) == 3
    assert result.status is ApplicationStatus.PARTIAL, result.execution_flow
    assert [r["status"] for r in result.execution_flow["routes"]] == [
        "needs_attention",
        "needs_attention",
        "completed",
    ]
    task_paths = [p for p in repo.list_markdown_paths() if "test-hybrid-task-f22" in p]
    assert len(task_paths) == 1, repo.list_markdown_paths()
    task = parse_note(repo.read_text(task_paths[0]))
    validate_note(task, task_schema)
    assert task.metadata["type"] == "task"
    assert task.metadata["status"] == "pending"
    assert task.metadata["target_date"] == "2026-10-05"
    assert task.content.count("Preparar la factura.") == 1
    assert not any(
        "preparar la factura" in repo.read_text(p).lower()
        for p in repo.list_markdown_paths()
        if p.startswith("calendar/days/") and "2026-10-05" in p
    )
