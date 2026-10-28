"""Authenticated Notes -> confirmed schema -> Core/E3 + Git on synthetic vault."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_core.git_history import GitHistoryRecorder
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.notes import Note, parse_note, serialize_note
from odyssey_core.schema_auto_backfill import AutomaticPropertyBackfill
from odyssey_core.storage import VaultRepository
from odyssey_runtime.composition import RuntimeComposition, build_runtime_from_environment
from odyssey_runtime.schema_backfill_interpreter import SemanticPropertyInterpreter
from odyssey_runtime.schema_backfill_jobs import LocalBackfillJob
from odyssey_runtime.user_schema_registry import SchemaConfirmation, UserSchemaRegistry

ROOT = Path(__file__).resolve().parents[2]
ALICE = AuthenticatedActorContext("00000000-0000-4000-8000-000000000001")
BOB = AuthenticatedActorContext("00000000-0000-4000-8000-000000000002")


def fixture(tmp_path: Path):
    vault, state = tmp_path / "vault", tmp_path / "state"
    vault.mkdir()
    state.mkdir()
    base = json.loads((ROOT / "config/note-schema.json").read_text())
    reg = UserSchemaRegistry(state, base)
    change = {
        "operation": "add_property",
        "type_id": "person",
        "property": {"id": "profesion", "value_type": "string", "description": "Profesión actual"},
    }
    proposed = reg.preview(change, expected_revision=0)
    published = reg.publish(
        change,
        SchemaConfirmation(
            ALICE.stable_user_id,
            "confirmed-prop",
            0,
            proposed.proposal_hash,
        ),
    )
    assert published.next_revision == 1
    revision, schema = reg.snapshot()
    for i, body in enumerate(("Profesión: médica", "Ana trabaja como profesora.")):
        note = Note(
            {
                "id": f"persona-{i}",
                "name": f"Persona {i}",
                "type": "person",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "created_by": {"human": None, "app": "test"},
                "updated_by": {"human": None, "app": "test"},
                "revision": 1,
                "schema_version": 3,
                "aliases": [],
                "tags": [],
            },
            f"# Added 26-10-2026\n- {body}\n<!-- odyssey:fact request=req{i} ordinal=0 -->\n",
        )
        (vault / f"{i}.md").write_text(serialize_note(note))
    for args in [
        ["init", "-q"],
        ["add", "."],
        [
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@localhost",
            "commit",
            "-m",
            "baseline",
            "-q",
        ],
    ]:
        subprocess.run(["git", *args], cwd=vault, capture_output=True, check=True, timeout=10)
    repo = VaultRepository(vault)
    writer = AutomaticPropertyBackfill(
        repository=repo,
        schema=schema,
        history=GitHistoryRecorder(vault),
    )
    app = RuntimeComposition(
        core_execute=lambda *a, **kw: None,
        refresh_indexes=lambda: None,
        notes_service=SimpleNamespace(),
        user_schema_registry=reg,
        user_schema_revision=revision,
        canonical_schema=schema,
        vault_repository=repo,
        schema_backfill_factory=lambda actor: LocalBackfillJob(
            state_root=state,
            repository=repo,
            writer=writer,
            actor_id=actor,
        ),
    )
    return app, repo, state


def request(action="status", revision=1):
    return {
        "target_type_id": "person",
        "property_id": "profesion",
        "expected_revision": revision,
        "action": action,
    }


def test_approved_actor_auto_enriches_one_note_and_reports_deferred_without_llm(tmp_path):
    app, repo, state = fixture(tmp_path)
    assert app.notes("schema_backfill", request(), ALICE) == {
        "kind": "schema_backfill",
        "status": "not_started",
    }
    staged = app.notes("schema_backfill", request("stage"), ALICE)
    assert staged["total"] == 2 and staged["pending"] == 2
    assert app.notes("schema_backfill", request("advance"), ALICE)["updated"] == 1
    done = app.notes("schema_backfill", request("advance"), ALICE)
    assert done["status"] == "awaiting_ai" and done["deferred"] == 1
    assert app.notes("schema_backfill", request("advance"), ALICE) == done
    assert parse_note(repo.read_text("0.md")).metadata["profesion"] == "médica"
    assert parse_note(repo.read_text("1.md")).metadata.get("profesion") is None
    stored = next((state / "schema-backfill-jobs").glob("*.json")).read_text()
    assert "médica" not in stored and "profesora" not in stored


def test_approved_semantic_evidence_uses_same_core_writer_and_git(tmp_path):
    """Model-backed path remains actor-approved; provider never writes Markdown."""
    app, repo, state = fixture(tmp_path)

    class ReviewedGateway:
        def __init__(self):
            self.calls = []

        def _complete(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return {
                    "decision": "SET",
                    "locator": "req1:0",
                    "quote": "Ana trabaja como profesora.",
                    "value": "profesora",
                }
            return {
                "verdict": "APPROVE",
                "reason": "ENTAILED_CURRENT",
                "locator": "req1:0",
                "quote": "Ana trabaja como profesora.",
                "value": "profesora",
            }

    provider = ReviewedGateway()
    app.schema_backfill_interpreter = SemanticPropertyInterpreter(provider)
    app.schema_backfill_call_limit = 6
    before = repo.read_text("1.md")
    with pytest.raises(ValueError, match="approved"):
        app.notes("schema_backfill", request("stage"), BOB)
    assert not provider.calls and repo.read_text("1.md") == before

    assert app.notes("schema_backfill", request("stage"), ALICE)["pending"] == 2
    assert app.notes("schema_backfill", request("advance"), ALICE)["updated"] == 1
    assert provider.calls == []  # Explicit values use no extra model call.
    first_pass = app.notes("schema_backfill", request("advance"), ALICE)
    assert first_pass["updated"] == 1 and first_pass["deferred"] == 1
    assert first_pass["status"] == "awaiting_ai"
    assert first_pass["reserved_calls"] == 0
    assert len(provider.calls) == 0  # The scan's auto-pass never uses GPT.
    staged = app.notes("schema_backfill", request("stage_followup"), ALICE)
    assert staged["phase"] == "semantic_followup"
    assert staged["total"] == staged["pending"] == 1
    finished = app.notes("schema_backfill", request("advance_followup"), ALICE)
    assert finished["updated"] == 1 and finished["status"] == "in_progress"
    assert finished["reserved_calls"] == 2 and finished["call_limit"] == 6
    assert len(provider.calls) == 2
    assert [call["name"] for call in provider.calls] == [
        "odyssey_schema_backfill_interpret_v1",
        "odyssey_schema_backfill_review_v1",
    ]
    assert parse_note(repo.read_text("1.md")).metadata["profesion"] == "profesora"
    completed = app.notes("schema_backfill", request("advance_followup"), ALICE)
    assert completed["status"] == "complete" and completed["reserved_calls"] == 2
    assert app.notes("schema_backfill", request("advance_followup"), ALICE) == completed
    assert len(provider.calls) == 2  # Replay never reissues paid model calls.
    assert (
        sum("profesora" in p.read_text() for p in (state / "schema-backfill-jobs").glob("*.json"))
        == 0
    )


def test_cannot_write_using_other_actor_revision_or_browser_authority(tmp_path):
    app, repo, _ = fixture(tmp_path)
    before = [repo.read_text(path) for path in repo.list_markdown_paths()]
    for caller, payload in [
        (BOB, request("stage")),
        (None, request("stage")),
        (ALICE, request("stage", revision=0)),
        (ALICE, {**request("stage"), "actor_id": ALICE.stable_user_id}),
        (ALICE, {**request("stage"), "approved": True}),
        (ALICE, {**request("advance"), "request_id": "forged"}),
        (ALICE, {**request("stage"), "property_id": "name"}),
        (ALICE, {**request("stage"), "property_id": "profesion2"}),
        (ALICE, {**request("stage"), "action": "delete"}),
    ]:
        with pytest.raises(ValueError):
            app.notes("schema_backfill", payload, caller)
    assert [repo.read_text(path) for path in repo.list_markdown_paths()] == before
    app.schema_backfill_factory = None
    with pytest.raises(ValueError, match="unavailable"):
        app.notes("schema_backfill", request("stage"), ALICE)


def test_backfill_requires_explicit_dev_and_is_rejected_before_touching_roots(
    tmp_path, monkeypatch
):
    combos = [
        {"ODYSSEY_SCHEMA_BACKFILL_ENABLED": "1", "ODYSSEY_DEPLOYMENT_ENV": "PROD"},
        {"ODYSSEY_SCHEMA_BACKFILL_ENABLED": "1", "ODYSSEY_USER_SCHEMA_ENABLED": "0"},
        {"ODYSSEY_SCHEMA_BACKFILL_ENABLED": "1", "ODYSSEY_SCHEMA_SCAN_ENABLED": "0"},
        {"ODYSSEY_SCHEMA_BACKFILL_ENABLED": "1", "ODYSSEY_SCHEMA_CONFIRM_ENABLED": "0"},
        {"ODYSSEY_SCHEMA_BACKFILL_ENABLED": "maybe"},
        {"ODYSSEY_SCHEMA_SEMANTIC_BACKFILL_ENABLED": "maybe"},
        {"ODYSSEY_SCHEMA_SEMANTIC_BACKFILL_ENABLED": "1"},
        {"ODYSSEY_SCHEMA_SEMANTIC_BACKFILL_ENABLED": "1", "ODYSSEY_SCHEMA_BACKFILL_ENABLED": "1"},
        {
            "ODYSSEY_SCHEMA_SEMANTIC_BACKFILL_ENABLED": "1",
            "ODYSSEY_SCHEMA_BACKFILL_ENABLED": "1",
            "ODYSSEY_DEPLOYMENT_ENV": "PROD",
        },
        {"ODYSSEY_SCHEMA_BACKFILL_ENABLED": "1", "ODYSSEY_VAULT_ROOT": "/data/odyssey/vault"},
    ]
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    for i, extras in enumerate(combos):
        root = tmp_path / f"isolated{i}"
        defaults = {
            "ODYSSEY_SCHEMA_BACKFILL_ENABLED": "0",
            "ODYSSEY_SCHEMA_SEMANTIC_BACKFILL_ENABLED": "0",
            "ODYSSEY_DEPLOYMENT_ENV": "DEV",
            "ODYSSEY_USER_SCHEMA_ENABLED": "1",
            "ODYSSEY_SCHEMA_SCAN_ENABLED": "1",
            "ODYSSEY_SCHEMA_CONFIRM_ENABLED": "1",
            "ODYSSEY_PENDING_ROOT": str(root / "state" / "pending"),
            "ODYSSEY_STATE_ROOT": str(root / "state"),
            "ODYSSEY_VAULT_ROOT": str(root / "vault"),
            "ODYSSEY_RUNTIME_ROOT": str(root / "runtime"),
        }
        for key, value in (defaults | extras).items():
            monkeypatch.setenv(key, value)
        with pytest.raises(ValueError, match="backfill|schema scan"):
            build_runtime_from_environment()
        assert not root.exists()


def _semantic_enabled_env(monkeypatch, root):
    """Synthetic, isolated DEV roots: never the running host's vault or secrets."""
    settings = {
        "ODYSSEY_DEPLOYMENT_ENV": "DEV",
        "ODYSSEY_USER_SCHEMA_ENABLED": "1",
        "ODYSSEY_SCHEMA_SCAN_ENABLED": "1",
        "ODYSSEY_SCHEMA_CONFIRM_ENABLED": "1",
        "ODYSSEY_SCHEMA_BACKFILL_ENABLED": "1",
        "ODYSSEY_SCHEMA_SEMANTIC_BACKFILL_ENABLED": "1",
        "ODYSSEY_SCHEMA_SEMANTIC_CALL_LIMIT": "6",
        "ODYSSEY_SCHEMA_ASSISTANT_ENABLED": "0",
        "ODYSSEY_VAULT_ROOT": str(root / "vault"),
        "ODYSSEY_STATE_ROOT": str(root / "state"),
        "ODYSSEY_PENDING_ROOT": str(root / "state" / "pending"),
        "ODYSSEY_RUNTIME_ROOT": str(root / "runtime"),
        "ODYSSEY_EMBEDDING_CACHE": str(root / "cache"),
        "OPENAI_API_KEY": "synthetic-placeholder-never-used",
    }
    for key, value in settings.items():
        monkeypatch.setenv(key, value)


