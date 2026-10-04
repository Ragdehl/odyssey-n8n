"""Tasks lifecycle invariants evaluated after Core resolves the exact canonical task."""

from __future__ import annotations

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
