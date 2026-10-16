"""Shared canonical mutation pre/post boundary for deterministic consumers.

This module deliberately does not interpret user language or select a target.
Callers provide a stable ID selected by an authenticated runtime/UI contract;
the gate re-grounds it against canonical Markdown before a domain-owned
operation and reads it back afterwards.  Persistence remains in
``materialization``/``persistence``.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any, Protocol

from .git_history import GitHistoryResult, HistoryRecorder, HistoryStatus
from .notes import Note, NoteFormatError, parse_note, validate_note
from .persistence import ActorInput, EntityPersistenceResult, normalize_actor_provenance
from .storage import NoteUnavailableError, VaultRepository


class CanonicalMutationError(ValueError):
    """A common fail-closed mutation-boundary rejection."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CanonicalPostwriteError(CanonicalMutationError):
    """A canonical write occurred, but its required post-write proof failed.

    The persistence result is intentionally retained so outer boundaries can
    report a partial outcome and must not retry as though no Markdown changed.
    """

    def __init__(
        self,
        code: str,
        *,
        target_id: str,
        operation: str,
        persistence: EntityPersistenceResult,
    ) -> None:
        super().__init__(code)
        self.target_id = target_id
        self.operation = operation
        self.persistence = persistence
        self.physical_write = True


@dataclass(frozen=True, slots=True)
class MutationCommand:
    """Trusted runtime command tokens; source text is intentionally absent."""

    operation: str
    target_id: str
    expected_revision: int
    expected_source_hash: str
    request_id: str
    actor: ActorInput
    now: str
    expected_type: str | None = None


@dataclass(frozen=True, slots=True)
class MutationTarget:
    id: str
    path: str
    note: Note
    source_hash: str


@dataclass(frozen=True, slots=True)
class CreateMutationCommand:
    """A deterministic CREATE command with optional rechecked owner evidence."""

    operation: str
    target_id: str
    target_path: str
    expected_type: str
    request_id: str
    actor: ActorInput
    now: str
    parent: MutationCommand | None = None


@dataclass(frozen=True, slots=True)
class CanonicalMutationReceipt:
    """Post-write evidence. A history failure never erases a physical receipt."""

    operation: str
    target_id: str
    before_revision: int
    before_source_hash: str
    persistence: EntityPersistenceResult
    after_revision: int
    after_source_hash: str
    readback: Note
    history: GitHistoryResult


@dataclass(frozen=True, slots=True)
class CanonicalCreateReceipt:
    operation: str
    target_id: str
    target_path: str
    persistence: EntityPersistenceResult
    readback: Note
    source_hash: str
    history: GitHistoryResult
    affected_ids: tuple[str, ...]


class MutationExecutor(Protocol):
    def __call__(self, target: MutationTarget) -> EntityPersistenceResult: ...


class CreateMutationExecutor(Protocol):
    def __call__(self, parent: MutationTarget | None) -> EntityPersistenceResult: ...