def test_semantic_enabled_environment_wires_trusted_interpreter(tmp_path, monkeypatch):
    from odyssey_runtime import composition

    root = tmp_path / "isolated-accepted"
    _semantic_enabled_env(monkeypatch, root)

    class FakeStructuredGateway:
        def _complete(self, **kwargs):
            raise AssertionError("Model must never be called at runtime construction")

    gateway = FakeStructuredGateway()
    monkeypatch.setattr(
        composition.OpenAIConversationGateway,
        "from_environment",
        classmethod(lambda cls: gateway),
    )
    seen = {}

    def build_under_lease(*, schema_backfill_interpreter, schema_backfill_call_limit):
        seen["interpreter"] = schema_backfill_interpreter
        assert schema_backfill_call_limit == 6
        assert (root / "state").exists()
        return RuntimeComposition(
            core_execute=lambda *_args, **_kwargs: None,
            refresh_indexes=lambda: None,
            schema_backfill_interpreter=schema_backfill_interpreter,
            schema_backfill_call_limit=schema_backfill_call_limit,
        )

    monkeypatch.setattr(composition, "_build_runtime_from_environment_unlocked", build_under_lease)
    result = build_runtime_from_environment()
    assert isinstance(result.schema_backfill_interpreter, SemanticPropertyInterpreter)
    assert result.schema_backfill_interpreter.gateway is gateway
    assert seen["interpreter"] is result.schema_backfill_interpreter


