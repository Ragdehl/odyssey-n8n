"""Isolated genuine *production composition* P4 → Tasks → WorkSession → Notes UI.

No browser, n8n or fresh GPT: Router/scope and TaskInterpreter outputs are
frozen, but every Core/Tasks service and index is the actual production class.
"""

from __future__ import annotations

import json
from uuid import uuid4

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import TASK_SCHEMA_EXTENSION, TaskInterpretation, TaskOperation
from odyssey_core import create_entity
from odyssey_core.context import ContextIndex
from odyssey_core.identity_boundary import AuthenticatedActorContext, SelfBindingRepository
from odyssey_core.notes import parse_note
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.storage import VaultRepository
from odyssey_runtime import composition
from tests.core.test_reference_preflight import UnresolvedReasoner
from tests.runtime.test_temporal_user_path_e2e import ConstantEmbedder
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient


def test_environment_factory_real_tasks_interpreter_resolution_session_and_notes_ui(
    tmp_path, monkeypatch
):
    # No private user's vault, n8n or paid remote model enters this test.
    vault = tmp_path / "vault"
    runtime_root = tmp_path / "runtime"
    state = tmp_path / "state"
    pending = state / "pending"
    for path in (vault, runtime_root, state, pending):
        path.mkdir(parents=True, exist_ok=True)
    repo = VaultRepository(vault)
    from pathlib import Path

    base = json.loads((Path(__file__).resolve().parents[2] / "config/note-schema.json").read_text())
    schema = compose_application_schema(base, (TASK_SCHEMA_EXTENSION,))
    create_entity(
        repo,
        schema,
        path="self.md",
        entity_id="p4-prod-self",
        metadata={"name": "Persona autenticada", "type": "person"},
        content="",
        actor="fixture",
        now="2026-10-16T17:00:00+02:00",
    )
    create_entity(
        repo,
        schema,
        path="atlas.md",
        entity_id="p4-prod-task",
        metadata={"name": "Preparar informe Atlas", "type": "task", "status": "pending"},
        content="- Preparar informe Atlas.\n",
        actor="fixture",
        now="2026-10-16T17:00:00+02:00",
    )
    actor = AuthenticatedActorContext(str(uuid4()))
    SelfBindingRepository(state, repo, schema).bind(actor.stable_user_id, "p4-prod-self")
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
    monkeypatch.setenv("ODYSSEY_PENDING_ROOT", str(pending))
    monkeypatch.setenv("ODYSSEY_STATE_ROOT", str(state))
    monkeypatch.setenv("ODYSSEY_EMBEDDING_CACHE", str(tmp_path / "fake-embed-cache"))
    monkeypatch.setattr(composition, "FastEmbedTextEmbedder", lambda **_kwargs: embedder)
    monkeypatch.setattr(composition, "_build_contextual_reasoner", UnresolvedReasoner)
    monkeypatch.setattr(composition, "GitHistoryRecorder", lambda _root: None)

    source = "Empieza a trabajar en Preparar informe Atlas."

    class TaskInterpreter:
        model = "frozen-tasks-interpretation"
        reasoning_effort = "low"
        last_usage = None
        calls = 0

        def interpret(self, scoped_source, _prior=()):
            assert scoped_source == source
            self.calls += 1
            return TaskInterpretation(
                scoped_source,
                TaskOperation.START_WORK_SESSION,
                task_reference="Preparar informe Atlas",
            )

    task_interpreter = TaskInterpreter()
    monkeypatch.setattr(
        composition.OpenAITaskInterpreter,
        "from_environment",
        classmethod(lambda _cls: task_interpreter),
    )
    product = composition.build_runtime_from_environment()
    assert product.full_source_mutation_guard is True
    assert product.hybrid_candidate_execute is not None
    product.hybrid_candidate_execute.client = RecordedClient(
        [
            {
                "capabilities": ["tasks"],
                "reason": "single",
                "interpretation": "joint",
                "app_scopes": [],
                "self_relation_span": None,
            },
            {"only_task_semantics": True, "exactly_one_operation": True, "source_quote": source},
        ]
    )
    first = product.execute_product(source, "p4-prod-composer-task-chat", "main", actor)
    assert first["status"] == "completed", first
    assert task_interpreter.calls == 1
    detail = product.notes("detail", {"note_id": "p4-prod-task"}, actor)
    assert len(detail["work_sessions"]) == 1
    session = detail["work_sessions"][0]
    assert session["task_id"] == "p4-prod-task"
    original = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    replay = product.execute_product(source, "p4-prod-composer-task-chat", "main", actor)
    assert replay["delivery_replayed"] is True
    assert task_interpreter.calls == 1
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == original
    added = product.notes(
        "work_session_activity_add",
        {
            "session_id": session["id"],
            "text": "Probado por composición auténtica.",
            "request_id": "p4-prod-composer-ui-activity",
            "expected_revision": session["mutation"]["revision"],
            "expected_source_hash": session["mutation"]["source_hash"],
        },
        actor,
    )
    assert len(added["work_sessions"][0]["activity"]) == 1
    assert (
        sum(
            parse_note(repo.read_text(p)).metadata["type"] == "work_session"
            for p in repo.list_markdown_paths()
        )
        == 1
    )

    # Also exercise real TCP transport against this SAME production composition.
    # Still not n8n or a browser: real HTTP, domain, resolver, E3 and Markdown.
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
            ),
            {"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        status, body = response.status, json.loads(response.read())
        connection.close()
        return status, body

    try:
        status, task_page = post("/notes", {"operation": "detail", "note_id": "p4-prod-task"})
        assert status == 200
        assert len(task_page["work_sessions"]) == 1
        assert len(task_page["work_sessions"][0]["activity"]) == 1
        status, again = post(
            "/execute",
            {
                "request": source,
                "request_id": "p4-prod-composer-task-chat",
                "conversation_id": "main",
            },
        )
        assert status == 200 and again["delivery_replayed"] is True
        assert task_interpreter.calls == 1
        assert len(product.work_session_service.list_for_task("p4-prod-task")) == 1
    finally:
        http.shutdown()
        http.server_close()
        worker.join(timeout=5)
