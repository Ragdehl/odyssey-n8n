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
        {"ODYSSEY_SCHEMA_BACKFILL_ENABLED": "1", "ODYSSEY_VAULT_ROOT": "/data/odyssey/vault"},
    ]
    for i, extras in enumerate(combos):
        root = tmp_path / f"isolated{i}"
        defaults = {
            "ODYSSEY_SCHEMA_BACKFILL_ENABLED": "0",
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