class CanonicalMutationGate:
    """Reusable precondition, receipt, history and readback guard for one Note.

    There is intentionally no multi-note transaction claim.  If an executor
    raises after a physical write, callers can call ``receipt_after_write`` to
    retain a partial receipt rather than retrying blindly.
    """

    def __init__(
        self,
        repository: VaultRepository,
        schema: dict[str, Any],
        history: HistoryRecorder | None,
    ) -> None:
        self.repository = repository
        self.schema = schema
        self.history = history

    def prepare(self, command: MutationCommand) -> MutationTarget:
        self._validate_command(command)
        # Validate provenance here: callers cannot smuggle arbitrary lifecycle
        # metadata through an otherwise direct operation.
        normalize_actor_provenance(command.actor)
        matches: list[MutationTarget] = []
        for path in self.repository.list_markdown_paths():
            try:
                raw = self.repository.read_text(path)
                note = parse_note(raw)
                validate_note(note, self.schema)
            except (NoteUnavailableError, NoteFormatError, ValueError) as error:
                raise CanonicalMutationError("TARGET_UNAVAILABLE") from error
            if note.metadata.get("id") == command.target_id:
                matches.append(MutationTarget(command.target_id, path, note, self._hash(raw)))
        if len(matches) != 1 or matches[0].note.metadata.get("deleted") is True:
            raise CanonicalMutationError("TARGET_UNAVAILABLE")
        target = matches[0]
        if (
            command.expected_type is not None
            and target.note.metadata.get("type") != command.expected_type
        ):
            raise CanonicalMutationError("TARGET_TYPE_MISMATCH")
        revision_matches = target.note.metadata.get("revision") == command.expected_revision
        if not revision_matches or not hmac.compare_digest(
            target.source_hash, command.expected_source_hash
        ):
            raise CanonicalMutationError("STALE_TARGET")
        return target

    def execute(
        self, command: MutationCommand, executor: MutationExecutor
    ) -> CanonicalMutationReceipt:
        target = self.prepare(command)
        return self.execute_prepared(command, target, executor)

    def execute_prepared(
        self, command: MutationCommand, target: MutationTarget, executor: MutationExecutor
    ) -> CanonicalMutationReceipt:
        """Execute after a caller's domain guard inspected this prepared target."""
        # Domain guards can legitimately do non-trivial work after ``prepare``.
        # Re-read only this exact canonical path before mutation: another actor
        # may have changed it meanwhile, including a body-only change that did
        # not advance a malformed/forged revision.  Do not rescan the vault.
        self._revalidate_prepared(command, target)
        snapshot = self._begin_history(command.request_id)
        result = executor(target)
        return self._receipt(command, target, result, snapshot)

    def receipt_after_write(
        self, command: MutationCommand, target: MutationTarget, result: EntityPersistenceResult
    ) -> CanonicalMutationReceipt:
        """Read back a known physical write when a later dependent step failed."""
        return self._receipt(command, target, result, None)

    def execute_create(
        self,
        command: CreateMutationCommand,
        executor: CreateMutationExecutor,
        *,
        affected_ids: tuple[str, ...] | None = None,
    ) -> CanonicalCreateReceipt:
        """Create one exact new Note and retain physical readback evidence.

        A parent is re-read immediately before persistence, so a stale owner
        cannot authorize a child after expensive preflight.  This is not a
        transaction over the parent and child; the underlying filesystem has
        no cross-note compare-and-swap primitive.
        """
        self._validate_create_command(command)
        normalize_actor_provenance(command.actor)
        parent = self.prepare(command.parent) if command.parent is not None else None
        if self._id_exists(command.target_id):
            raise CanonicalMutationError("CREATE_TARGET_EXISTS")
        snapshot = self._begin_history(command.request_id)
        # Re-read the owner immediately before the only physical create.
        if command.parent is not None:
            parent = self.prepare(command.parent)
        result = executor(parent)
        if result.id != command.target_id or result.path != command.target_path:
            raise CanonicalPostwriteError(
                "UNEXPECTED_PERSISTENCE_RESULT",
                target_id=command.target_id,
                operation=command.operation,
                persistence=result,
            )
        try:
            raw = self.repository.read_text(command.target_path)
            note = parse_note(raw)
            validate_note(note, self.schema)
        except (NoteUnavailableError, NoteFormatError, ValueError) as error:
            raise CanonicalPostwriteError(
                "POSTWRITE_READBACK_FAILED",
                target_id=command.target_id,
                operation=command.operation,
                persistence=result,
            ) from error
        if (
            note.metadata.get("id") != command.target_id
            or note.metadata.get("type") != command.expected_type
        ):
            raise CanonicalPostwriteError(
                "POSTWRITE_IDENTITY_MISMATCH",
                target_id=command.target_id,
                operation=command.operation,
                persistence=result,
            )
        ids = affected_ids or (command.target_id,)
        if not ids or len(set(ids)) != len(ids) or command.target_id not in ids:
            raise CanonicalMutationError("INVALID_AFFECTED_IDS")
        return CanonicalCreateReceipt(
            command.operation,
            command.target_id,
            command.target_path,
            result,
            note,
            self._hash(raw),
            self._record_history(command.request_id, snapshot, ids),
            ids,
        )

    def _receipt(
        self,
        command: MutationCommand,
        target: MutationTarget,
        result: EntityPersistenceResult,
        snapshot: object | None,
    ) -> CanonicalMutationReceipt:
        if result.id != command.target_id or result.path != target.path:
            raise CanonicalPostwriteError(
                "UNEXPECTED_PERSISTENCE_RESULT",
                target_id=command.target_id,
                operation=command.operation,
                persistence=result,
            )
        try:
            raw = self.repository.read_text(target.path)
            note = parse_note(raw)
            validate_note(note, self.schema)
        except (NoteUnavailableError, NoteFormatError, ValueError) as error:
            raise CanonicalPostwriteError(
                "POSTWRITE_READBACK_FAILED",
                target_id=command.target_id,
                operation=command.operation,
                persistence=result,
            ) from error
        if note.metadata.get("id") != command.target_id:
            raise CanonicalPostwriteError(
                "POSTWRITE_IDENTITY_MISMATCH",
                target_id=command.target_id,
                operation=command.operation,
                persistence=result,
            )
        revision = note.metadata.get("revision")
        if not isinstance(revision, int) or revision != result.revision:
            raise CanonicalPostwriteError(
                "POSTWRITE_REVISION_MISMATCH",
                target_id=command.target_id,
                operation=command.operation,
                persistence=result,
            )
        return CanonicalMutationReceipt(
            command.operation,
            command.target_id,
            command.expected_revision,
            target.source_hash,
            result,
            revision,
            self._hash(raw),
            note,
            self._record_history(command.request_id, snapshot, command.target_id),
        )

    def _begin_history(self, request_id: str) -> object | None:
        if self.history is None:
            return None
        try:
            return self.history.begin(request_id)
        except Exception:
            return None

    def _revalidate_prepared(self, command: MutationCommand, target: MutationTarget) -> None:
        """Fail closed if an exact prepared target drifted before execution."""
        try:
            raw = self.repository.read_text(target.path)
            note = parse_note(raw)
            validate_note(note, self.schema)
        except (NoteUnavailableError, NoteFormatError, ValueError) as error:
            raise CanonicalMutationError("TARGET_UNAVAILABLE") from error
        if (
            note.metadata.get("id") != command.target_id
            or note.metadata.get("deleted") is True
            or note.metadata.get("revision") != command.expected_revision
            or self._hash(raw) != command.expected_source_hash
            or command.expected_type is not None
            and note.metadata.get("type") != command.expected_type
        ):
            raise CanonicalMutationError("STALE_TARGET")

    def _record_history(
        self, request_id: str, snapshot: object | None, target_ids: tuple[str, ...] | str
    ) -> GitHistoryResult:
        if self.history is None:
            return GitHistoryResult.disabled()
        if snapshot is None:
            return GitHistoryResult(HistoryStatus.FAILED, reason="history snapshot failed")
        try:
            return self.history.record(
                request_id=request_id,
                snapshot=snapshot,
                affected_stable_note_ids=(
                    target_ids if isinstance(target_ids, tuple) else (target_ids,)
                ),
                repository=self.repository,
                schema=self.schema,
            )
        except Exception:
            return GitHistoryResult(HistoryStatus.FAILED, reason="history record failed")

    @staticmethod
    def _hash(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _validate_command(command: MutationCommand) -> None:
        strings = (command.operation, command.target_id, command.request_id, command.now)
        if any(not isinstance(value, str) or not value for value in strings):
            raise CanonicalMutationError("INVALID_COMMAND")
        if (
            not isinstance(command.expected_revision, int)
            or isinstance(command.expected_revision, bool)
            or command.expected_revision < 1
        ):
            raise CanonicalMutationError("STALE_TARGET")
        if (
            not isinstance(command.expected_source_hash, str)
            or len(command.expected_source_hash) != 64
            or any(c not in "0123456789abcdef" for c in command.expected_source_hash)
        ):
            raise CanonicalMutationError("STALE_TARGET")

    @staticmethod
    def _validate_create_command(command: CreateMutationCommand) -> None:
        values = (
            command.operation,
            command.target_id,
            command.target_path,
            command.expected_type,
            command.request_id,
            command.now,
        )
        if any(not isinstance(value, str) or not value for value in values):
            raise CanonicalMutationError("INVALID_COMMAND")
        if "/" in command.target_id or "\\" in command.target_id:
            raise CanonicalMutationError("INVALID_COMMAND")

    def _id_exists(self, entity_id: str) -> bool:
        for path in self.repository.list_markdown_paths():
            try:
                note = parse_note(self.repository.read_text(path))
                validate_note(note, self.schema)
            except (NoteUnavailableError, NoteFormatError, ValueError) as error:
                raise CanonicalMutationError("TARGET_UNAVAILABLE") from error
            if note.metadata.get("id") == entity_id:
                return True
        return False
