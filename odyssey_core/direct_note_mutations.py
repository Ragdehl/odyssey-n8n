"""Bounded direct Notes mutations that reuse canonical Core materialization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from odyssey_core.atomic_facts import AtomicFactError, parse_atomic_facts
from odyssey_core.fact_selection import FactCandidate
from odyssey_core.git_history import GitHistoryResult, HistoryRecorder
from odyssey_core.materialization import (
    MaterializationError,
    materialize_delete,
    materialize_update,
)
from odyssey_core.mutation_gate import (
    CanonicalMutationError,
    CanonicalMutationGate,
    MutationCommand,
)
from odyssey_core.note_queries import NotesQueryError, NotesQueryService
from odyssey_core.persistence import ActorInput, PersistenceOperation
from odyssey_core.request_planning import KnowledgeUnit, SelectionCriteria
from odyssey_core.storage import VaultRepository
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
        self._gate = CanonicalMutationGate(repository, schema, history)

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
        command = MutationCommand(
            "fact_deleted",
            note_id,
            expected_revision,
            expected_source_hash,
            request_id,
            actor,
            now,
        )
        try:
            target = self._gate.prepare(command)
        except CanonicalMutationError as error:
            code = (
                "STALE_NOTE"
                if error.code in {"STALE_TARGET", "INVALID_COMMAND"}
                else "NOTE_UNAVAILABLE"
            )
            raise DirectNoteMutationError(code) from error
        note = target.note
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
        try:
            receipt = self._gate.execute_prepared(
                command,
                target,
                lambda _target: materialize_update(
                    unit,
                    WriteTargetDecision(WriteTargetOutcome.UPDATE, existing_note_id=note_id),
                    repository=self.repository,
                    schema=self.schema,
                    actor=actor,
                    now=now,
                    request_id=request_id,
                    fact_selector=_ExactLocatorSelector(fact_locator),
                ),
            )
        except (MaterializationError, ValueError, CanonicalMutationError) as error:
            raise DirectNoteMutationError("FACT_UNAVAILABLE") from error
        if receipt.persistence.operation is not PersistenceOperation.UPDATED:
            raise DirectNoteMutationError("FACT_UNAVAILABLE")
        return DirectNoteMutationResult("fact_deleted", note_id, receipt.history)

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
        """Soft-delete a Note only when canonical incoming-reference evidence is empty."""
        command = MutationCommand(
            "note_deleted",
            note_id,
            expected_revision,
            expected_source_hash,
            request_id,
            actor,
            now,
        )
        try:
            target = self._gate.prepare(command)
        except CanonicalMutationError as error:
            code = (
                "STALE_NOTE"
                if error.code in {"STALE_TARGET", "INVALID_COMMAND"}
                else "NOTE_UNAVAILABLE"
            )
            raise DirectNoteMutationError(code) from error
        note = target.note
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
        try:
            receipt = self._gate.execute_prepared(
                command,
                target,
                lambda _target: materialize_delete(
                    unit,
                    WriteTargetDecision(WriteTargetOutcome.UPDATE, existing_note_id=note_id),
                    repository=self.repository,
                    schema=self.schema,
                    actor=actor,
                    now=now,
                ),
            )
        except (MaterializationError, ValueError, CanonicalMutationError) as error:
            raise DirectNoteMutationError("NOTE_UNAVAILABLE") from error
        if receipt.persistence.operation is not PersistenceOperation.DELETED:
            raise DirectNoteMutationError("NOTE_UNAVAILABLE")
        return DirectNoteMutationResult("note_deleted", note_id, receipt.history)
