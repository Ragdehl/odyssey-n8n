"""Real production factory + generic Core writer + dependent Tasks Work Session.

Model output is frozen, while factory services, semantic indexes, real
Markdown, E2 carrier, E3 receipt and the Notes API all execute unmodified.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TASK_SCHEMA_EXTENSION,
    TaskActivityTarget,
    TaskInterpretation,
    TaskOperation,
    TaskRelationshipMention,
    TaskRelationshipRole,
    TaskTemporalMention,
    TaskTemporalRole,
)
from odyssey_core import create_entity
from odyssey_core.context import ContextIndex
from odyssey_core.identity_boundary import AuthenticatedActorContext, SelfBindingRepository
from odyssey_core.notes import parse_note
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    PropertyChange,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal_interpretation import parse_temporal_interpretation
from odyssey_runtime import composition
from tests.core.test_reference_preflight import UnresolvedReasoner
from tests.runtime.test_p4_dependent_router_integrated import (
    AFTER,
    BEFORE,
    CLOCK,
    SOURCE,
    _attestation,
    _partition,
    _route,
)
from tests.runtime.test_temporal_user_path_e2e import ConstantEmbedder
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient


def test_real_product_factory_core_and_tasks_dependent_work_session(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    runtime_root = tmp_path / "derived"
    for path in (vault, state / "pending", runtime_root):
        path.mkdir(parents=True)
    repo = VaultRepository(vault)
    base = json.loads((Path(__file__).resolve().parents[2] / "config/note-schema.json").read_text())
    schema = compose_application_schema(base, (TASK_SCHEMA_EXTENSION,))
    create_entity(
        repo,
        schema,
        path="self.md",
        entity_id="self-factory-p4-dependent",
        metadata={"name": "Persona local", "type": "person"},
        content="",
        actor="fixture",
        now=CLOCK,
    )
    create_entity(
        repo,
        schema,
        path="atlas.md",
        entity_id="atlas-factory-p4-dependent",
        metadata={"name": "Preparar informe Atlas", "type": "task", "status": "pending"},
        content="- Tarea existente.\n",
        actor="fixture",
        now=CLOCK,
    )
    actor = AuthenticatedActorContext(str(uuid4()))
    SelfBindingRepository(state, repo, schema).bind(
        actor.stable_user_id, "self-factory-p4-dependent"
    )
    embedder = ConstantEmbedder()
    for index in (
        ContextIndex(runtime_root / "context.sqlite3"),
        SemanticEntityIndex(runtime_root / "semantic.sqlite3"),
        SemanticEntityIndex(runtime_root / "semantic-tasks.sqlite3"),
    ):
        index.rebuild(repo, schema, embedder)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-synthetic-unused-do-not-send")
    monkeypatch.setenv("ODYSSEY_LIGHT_SOURCE_V1", "1")
    monkeypatch.setenv("ODYSSEY_ENABLED_APPLICATIONS", "tasks")
    monkeypatch.setenv("ODYSSEY_VAULT_ROOT", str(vault))
    monkeypatch.setenv("ODYSSEY_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("ODYSSEY_STATE_ROOT", str(state))
    monkeypatch.setenv("ODYSSEY_PENDING_ROOT", str(state / "pending"))
    monkeypatch.setenv("ODYSSEY_EMBEDDING_CACHE", str(tmp_path / "fake-cache"))
    monkeypatch.setattr(composition, "FastEmbedTextEmbedder", lambda **_kwargs: embedder)
    monkeypatch.setattr(composition, "_build_contextual_reasoner", UnresolvedReasoner)
    monkeypatch.setattr(composition, "GitHistoryRecorder", lambda _root: None)
    monkeypatch.setattr(
        composition,
        "_current_time",
        lambda: {
            # Simulate the actual wall clock advancing past midnight while
            # the same logical delivery was received on the previous day.
            "date": "2026-10-17",
            "time": "00:00:02",
            "timezone": "Europe/Paris",
            "timestamp": "2026-10-17T00:00:02+02:00",
        },
    )
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
    core_sources: list[str] = []
    followup_sources: set[str] = set()
    followup_antecedents: set[str] = set()

    class Planner:
        def plan(self, text, *args):
            core_sources.append(text)
            assert text in {SOURCE, BEFORE} | followup_sources | followup_antecedents
            # Reuse the general Core plan structure with the *actual* fresh
            # antecedent text and link marker. The read-only guard probes the
            # original complete source, but cannot mutate anything.
            if text in followup_antecedents:
                assert text.count("Preparar informe Atlas") == 1
                rewritten = replace(
                    unit, facts=(text.replace("Preparar informe Atlas", "{{ref:0}}"),)
                )
                return RequestPlan((WriteAction((rewritten, helper)),), ())
            return plan

    planner_dates: list[str] = []

    def planner_from_environment(_cls, _schema, clock, **_kwargs):
        planner_dates.append(clock["date"])
        return Planner()

    monkeypatch.setattr(
        composition.OpenAIRequestPlanner,
        "from_environment",
        classmethod(planner_from_environment),
    )
    task_sources: list[str] = []
    followup_interpretations: dict[str, TaskInterpretation] = {}

    class Interpreter:
        def interpret(self, text, context=()):
            assert text == AFTER.strip() or text in followup_interpretations
            task_sources.append(text)
            return (
                TaskInterpretation(
                    text, TaskOperation.START_WORK_SESSION, task_reference="esa tarea"
                )
                if text == AFTER.strip()
                else followup_interpretations[text]
            )

    monkeypatch.setattr(
        composition.OpenAITaskInterpreter,
        "from_environment",
        classmethod(lambda cls: Interpreter()),
    )

    class TemporalInterpreter:
        model = "frozen-temporal-boundary"
        reasoning_effort = "low"
        last_usage = None
        last_call = False

        def interpret(self, text, _context=()):
            return parse_temporal_interpretation(
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
                text,
                timezone="Europe/Paris",
            )

    temporal_review_clocks: list[str] = []

    def temporal_from_environment(_cls, context):
        temporal_review_clocks.append(context["date"])
        assert context["date"] == "2026-10-16"  # captured, NOT later 17 October
        return TemporalInterpreter()

    monkeypatch.setattr(
        composition.OpenAITemporalInterpreter,
        "from_environment",
        classmethod(temporal_from_environment),
    )
    product = composition.build_runtime_from_environment()
    # The opt-in P4 route MUST still respect application availability. A
    # deployment without Tasks never exposes dependent Task write adapters.
    monkeypatch.setenv("ODYSSEY_ENABLED_APPLICATIONS", "")
    without_tasks = composition.build_runtime_from_environment()
    assert without_tasks.hybrid_candidate_execute.dependent_core_delegate is None
    assert without_tasks.hybrid_candidate_execute.dependent_task_prepare is None
    assert without_tasks.hybrid_candidate_execute.dependent_subtask_prepare is None
    assert without_tasks.hybrid_candidate_execute.dependent_task_delegate is None
    assert without_tasks.hybrid_candidate_execute.independent_task_prepare is None
    assert without_tasks.hybrid_candidate_execute.independent_task_delegate is None
    monkeypatch.setenv("ODYSSEY_ENABLED_APPLICATIONS", "tasks")
    scheduled_indexes: list[tuple[str, ...]] = []
    original_scheduler = product.schedule_index_refresh
    assert original_scheduler is not None

    def record_schedule(affected):
        scheduled_indexes.append(tuple(affected))
        return original_scheduler(affected)

    product.schedule_index_refresh = record_schedule
    executor = product.hybrid_candidate_execute
    assert executor is not None
    assert callable(executor.independent_task_prepare)
    assert callable(executor.independent_task_delegate)
    assert callable(executor.refresh_between_independent_scopes)
    clock_for_delivery = [datetime.fromisoformat(CLOCK)]
    executor.now = lambda: clock_for_delivery[0]
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
    result = product.execute_product(SOURCE, "p4-factory-dependent", "main", actor)
    assert result["status"] == "completed", result
    assert core_sources == [SOURCE, BEFORE]
    assert planner_dates[:2] == ["2026-10-17", "2026-10-16"]
    assert task_sources == [AFTER.strip()]
    assert executor.client.rows == []
    assert len(product.work_session_service.list_for_task("atlas-factory-p4-dependent")) == 1
    assert result["execution_flow"]["routes"][0]["capability"] == "core"
    assert result["execution_flow"]["routes"][1]["capability"] == "tasks"
    assert result["affected_stable_note_ids"]
    assert scheduled_indexes == [tuple(result["affected_stable_note_ids"])]

    # The child title is prepared by the production GPT-5.6 Core planner
    # seam, then shaped by the existing Tasks decorator; no separate prompt
    # or direct Markdown path participates.
    subtask_source = "Ahora crea la subtarea Preparar el índice dentro de esa tarea."
    subtask = TaskInterpretation(
        subtask_source,
        TaskOperation.CREATE,
        relationship_mentions=(
            TaskRelationshipMention("esa tarea", TaskRelationshipRole.PARENT_TASK),
        ),
    )
    raw_subtask_plan = RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria(
                            "Preparar el índice", "Preparar el índice", "task", (), None
                        ),
                        "record",
                        (PropertyChange("status", "set", "pending"),),
                        (),
                        ("Preparar el índice.",),
                        (),
                    ),
                )
            ),
        ),
        (),
    )

    class GPT56Planner:
        def plan(self, text, _context=()):
            assert text == subtask_source
            return raw_subtask_plan

    monkeypatch.setattr(
        composition.GPT56RequestPlanner,
        "from_environment",
        classmethod(lambda _cls, *_args, **_kwargs: GPT56Planner()),
    )
    assert executor.dependent_subtask_prepare is not None
    prepared = executor.dependent_subtask_prepare(
        subtask_source, subtask, datetime.fromisoformat(CLOCK)
    )
    assert prepared.require_matches(subtask_source, TaskOperation.CREATE) == "Preparar el índice"

    # Exercise the production delegate itself: Core writes a fresh backlink,
    # then execute_tasks uses TaskDirectMutationService.create_subtask rather
    # than the test's own mutation shim.
    subtask_before = "Hoy comprobé Preparar informe Atlas."
    subtask_dependent = " Ahora crea la subtarea Preparar el índice dentro de esa tarea."
    subtask_full_source = subtask_before + subtask_dependent
    followup_antecedents.add(subtask_before)
    followup_interpretations[subtask_dependent.strip()] = TaskInterpretation(
        subtask_dependent.strip(),
        TaskOperation.CREATE,
        relationship_mentions=(
            TaskRelationshipMention("esa tarea", TaskRelationshipRole.PARENT_TASK),
        ),
    )
    executor.client = RecordedClient(
        [
            _route(),
            {
                "full_source_quote": subtask_full_source,
                "antecedent_quote": subtask_before,
                "dependent_quote": subtask_dependent,
                "dependent_mention": "esa tarea",
            },
            {
                "only_task_semantics": True,
                "exactly_one_operation": True,
                "source_quote": subtask_dependent.strip(),
            },
            {
                "full_source_quote": subtask_full_source,
                "antecedent_quote": subtask_before,
                "dependent_quote": subtask_dependent,
                "dependent_mention": "esa tarea",
                "one_target": True,
                "same_target": True,
                "target_type": "task",
                "operation": "CREATE_SUBTASK",
                "operation_supported": True,
            },
            {
                "full_source_quote": subtask_full_source,
                "antecedent_quote": subtask_before,
                "dependent_quote": subtask_dependent,
                "dependent_mention": "esa tarea",
                "one_target": True,
                "same_target": True,
                "target_type": "task",
                "operation": "CREATE_SUBTASK",
                "operation_supported": True,
            },
        ]
    )
    subtask_result = product.execute_product(
        subtask_full_source, "p4-factory-subtask", "main", actor
    )
    assert subtask_result["status"] == "completed", subtask_result
    created_child = next(
        parse_note(repo.read_text(path))
        for path in repo.list_markdown_paths()
        if parse_note(repo.read_text(path)).metadata.get("name") == "Preparar el índice"
    )
    assert created_child.metadata["type"] == "task"
    assert "[[atlas|Preparar informe Atlas]]" in created_child.content
    subtask_snapshot = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    assert product.execute_product(subtask_full_source, "p4-factory-subtask", "main", actor)[
        "delivery_replayed"
    ]
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == subtask_snapshot

    # Evaluate the workflow's ACTUAL JavaScript bounded flow guards against
    # the real product result, rather than duplicating their logic in Python.
    import subprocess

    bridge = subprocess.run(
        ["node", str(Path(__file__).resolve().parents[1] / "p4_dependent_n8n_flow_contract.mjs")],
        input=json.dumps(result, ensure_ascii=False),
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert bridge.returncode == 0, bridge.stderr or bridge.stdout
    assert json.loads(bridge.stdout)["n8n_flow_accepted"] is True
    day = next(
        parse_note(repo.read_text(p))
        for p in repo.list_markdown_paths()
        if parse_note(repo.read_text(p)).metadata["id"] == "date:2026-10-16"
    )
    assert "[[atlas|Preparar informe Atlas]]" in day.content
    detail = product.notes("detail", {"note_id": "atlas-factory-p4-dependent"}, actor)
    assert len(detail["work_sessions"]) == 1
    session = detail["work_sessions"][0]
    assert session["started_at"] == CLOCK
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    replay = product.execute_product(SOURCE, "p4-factory-dependent", "main", actor)
    assert replay["delivery_replayed"] is True
    assert core_sources == [SOURCE, BEFORE, subtask_full_source, subtask_before]
    assert task_sources == [AFTER.strip(), subtask_dependent.strip()]
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before
    ui = product.notes(
        "work_session_activity_add",
        {
            "session_id": session["id"],
            "text": "Actividad UI real tras chat dependiente.",
            "request_id": "p4-dependent-factory-ui",
            "expected_revision": session["mutation"]["revision"],
            "expected_source_hash": session["mutation"]["source_hash"],
        },
        actor,
    )
    assert len(ui["work_sessions"][0]["activity"]) == 1

    # The actual HTTP runtime observes this *dependent* route's durable E3
    # receipt, two truthful execution_flow branches and the SAME Notes UI.
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer
    from threading import Thread

    from odyssey_runtime.server import _handler_for

    http = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(product))
    worker = Thread(target=http.serve_forever, daemon=True)
    worker.start()

    def post(endpoint, payload):
        connection = HTTPConnection("127.0.0.1", http.server_port, timeout=15)
        connection.request(
            "POST",
            endpoint,
            json.dumps(
                {**payload, "authenticated_actor": {"stable_user_id": actor.stable_user_id}},
                ensure_ascii=False,
            ).encode("utf-8"),
            {"Content-Type": "application/json; charset=utf-8"},
        )
        response = connection.getresponse()
        status, body = response.status, json.loads(response.read())
        connection.close()
        return status, body

    try:
        code, graph = post(
            "/execute",
            {
                "request": SOURCE,
                "request_id": "p4-factory-dependent",
                "conversation_id": "main",
            },
        )
        print("DEPENDENT_HTTP_DIAGNOSTIC", code, graph)
        assert code == 200 and graph["delivery_replayed"] is True
        assert [route["capability"] for route in graph["execution_flow"]["routes"]] == [
            "core",
            "tasks",
        ]
        code, page = post(
            "/notes", {"operation": "detail", "note_id": "atlas-factory-p4-dependent"}
        )
        assert code == 200 and len(page["work_sessions"]) == 1
        assert len(page["work_sessions"][0]["activity"]) == 1
        code, progress_view = post("/conversation/progress", {"request_id": "p4-factory-dependent"})
        assert code == 200
        assert progress_view["stage"] in {
            "action.delegate.started",
            "action.write.started",
            "finalizing",
        }
        assert progress_view["progress"] >= 68
    finally:
        http.shutdown()
        http.server_close()
        worker.join(timeout=5)

    # The same dependent handoff must use ordinary Tasks ACTIVITY and STOP
    # operations too, not only START. Every delivery has its own exact source,
    # Core proof, Task interpretation, E3 receipt and shared WorkSession Note.
    def followup(
        antecedent: str,
        fragment: str,
        operation: TaskOperation,
        *,
        activity: str | None = None,
    ):
        original = antecedent + fragment
        followup_sources.add(original)
        followup_antecedents.add(antecedent)
        followup_interpretations[fragment.strip()] = TaskInterpretation(
            fragment.strip(),
            operation,
            task_reference="esa tarea",
            temporal_mentions=(
                (TaskTemporalMention("a las 15:10", TaskTemporalRole.WORK_SESSION_START_AT),)
                if operation is TaskOperation.EDIT_WORK_SESSION
                else ()
            ),
            activity_target=(TaskActivityTarget.TASK if activity else TaskActivityTarget.NONE),
            activity_text=activity,
        )
        executor.client = RecordedClient(
            [
                _route(),
                _partition()
                | {
                    "full_source_quote": original,
                    "antecedent_quote": antecedent,
                    "dependent_quote": fragment,
                },
                {
                    "only_task_semantics": True,
                    "exactly_one_operation": True,
                    "source_quote": fragment.strip(),
                },
                _attestation(
                    full_source_quote=original,
                    antecedent_quote=antecedent,
                    dependent_quote=fragment,
                    operation=operation.value,
                ),
                _attestation(
                    full_source_quote=original,
                    antecedent_quote=antecedent,
                    dependent_quote=fragment,
                    operation=operation.value,
                ),
            ]
        )
        return product.execute_product(original, f"p4-factory-{operation.value}", "main", actor)

    clock_for_delivery[0] = datetime.fromisoformat("2026-10-16T15:50:00+02:00")
    progress = followup(
        "Hoy avancé con Preparar informe Atlas.",
        " Ahora anota en la sesión de esa tarea que verifiqué los plazos.",
        TaskOperation.ADD_WORK_SESSION_ACTIVITY,
        activity="verifiqué los plazos",
    )
    assert progress["status"] == "completed", progress
    assert len(scheduled_indexes) == 3  # Exactly one scheduled index update per Chat delivery
    assert scheduled_indexes[-1] == tuple(progress["affected_stable_note_ids"])
    updated = product.notes("detail", {"note_id": "atlas-factory-p4-dependent"}, actor)
    assert len(updated["work_sessions"][0]["activity"]) == 2
    assert "verifiqué los plazos" in [
        item["text"] for item in updated["work_sessions"][0]["activity"]
    ]
    clock_for_delivery[0] = datetime.fromisoformat("2026-10-16T16:00:00+02:00")
    stopped_source = " Ahora termina la sesión de esa tarea."
    stop_antecedent = "Hoy cerré la revisión de Preparar informe Atlas."
    stopped = followup(stop_antecedent, stopped_source, TaskOperation.STOP_WORK_SESSION)
    assert stopped["status"] == "completed", stopped
    assert len(scheduled_indexes) == 4
    assert scheduled_indexes[-1] == tuple(stopped["affected_stable_note_ids"])
    ended = product.notes("detail", {"note_id": "atlas-factory-p4-dependent"}, actor)
    assert len(ended["work_sessions"]) == 1
    assert ended["work_sessions"][0]["ended_at"] == "2026-10-16T16:00:00+02:00"
    old_notes = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    again = product.execute_product(
        stop_antecedent + stopped_source, "p4-factory-STOP_WORK_SESSION", "main", actor
    )
    assert again["delivery_replayed"] is True
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == old_notes
    assert len(product.work_session_service.list_for_task("atlas-factory-p4-dependent")) == 1

    # EDIT also belongs to the ordinary Work Session service. Its temporal
    # interpreter must receive the delivery's captured day even though the
    # simulated wall clock crossed midnight while models were running.
    clock_for_delivery[0] = datetime.fromisoformat("2026-10-16T16:05:00+02:00")
    edit_antecedent = "Hoy comprobé el avance de Preparar informe Atlas."
    edit_fragment = " Ahora corrige el inicio de la sesión de esa tarea a las 15:10."
    edited = followup(edit_antecedent, edit_fragment, TaskOperation.EDIT_WORK_SESSION)
    assert edited["status"] == "completed", edited
    assert len(scheduled_indexes) == 5
    assert scheduled_indexes[-1] == tuple(edited["affected_stable_note_ids"])
    assert temporal_review_clocks == ["2026-10-16"]
    after_edit = product.notes("detail", {"note_id": "atlas-factory-p4-dependent"}, actor)
    assert after_edit["work_sessions"][0]["started_at"] == "2026-10-16T15:10:00+02:00"
    assert after_edit["work_sessions"][0]["ended_at"] == "2026-10-16T16:00:00+02:00"
    edited_snapshot = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    edit_replay = product.execute_product(
        edit_antecedent + edit_fragment, "p4-factory-EDIT_WORK_SESSION", "main", actor
    )
    assert edit_replay["delivery_replayed"] is True
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == edited_snapshot
