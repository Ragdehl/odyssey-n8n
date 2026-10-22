"""E5 independently reviewed Event + Task scopes on the EXISTING E2/E3 product gate.

Uses frozen Router/scope reviewers and physically real Core Event and Task
WorkSession mutations with shared product delivery replay in a disposable vault.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from odyssey_apps.events import EVENT_SCHEMA_EXTENSION
from odyssey_apps.events.execution import execute_event_candidate
from odyssey_apps.events.mutations import EventMutationService
from odyssey_apps.events.provider import validate_event_candidate
from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TASK_SCHEMA_EXTENSION,
    TaskInterpretation,
    TaskOperation,
    TaskWorkSessionService,
)
from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.independent_source_scopes import (
    IndependentSourceScopesError,
    verify_independent_source_scopes,
)
from odyssey_core.notes import parse_note
from odyssey_core.temporal_interpretation import TemporalInterpretation, TemporalMention
from odyssey_core.temporal_resolution import TemporalResolution, TemporalResolutionKind
from odyssey_runtime.delivery_results import LocalDeliveryResultStore
from tests.runtime.test_p4_independent_mixed_scopes import TASK, _runtime
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient

EVENT = "Concierto independiente E5 el 24 de noviembre de 2026."
SOURCE = EVENT + " " + TASK


def _router(*, independent: bool = True):
    return {
        "capabilities": ["events", "tasks", "temporal"],
        "interpretation": "separable" if independent else "joint",
        "reason": "independent" if independent else "shared_event",
        "self_relation_span": None,
        "app_scopes": [
            {"capability": "events", "description": "concierto", "depends_on_another_scope": False},
            {
                "capability": "tasks",
                "description": "empezar sesión en tarea Atlas",
                "depends_on_another_scope": not independent,
            },
        ],
    }


def _partition():
    return {
        "full_source_quote": SOURCE,
        "parts": [
            {"capability": "events", "source_quote": EVENT + " "},
            {"capability": "tasks", "source_quote": TASK},
        ],
    }


def _review(**overrides):
    return {
        "full_source_quote": SOURCE,
        "complete": True,
        "independent": True,
        "no_cross_scope_referents": True,
        **overrides,
    }


def _client_rows():
    return [
        _router(),
        _partition(),
        _review(),
        {"only_task_semantics": True, "exactly_one_operation": True, "source_quote": TASK},
    ]


def _fixture(tmp_path: Path):
    repo, actor, executor, runtime, session_calls = _runtime(tmp_path)
    schema = compose_application_schema(
        __import__("json").loads(
            (Path(__file__).resolve().parents[2] / "config/note-schema.json").read_text()
        ),
        (TASK_SCHEMA_EXTENSION, EVENT_SCHEMA_EXTENSION),
    )
    executor.schema = schema
    runtime.canonical_schema = schema
    mutation = EventMutationService(repo, schema)
    # Shared vault requires a composed schema in the real Task service too.
    task_sessions = TaskWorkSessionService(
        repo, schema, None, id_allocator=lambda: "e5-mixed-session-one"
    )
    runtime.work_session_service = task_sessions

    def run_real_task(source, delivery, who):
        assert source == TASK and who == actor
        receipt = task_sessions.start(
            task_id="atlas-task",
            started_at="2026-10-16T18:00:00+02:00",
            request_id=delivery,
            actor=who.stable_user_id,
            now="2026-10-16T18:00:00+02:00",
        )
        session_calls.append(delivery)
        return ApplicationResult(delivery, ApplicationStatus.COMPLETED, (), (receipt.session.id,))

    executor.task_delegate = run_real_task
    # Exercise the same durable E3 manifest that active DEV uses, rather
    # than accepting a provider-free result without operation journaling.
    manifest = LocalDeliveryResultStore(
        runtime.conversation_root_resolver.resolve(actor.stable_user_id) / "delivery-results",
        manifest_capabilities=frozenset({"core", "tasks", "events"}),
    )
    executor.operation_manifest_begin = lambda rid, text, _who, groups: (
        manifest.begin_operation_manifest(rid, manifest.fingerprint(text, "main"), text, groups)
    )
    executor.operation_manifest_observe = lambda rid, text, _who, index, cap, result: (
        manifest.observe_operation_manifest(
            rid,
            manifest.fingerprint(text, "main"),
            index,
            cap,
            result.status.value,
            result.affected_stable_note_ids,
        )
    )
    stages = []

    def prepare_event(source: str, instant):
        assert source == EVENT
        stages.append("event_prepared")
        candidate = validate_event_candidate(
            source,
            {
                "operation": "CREATE",
                "title_quote": "Concierto independiente E5",
                "event_reference": None,
                "query_quote": None,
                "temporal_mentions": [
                    {"quote": "24 de noviembre de 2026", "role": "DATE"},
                ],
            },
        )
        temporal = TemporalInterpretation(
            source,
            (
                TemporalMention(
                    "24 de noviembre de 2026",
                    TemporalResolution(TemporalResolutionKind.EXACT_DATE, exact_date="2026-11-24"),
                ),
            ),
        )
        return candidate, temporal

    def prepare_task(source: str, instant):
        assert source == TASK
        stages.append("task_prepared")
        return TaskInterpretation(
            source, TaskOperation.START_WORK_SESSION, task_reference="Preparar informe Atlas"
        ), None

    def execute_event(source, delivery, who, candidate, temporal, instant):
        assert who == actor and stages[:2] == ["task_prepared", "event_prepared"]
        stages.append("event_written")
        return execute_event_candidate(
            candidate=candidate,
            temporal=temporal,
            repository=repo,
            schema=schema,
            mutations=mutation,
            request_id=delivery,
            actor=actor.stable_user_id,
            now=instant.isoformat(timespec="seconds"),
            authenticated=True,
        )

    def execute_task(source, delivery, who, task, temporal, instant):
        assert who == actor and stages[:2] == ["task_prepared", "event_prepared"]
        stages.append("task_written")
        return executor.task_delegate(source, delivery, who)

    executor.event_delegate = lambda *_: (_ for _ in ()).throw(
        AssertionError("Events-only route must not bypass independent source partition")
    )
    executor.independent_event_prepare = prepare_event
    executor.independent_event_delegate = execute_event
    executor.independent_task_prepare = prepare_task
    executor.independent_task_delegate = execute_task
    return repo, actor, executor, runtime, session_calls, stages


def _event_notes(repo):
    return [
        parse_note(repo.read_text(path))
        for path in repo.list_markdown_paths()
        if parse_note(repo.read_text(path)).metadata.get("type") == "event"
    ]


def test_mixed_event_task_one_canonical_event_and_one_session_then_byte_identical_replay(tmp_path):
    repo, actor, executor, runtime, calls, stages = _fixture(tmp_path)
    executor.client = RecordedClient(_client_rows())
    result = runtime.execute_product(SOURCE, "e5-real-mixed-frozen", "main", actor)
    assert result["status"] == "completed", result
    assert executor.client.rows == []
    assert len(calls) == 1
    assert len(_event_notes(repo)) == 1
    assert _event_notes(repo)[0].metadata["start_date"] == "2026-11-24"
    assert _event_notes(repo)[0].metadata["event_status"] == "scheduled"
    assert stages == ["task_prepared", "event_prepared", "event_written", "task_written"]
    manifest_receipt = LocalDeliveryResultStore(
        runtime.conversation_root_resolver.resolve(actor.stable_user_id) / "delivery-results",
        manifest_capabilities=frozenset({"core", "tasks", "events"}),
    ).inspect_operation_manifest(
        "e5-real-mixed-frozen", LocalDeliveryResultStore.fingerprint(SOURCE, "main")
    )
    assert manifest_receipt["planned_operations"] == 2
    assert manifest_receipt["observed_operations"] == 2
    flow = result["execution_flow"]
    assert [r["capability"] for r in flow["routes"]] == ["events", "tasks"]
    assert all(r["status"] == "completed" for r in flow["routes"])
    before = {str(path): repo.read_text(path) for path in repo.list_markdown_paths()}
    replay = runtime.execute_product(SOURCE, "e5-real-mixed-frozen", "main", actor)
    assert replay["delivery_replayed"] is True
    assert {str(path): repo.read_text(path) for path in repo.list_markdown_paths()} == before
    assert len(calls) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"full_source_quote": EVENT + TASK},
        {
            "parts": [
                {"capability": "events", "source_quote": EVENT},
                {"capability": "tasks", "source_quote": TASK},
            ]
        },
        {
            "parts": [
                {"capability": "tasks", "source_quote": TASK},
                {"capability": "events", "source_quote": EVENT + " "},
            ]
        },
    ],
)
def test_event_task_provenance_rejects_missing_characters_or_reordered_parts(change):
    with pytest.raises(IndependentSourceScopesError):
        verify_independent_source_scopes(
            SOURCE,
            _partition() | change,
            _review(),
            permitted_capabilities=frozenset({"events", "tasks"}),
        )


@pytest.mark.parametrize("route_rejected", [True, False])
def test_dependent_or_unverified_event_task_never_writes(tmp_path, route_rejected):
    repo, actor, executor, runtime, calls, stages = _fixture(tmp_path)
    pre = {str(path): repo.read_text(path) for path in repo.list_markdown_paths()}
    if route_rejected:
        executor.client = RecordedClient([_router(independent=False)])
    else:
        executor.client = RecordedClient(
            [_router(), _partition(), _review(no_cross_scope_referents=False)]
        )
    result = runtime.execute_product(SOURCE, "e5-invalid-independent", "main", actor)
    assert result["status"] == "needs_attention", result
    assert not calls and not stages
    assert not _event_notes(repo)
    assert {str(path): repo.read_text(path) for path in repo.list_markdown_paths()} == pre


def test_task_preparation_unavailable_prevents_first_event_write(tmp_path):
    repo, actor, executor, runtime, calls, stages = _fixture(tmp_path)
    executor.client = RecordedClient(_client_rows())
    executor.independent_task_prepare = lambda *_: (_ for _ in ()).throw(
        ValueError("test prewrite task refusal")
    )
    result = runtime.execute_product(SOURCE, "e5-task-preflight-failed", "main", actor)
    assert result["status"] == "needs_attention", result
    assert not _event_notes(repo)
    assert not stages and not calls


def test_event_preparation_unavailable_prevents_first_task_write(tmp_path):
    repo, actor, executor, runtime, calls, stages = _fixture(tmp_path)
    executor.client = RecordedClient(_client_rows())
    executor.independent_event_prepare = lambda *_: (_ for _ in ()).throw(
        ValueError("test prewrite Event refusal")
    )
    result = runtime.execute_product(SOURCE, "e5-event-preflight-failed", "main", actor)
    assert result["status"] == "needs_attention", result
    assert not _event_notes(repo)
    assert stages == ["task_prepared"] and not calls


def test_runtime_exception_after_event_write_stays_partial_and_replay_is_safe(tmp_path):
    repo, actor, executor, runtime, calls, stages = _fixture(tmp_path)
    executor.client = RecordedClient(_client_rows())
    executor.independent_task_delegate = lambda *_: (_ for _ in ()).throw(
        ValueError("unknown write status in second independent app")
    )
    result = runtime.execute_product(SOURCE, "e5-mixed-uncertain", "main", actor)
    assert result["status"] == "partial", result
    assert "INDEPENDENT_EVENT_TASK_POSTWRITE_UNVERIFIED" in str(result)
    assert len(_event_notes(repo)) == 1
    before = {str(path): repo.read_text(path) for path in repo.list_markdown_paths()}
    replay = runtime.execute_product(SOURCE, "e5-mixed-uncertain", "main", actor)
    assert replay["delivery_replayed"] is True
    assert {str(path): repo.read_text(path) for path in repo.list_markdown_paths()} == before
