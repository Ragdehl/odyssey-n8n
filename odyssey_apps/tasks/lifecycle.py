"""Tasks lifecycle invariants evaluated after Core resolves the exact canonical task."""

from __future__ import annotations

import re
from dataclasses import dataclass

from odyssey_core.application import WritePreflightGuardError
from odyssey_core.notes import NoteFormatError, NoteValidationError, parse_note, validate_note
from odyssey_core.reference_preflight import UnitTargetPreflight
from odyssey_core.request_planning import WriteAction
from odyssey_core.storage import NoteUnavailableError, VaultRepository
from odyssey_core.write_target import WriteTargetOutcome

from .interpretation import TaskOperation
from .schema import TASK_STATUS_VALUES, TASK_TYPE

_ALLOWED_FROM = {
    TaskOperation.START: frozenset({"pending"}),
    TaskOperation.COMPLETE: frozenset({"pending", "in_progress"}),
    TaskOperation.REOPEN: frozenset({"completed"}),
    TaskOperation.CANCEL: frozenset({"pending", "in_progress"}),
    TaskOperation.UPDATE: frozenset({"pending", "in_progress"}),
}


@dataclass(frozen=True, slots=True)
class TaskLifecycleGuard:
    """Authorize one Tasks v0 transition against freshly resolved canonical state."""

    operation: TaskOperation

    def __call__(
        self,
        action: WriteAction,
        preflight: tuple[UnitTargetPreflight, ...],
        repository: VaultRepository,
        schema: dict,
    ) -> None:
        primary = [
            (index, unit)
            for index, unit in enumerate(action.units)
            if not unit.reference_lookup_only
        ]
        if len(primary) != 1:
            raise WritePreflightGuardError("TASK_INVALID_WRITE_SHAPE")
        unit_index, unit = primary[0]
        if unit.target.type != TASK_TYPE or unit.cardinality != "one":
            raise WritePreflightGuardError("TASK_INVALID_WRITE_SHAPE")
        decision = next((item for item in preflight if item.unit_index == unit_index), None)
        if decision is None:
            raise WritePreflightGuardError("TASK_TARGET_UNAVAILABLE")
        # Preserve Core's own clarification/deferred target outcome rather than replacing it.
        if decision.outcome not in {WriteTargetOutcome.CREATE, WriteTargetOutcome.UPDATE}:
            return
        _validate_task_relationships(unit, decision, preflight, repository, schema)
        if self.operation is TaskOperation.CREATE:
            if decision.outcome is not WriteTargetOutcome.CREATE:
                raise WritePreflightGuardError("TASK_ALREADY_EXISTS")
            return
        if decision.outcome is not WriteTargetOutcome.UPDATE or decision.stable_id is None:
            raise WritePreflightGuardError("TASK_TARGET_MUST_EXIST")
        note = _load_task(repository, schema, decision.stable_id)
        status = note.metadata.get("status")
        if status not in TASK_STATUS_VALUES:
            raise WritePreflightGuardError("TASK_STATUS_INVALID")
        allowed = _ALLOWED_FROM.get(self.operation)
        if allowed is None or status not in allowed:
            raise WritePreflightGuardError("TASK_INVALID_TRANSITION")


_PARENT_LINK = re.compile(r"Tarea superior:\s*\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
_ASSIGNEE_LINK = re.compile(r"Responsable:\s*\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def _validate_task_relationships(
    unit,  # type: ignore[no-untyped-def]
    decision: UnitTargetPreflight,
    preflight: tuple[UnitTargetPreflight, ...],
    repository: VaultRepository,
    schema: dict,
) -> None:
    """Keep Tasks role relations singular and parent graphs acyclic after exact Core resolution."""
    parent_refs = [ref for ref in unit.references if ref.role == "parent_task"]
    assignee_refs = [ref for ref in unit.references if ref.role == "assignee"]
    if len(parent_refs) > 1 or len(assignee_refs) > 1:
        raise WritePreflightGuardError("TASK_RELATIONSHIP_CARDINALITY")
    if decision.outcome is WriteTargetOutcome.UPDATE and decision.stable_id is not None:
        current = _load_task(repository, schema, decision.stable_id)
        if parent_refs and _PARENT_LINK.search(current.content):
            raise WritePreflightGuardError("TASK_PARENT_ALREADY_SET")
        if assignee_refs and _ASSIGNEE_LINK.search(current.content):
            raise WritePreflightGuardError("TASK_ASSIGNEE_ALREADY_SET")
    if not parent_refs:
        return
    reference = parent_refs[0]
    if reference.target_index is None:
        raise WritePreflightGuardError("TASK_PARENT_UNAVAILABLE")
    parent = next((item for item in preflight if item.unit_index == reference.target_index), None)
    if (
        parent is None
        or parent.outcome is not WriteTargetOutcome.UPDATE
        or parent.stable_id is None
    ):
        return
    task_id = decision.stable_id
    if task_id is None:
        raise WritePreflightGuardError("TASK_TARGET_UNAVAILABLE")
    if parent.stable_id == task_id:
        raise WritePreflightGuardError("TASK_PARENT_CYCLE")
    parent_map = _task_parent_map(repository, schema)
    seen: set[str] = set()
    cursor: str | None = parent.stable_id
    while cursor is not None:
        if cursor == task_id or cursor in seen:
            raise WritePreflightGuardError("TASK_PARENT_CYCLE")
        seen.add(cursor)
        cursor = parent_map.get(cursor)


def _task_parent_map(repository: VaultRepository, schema: dict) -> dict[str, str]:
    notes: list[object] = []
    path_to_id: dict[str, str] = {}
    for path in repository.list_markdown_paths():
        try:
            note = parse_note(repository.read_text(path))
            validate_note(note, schema)
        except (NoteUnavailableError, NoteFormatError, NoteValidationError, ValueError) as error:
            raise WritePreflightGuardError("TASK_STATE_UNAVAILABLE") from error
        note_id = note.metadata.get("id")
        if not isinstance(note_id, str) or not note_id:
            raise WritePreflightGuardError("TASK_STATE_UNAVAILABLE")
        path_to_id[path.removesuffix(".md").casefold()] = note_id
        notes.append(note)
    result: dict[str, str] = {}
    for note in notes:
        if note.metadata.get("type") != TASK_TYPE or note.metadata.get("deleted") is True:
            continue
        matches = _PARENT_LINK.findall(note.content)
        if len(matches) > 1:
            raise WritePreflightGuardError("TASK_PARENT_CARDINALITY_INVALID")
        if not matches:
            continue
        parent_id = path_to_id.get(matches[0].removesuffix(".md").casefold())
        if parent_id is None:
            raise WritePreflightGuardError("TASK_PARENT_UNAVAILABLE")
        result[str(note.metadata["id"])] = parent_id
    return result


def _load_task(repository: VaultRepository, schema: dict, stable_id: str):  # type: ignore[no-untyped-def]
    matches = []
    for path in repository.list_markdown_paths():
        try:
            note = parse_note(repository.read_text(path))
            validate_note(note, schema)
        except (NoteUnavailableError, NoteFormatError, NoteValidationError, ValueError) as error:
            raise WritePreflightGuardError("TASK_STATE_UNAVAILABLE") from error
        if note.metadata.get("id") == stable_id:
            matches.append(note)
    if len(matches) != 1 or matches[0].metadata.get("type") != TASK_TYPE:
        raise WritePreflightGuardError("TASK_TARGET_UNAVAILABLE")
    return matches[0]
