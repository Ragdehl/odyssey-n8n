"""Opt-in hybrid Task route delegates to real Tasks Core lifecycle, never Day facts.

The hybrid compiler does not create or label Tasks. Registered Tasks alone
owns its schema, lifecycle and Core writer. No DEV/PROD registration occurs.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from functools import partial
from types import SimpleNamespace

import pytest

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TASK_SCHEMA_EXTENSION,
    TaskCorePlanner,
    TaskInterpretation,
    TaskLifecycleGuard,
    TaskOperation,
    TaskScopedEvidence,
    TaskScopedExecution,
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
from odyssey_core.temporal_interpretation import parse_temporal_interpretation
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from odyssey_runtime.scoped_temporal_handoff import ScopedTemporalHandoff
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import RecordedRouter, _source_temporal
from tests.runtime.test_fact_candidate_planning_vertical import _exact_date
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
    # The ordinary four-argument executor remains callable for local routes,
    # but cannot receive the typed predecessor date required by route two.
    assert visited == ["Hoy tengo que llamar a Ana", "; mañana preparar la factura."]
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


def test_scoped_task_executor_reuses_verified_date_without_predecessor_task_write(tmp_path):
    """Create independent Tasks only through a typed Temporal/modality bridge."""
    source = _source("F22")
    repo, ctx, semantic, embedder = fresh_corpus_vault(tmp_path)
    task_schema = compose_application_schema(SCHEMA, (TASK_SCHEMA_EXTENSION,))
    ctx.rebuild(repo, task_schema, embedder)
    semantic.rebuild(repo, task_schema, embedder)
    created = 0
    seen = []

    def task_plan(label, date):
        return RequestPlan(
            (
                WriteAction(
                    (
                        KnowledgeUnit(
                            SelectionCriteria(label, label.casefold(), "task", (), None),
                            "record",
                            (
                                PropertyChange("status", "set", "pending"),
                                PropertyChange("target_date", "set", date),
                            ),
                            (),
                            (f"{label}.",),
                            (),
                        ),
                    )
                ),
            ),
            (),
        )

    class ScopedTasks:
        def execute_scoped(self, fragment, locator, _actor, _prior, *, scoped_evidence):
            nonlocal created
            seen.append(fragment)
            if fragment == "Hoy tengo que llamar a Ana":
                date, temporal = "2026-10-04", _source_temporal(fragment)
            elif fragment == " y escribir a Luis":
                assert [
                    (item.source_text, item.value) for item in scoped_evidence.inherited_temporal
                ] == [("Hoy", "2026-10-04")]
                assert [(item.role, item.text) for item in scoped_evidence.modality_provenance] == [
                    ("modality", "tengo que")
                ]
                assert "Hoy" not in fragment and "tengo que" not in fragment
                date, temporal = "2026-10-04", None
            else:
                assert fragment == "; mañana preparar la factura."
                date = "2026-10-05"
                temporal = parse_temporal_interpretation(
                    {"mentions": [_exact_date("mañana", date)]}, fragment, timezone="Europe/Paris"
                )
            task = TaskInterpretation(fragment, TaskOperation.CREATE)
            planner = TaskCorePlanner(
                SimpleNamespace(
                    plan=lambda _request, _context=(): task_plan(
                        fragment.strip(" ;.").capitalize(), date
                    ),
                    is_local_replay=True,
                ),
                task,
            )
            created += 1
            result = execute_request(
                fragment,
                planner=planner,
                repository=repo,
                schema=task_schema,
                context_index=ctx,
                semantic_index=semantic,
                embedder=embedder,
                contextual_reasoner=object(),
                actor="scoped-task-bridge",
                now=NOW,
                context_limit=5,
                request_id_factory=lambda: locator,
                preflight_id_allocator=lambda: f"scoped-task-{created}",
                write_preflight_guard=TaskLifecycleGuard(task.operation),
            )
            return TaskScopedExecution(result, temporal)

    result = execute_candidate_routed_message(
        source,
        router=RecordedRouter("F22"),
        temporal=None,
        core_planner_factory=lambda *_: (_ for _ in ()).throw(AssertionError("Core fallback")),
        candidate_coverage_factory=lambda *_: (_ for _ in ()).throw(AssertionError("No Day write")),
        repository=repo,
        schema=SCHEMA,
        context_index=ctx,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="scoped-task-test",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "scoped-task-bridge",
        bundle_compiler=_enabled_compiler(),
        task_route_executor=ScopedTasks(),
    )
    assert result.status is ApplicationStatus.COMPLETED, result.execution_flow
    assert seen == [
        "Hoy tengo que llamar a Ana",
        " y escribir a Luis",
        "; mañana preparar la factura.",
    ]
    paths = [path for path in repo.list_markdown_paths() if "scoped-task-" in path]
    assert len(paths) == 3
    notes = [parse_note(repo.read_text(path)) for path in paths]
    assert all(
        note.metadata["type"] == "task" and note.metadata["status"] == "pending" for note in notes
    )
    assert sorted(note.metadata["target_date"] for note in notes) == [
        "2026-10-04",
        "2026-10-04",
        "2026-10-05",
    ]
    day_text = "\n".join(
        repo.read_text(path)
        for path in repo.list_markdown_paths()
        if path.startswith("calendar/days/")
    ).casefold()
    assert "llamar a ana" not in day_text
    assert "escribir a luis" not in day_text
    assert "preparar la factura" not in day_text


def test_task_scoped_evidence_rejects_forged_source_and_non_modality_role():
    """Keep Task bridge provenance tied to the untouched original and exact role."""
    source = _source("F22")
    bundle = _enabled_compiler()(RecordedRouter("F22").propose(source))
    first, second = bundle.units[:2]
    handoff = ScopedTemporalHandoff(source)
    handoff.remember(
        _source_temporal(first.context.source),
        route_index=0,
        start=first.original_start,
        end=first.original_end,
    )
    inherited = handoff.inherited(
        second.context,
        current_route_index=1,
        start=second.original_start,
        end=second.original_end,
    )
    modality = tuple(role for role in second.context.source_provenance if role.role == "modality")
    evidence = TaskScopedEvidence(
        second.context.source, hashlib.sha256(source.encode()).hexdigest(), 1, inherited, modality
    )
    evidence.validate(source)
    with pytest.raises(ValueError, match="malformed"):
        replace(evidence, original_sha256="0" * 64).validate(source)
    with pytest.raises(ValueError, match="modality"):
        replace(evidence, modality_provenance=(replace(modality[0], role="polarity"),)).validate(
            source
        )
