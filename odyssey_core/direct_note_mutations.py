"""Bounded direct Notes mutations that reuse canonical Core materialization."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from odyssey_core.atomic_facts import AtomicFactError, parse_atomic_facts
from odyssey_core.fact_selection import FactCandidate
from odyssey_core.git_history import GitHistoryResult, HistoryRecorder, HistoryStatus
from odyssey_core.materialization import (
    MaterializationError,
    materialize_delete,
    materialize_update,
)
from odyssey_core.note_queries import NotesQueryError, NotesQueryService
from odyssey_core.notes import NoteFormatError, parse_note, validate_note
from odyssey_core.persistence import ActorInput, PersistenceOperation
from odyssey_core.request_planning import KnowledgeUnit, SelectionCriteria
from odyssey_core.storage import NoteUnavailableError, VaultRepository
from odyssey_core.write_target import WriteTargetDecision, WriteTargetOutcome


class DirectNoteMutationError(ValueError):
    """Indicate a bounded direct Notes mutation that cannot safely proceed."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class DirectNoteMutationResult:
    """Return bounded evidence for one direct canonical Notes mutation."""

    operation: str
    note_id: str
    history: GitHistoryResult


class _ExactLocatorSelector:
    """Select only the browser-supplied locator after Core has re-grounded it."""

    def __init__(self, locator: str) -> None:
        self.locator = locator

    def select(
        self, note_id: str, description: str, candidates: tuple[FactCandidate, ...]
    ) -> object:
        """Return MATCH only when the fresh candidate set contains the exact locator."""
        del note_id, description
        if any(candidate.locator == self.locator for candidate in candidates):
            return {"outcome": "MATCH", "locator": self.locator}
        return {"outcome": "NO_MATCH", "locator": None}