def test_semantic_missing_or_invalid_host_allowance_precedes_state_creation(tmp_path, monkeypatch):
    root = tmp_path / "isolated-invalid-budget"
    _semantic_enabled_env(monkeypatch, root)
    for raw in ("", "0", "37", "-1", "5.0", "unbounded", "٣"):
        monkeypatch.setenv("ODYSSEY_SCHEMA_SEMANTIC_CALL_LIMIT", raw)
        with pytest.raises(ValueError, match="host call allowance"):
            build_runtime_from_environment()
        assert not root.exists()


def test_semantic_provider_construction_failure_precedes_state_creation(tmp_path, monkeypatch):
    from odyssey_runtime import composition

    root = tmp_path / "isolated-provider-failure"
    _semantic_enabled_env(monkeypatch, root)

    def unavailable_provider(_cls):
        raise RuntimeError("provider SDK unavailable before state creation")

    monkeypatch.setattr(
        composition.OpenAIConversationGateway,
        "from_environment",
        classmethod(unavailable_provider),
    )
    with pytest.raises(RuntimeError, match="provider SDK unavailable"):
        build_runtime_from_environment()
    assert not root.exists()


def test_real_local_http_adapter_accepts_confirmed_backfill_and_writes_markdown(tmp_path):
    """Real HTTP adapter + registry + Core/E3 + Git, without n8n or model mocks."""
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer
    from threading import Thread

    from odyssey_runtime.server import _handler_for

    app, repo, _ = fixture(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(app))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def post(actor, action, **extra):
        connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        body = {
            "operation": "schema_backfill",
            **request(action),
            **extra,
            "authenticated_actor": {"stable_user_id": actor.stable_user_id},
        }
        connection.request(
            "POST",
            "/notes",
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        status = response.status
        result = json.loads(response.read())
        connection.close()
        return status, result

    try:
        unauthorized, denied = post(BOB, "stage")
        assert unauthorized == 400 and "error" in denied
        before = repo.read_text("0.md")
        malformed, rejected = post(ALICE, "stage", note_id="forged-note")
        assert malformed == 400 and "error" in rejected
        assert repo.read_text("0.md") == before
        status, staged = post(ALICE, "stage")
        assert status == 200 and staged["pending"] == 2
        status, progress = post(ALICE, "advance")
        assert status == 200 and progress["updated"] == 1
        status, complete = post(ALICE, "advance")
        assert status == 200 and complete["status"] == "awaiting_ai"
        assert complete["deferred"] == 1
        assert parse_note(repo.read_text("0.md")).metadata["profesion"] == "médica"
        assert parse_note(repo.read_text("1.md")).metadata.get("profesion") is None
        status, finished = post(ALICE, "advance")
        assert status == 200 and finished == complete
        assert (
            subprocess.check_output(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=repo.root,
                text=True,
            ).strip()
            == "2"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_user_created_type_property_enriches_without_person_specific_routing(tmp_path):
    """Generic workflow: new Book type, later custom attribute, then Core Git write."""
    app, repo, _ = fixture(tmp_path)
    reg = app.user_schema_registry
    book_change = {
        "operation": "add_type",
        "type": {
            "id": "book",
            "name": "Libro",
            "description": "An identifiable written work.",
            "examples": ["A novel"],
            "properties": [],
        },
    }
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    proposal = reg.preview(book_change, expected_revision=1)
    reg.publish(
        book_change,
        SchemaConfirmation(ALICE.stable_user_id, "create-book", 1, proposal.proposal_hash),
    )
    genre_change = {
        "operation": "add_property",
        "type_id": "book",
        "property": {
            "id": "genre",
            "value_type": "string",
            "description": "Genre of the book, when explicitly known.",
        },
    }
    proposal = reg.preview(genre_change, expected_revision=2)
    reg.publish(
        genre_change,
        SchemaConfirmation(ALICE.stable_user_id, "approve-genre", 2, proposal.proposal_hash),
    )
    revision, schema = reg.snapshot()
    assert revision == 3
    from odyssey_core.notes import validate_note

    book = Note(
        {
            **parse_note(before["0.md"]).metadata,
            "id": "libro-sintetico",
            "name": "Libro sintético",
            "type": "book",
        },
        "# Added 26-10-2026\n- genre: novela\n<!-- odyssey:fact request=book-one ordinal=0 -->\n",
    )
    validate_note(book, schema)
    (repo.root / "book.md").write_text(serialize_note(book))
    subprocess.run(["git", "add", "book.md"], cwd=repo.root, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@localhost",
            "commit",
            "-q",
            "-m",
            "synthetic-book-baseline",
        ],
        cwd=repo.root,
        check=True,
        capture_output=True,
    )
    writer = AutomaticPropertyBackfill(
        repository=repo,
        schema=schema,
        history=GitHistoryRecorder(repo.root),
    )
    app.user_schema_revision = revision
    app.canonical_schema = schema
    app.schema_backfill_factory = lambda actor: LocalBackfillJob(
        state_root=tmp_path / "state", repository=repo, writer=writer, actor_id=actor
    )
    payload = {
        "target_type_id": "book",
        "property_id": "genre",
        "expected_revision": revision,
        "action": "stage",
    }
    staged = app.notes("schema_backfill", payload, ALICE)
    assert staged["total"] == staged["pending"] == 1
    result = app.notes("schema_backfill", {**payload, "action": "advance"}, ALICE)
    assert result["updated"] == 1 and result["status"] == "complete"
    updated = parse_note(repo.read_text("book.md"))
    assert updated.metadata["genre"] == "novela" and updated.metadata["revision"] == 2
    assert all(repo.read_text(path) == text for path, text in before.items())
    with pytest.raises(ValueError, match="not approved"):
        app.notes("schema_backfill", payload, BOB)
    with pytest.raises(ValueError, match="not approved"):
        app.notes("schema_backfill", {**payload, "target_type_id": "task"}, ALICE)


def test_http_backfill_postwrite_index_failure_is_recoverable_conflict(tmp_path):
    """Genuine local HTTP: persisted Core/Git write must not look like invalid input."""
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer
    from threading import Thread

    from odyssey_runtime.server import _handler_for

    app, repo, state = fixture(tmp_path)
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    writer = AutomaticPropertyBackfill(
        repository=repo,
        schema=app.canonical_schema,
        history=GitHistoryRecorder(repo.root),
    )

    def broken_refresh(_note_id):
        raise RuntimeError("private synthetic index failure")

    app.schema_backfill_factory = lambda actor: LocalBackfillJob(
        state_root=state,
        repository=repo,
        writer=writer,
        actor_id=actor,
        on_updated=broken_refresh,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(app))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def post(action: str):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        body = {
            "operation": "schema_backfill",
            **request(action),
            "authenticated_actor": {"stable_user_id": ALICE.stable_user_id},
        }
        connection.request(
            "POST",
            "/notes",
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        status, content = response.status, json.loads(response.read())
        connection.close()
        return status, content

    try:
        assert post("stage")[0] == 200
        code, response = post("advance")
        assert code == 409
        assert response == {"error": "SCHEMA_BACKFILL_OUTCOME_UNVERIFIED"}
        assert "private" not in json.dumps(response)
        assert app.notes("schema_backfill", request("status"), ALICE)["status"] == "attention"
        assert parse_note(repo.read_text("0.md")).metadata["profesion"] == "médica"
        assert repo.read_text("1.md") == before["1.md"]
        commits_before = subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"], cwd=repo.root, text=True
        ).strip()
        assert commits_before == "2"
        app.schema_backfill_factory = lambda actor: LocalBackfillJob(
            state_root=state,
            repository=repo,
            writer=writer,
            actor_id=actor,
            on_updated=lambda _note_id: None,
        )
        code, reconciled = post("advance")
        assert code == 200 and reconciled["updated"] == 1
        assert reconciled["pending"] == 1
        assert (
            subprocess.check_output(
                ["git", "rev-list", "--count", "HEAD"], cwd=repo.root, text=True
            ).strip()
            == commits_before
        )
        assert all(repo.read_text(path) == before[path] for path in ("1.md",))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_backfill_refreshes_real_local_index_before_filtered_notes_readback(tmp_path):
    """Canonical Markdown and a rebuilt local index agree after automatic writes."""
    from odyssey_core.context import ContextFilter, ContextIndex
    from odyssey_core.note_queries import NotesQueryService
    from odyssey_runtime.composition import DerivedIndexRefreshCoordinator

    app, repo, state = fixture(tmp_path)
    schema = app.canonical_schema

    class LocalEmbedder:
        model_name = "tests/backfill-local"
        model_version = "1"

        def embed_documents(self, texts):
            return [[1.0, 0.0] for _ in texts]

        def embed_queries(self, texts):
            return self.embed_documents(texts)

    embedder = LocalEmbedder()
    index = ContextIndex(tmp_path / "derived" / "context.sqlite3")
    assert index.rebuild(repo, schema, embedder) == 2
    notes = NotesQueryService(repo, schema, index)
    condition = [ContextFilter("profesion", "eq", "médica")]
    assert notes.query(filters=condition).total == 0
    refreshes = []

    def refresh(note_ids):
        refreshes.append(tuple(note_ids))
        index.refresh_notes(repo, schema, embedder, note_ids=note_ids)

    coordinator = DerivedIndexRefreshCoordinator(refresh)
    writer = AutomaticPropertyBackfill(
        repository=repo, schema=schema, history=GitHistoryRecorder(repo.root)
    )
    app.schema_backfill_factory = lambda actor: LocalBackfillJob(
        state_root=state,
        repository=repo,
        writer=writer,
        actor_id=actor,
        on_updated=lambda note_id: coordinator.schedule((note_id,)),
    )
    assert app.notes("schema_backfill", request("stage"), ALICE)["pending"] == 2
    assert app.notes("schema_backfill", request("advance"), ALICE)["updated"] == 1
    coordinator.wait_until_clean()
    page = notes.query(filters=condition)
    assert page.total == 1
    assert [item.id for item in page.items] == ["persona-0"]
    assert page.items[0].properties["profesion"] == "médica"
    assert notes.detail("persona-0").note.properties["profesion"] == "médica"
    assert refreshes == [("persona-0",)]


def test_real_backfill_batches_index_refresh_but_reader_sees_all_properties(tmp_path):
    """Six E3/Git commits reconcile context plus semantic in one derived batch."""
    import hashlib
    import sqlite3

    from odyssey_core.context import ContextFilter, ContextIndex
    from odyssey_core.note_queries import NotesQueryService
    from odyssey_core.semantic import SemanticEntityIndex
    from odyssey_core.verified_source_inventory import verified_context_source_inventory
    from odyssey_runtime.composition import DerivedIndexRefreshCoordinator
    from odyssey_runtime.index_startup import p4_indexes_reusable
    from tests.runtime.test_schema_backfill_jobs import ACTOR, NOW, setup

    state, repo, writer = setup(tmp_path, ["Profesión: médica"] * 6)
    schema = writer.schema

    class LocalEmbedder:
        model_name = "tests/batched-index"
        model_version = "1"

        def embed_documents(self, texts):
            return [[1.0, 0.0] for _ in texts]

        def embed_queries(self, texts):
            return self.embed_documents(texts)

    embedder = LocalEmbedder()
    index = ContextIndex(tmp_path / "derived" / "context.sqlite3")
    index.rebuild(repo, schema, embedder)
    semantic = SemanticEntityIndex(tmp_path / "derived" / "semantic.sqlite3")
    semantic.rebuild(repo, schema, embedder)
    refreshes = []

    def refresh(note_ids):
        refreshes.append(tuple(note_ids))
        index.refresh_notes(repo, schema, embedder, note_ids=note_ids)
        inventory = verified_context_source_inventory(repo, schema, index.path)
        semantic.refresh_notes(
            repo, schema, embedder, note_ids=note_ids, verified_inventory=inventory
        )

    coordinator = DerivedIndexRefreshCoordinator(
        refresh, backfill_window_s=5, backfill_flush_threshold=8
    )
    worker = LocalBackfillJob(
        state_root=state,
        repository=repo,
        writer=writer,
        actor_id="synthetic",
        on_updated=lambda note_id: coordinator.schedule_backfill((note_id,)),
    )
    assert worker.stage(job_id="batch", type_id="person", property_id="profesion")["pending"] == 6
    for count in range(1, 7):
        receipt = worker.advance(
            job_id="batch",
            type_id="person",
            property_id="profesion",
            actor=ACTOR,
            now=NOW,
        )
        assert receipt["updated"] == count
    assert not refreshes, "Derived index work should coalesce without blocking E3/Git"
    # If the process dies now, bootstrap MUST reject the stale indexes and
    # rebuild from physical canonical Markdown instead of trusting a lost queue.
    assert not p4_indexes_reusable(repo, schema, embedder, index, semantic, {})
    coordinator.wait_until_clean()
    assert p4_indexes_reusable(repo, schema, embedder, index, semantic, {})
    assert refreshes == [tuple(f"persona-{i}" for i in range(6))]
    results = NotesQueryService(repo, schema, index).query(
        filters=[ContextFilter("profesion", "eq", "médica")], page_size=20
    )
    assert results.total == 6
    assert all(
        parse_note(repo.read_text(f"{i}.md")).metadata["profesion"] == "médica" for i in range(6)
    )
    with sqlite3.connect(semantic.path) as connection:
        indexed_hashes = dict(connection.execute("SELECT id,source_hash FROM notes"))
    assert indexed_hashes == {
        f"persona-{i}": hashlib.sha256(repo.read_text(f"{i}.md").encode()).hexdigest()
        for i in range(6)
    }
    commits = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=repo.root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert commits.stdout.strip() == "7"  # baseline + 6 independently undoable commits


def test_backfill_batches_all_four_indexes_with_real_task_and_event_notes(tmp_path):
    """The four production-shaped index roles agree after three protected commits."""
    from benchmarks.indexing.probe_schema_backfill_batches import run_sample

    result = run_sample(tmp_path, 28, 3, with_app_indexes=True)
    assert result["vault_notes"] == 28
    assert result["eligible_people"] == 26
    assert result["app_indexes_enabled"] == ["tasks", "events"]
    assert result["semantic_enabled"] is True
    assert result["refresh_calls"] == 1
    assert result["batch_sizes"] == [3]
    assert result["filtered_query_count"] == 3
    assert result["git_commits"] == 5  # two baseline commits and one per E3 write


def test_confirmed_notes_api_routes_large_corpus_to_bounded_campaign(tmp_path, monkeypatch):
    """No new UI action/permission: same actor approval, independently scoped segments."""
    from odyssey_core import schema_retrospection
    from odyssey_core.notes import parse_note
    from odyssey_runtime import schema_backfill_campaign

    app, repo, state = fixture(tmp_path)
    monkeypatch.setattr(schema_retrospection, "_MAX_PROGRESS_IDS", 3)
    monkeypatch.setattr(schema_backfill_campaign, "_DEFAULT_SEGMENT_SIZE", 2)
    sample = parse_note(repo.read_text("0.md"))
    for i in range(2, 7):
        note = Note(
            {**sample.metadata, "id": f"persona-{i}", "name": f"Persona {i}"},
            "# Added 26-10-2026\n- Profesión: médica\n<!-- odyssey:fact request=req0 ordinal=0 -->\n",
        )
        (repo.root / f"{i}.md").write_text(serialize_note(note), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo.root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@localhost",
            "commit",
            "-qm",
            "extend-synthetic-vault",
        ],
        cwd=repo.root,
        check=True,
    )
    assert app.notes("schema_backfill", request(), ALICE)["status"] == "not_started"
    staged = app.notes("schema_backfill", request("stage"), ALICE)
    assert staged["pending"] == 2 and staged["total"] == 2
    for unauthorized, payload in [
        (BOB, request("advance")),
        (ALICE, {**request("advance"), "property_id": "otro"}),
        (ALICE, request("advance", revision=0)),
    ]:
        with pytest.raises(ValueError):
            app.notes("schema_backfill", payload, unauthorized)
    result = None
    for _ in range(15):
        result = app.notes("schema_backfill", request("advance"), ALICE)
        if result["finished"]:
            break
    assert result is not None and result["finished"]
    assert result["total"] == 7
    assert result["updated"] == 6
    assert result["deferred"] == 1
    assert result["status"] == "awaiting_ai"
    assert app.notes("schema_backfill", request("status"), ALICE) == result
    for i in range(2, 7):
        assert parse_note(repo.read_text(f"{i}.md")).metadata["profesion"] == "médica"
    assert len(list((state / "schema-backfill-jobs").glob("*.campaign.json"))) == 1


