"""F22 three genuinely modeled Task operations, exact links and dated readback."""

from __future__ import annotations

import json
from functools import partial
from pathlib import Path

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TASK_SCHEMA_EXTENSION,
    OpenAITaskInterpreter,
    TaskCorePlanner,
    TaskLifecycleGuard,
    TaskScopedExecution,
    compose_scoped_task_domain_interpretation,
)
from odyssey_core.application import ApplicationStatus, execute_request
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


def test_f22_all_three_task_notes_preserve_named_identity_and_schedule(tmp_path: Path) -> None:
    """No mock GPT output: original real responses + new actual second GPT-5.6 reply."""
    old = json.loads(
        (ROOT / "benchmarks/application_router/hybrid_tasks_v1/F22-full-v2.json").read_text()
    )
    new = json.loads(
        (
            ROOT / "benchmarks/application_router/hybrid_tasks_named_link_v1/F22-second.json"
        ).read_text()
    )
    outputs = old["provider_outputs"]
    assert len(outputs) == 8
    assert len(new["real_new_model_outputs"]) == 1
    source = next(row["source"] for row in CASES if row["id"] == "F22")
    repo, index, semantic, embedder = fresh_corpus_vault(tmp_path)
    task_schema = compose_application_schema(SCHEMA, (TASK_SCHEMA_EXTENSION,))
    plan_schema = planning_schema_for_capability(task_schema, "tasks")
    index.rebuild(repo, task_schema, embedder)
    semantic.rebuild(repo, plan_schema, embedder)
    routes_seen = []

    class TasksRunner:
        def execute_scoped(self, fragment, locator, _actor, _prior, *, scoped_evidence):
            route = scoped_evidence.route_index
            routes_seen.append((route, fragment))
            assert route in {0, 1, 2}
            task_index, time_index, plan_row = {
                0: (0, 1, outputs[2]),
                1: (3, None, new["real_new_model_outputs"][0]),
                2: (5, 6, outputs[7]),
            }[route]
            task = OpenAITaskInterpreter(FrozenProvider([outputs[task_index]])).interpret_scoped(
                fragment, scoped_evidence=scoped_evidence
            )
            temporal = (
                OpenAITemporalInterpreter(
                    FrozenProvider([outputs[time_index]]),
                    CLOCK,
                    max_output_tokens=1536,
                    scoped_date_time_context=True,
                ).interpret(fragment)
                if time_index is not None
                else None
            )
            domain = compose_scoped_task_domain_interpretation(
                task, temporal, scoped_evidence, now=NOW
            )
            model = FrozenProvider([plan_row])
            planner = TaskCorePlanner(
                OpenAILunaExperimentalPlanner(
                    model, plan_schema, CLOCK, domain_interpretation=domain
                ),
                task.task,
            )
            result = execute_request(
                fragment,
                planner=planner,
                repository=repo,
                schema=plan_schema,
                context_index=index,
                semantic_index=semantic,
                embedder=embedder,
                contextual_reasoner=object(),
                actor="isolated-all-real-f22-test",
                now=NOW,
                context_limit=5,
                request_id_factory=lambda: locator,
                preflight_id_allocator=lambda: "replay-f22-generic-task-" + str(route),
                write_preflight_guard=TaskLifecycleGuard(task.task.operation),
            )
            assert len(model.calls) == 1
            return TaskScopedExecution(result, temporal)

    before = set(repo.list_markdown_paths())
    result = execute_candidate_routed_message(
        source,
        router=RecordedRouter("F22"),
        temporal=None,
        core_planner_factory=lambda *_: (_ for _ in ()).throw(
            AssertionError("Tasks must never create ordinary Day Core facts")
        ),
        candidate_coverage_factory=lambda *_: (_ for _ in ()).throw(
            AssertionError("Tasks must not fallback to Day facts")
        ),
        repository=repo,
        schema=SCHEMA,
        context_index=index,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="isolated-f22-genuine-task-routing",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "f22-complete-genuine",
        bundle_compiler=partial(compile_hybrid_candidate_bundle, enable_tasks=True),
        task_route_executor=TasksRunner(),
    )
    assert result.status is ApplicationStatus.COMPLETED, result.execution_flow
    assert [r["status"] for r in result.execution_flow["routes"]] == ["completed"] * 3
    assert routes_seen == [
        (0, "Hoy tengo que llamar a Ana"),
        (1, " y escribir a Luis"),
        (2, "; mañana preparar la factura."),
    ]
    created = sorted(set(repo.list_markdown_paths()) - before)
    tasks = [path for path in created if "replay-f22-generic-task-" in path]
    assert len(tasks) == 3, created
    # Tasks can create frontmatter-only Day stubs for calendar navigation;
    # never misreport them as invented Day FACTS.
    for path in created:
        if path.startswith("calendar/days"):
            assert not any(line.startswith("- ") for line in repo.read_text(path).splitlines())
    notes = {
        parse_note(repo.read_text(path)).metadata["name"]: parse_note(repo.read_text(path))
        for path in tasks
    }
    assert set(notes) == {"llamar a Ana", "escribir a Luis", "preparar la factura"}
    for note in notes.values():
        validate_note(note, task_schema)
        assert note.metadata["type"] == "task"
        assert note.metadata["status"] == "pending"
    assert notes["llamar a Ana"].metadata["target_date"] == "2026-10-04"
    assert notes["escribir a Luis"].metadata["target_date"] == "2026-10-04"
    assert notes["preparar la factura"].metadata["target_date"] == "2026-10-05"
    assert "Llamar a [[Ana|Ana]]." in notes["llamar a Ana"].content
    assert "Escribir a [[Luis|Luis]]." in notes["escribir a Luis"].content
    assert notes["escribir a Luis"].content.count("Escribir a") == 1
    assert "preparar la factura." in notes["preparar la factura"].content.casefold()