class DirectNoteMutationService:
    """Apply direct selected-note deletes through existing materialization and Git history."""

    def __init__(
        self,
        repository: VaultRepository,
        schema: dict[str, Any],
        notes: NotesQueryService,
        history: HistoryRecorder | None,
    ) -> None:
        """Configure the authoritative dependencies used by each guarded mutation."""
        self.repository = repository
        self.schema = schema
        self.notes = notes
        self.history = history

    def delete_fact(
        self,
        *,
        note_id: str,
        fact_locator: str,
        expected_revision: int,
        expected_source_hash: str,
        request_id: str,
        actor: ActorInput,
        now: str,
    ) -> DirectNoteMutationResult:
        """Remove one current marked fact while preserving every other Markdown occurrence."""
        path, note, source_hash = self._load_current(
            note_id, expected_revision, expected_source_hash
        )
        try:
            facts = parse_atomic_facts(note.content)
        except AtomicFactError as error:
            raise DirectNoteMutationError("FACT_UNAVAILABLE") from error
        selected = next((fact for fact in facts if fact.locator == fact_locator), None)
        if selected is None:
            raise DirectNoteMutationError("FACT_UNAVAILABLE")
        unit = KnowledgeUnit(
            SelectionCriteria(
                note.metadata["name"], note.metadata["name"], note.metadata["type"], (), None
            ),
            "remove",
            (),
            (),
            (selected.text,),
            (),
            "one",
        )
        history = self._begin_history(request_id)
        try:
            result = materialize_update(
                unit,
                WriteTargetDecision(WriteTargetOutcome.UPDATE, existing_note_id=note_id),
                repository=self.repository,
                schema=self.schema,
                actor=actor,
                now=now,
                request_id=request_id,
                fact_selector=_ExactLocatorSelector(fact_locator),
            )
        except (MaterializationError, ValueError) as error:
            raise DirectNoteMutationError("FACT_UNAVAILABLE") from error
        if result.operation is not PersistenceOperation.UPDATED:
            raise DirectNoteMutationError("FACT_UNAVAILABLE")
        return DirectNoteMutationResult(
            "fact_deleted", note_id, self._record_history(request_id, history, note_id)
        )

    def delete_note(
        self,
        *,
        note_id: str,
        expected_revision: int,
        expected_source_hash: str,
        request_id: str,
        actor: ActorInput,
        now: str,
    ) -> DirectNoteMutationResult:
        """Soft-delete one current note only when canonical incoming-reference evidence is empty."""
        path, note, source_hash = self._load_current(
            note_id, expected_revision, expected_source_hash
        )
        try:
            if self.notes.backlinks(note_id, page_size=1).total:
                raise DirectNoteMutationError("INCOMING_REFERENCES")
        except NotesQueryError as error:
            raise DirectNoteMutationError("NOTE_UNAVAILABLE") from error
        unit = KnowledgeUnit(
            SelectionCriteria(
                note.metadata["name"], note.metadata["name"], note.metadata["type"], (), None
            ),
            "delete",
            (),
            (),
            (),
            (),
            "one",
        )
        history = self._begin_history(request_id)
        try:
            result = materialize_delete(
                unit,
                WriteTargetDecision(WriteTargetOutcome.UPDATE, existing_note_id=note_id),
                repository=self.repository,
                schema=self.schema,
                actor=actor,
                now=now,
            )
        except (MaterializationError, ValueError) as error:
            raise DirectNoteMutationError("NOTE_UNAVAILABLE") from error
        if result.operation is not PersistenceOperation.DELETED:
            raise DirectNoteMutationError("NOTE_UNAVAILABLE")
        return DirectNoteMutationResult(
            "note_deleted", note_id, self._record_history(request_id, history, note_id)
        )

    def _load_current(
        self, note_id: str, expected_revision: int, expected_source_hash: str
    ) -> tuple[str, Any, str]:
        """Re-read and validate the selected active note and all stale-write tokens."""
        if not isinstance(note_id, str) or not note_id or not isinstance(expected_revision, int):
            raise DirectNoteMutationError("STALE_NOTE")
        if not isinstance(expected_source_hash, str) or len(expected_source_hash) != 64:
            raise DirectNoteMutationError("STALE_NOTE")
        matches: list[tuple[str, Any, str]] = []
        for path in self.repository.list_markdown_paths():
            try:
                raw = self.repository.read_text(path)
                note = parse_note(raw)
                validate_note(note, self.schema)
            except (NoteUnavailableError, NoteFormatError, ValueError) as error:
                raise DirectNoteMutationError("NOTE_UNAVAILABLE") from error
            if note.metadata.get("id") == note_id:
                matches.append((path, note, hashlib.sha256(raw.encode()).hexdigest()))
        if len(matches) != 1:
            raise DirectNoteMutationError("NOTE_UNAVAILABLE")
        path, note, source_hash = matches[0]
        if note.metadata.get("deleted") is True:
            raise DirectNoteMutationError("NOTE_UNAVAILABLE")
        if note.metadata.get("revision") != expected_revision or not hmac.compare_digest(
            source_hash, expected_source_hash
        ):
            raise DirectNoteMutationError("STALE_NOTE")
        return path, note, source_hash

    def _begin_history(self, request_id: str) -> object | None:
        """Begin existing request-correlated history without making history a mutation authority."""
        if self.history is None:
            return None
        try:
            return self.history.begin(request_id)
        except Exception:
            return None

    def _record_history(
        self, request_id: str, snapshot: object | None, note_id: str
    ) -> GitHistoryResult:
        """Record the same affected-note Git evidence used by normal Core writes."""
        if self.history is None:
            return GitHistoryResult.disabled()
        if snapshot is None:
            return GitHistoryResult(HistoryStatus.FAILED, reason="history snapshot failed")
        try:
            return self.history.record(
                request_id=request_id,
                snapshot=snapshot,
                affected_stable_note_ids=(note_id,),
                repository=self.repository,
                schema=self.schema,
            )
        except Exception:
            return GitHistoryResult(HistoryStatus.FAILED, reason="history record failed")
