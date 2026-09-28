"""Deterministic coverage for bounded direct Notes mutation authority."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from odyssey_core import direct_note_mutations as mutation_module
from odyssey_core.atomic_facts import append_atomic_facts
from odyssey_core.context import ContextIndex
from odyssey_core.direct_note_mutations import (
    DirectNoteMutationError,
    DirectNoteMutationService,
    _ExactLocatorSelector,
)
from odyssey_core.fact_selection import FactCandidate
from odyssey_core.git_history import GitHistoryResult, HistoryStatus
from odyssey_core.note_queries import NotesQueryError, NotesQueryService
from odyssey_core.notes import Note, parse_note, serialize_note
from odyssey_core.persistence import EntityPersistenceResult, PersistenceOperation
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


def test_mutation_tokens_fail_closed_for_invalid_identity_revision_and_hash(tmp_path: Path) -> None:
    """Reject malformed selected identity and stale-state tokens before reading or mutating."""
    repository, notes, mutations, _ = build(tmp_path)
    revision, source_hash = mutation_tokens(repository, "people/ada.md")
    cases = (
        {"note_id": "", "expected_revision": revision, "expected_source_hash": source_hash},
        {"note_id": "ada", "expected_revision": True, "expected_source_hash": source_hash},
        {"note_id": "ada", "expected_revision": 0, "expected_source_hash": source_hash},
        {"note_id": "ada", "expected_revision": revision, "expected_source_hash": "z" * 64},
        {"note_id": "ada", "expected_revision": revision + 1, "expected_source_hash": source_hash},
        {"note_id": "ada", "expected_revision": revision, "expected_source_hash": "b" * 64},
    )

    for index, case in enumerate(cases):
        with pytest.raises(DirectNoteMutationError, match="STALE_NOTE"):
            mutations.delete_note(
                **case,
                request_id=f"invalid-token-{index}",
                actor="test",
                now=NOW,
            )


def test_mutation_rejects_unavailable_duplicate_and_deleted_note_identity(tmp_path: Path) -> None:
    """Require exactly one active canonical note for the selected stable identity."""
    repository, notes, mutations, schema = build(tmp_path)
    revision, source_hash = mutation_tokens(repository, "people/ada.md")
    with pytest.raises(DirectNoteMutationError, match="NOTE_UNAVAILABLE"):
        mutations.delete_note(
            note_id="missing",
            expected_revision=revision,
            expected_source_hash=source_hash,
            request_id="missing-note",
            actor="test",
            now=NOW,
        )
    write(repository.root, "archive/duplicate.md", "ada", "Ada duplicate", "Duplicate identity.")
    with pytest.raises(DirectNoteMutationError, match="NOTE_UNAVAILABLE"):
        mutations.delete_note(
            note_id="ada",
            expected_revision=revision,
            expected_source_hash=source_hash,
            request_id="duplicate-note",
            actor="test",
            now=NOW,
        )

    duplicate = parse_note(repository.read_text("archive/duplicate.md"))
    duplicate.metadata["id"] = "retired"
    repository.replace_text("archive/duplicate.md", serialize_note(duplicate))
    current = parse_note(repository.read_text("people/ada.md"))
    current.metadata["deleted"] = True
    repository.replace_text("people/ada.md", serialize_note(current))
    revision, source_hash = mutation_tokens(repository, "people/ada.md")
    with pytest.raises(DirectNoteMutationError, match="NOTE_UNAVAILABLE"):
        mutations.delete_note(
            note_id="ada",
            expected_revision=revision,
            expected_source_hash=source_hash,
            request_id="deleted-note",
            actor="test",
            now=NOW,
        )


def test_mutation_rejects_unreadable_or_invalid_canonical_note(tmp_path: Path, monkeypatch) -> None:
    """Fail closed if any vault note cannot be parsed and validated during identity grounding."""
    repository, notes, mutations, _ = build(tmp_path)
    revision, source_hash = mutation_tokens(repository, "people/ada.md")
    original_read = repository.read_text

    def unreadable(path: str) -> str:
        if path == "people/ada.md":
            return "not a canonical note"
        return original_read(path)

    monkeypatch.setattr(repository, "read_text", unreadable)
    with pytest.raises(DirectNoteMutationError, match="NOTE_UNAVAILABLE"):
        mutations.delete_note(
            note_id="ada",
            expected_revision=revision,
            expected_source_hash=source_hash,
            request_id="invalid-canonical-note",
            actor="test",
            now=NOW,
        )


def test_exact_locator_selector_only_returns_a_current_candidate() -> None:
    """Keep the selector result constrained to the exact fresh candidate identity."""
    selector = _ExactLocatorSelector("request-1:0")

    assert selector.select("ada", "ignored", (FactCandidate("request-1:0", "Fact"),)) == {
        "outcome": "MATCH",
        "locator": "request-1:0",
    }
    assert selector.select("ada", "ignored", (FactCandidate("request-1:1", "Fact"),)) == {
        "outcome": "NO_MATCH",
        "locator": None,
    }


def test_fact_delete_fails_closed_for_malformed_facts_and_missing_locator(tmp_path: Path) -> None:
    """Reject malformed markers and locators that no longer identify a current atomic fact."""
    repository, notes, mutations, _ = build(tmp_path)
    raw = repository.read_text("people/ada.md")
    malformed = raw.replace("ordinal=0", "broken=0")
    repository.replace_text("people/ada.md", malformed)
    revision, source_hash = mutation_tokens(repository, "people/ada.md")
    with pytest.raises(DirectNoteMutationError, match="FACT_UNAVAILABLE"):
        mutations.delete_fact(
            note_id="ada",
            fact_locator="first:0",
            expected_revision=revision,
            expected_source_hash=source_hash,
            request_id="malformed-facts",
            actor="test",
            now=NOW,
        )

    repository.replace_text("people/ada.md", raw)
    revision, source_hash = mutation_tokens(repository, "people/ada.md")
    with pytest.raises(DirectNoteMutationError, match="FACT_UNAVAILABLE"):
        mutations.delete_fact(
            note_id="ada",
            fact_locator="missing:99",
            expected_revision=revision,
            expected_source_hash=source_hash,
            request_id="missing-fact",
            actor="test",
            now=NOW,
        )


@pytest.mark.parametrize("failure", [mutation_module.MaterializationError, ValueError])
def test_fact_delete_maps_materialization_failures_to_bounded_error(
    monkeypatch, tmp_path: Path, failure: type[Exception]
) -> None:
    """Translate Core materialization failures to the existing bounded fact error."""
    repository, notes, mutations, _ = build(tmp_path)
    revision, source_hash = mutation_tokens(repository, "people/ada.md")
    monkeypatch.setattr(
        mutation_module,
        "materialize_update",
        lambda *args, **kwargs: (_ for _ in ()).throw(failure("fixture")),
    )

    with pytest.raises(DirectNoteMutationError, match="FACT_UNAVAILABLE"):
        mutations.delete_fact(
            note_id="ada",
            fact_locator="first:0",
            expected_revision=revision,
            expected_source_hash=source_hash,
            request_id="failed-materialize",
            actor="test",
            now=NOW,
        )


def test_fact_delete_maps_non_update_materialization_to_bounded_error(
    monkeypatch, tmp_path: Path
) -> None:
    """Treat a no-change materialization result as a failed exact deletion."""
    repository, notes, mutations, _ = build(tmp_path)
    revision, source_hash = mutation_tokens(repository, "people/ada.md")
    monkeypatch.setattr(
        mutation_module,
        "materialize_update",
        lambda *args, **kwargs: EntityPersistenceResult(
            PersistenceOperation.NO_CHANGE, "ada", "people/ada.md", revision
        ),
    )

    with pytest.raises(DirectNoteMutationError, match="FACT_UNAVAILABLE"):
        mutations.delete_fact(
            note_id="ada",
            fact_locator="first:0",
            expected_revision=revision,
            expected_source_hash=source_hash,
            request_id="no-change-fact",
            actor="test",
            now=NOW,
        )


def test_note_delete_maps_backlink_query_failure_to_bounded_error(
    monkeypatch, tmp_path: Path
) -> None:
    """Refuse note deletion when Core cannot establish incoming-reference evidence."""
    repository, notes, mutations, _ = build(tmp_path)
    revision, source_hash = mutation_tokens(repository, "people/ada.md")
    monkeypatch.setattr(
        notes,
        "backlinks",
        lambda *args, **kwargs: (_ for _ in ()).throw(NotesQueryError("fixture")),
    )

    with pytest.raises(DirectNoteMutationError, match="NOTE_UNAVAILABLE"):
        mutations.delete_note(
            note_id="ada",
            expected_revision=revision,
            expected_source_hash=source_hash,
            request_id="backlink-error",
            actor="test",
            now=NOW,
        )


@pytest.mark.parametrize("failure", [mutation_module.MaterializationError, ValueError])
def test_note_delete_maps_materialization_failures_to_bounded_error(
    monkeypatch, tmp_path: Path, failure: type[Exception]
) -> None:
    """Translate soft-delete materialization errors without exposing storage details."""
    repository, notes, mutations, _ = build(tmp_path)
    revision, source_hash = mutation_tokens(repository, "people/ada.md")
    monkeypatch.setattr(
        mutation_module,
        "materialize_delete",
        lambda *args, **kwargs: (_ for _ in ()).throw(failure("fixture")),
    )

    with pytest.raises(DirectNoteMutationError, match="NOTE_UNAVAILABLE"):
        mutations.delete_note(
            note_id="ada",
            expected_revision=revision,
            expected_source_hash=source_hash,
            request_id="failed-soft-delete",
            actor="test",
            now=NOW,
        )


def test_note_delete_maps_non_delete_materialization_to_bounded_error(
    monkeypatch, tmp_path: Path
) -> None:
    """Do not report success when materialization did not soft-delete the selected note."""
    repository, notes, mutations, _ = build(tmp_path)
    revision, source_hash = mutation_tokens(repository, "people/ada.md")
    monkeypatch.setattr(
        mutation_module,
        "materialize_delete",
        lambda *args, **kwargs: EntityPersistenceResult(
            PersistenceOperation.NO_CHANGE, "ada", "people/ada.md", revision
        ),
    )

    with pytest.raises(DirectNoteMutationError, match="NOTE_UNAVAILABLE"):
        mutations.delete_note(
            note_id="ada",
            expected_revision=revision,
            expected_source_hash=source_hash,
            request_id="no-op-soft-delete",
            actor="test",
            now=NOW,
        )


def test_history_failures_are_reported_without_reversing_a_completed_mutation(
    tmp_path: Path,
) -> None:
    """Keep history best-effort while exposing its disabled, begin-failed, and record-failed states."""
    repository, notes, _, schema = build(tmp_path)
    revision, source_hash = mutation_tokens(repository, "people/ada.md")

    disabled = DirectNoteMutationService(repository, schema, notes, None).delete_fact(
        note_id="ada",
        fact_locator="first:0",
        expected_revision=revision,
        expected_source_hash=source_hash,
        request_id="history-disabled",
        actor="test",
        now=NOW,
    )
    assert disabled.history.status is HistoryStatus.DISABLED

    class FailedHistory:
        def begin(self, request_id: str) -> object:
            raise RuntimeError("begin failed")

        def record(self, **kwargs: object) -> GitHistoryResult:
            raise RuntimeError("record failed")

    revision, source_hash = mutation_tokens(repository, "people/ada.md")
    begin_failed = DirectNoteMutationService(
        repository, schema, notes, FailedHistory()
    ).delete_fact(
        note_id="ada",
        fact_locator="first:1",
        expected_revision=revision,
        expected_source_hash=source_hash,
        request_id="history-begin-failed",
        actor="test",
        now=NOW,
    )
    assert begin_failed.history.status is HistoryStatus.FAILED
    assert begin_failed.history.reason == "history snapshot failed"

    class RecordFailedHistory:
        def begin(self, request_id: str) -> object:
            return object()

        def record(self, **kwargs: object) -> GitHistoryResult:
            raise RuntimeError("record failed")

    record_tmp = tmp_path / "record-failure"
    record_tmp.mkdir()
    record_repository, record_notes, _, record_schema = build(record_tmp)
    revision, source_hash = mutation_tokens(record_repository, "people/ada.md")
    record_failed = DirectNoteMutationService(
        record_repository, record_schema, record_notes, RecordFailedHistory()
    ).delete_fact(
        note_id="ada",
        fact_locator="first:1",
        expected_revision=revision,
        expected_source_hash=source_hash,
        request_id="history-record-failed",
        actor="test",
        now=NOW,
    )
    assert record_failed.history.status is HistoryStatus.FAILED
    assert record_failed.history.reason == "history record failed"


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
