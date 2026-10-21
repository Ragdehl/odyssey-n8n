"""E5 trusted Events mutation boundary reusing Core preflight, Writer and E3 gate.

This service consumes an already-authorized Events intent plus TemporalAnchor
values. It is NOT a natural-language interpreter or an HTTP endpoint: neither
LLM proposals nor user text may call it until Router/E2/E3 permissions,
conversation delivery idempotency and actor checks are integrated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from odyssey_core.git_history import HistoryRecorder
from odyssey_core.materialization import (
    MaterializationError,
    materialize_create,
    materialize_update,
)
from odyssey_core.mutation_gate import (
    CanonicalCreateReceipt,
    CanonicalMutationError,
    CanonicalMutationGate,
    CanonicalMutationReceipt,
    CanonicalPostwriteError,
    CreateMutationCommand,
    MutationCommand,
)
from odyssey_core.persistence import ActorInput, PersistenceOperation
from odyssey_core.reference_preflight import ReferencePreflightError, preflight_write_action
from odyssey_core.request_planning import (
    KnowledgeUnit,
    PropertyChange,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal import TemporalAnchor
from odyssey_core.write_target import WriteTargetDecision, WriteTargetOutcome

from .schema import EVENT_TYPE


class EventMutationError(ValueError):
    """Unsafe transition or unresolved canonical identity."""

    def __init__(self, code: str, *, physical_write: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.physical_write = physical_write


@dataclass(frozen=True, slots=True)
class EventOccurrence:
    """Coordinates resolved upstream by Temporal; never a model-created Note ID."""

    start: TemporalAnchor
    end: TemporalAnchor | None = None
    recurrence_weekday: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.start, TemporalAnchor) or (
            self.end is not None and not isinstance(self.end, TemporalAnchor)
        ):
            raise EventMutationError("TEMPORAL_EVIDENCE_REQUIRED")
        if self.recurrence_weekday is not None:
            if (
                type(self.recurrence_weekday) is not int
                or not 0 <= self.recurrence_weekday <= 6
                or self.end is None
                or self.start.time is not None
                or self.end.time is not None
            ):
                raise EventMutationError("BOUNDED_WEEKLY_RECURRENCE_REQUIRED")
        if self.end is not None:
            if self.end.date < self.start.date:
                raise EventMutationError("EVENT_INTERVAL_INVALID")
            if self.end.time is not None:
                if self.start.time is None:
                    raise EventMutationError("EVENT_INTERVAL_INVALID")
                if datetime.fromisoformat(self.end.value) <= datetime.fromisoformat(
                    self.start.value
                ):
                    raise EventMutationError("EVENT_INTERVAL_INVALID")
            if self.start.time is not None and self.end.time is None:
                raise EventMutationError("EVENT_INTERVAL_INVALID")

    def properties(self) -> tuple[PropertyChange, ...]:
        values: list[PropertyChange] = [
            PropertyChange("start_date", "set", self.start.date),
        ]
        if self.end is not None:
            values.append(PropertyChange("end_date", "set", self.end.date))
        if self.start.time is not None:
            values.append(PropertyChange("start_at", "set", self.start.value))
        if self.end is not None and self.end.time is not None:
            values.append(PropertyChange("end_at", "set", self.end.value))
        if self.recurrence_weekday is not None:
            values.append(PropertyChange("recurrence_weekday", "set", self.recurrence_weekday))
        return tuple(values)


class EventMutationService:
    """Only trusted callers: domain validation, Core allocation, E3 receipts."""

    def __init__(
        self,
        repository: VaultRepository,
        schema: dict[str, Any],
        history: HistoryRecorder | None = None,
    ) -> None:
        self.repository = repository
        self.schema = schema
        self._gate = CanonicalMutationGate(repository, schema, history)

    def create(
        self,
        *,
        name: str,
        source_text: str,
        occurrence: EventOccurrence,
        request_id: str,
        actor: ActorInput,
        now: str,
    ) -> CanonicalCreateReceipt:
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name) > 200
            or not isinstance(source_text, str)
            or not source_text.strip()
            or len(source_text) > 4096
            or "\n" in source_text
            or "\r" in source_text
            or not isinstance(occurrence, EventOccurrence)
        ):
            raise EventMutationError("EVENT_SOURCE_INVALID")
        unit = KnowledgeUnit(
            SelectionCriteria(name.strip(), name.strip(), EVENT_TYPE, (), None),
            "record",
            (PropertyChange("event_status", "set", "scheduled"), *occurrence.properties()),
            (),
            (source_text,),
            (),
            "one",
            fact_temporal_anchors=((occurrence.start,),),
            force_create=True,
        )
        try:
            selection = preflight_write_action(
                WriteAction((unit,)),
                repository=self.repository,
                schema=self.schema,
                semantic_index=None,
                embedder=None,
                contextual_reasoner=None,
                semantic_limit=10,
            )[0]
            if (
                selection.outcome is not WriteTargetOutcome.CREATE
                or selection.stable_id is None
                or selection.path is None
            ):
                raise EventMutationError("EVENT_CREATE_UNAVAILABLE")
            receipt = self._gate.execute_create(
                CreateMutationCommand(
                    "event_created",
                    selection.stable_id,
                    selection.path,
                    EVENT_TYPE,
                    request_id,
                    actor,
                    now,
                ),
                lambda _parent: materialize_create(
                    unit,
                    selection,
                    unit_index=0,
                    repository=self.repository,
                    schema=self.schema,
                    actor=actor,
                    now=now,
                    request_id=request_id,
                    fact_ordinals=(0,),
                ),
            )
        except CanonicalPostwriteError as error:
            raise EventMutationError("POSTWRITE_UNVERIFIED", physical_write=True) from error
        except (
            ReferencePreflightError,
            CanonicalMutationError,
            MaterializationError,
            ValueError,
        ) as error:
            if isinstance(error, EventMutationError):
                raise
            raise EventMutationError("EVENT_CREATE_UNAVAILABLE") from error
        if receipt.persistence.operation is not PersistenceOperation.CREATED:
            raise EventMutationError("EVENT_CREATE_UNAVAILABLE")
        return receipt

    def change(
        self,
        *,
        note_id: str,
        expected_revision: int,
        expected_source_hash: str,
        request_id: str,
        actor: ActorInput,
        now: str,
        operation: str,
        occurrence: EventOccurrence | None = None,
    ) -> CanonicalMutationReceipt:
        if operation not in {"cancel", "reschedule"}:
            raise EventMutationError("EVENT_OPERATION_INVALID")
        if operation == "reschedule" and not isinstance(occurrence, EventOccurrence):
            raise EventMutationError("TEMPORAL_EVIDENCE_REQUIRED")
        if operation == "cancel" and occurrence is not None:
            raise EventMutationError("EVENT_OPERATION_INVALID")
        command = MutationCommand(
            "event_" + operation,
            note_id,
            expected_revision,
            expected_source_hash,
            request_id,
            actor,
            now,
            EVENT_TYPE,
        )
        try:
            target = self._gate.prepare(command)
            if target.note.metadata.get("event_status") != "scheduled":
                raise EventMutationError("EVENT_INVALID_TRANSITION")
            changes: tuple[PropertyChange, ...]
            if operation == "cancel":
                changes = (PropertyChange("event_status", "set", "cancelled"),)
            else:
                assert occurrence is not None
                existing = target.note.metadata
                changes = occurrence.properties() + tuple(
                    PropertyChange(field, "remove", None)
                    for field in ("end_date", "start_at", "end_at", "recurrence_weekday")
                    if field in existing
                    and not any(changed.field == field for changed in occurrence.properties())
                )
            unit = KnowledgeUnit(
                SelectionCriteria(
                    target.note.metadata["name"], target.note.metadata["name"], EVENT_TYPE, (), None
                ),
                "amend",
                changes,
                (),
                (),
                (),
                "one",
            )
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
                    fact_ordinals=(),
                ),
            )
        except CanonicalPostwriteError as error:
            raise EventMutationError("POSTWRITE_UNVERIFIED", physical_write=True) from error
        except (CanonicalMutationError, MaterializationError, ValueError) as error:
            if isinstance(error, EventMutationError):
                raise
            raise EventMutationError("EVENT_TARGET_UNAVAILABLE") from error
        if receipt.persistence.operation is not PersistenceOperation.UPDATED or (
            operation == "cancel" and receipt.readback.metadata.get("event_status") != "cancelled"
        ):
            raise EventMutationError("EVENT_POSTWRITE_UNVERIFIED", physical_write=True)
        return receipt