@pytest.mark.parametrize("force_campaign", [False, True])
def test_notes_actor_explicit_semantic_followup_preserves_sealed_original(
    tmp_path, monkeypatch, force_campaign
):
    """The public Notes API cannot replay the old job or select new candidates."""
    from odyssey_core import schema_retrospection as scan_limits

    app, repo, state = fixture(tmp_path)
    if force_campaign:
        monkeypatch.setattr(scan_limits, "_MAX_PROGRESS_IDS", 1)
    assert app.notes("schema_backfill", request("stage"), ALICE)["pending"] >= 1
    for _ in range(7):
        original = app.notes("schema_backfill", request("advance"), ALICE)
        if original["status"] == "awaiting_ai" and (
            original.get("finished") is True or "finished" not in original
        ):
            break
    assert original["updated"] == 1 and original["deferred"] == 1
    old_receipts = {f.name: f.read_bytes() for f in (state / "schema-backfill-jobs").glob("*.json")}
    original_md = repo.read_text("1.md")
    assert "profesion" not in parse_note(original_md).metadata

    class Gateway:
        def __init__(self):
            self.calls = []

        def _complete(self, **kwargs):
            self.calls.append(kwargs)
            common = {
                "locator": "req1:0",
                "quote": "Ana trabaja como profesora.",
                "value": "profesora",
            }
            if len(self.calls) == 1:
                return {"decision": "SET", **common}
            return {"verdict": "APPROVE", "reason": "ENTAILED_CURRENT", **common}

    gateway = Gateway()
    with pytest.raises(ValueError, match="enabled trusted model"):
        app.notes("schema_backfill", request("stage_followup"), ALICE)
    app.schema_backfill_interpreter = SemanticPropertyInterpreter(gateway)
    app.schema_backfill_call_limit = 4

    assert app.notes("schema_backfill", request("status_followup"), ALICE) == {
        "kind": "schema_backfill",
        "status": "not_started",
    }
    with pytest.raises(ValueError, match="approved"):
        app.notes("schema_backfill", request("stage_followup"), BOB)
    stage = app.notes("schema_backfill", request("stage_followup"), ALICE)
    assert stage["phase"] == "semantic_followup"
    assert stage["pending"] == stage["total"] == 1
    assert stage["reserved_calls"] == 0
    assert repo.read_text("1.md") == original_md
    for _ in range(7):
        done = app.notes("schema_backfill", request("advance_followup"), ALICE)
        if done["finished"]:
            break
    assert done["status"] == "complete" and done["updated"] == 1
    assert done["reserved_calls"] == 2 and done["call_limit"] == 4
    assert len(gateway.calls) == 2
    assert parse_note(repo.read_text("1.md")).metadata["profesion"] == "profesora"
    assert app.notes("schema_backfill", request("advance_followup"), ALICE) == done
    assert len(gateway.calls) == 2
    assert app.notes("schema_backfill", request("status"), ALICE)["deferred"] == 1
    after = {
        f.name: f.read_bytes()
        for f in (state / "schema-backfill-jobs").glob("*.json")
        if f.name in old_receipts
    }
    assert after == old_receipts


