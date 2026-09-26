"""Deterministic coverage for bounded direct Notes mutation authority."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from odyssey_core.atomic_facts import append_atomic_facts
from odyssey_core.context import ContextIndex
from odyssey_core.direct_note_mutations import DirectNoteMutationError, DirectNoteMutationService
from odyssey_core.git_history import GitHistoryResult, HistoryStatus
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import Note, parse_note, serialize_note
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-09-26T10:00:00Z"


class Embedder:
    """Provide fixed no-network vectors for the disposable Notes index."""

    model_name = "tests/direct-notes"
    model_version = "1"

    def embed_documents(self, texts):
        """Return one fixed vector per supplied text."""
        return [[1.0] for _ in texts]

    embed_queries = embed_documents


def write(vault: Path, path: str, note_id: str, name: str, body: str) -> None:
    """Write one schema-valid disposable canonical note."""
    target = vault / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        serialize_note(
            Note(
                {
                    "id": note_id,
                    "name": name,
                    "type": "person",
                    "created_at": NOW,
                    "updated_at": NOW,
                    "created_by": {"human": None, "app": "test"},
                    "updated_by": {"human": None, "app": "test"},
                    "revision": 1,
                    "schema_version": 3,
                    "aliases": [],
                    "tags": [],
                },
                body,
            )
        ),
        encoding="utf-8",
    )


def build(
    tmp_path: Path,
) -> tuple[VaultRepository, NotesQueryService, DirectNoteMutationService, dict]:
    """Build a disposable Markdown vault with its current derived Notes index."""
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    vault = tmp_path / "vault"
    vault.mkdir()
    write(
        vault,
        "people/ada.md",
        "ada",
        "Ada",
        append_atomic_facts(
            "Legacy prose.", ("Ada works at Airbus.", "Ada plays piano."), "first", (0, 1), NOW
        ),
    )
    repository = VaultRepository(vault)
    index = ContextIndex(tmp_path / "runtime" / "context.sqlite3")
    index.rebuild(repository, schema, Embedder())
    notes = NotesQueryService(repository, schema, index)
    return repository, notes, DirectNoteMutationService(repository, schema, notes, None), schema


def mutation_tokens(repository: VaultRepository, path: str) -> tuple[int, str]:
    """Return exact stale-write tokens from one disposable current note."""
    raw = repository.read_text(path)
    return parse_note(raw).metadata["revision"], hashlib.sha256(raw.encode()).hexdigest()


def test_direct_fact_delete_uses_exact_locator_and_preserves_other_facts(tmp_path: Path) -> None:
    """Delete exactly the selected atomic fact without a writer/provider or collateral removal."""
    repository, notes, mutations, _ = build(tmp_path)
    detail = notes.detail("ada")
    revision, source_hash = mutation_tokens(repository, "people/ada.md")

    result = mutations.delete_fact(
        note_id="ada",
        fact_locator=detail.atomic_facts[0][0],
        expected_revision=revision,
        expected_source_hash=source_hash,
        request_id="notes-delete-fact",
        actor="test",
        now=NOW,
    )

    body = parse_note(repository.read_text("people/ada.md")).content
    assert result.operation == "fact_deleted"
    assert "Ada works at Airbus." not in body
    assert "Ada plays piano." in body and "Legacy prose." in body


def test_direct_fact_delete_rejects_stale_state_before_mutation(tmp_path: Path) -> None:
    """Fail closed when the browser's detail projection no longer matches canonical Markdown."""
    repository, notes, mutations, _ = build(tmp_path)
    detail = notes.detail("ada")
    revision, source_hash = mutation_tokens(repository, "people/ada.md")
    repository.replace_text("people/ada.md", repository.read_text("people/ada.md") + "\n")

    with pytest.raises(DirectNoteMutationError, match="STALE_NOTE"):
        mutations.delete_fact(
            note_id="ada",
            fact_locator=detail.atomic_facts[0][0],
            expected_revision=revision,
            expected_source_hash=source_hash,
            request_id="notes-stale-fact",
            actor="test",
            now=NOW,
        )


def test_direct_fact_delete_records_the_existing_request_history_boundary(tmp_path: Path) -> None:
    """Pass the selected stable note through the ordinary request-correlated history recorder."""
    repository, notes, _, schema = build(tmp_path)
    detail = notes.detail("ada")
    revision, source_hash = mutation_tokens(repository, "people/ada.md")

    class History:
        """Record the Core history call without adding a second persistence mechanism."""

        def __init__(self) -> None:
            self.recorded: dict | None = None

        def begin(self, request_id: str) -> object:
            """Return one opaque existing-history snapshot."""
            assert request_id == "notes-history"
            return object()

        def record(self, **kwargs: object) -> GitHistoryResult:
            """Capture the exact existing history arguments and report a commit."""
            self.recorded = kwargs
            return GitHistoryResult(HistoryStatus.COMMITTED, commit_sha="a" * 40)

    history = History()
    mutations = DirectNoteMutationService(repository, schema, notes, history)
    result = mutations.delete_fact(
        note_id="ada",
        fact_locator=detail.atomic_facts[0][0],
        expected_revision=revision,
        expected_source_hash=source_hash,
        request_id="notes-history",
        actor="test",
        now=NOW,
    )

    assert result.history.status is HistoryStatus.COMMITTED
    assert history.recorded is not None
    assert history.recorded["affected_stable_note_ids"] == ("ada",)


def test_direct_note_delete_refuses_incoming_reference_then_soft_deletes_when_eligible(
    tmp_path: Path,
) -> None:
    """Keep referring Notes intact and retire only a backlink-free selected Note."""
    repository, notes, mutations, schema = build(tmp_path)
    write(tmp_path / "vault", "people/source.md", "source", "Source", "See [[people/ada|Ada]].")
    notes.context_index.rebuild(repository, schema, Embedder())
    revision, source_hash = mutation_tokens(repository, "people/ada.md")

    with pytest.raises(DirectNoteMutationError, match="INCOMING_REFERENCES"):
        mutations.delete_note(
            note_id="ada",
            expected_revision=revision,
            expected_source_hash=source_hash,
            request_id="notes-backlink-refusal",
            actor="test",
            now=NOW,
        )
    assert "[[people/ada|Ada]]" in repository.read_text("people/source.md")

    write(tmp_path / "vault", "people/source.md", "source", "Source", "No reference.")
    notes.context_index.rebuild(repository, schema, Embedder())
    result = mutations.delete_note(
        note_id="ada",
        expected_revision=revision,
        expected_source_hash=source_hash,
        request_id="notes-delete-note",
        actor="test",
        now=NOW,
    )
    assert result.operation == "note_deleted"
    assert parse_note(repository.read_text("people/ada.md")).metadata["deleted"] is True
