"""Authenticated Notes API -> device-local read-only retrospective job progress."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.notes import Note, serialize_note
from odyssey_core.schema_retrospection_jobs import LocalSchemaScanError, LocalSchemaScanJobs
from odyssey_core.storage import VaultRepository
from odyssey_runtime.composition import RuntimeComposition, build_runtime_from_environment

ROOT = Path(__file__).resolve().parents[2]
ALICE = AuthenticatedActorContext("00000000-0000-4000-8000-000000000001")
BOB = AuthenticatedActorContext("00000000-0000-4000-8000-000000000002")


def runtime(tmp_path: Path) -> tuple[RuntimeComposition, VaultRepository, Path]:
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    vault.mkdir()
    state.mkdir()
    schema = json.loads((ROOT / "config/note-schema.json").read_text())
    schema["types"].append(
        {"id": "libro", "name": "Libro", "description": "Libros", "properties": [], "examples": []}
    )
    person = next(item for item in schema["types"] if item["id"] == "person")
    person["properties"].append(
        {
            "id": "profesion",
            "value_type": "string",
            "description": "Trabajo",
            "required": False,
            "filterable": True,
        }
    )
    for i in range(5):
        note = Note(
            {
                "id": f"person-{i}",
                "name": f"Person {i}",
                "type": "person",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "created_by": {"human": None, "app": "tests"},
                "updated_by": {"human": None, "app": "tests"},
                "revision": 1,
                "schema_version": 3,
                "aliases": [],
                "tags": [],
            },
            f"# Added 01-01-2026\n- He leído un libro {i}\n"
            f"<!-- odyssey:fact request=req{i} ordinal=0 -->\n",
        )
        (vault / f"{i}.md").write_text(serialize_note(note))
    repo = VaultRepository(vault)
    composition = RuntimeComposition(
        core_execute=lambda *a, **kw: None,
        refresh_indexes=lambda: None,
        notes_service=SimpleNamespace(),
        vault_repository=repo,
        canonical_schema=schema,
        user_schema_registry=object(),
        user_schema_revision=0,
        schema_scan_factory=lambda actor: LocalSchemaScanJobs(
            state_root=state, repository=repo, actor_id=actor
        ),
    )
    return composition, repo, state


def req(
    *,
    action: str = "advance",
    kind: str = "discover_type",
    target: str = "libro",
    prop: str | None = None,
    rev: int = 0,
):
    return {
        "scan_kind": kind,
        "target_type_id": target,
        "property_id": prop,
        "expected_revision": rev,
        "action": action,
    }


def test_authored_scans_advance_twenty_max_recover_and_preserve_notes(tmp_path):
    app, repo, state = runtime(tmp_path)
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    assert app.notes("schema_scan", req(action="status"), ALICE)["status"] == "not_started"
    first = app.notes("schema_scan", req(), ALICE)
    assert first == {
        "kind": "schema_scan",
        "status": "complete",
        "scanned_paths": 5,
        "eligible_notes": 5,
        "skipped_existing_values": 0,
        "legacy_sources": 0,
    }
    assert app.notes("schema_scan", req(action="status"), ALICE) == first
    assert app.notes("schema_scan", req(), ALICE) == first
    assert app.notes("schema_scan", req(action="status"), BOB)["status"] == "not_started"
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before
    records = list((state / "schema-retrospection-jobs").glob("*.json"))
    assert len(records) == 1 and "He leído" not in records[0].read_text()


def test_property_scan_counts_only_notes_missing_value(tmp_path):
    app, repo, _ = runtime(tmp_path)
    output = app.notes(
        "schema_scan", req(kind="backfill_property", target="person", prop="profesion"), ALICE
    )
    assert output["eligible_notes"] == 5
    assert output["status"] == "complete"
    assert (
        app.notes(
            "schema_scan",
            req(action="status", kind="backfill_property", target="person", prop="profesion"),
            ALICE,
        )
        == output
    )
    assert app.notes("schema_scan", req(action="status"), ALICE)["status"] == "not_started"


def test_scan_rejects_untrusted_user_stale_schema_mismatched_target_and_unavailable(tmp_path):
    app, repo, _ = runtime(tmp_path)
    with pytest.raises(ValueError, match="unavailable"):
        app.notes("schema_scan", req())
    with pytest.raises(ValueError, match="arguments"):
        app.notes("schema_scan", req(rev=1), ALICE)
    with pytest.raises(ValueError, match="request"):
        app.notes("schema_scan", {**req(), "actor_id": BOB.stable_user_id}, ALICE)
    with pytest.raises(ValueError, match="arguments"):
        app.notes("schema_scan", req(kind="erase_everything"), ALICE)
    with pytest.raises(ValueError):
        app.notes("schema_scan", req(target="../other"), ALICE)
    first = app.notes("schema_scan", req(), ALICE)
    assert first["status"] == "complete"
    (repo.root / "0.md").write_text((repo.root / "0.md").read_text() + "changed")
    with pytest.raises(LocalSchemaScanError, match="Stale"):
        app.notes("schema_scan", req(), ALICE)
    app.schema_scan_factory = None
    with pytest.raises(ValueError, match="unavailable"):
        app.notes("schema_scan", req(action="status"), ALICE)


def test_empty_vault_and_unauthorized_status_stay_nonmutating(tmp_path):
    app, repo, _ = runtime(tmp_path)
    for path in repo.list_markdown_paths():
        (repo.root / path).unlink()
    result = app.notes("schema_scan", req(), ALICE)
    assert result["status"] == "complete" and result["scanned_paths"] == 0
    with pytest.raises(ValueError, match="unavailable"):
        app.notes("schema_scan", req(action="status"), None)


def test_scan_flag_refuses_prod_before_creating_any_pending_state(tmp_path, monkeypatch):
    for key, value in {
        "ODYSSEY_USER_SCHEMA_ENABLED": "0",
        "ODYSSEY_SCHEMA_SCAN_ENABLED": "1",
        "ODYSSEY_DEPLOYMENT_ENV": "PROD",
        "ODYSSEY_PENDING_ROOT": str(tmp_path / "pending"),
        "ODYSSEY_STATE_ROOT": str(tmp_path / "state"),
        "ODYSSEY_VAULT_ROOT": str(tmp_path / "vault"),
        "ODYSSEY_RUNTIME_ROOT": str(tmp_path / "runtime"),
    }.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match="isolated DEV"):
        build_runtime_from_environment()
    assert not any(tmp_path.iterdir())


def test_api_scans_large_operational_vault_across_restarts_and_scopes(tmp_path, monkeypatch):
    """Actual Notes API returns bounded progress while compact scanner holds 28 IDs."""
    from odyssey_core import schema_large_scan_jobs
    from odyssey_core.notes import parse_note

    monkeypatch.setattr(schema_large_scan_jobs, "_LARGE_THRESHOLD", 3)
    app, repo, state = runtime(tmp_path)
    sample = parse_note(repo.read_text("0.md"))
    for i in range(5, 28):
        extra = Note(
            {**sample.metadata, "id": f"person-{i}", "name": f"Person {i}"},
            sample.content,
        )
        (repo.root / f"{i}.md").write_text(serialize_note(extra), encoding="utf-8")
    first = app.notes("schema_scan", req(), ALICE)
    assert first["status"] == "scanning"
    assert first["scanned_paths"] == first["eligible_notes"] == 20
    assert app.notes("schema_scan", req(action="status"), ALICE) == first
    assert app.notes("schema_scan", req(action="status"), BOB)["status"] == "not_started"
    second = app.notes("schema_scan", req(), ALICE)
    assert second["status"] == "complete"
    assert second["scanned_paths"] == second["eligible_notes"] == 28
    assert app.notes("schema_scan", req(action="status"), ALICE) == second
    assert app.notes("schema_scan", req(), ALICE) == second
    assert len(list((state / "schema-retrospection-jobs").glob("*.sqlite3"))) == 1
    assert not list((state / "schema-retrospection-jobs").glob("*.json"))
    (repo.root / "25.md").write_text((repo.root / "25.md").read_text() + "edited")
    with pytest.raises(LocalSchemaScanError, match="Large scan"):
        app.notes("schema_scan", req(), ALICE)
