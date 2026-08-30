"""Focused deterministic coverage for Phase 16.7B soft-delete semantics."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from odyssey_core import (
    ContextIndex,
    EntityAlreadyExistsError,
    EntityRevisionMismatchError,
    MaterializationError,
    PersistenceOperation,
    ProtectedMetadataError,
    SelectionCriteria,
    SemanticEntityIndex,
    WriteTargetDecision,
    WriteTargetOutcome,
    create_entity,
    find_exact_entity_candidates,
    get_context,
    materialize_delete,
    soft_delete_entity,
    update_entity,
)
from odyssey_core.notes import Note, NoteValidationError, parse_note, validate_note
from odyssey_core.request_planning import KnowledgeUnit
from odyssey_core.resolution import ExistingEntityOutcome, resolve_existing_entity
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-08-27T22:00:00+02:00"


class Embedder:
    """Provide fixed local vectors for disposable derived-index tests."""

    model_name = "tests/soft-delete"
    model_version = "1"

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one stable vector per indexed source text."""
        return [[1.0, 0.0] for _ in texts]

    def embed_queries(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one stable vector per query text."""
        return [[1.0, 0.0] for _ in texts]


class RejectingReasoner:
    """Fail a test when stale semantic evidence reaches contextual resolution."""

    def __init__(self) -> None:
        """Initialize the observable no-call guard."""
        self.calls = 0

    def resolve(self, request: object) -> object:
        """Reject any unexpected contextual provider invocation."""
        self.calls += 1
        raise AssertionError(
            f"Deleted semantic candidate reached contextual resolution: {request!r}"
        )


@pytest.fixture
def schema() -> dict:
    """Load the checked-in canonical schema."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


@pytest.fixture
def repository(tmp_path: Path, schema: dict) -> VaultRepository:
    """Create an active Marta note and an unchanged inbound backlink."""
    (tmp_path / "people").mkdir()
    (tmp_path / "journals").mkdir()
    vault = VaultRepository(tmp_path)
    create_entity(
        vault,
        schema,
        path="people/marta.md",
        entity_id="marta",
        metadata={"name": "Marta", "type": "person", "aliases": ["Martita"], "tags": ["idea"]},
        content="Marta lives in Lyon.\n",
        actor="test",
        now=NOW,
    )
    create_entity(
        vault,
        schema,
        path="journals/today.md",
        entity_id="today",
        metadata={"name": "Today", "type": "journal_entry", "entry_date": "2026-08-27"},
        content="Hoy he comido con [[Marta]].\n",
        actor="test",
        now=NOW,
    )
    return vault


def test_schema_accepts_optional_boolean_deleted_and_rejects_non_boolean(schema: dict) -> None:
    """Keep absent lifecycle state active while validating only boolean deleted values."""
    metadata = {
        "id": "marta",
        "name": "Marta",
        "type": "person",
        "created_at": NOW,
        "updated_at": NOW,
        "created_by": {"human": None, "app": "test"},
        "updated_by": {"human": None, "app": "test"},
        "revision": 1,
        "schema_version": 3,
    }
    validate_note(Note(metadata, ""), schema)  # type: ignore[arg-type]
    validate_note(Note({**metadata, "deleted": True}, ""), schema)  # type: ignore[arg-type]
    with pytest.raises(NoteValidationError, match="deleted"):
        validate_note(Note({**metadata, "deleted": "true"}, ""), schema)  # type: ignore[arg-type]


def test_soft_delete_preserves_note_and_backlinks_with_revision_guard(
    repository: VaultRepository, schema: dict
) -> None:
    """Retire exactly one note without moving its file, body, or other-note wikilinks."""
    before = parse_note(repository.read_text("people/marta.md"))
    backlink = repository.read_text("journals/today.md")
    with pytest.raises(ProtectedMetadataError):
        update_entity(
            repository,
            schema,
            path="people/marta.md",
            expected_id="marta",
            set_metadata={"deleted": True},
            actor="test",
            now=NOW,
        )
    result = soft_delete_entity(
        repository,
        schema,
        path="people/marta.md",
        expected_id="marta",
        expected_revision=1,
        actor="deleter",
        now="2026-08-27T23:00:00+02:00",
    )
    after = parse_note(repository.read_text("people/marta.md"))
    assert result.operation is PersistenceOperation.DELETED
    assert after.content == before.content
    assert {key: after.metadata[key] for key in ("id", "name", "type", "aliases", "tags")} == {
        key: before.metadata[key] for key in ("id", "name", "type", "aliases", "tags")
    }
    assert after.metadata["deleted"] is True
    assert repository.read_text("journals/today.md") == backlink
    with pytest.raises(EntityRevisionMismatchError):
        soft_delete_entity(
            repository,
            schema,
            path="people/marta.md",
            expected_id="marta",
            expected_revision=1,
            actor="deleter",
            now=NOW,
        )


def test_materialize_delete_requires_one_resolved_factless_unit(
    repository: VaultRepository, schema: dict
) -> None:
    """Exercise the DELETE unit-to-Core boundary and reject bulk DELETE before persistence."""
    unit = KnowledgeUnit(
        SelectionCriteria("Marta", "Marta", "person", (), None), "delete", (), (), (), (), "one"
    )
    decision = WriteTargetDecision(WriteTargetOutcome.UPDATE, existing_note_id="marta")
    result = materialize_delete(
        unit, decision, repository=repository, schema=schema, actor="test", now=NOW
    )
    assert result.operation is PersistenceOperation.DELETED
    bulk = KnowledgeUnit(
        SelectionCriteria(None, "all people", "person", (), None),
        "delete",
        (),
        (),
        (),
        (),
        "all_matching",
    )
    with pytest.raises(MaterializationError, match="cardinality=one"):
        materialize_delete(
            bulk, decision, repository=repository, schema=schema, actor="test", now=NOW
        )


def test_deleted_notes_are_excluded_from_exact_indexes_context_and_duplicate_ids(
    repository: VaultRepository, schema: dict, tmp_path: Path
) -> None:
    """Omit retired notes from active projections while retaining stable-ID uniqueness."""
    semantic = SemanticEntityIndex(tmp_path.parent / f"{tmp_path.name}-semantic.sqlite3")
    context = ContextIndex(tmp_path.parent / f"{tmp_path.name}-context.sqlite3")
    assert semantic.rebuild(repository, schema, Embedder()) == 2
    assert context.rebuild(repository, schema, Embedder()) == 2
    soft_delete_entity(
        repository,
        schema,
        path="people/marta.md",
        expected_id="marta",
        expected_revision=1,
        actor="test",
        now=NOW,
    )
    assert find_exact_entity_candidates(repository, schema, "Marta") == ()
    assert semantic.rebuild(repository, schema, Embedder()) == 1
    assert context.rebuild(repository, schema, Embedder()) == 1
    with pytest.raises(EntityAlreadyExistsError):
        create_entity(
            repository,
            schema,
            path="people/another.md",
            entity_id="marta",
            metadata={"name": "Another", "type": "person"},
            content="",
            actor="test",
            now=NOW,
        )


def test_stale_context_index_cannot_return_currently_deleted_note(
    repository: VaultRepository, schema: dict, tmp_path: Path
) -> None:
    """Ground stale derived context evidence in authoritative deleted Markdown before return."""
    index = ContextIndex(tmp_path.parent / f"{tmp_path.name}-context.sqlite3")
    index.rebuild(repository, schema, Embedder())
    soft_delete_entity(
        repository,
        schema,
        path="people/marta.md",
        expected_id="marta",
        expected_revision=1,
        actor="test",
        now=NOW,
    )
    package = get_context(repository, schema, index, Embedder(), query="Marta", limit=5)
    assert all(item.id != "marta" for item in package.items)


def test_stale_semantic_index_cannot_resolve_or_disclose_deleted_candidate(
    repository: VaultRepository, schema: dict, tmp_path: Path
) -> None:
    """Ground semantic candidates in current Markdown before contextual evidence construction."""
    index = SemanticEntityIndex(tmp_path.parent / f"{tmp_path.name}-semantic.sqlite3")
    index.rebuild(repository, schema, Embedder())
    soft_delete_entity(
        repository,
        schema,
        path="people/marta.md",
        expected_id="marta",
        expected_revision=1,
        actor="test",
        now=NOW,
    )
    reasoner = RejectingReasoner()
    result = resolve_existing_entity(
        "the person in Lyon",
        "",
        type="person",
        repository=repository,
        schema=schema,
        semantic_index=index,
        embedder=Embedder(),
        contextual_reasoner=reasoner,
        semantic_limit=5,
    )
    assert result.outcome is ExistingEntityOutcome.UNRESOLVED
    assert result.id is None
    assert reasoner.calls == 0
