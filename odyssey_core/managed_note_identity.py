"""Read-only app-owned Note identity ports for E2 composable context.

Managed Notes and virtual Days are NOT silently promoted into ordinary fact
references. Each owner retains its established lifecycle/identity rules, while
all consumers see a common, typed, non-authorizing projection.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .execution_context import (
    ContextContractError,
    ContextPort,
    ManagedNoteHandle,
    StageInput,
    StageOutput,
    StageSpec,
)
from .schema_types import canonical_type_definitions
from .temporal import CalendarDayRepository, normalize_iso_date


@runtime_checkable
class ManagedNoteIdentityPort(Protocol):
    """A structural, owner-specific read-only identity port.

    Inheritance is unnecessary: compatible objects match this shape. A static
    checker validates parameter and return types; Python's isinstance only
    checks that required method names exist. The execution boundary validates
    returned values and ownership against the composed runtime NoteSchema.
    """

    note_type: str

    def locate(self, key: str) -> ManagedNoteHandle:
        """Read one existing/virtual canonical Note identity; never write."""
        ...


class CalendarDayIdentityPort:
    """Reuse Core-owned deterministic Day identity, including virtual Days."""

    note_type = "calendar_day"

    def __init__(self, days: CalendarDayRepository) -> None:
        self._days = days

    def locate(self, key: str) -> ManagedNoteHandle:
        day = self._days.resolve(normalize_iso_date(key))
        return ManagedNoteHandle(day.id, self.note_type, "core", day.materialized)


class WorkSessionSnapshotPort(Protocol):
    """Only the stable canonical ID is necessary at the E2 read boundary."""

    id: str


class WorkSessionReader(Protocol):
    """Tasks lifecycle service satisfies this without Core importing Tasks."""

    def list_for_task(self, task_id: str) -> tuple[WorkSessionSnapshotPort, ...]: ...


class WorkSessionIdentityPort:
    """Reuse Tasks' already-authorized task ownership + session listing.

    Explicit Task scope is fixed when composing this port. It cannot resolve
    arbitrary user wording to a Work Session, and does not authorize generic
    links to Work Sessions (currently referenceable=False in Tasks schema).
    """

    note_type = "work_session"

    def __init__(self, sessions: WorkSessionReader, *, task_id: str) -> None:
        if not isinstance(task_id, str) or not task_id.strip():
            raise ContextContractError("Work Session lookup needs exact Task scope")
        self._sessions = sessions
        self._task_id = task_id

    def locate(self, key: str) -> ManagedNoteHandle:
        if not isinstance(key, str) or not key.strip():
            raise ContextContractError("Work Session lookup needs exact session ID")
        matches = [
            session for session in self._sessions.list_for_task(self._task_id) if session.id == key
        ]
        if len(matches) != 1:
            raise ContextContractError("Work Session is not uniquely in Task scope")
        return ManagedNoteHandle(matches[0].id, self.note_type, "tasks", True)


def locate_managed_note(
    port: ManagedNoteIdentityPort, key: str, *, schema: dict[str, Any]
) -> ManagedNoteHandle:
    """A common checked boundary for Calendar, Work Sessions and later Apps.

    A schema extension controls owner and referenceability. This read-only
    result cannot be confused with an authorized NoteReferenceCandidate.
    """
    if not isinstance(port, ManagedNoteIdentityPort):
        raise ContextContractError("Managed Note port is missing required capabilities")
    definition = next(
        (item for item in canonical_type_definitions(schema) if item.get("id") == port.note_type),
        None,
    )
    if definition is None or not isinstance(definition.get("managed_by"), str):
        raise ContextContractError("Managed Note type has no schema owner")
    result = port.locate(key)
    if (
        not isinstance(result, ManagedNoteHandle)
        or result.note_type != port.note_type
        or result.owner != definition["managed_by"]
    ):
        raise ContextContractError("Managed Note adapter returned incorrect owner or type")
    return result


class ManagedNoteContextStage:
    """E2 adapter connecting any owner-specific NoteIdentityPort to the same context.

    Keys originate in a separate typed read/UI request, never from a model's
    claimed Note ID. Outputs are located read-only handles, not NoteReferences
    and not evidence that a current note may be written or linked by Core.
    """

    spec = StageSpec(
        "core.managed_notes",
        frozenset({ContextPort.SOURCE}),
        frozenset({ContextPort.MANAGED_NOTES}),
    )

    def __init__(
        self,
        *,
        lookups: tuple[tuple[ManagedNoteIdentityPort, str], ...],
        schema: dict[str, Any],
    ) -> None:
        if not isinstance(lookups, tuple) or not 1 <= len(lookups) <= 8:
            raise ContextContractError("Managed Note stage has invalid lookup count")
        self._lookups = lookups
        self._schema = schema

    def execute(self, data: StageInput) -> StageOutput:
        if not isinstance(data.source, str) or not data.source.strip():
            raise ContextContractError("Managed Note request has no source boundary")
        handles = tuple(
            locate_managed_note(port, key, schema=self._schema) for port, key in self._lookups
        )
        return StageOutput(managed_notes=handles)