def test_http_provider_failure_is_precise_pause_not_unknown_write(tmp_path):
    """No E3 write intent occurred: return a truthful semantic pause code."""
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer
    from threading import Thread

    from odyssey_runtime.server import _handler_for

    app, repo, _state = fixture(tmp_path)

    class FailedGateway:
        calls = 0

        def _complete(self, **_kwargs):
            self.calls += 1
            raise RuntimeError("synthetic secret diagnostic, do not echo")

    gateway = FailedGateway()
    app.schema_backfill_interpreter = SemanticPropertyInterpreter(gateway)
    app.schema_backfill_call_limit = 4
    before = repo.read_text("1.md")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(app))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def post(action):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        payload = {
            "operation": "schema_backfill",
            **request(action),
            "authenticated_actor": {"stable_user_id": ALICE.stable_user_id},
        }
        connection.request(
            "POST",
            "/notes",
            body=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        output = response.status, json.loads(response.read())
        connection.close()
        return output

    try:
        assert post("stage")[0] == 200
        assert post("advance")[1]["updated"] == 1
        first = post("advance")
        assert first[0] == 200 and first[1]["status"] == "awaiting_ai"
        assert gateway.calls == 0  # Never call model in first pass.
        assert post("stage_followup")[0] == 200
        code, error = post("advance_followup")
        assert code == 409
        assert error == {"error": "SCHEMA_BACKFILL_SEMANTIC_PAUSED"}
        assert "secret" not in json.dumps(error)
        assert repo.read_text("1.md") == before
        state = post("status_followup")[1]
        assert state["deferred"] == 1 and state["reserved_calls"] == 1
        assert post("advance_followup")[1]["status"] == "awaiting_ai"
        assert gateway.calls == 1
        assert repo.read_text("1.md") == before
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
