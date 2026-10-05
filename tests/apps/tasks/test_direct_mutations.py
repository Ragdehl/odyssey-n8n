"""Explicit Notes checkbox actions reuse Tasks lifecycle semantics without a provider."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TASK_SCHEMA_EXTENSION,
    TaskDirectMutationError,
    TaskDirectMutationService,
)
from odyssey_core import create_entity
from odyssey_core.notes import parse_note
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[3]
BASE = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
SCHEMA = compose_application_schema(BASE, (TASK_SCHEMA_EXTENSION,))


class EmptyIndex:
    """Keep Core preflight deterministic while exact identity handles this fixture."""

    def find_candidates(self, *args: object, **kwargs: object) -> tuple[object, ...]:
        """Return no semantic candidates."""
        return ()


class EmptyEmbedder:
    """Satisfy the local Core resolution dependency."""

    model_name = "test"
    model_version = "1"


class NoReasoner:
    """Fail if exact fixture identity unexpectedly reaches contextual reasoning."""

    def resolve(self, request: object) -> object:
        """Reject unexpected contextual resolution."""
        raise AssertionError("unexpected contextual resolution")


def _build(tmp_path: Path, status: str = "pending"):
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    create_entity(
        repository,
        SCHEMA,
        path="bank.md",
        entity_id="task-bank",
        metadata={"name": "Llamar al banco", "type": "task", "status": status},
        content=("- Llamar al banco.\n" if status == "completed" else "- Llamar al banco.\n"),
        actor="fixture",
        now="2026-10-05T07:00:00+02:00",
    )
    service = TaskDirectMutationService(repository, SCHEMA, None)
    return repository, service


def _tokens(repository: VaultRepository) -> tuple[int, str]:
    raw = repository.read_text("bank.md")
    return parse_note(raw).metadata["revision"], hashlib.sha256(raw.encode()).hexdigest()


def test_checkbox_complete_and_reopen_are_exact_lifecycle_mutations(tmp_path: Path) -> None:
    repository, service = _build(tmp_path)
    revision, source_hash = _tokens(repository)
    result = service.set_completed(
        note_id="task-bank",
        completed=True,
        expected_revision=revision,
        expected_source_hash=source_hash,
        request_id="complete",
        actor="test",
        now="2026-10-05T07:10:00+02:00",
    )
    assert result.operation == "task_completed"
    completed = parse_note(repository.read_text("bank.md"))
    assert completed.metadata["status"] == "completed"
    assert completed.metadata["completed_at"] == "2026-10-05T07:10:00+02:00"
    assert "- Llamar al banco." in completed.content

    revision, source_hash = _tokens(repository)
    result = service.set_completed(
        note_id="task-bank",
        completed=False,
        expected_revision=revision,
        expected_source_hash=source_hash,
        request_id="reopen",
        actor="test",
        now="2026-10-05T07:12:00+02:00",
    )
    assert result.operation == "task_reopened"
    reopened = parse_note(repository.read_text("bank.md"))
    assert reopened.metadata["status"] == "pending"
    assert "completed_at" not in reopened.metadata
    assert "- Llamar al banco." in reopened.content


def test_checkbox_rejects_stale_or_invalid_transition(tmp_path: Path) -> None:
    repository, service = _build(tmp_path, "completed")
    revision, source_hash = _tokens(repository)
    with pytest.raises(TaskDirectMutationError, match="TASK_INVALID_TRANSITION"):
        service.set_completed(
            note_id="task-bank",
            completed=True,
            expected_revision=revision,
            expected_source_hash=source_hash,
            request_id="bad",
            actor="test",
            now="2026-10-05T07:10:00+02:00",
        )

    with pytest.raises(TaskDirectMutationError, match="STALE_NOTE"):
        service.set_completed(
            note_id="task-bank",
            completed=False,
            expected_revision=revision + 1,
            expected_source_hash=source_hash,
            request_id="stale",
            actor="test",
            now="2026-10-05T07:10:00+02:00",
        )


def test_subtask_create_uses_core_preflight_and_one_canonical_parent_fact(tmp_path: Path) -> None:
    repository, _service = _build(tmp_path)
    service = TaskDirectMutationService(
        repository,
        SCHEMA,
        None,
        semantic_index=EmptyIndex(),
        embedder=EmptyEmbedder(),
        contextual_reasoner=NoReasoner(),
        semantic_limit=5,
    )
    revision, source_hash = _tokens(repository)
    result = service.create_subtask(
        parent_note_id="task-bank",
        title="Pedir el extracto",
        expected_revision=revision,
        expected_source_hash=source_hash,
        request_id="child",
        actor="test",
        now="2026-10-05T07:10:00+02:00",
    )
    assert result.operation == "task_subtask_created"
    assert result.status == "pending"
    child = parse_note(repository.read_text(result.path))
    assert child.metadata["type"] == "task"
    assert child.metadata["status"] == "pending"
    assert child.content.count("Tarea superior:") == 1
    assert "[[bank|Llamar al banco]]" in child.content


def test_subtask_create_rejects_closed_parent(tmp_path: Path) -> None:
    repository, _service = _build(tmp_path, "completed")
    service = TaskDirectMutationService(
        repository,
        SCHEMA,
        None,
        semantic_index=EmptyIndex(),
        embedder=EmptyEmbedder(),
        contextual_reasoner=NoReasoner(),
        semantic_limit=5,
    )
    revision, source_hash = _tokens(repository)
    with pytest.raises(TaskDirectMutationError, match="TASK_PARENT_CLOSED"):
        service.create_subtask(
            parent_note_id="task-bank",
            title="No crear",
            expected_revision=revision,
            expected_source_hash=source_hash,
            request_id="child",
            actor="test",
            now="2026-10-05T07:10:00+02:00",
        )


def test_subtask_create_rejects_an_existing_task_title(tmp_path: Path) -> None:
    repository, _service = _build(tmp_path)
    create_entity(
        repository,
        SCHEMA,
        path="existing.md",
        entity_id="task-existing",
        metadata={"name": "Pedir el extracto", "type": "task", "status": "pending"},
        content="- Existente.\n",
        actor="fixture",
        now="2026-10-05T07:00:00+02:00",
    )
    service = TaskDirectMutationService(
        repository,
        SCHEMA,
        None,
        semantic_index=EmptyIndex(),
        embedder=EmptyEmbedder(),
        contextual_reasoner=NoReasoner(),
        semantic_limit=5,
    )
    revision, source_hash = _tokens(repository)
    with pytest.raises(TaskDirectMutationError, match="TASK_SUBTASK_TARGET_UNAVAILABLE"):
        service.create_subtask(
            parent_note_id="task-bank",
            title="Pedir el extracto",
            expected_revision=revision,
            expected_source_hash=source_hash,
            request_id="child",
            actor="test",
            now="2026-10-05T07:10:00+02:00",
        )
