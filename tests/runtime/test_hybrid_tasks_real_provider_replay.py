"""Replay genuine hybrid Tasks GPT-6/Temporal GPT-6/Core GPT-5.6 output."""

from __future__ import annotations

import hashlib
import json
from functools import partial

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TASK_SCHEMA_EXTENSION,
    OpenAITaskInterpreter,
    TaskCorePlanner,
    TaskLifecycleGuard,
    TaskOperation,
    compose_task_domain_interpretation,
)
from odyssey_core.application import ApplicationResult, ApplicationStatus, execute_request
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.notes import parse_note, validate_note
from odyssey_core.schema_types import planning_schema_for_capability
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_candidate_route_dispatch_e2e import RecordedRouter
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import ROOT, fresh_corpus_vault
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider


def test_real_tasks_model_creates_canonical_pending_task_through_opt_in_hybrid(tmp_path):
    saved = json.loads(
        (ROOT / "benchmarks/application_router/hybrid_tasks_v1/F22-last.json").read_text()
    )
    assert saved["source_sha256"] == hashlib.sha256(saved["source"].encode()).hexdigest()
    full = next(c["source"] for c in CASES if c["id"] == "F22")
    bundle = compile_hybrid_candidate_bundle(RecordedRouter("F22").propose(full), enable_tasks=True)
    assert len(bundle.units) == 3 and all(u.route.capability_id == "tasks" for u in bundle.units)
    assert bundle.units[-1].context.source == saved["source"]
    sdk = FrozenProvider(saved["provider_outputs"])
    repo, index, semantic, embedder = fresh_corpus_vault(tmp_path)
    task_schema = compose_application_schema(SCHEMA, (TASK_SCHEMA_EXTENSION,))
    planner_schema = planning_schema_for_capability(task_schema, "tasks")
    index.rebuild(repo, task_schema, embedder)
    semantic.rebuild(repo, planner_schema, embedder)

    def tasks_run(fragment, locator, *_unused):
        if fragment != saved["source"]:
            return ApplicationResult(
                locator,
                ApplicationStatus.NEEDS_ATTENTION,
                (),
                (),
                planning_error="OTHER_TASK_ROUTE_NOT_TESTED",
            )
        task = OpenAITaskInterpreter(sdk).interpret(fragment)
        assert task.operation is TaskOperation.CREATE
        interpretation = (
            OpenAITemporalInterpreter(
                sdk, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
            ).interpret(fragment)
            if task.requires_temporal()
            else None
        )
        domain = compose_task_domain_interpretation(
            task, interpretation, now="2026-10-04T17:35:00+02:00"
        )
        planner = TaskCorePlanner(
            OpenAILunaExperimentalPlanner(sdk, planner_schema, CLOCK, domain_interpretation=domain),
            task,
        )
        return execute_request(
            fragment,
            planner=planner,
            repository=repo,
            schema=planner_schema,
            context_index=index,
            semantic_index=semantic,
            embedder=embedder,
            contextual_reasoner=object(),
            actor="genuine-tasks-replay",
            now="2026-10-04T17:35:00+02:00",
            context_limit=5,
            request_id_factory=lambda: locator,
            preflight_id_allocator=lambda: "f22-real-task-unique",
            write_preflight_guard=TaskLifecycleGuard(task.operation),
        )

    result = execute_candidate_routed_message(
        full,
        router=RecordedRouter("F22"),
        temporal=None,
        core_planner_factory=lambda *_: (_ for _ in ()).throw(AssertionError("No Core fallback")),
        candidate_coverage_factory=lambda *_: (_ for _ in ()).throw(AssertionError("No Day write")),
        repository=repo,
        schema=SCHEMA,
        context_index=index,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="genuine-hybrid-tasks",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "F22-genuine-hybrid",
        bundle_compiler=partial(compile_hybrid_candidate_bundle, enable_tasks=True),
        task_route_executor=tasks_run,
    )
    assert result.status is ApplicationStatus.PARTIAL, result.execution_flow
    assert [x["status"] for x in result.execution_flow["routes"]] == [
        "needs_attention",
        "needs_attention",
        "completed",
    ]
    assert len(sdk.calls) == 3
    paths = [p for p in repo.list_markdown_paths() if "f22-real-task-unique" in p]
    assert len(paths) == 1
    task = parse_note(repo.read_text(paths[0]))
    validate_note(task, task_schema)
    assert task.metadata["type"] == "task"
    assert task.metadata["status"] == "pending"
    assert task.metadata["target_date"] == "2026-10-05"
    assert "preparar la factura." in task.content
    assert "calendar/days/2026-10-05.md" not in repo.list_markdown_paths()
