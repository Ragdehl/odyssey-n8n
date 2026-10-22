"""Core-owned use case for changing canonical properties after app validation.

Apps determine which lifecycle transition is allowed. Core translates that
decision into its Writer and retains the E3 CAS, history and physical readback.
"""

from __future__ import annotations

from typing import Any

from .materialization import materialize_update
from .mutation_gate import (
    CanonicalMutationError,
    CanonicalMutationGate,
    CanonicalMutationReceipt,
    MutationCommand,
    MutationTarget,
)
from .persistence import ActorInput
from .request_planning import KnowledgeUnit, PropertyChange, SelectionCriteria
from .storage import VaultRepository
from .write_target import WriteTargetDecision, WriteTargetOutcome


def execute_prepared_property_mutation(
    *,
    gate: CanonicalMutationGate,
    command: MutationCommand,
    target: MutationTarget,
    note_type: str,
    changes: tuple[PropertyChange, ...],
    repository: VaultRepository,
    schema: dict[str, Any],
    actor: ActorInput,
    now: str,
    request_id: str,
) -> CanonicalMutationReceipt:
    """Apply a domain-authorized property update through existing E3 protections.

    The caller prepares the target and validates its domain transition first.
    E3 rechecks exact canonical revision/hash directly before physical writing.
    """
    if (
        not isinstance(gate, CanonicalMutationGate)
        or gate.repository is not repository
        or gate.schema is not schema
        or not isinstance(command, MutationCommand)
        or not isinstance(target, MutationTarget)
        or not isinstance(note_type, str)
        or not note_type
        or command.expected_type != note_type
        or target.id != command.target_id
        or target.note.metadata.get("type") != note_type
        or not isinstance(changes, tuple)
        or not changes
        or any(not isinstance(item, PropertyChange) for item in changes)
        or actor != command.actor
        or now != command.now
        or request_id != command.request_id
    ):
        raise CanonicalMutationError("PREPARED_PROPERTY_MUTATION_INVALID")

    canonical_name = target.note.metadata.get("name")
    if not isinstance(canonical_name, str) or not canonical_name:
        raise CanonicalMutationError("PREPARED_PROPERTY_MUTATION_INVALID")
    unit = KnowledgeUnit(
        SelectionCriteria(canonical_name, canonical_name, note_type, (), None),
        "amend",
        changes,
        (),
        (),
        (),
        "one",
    )
    return gate.execute_prepared(
        command,
        target,
        lambda _target: materialize_update(
            unit,
            WriteTargetDecision(WriteTargetOutcome.UPDATE, existing_note_id=target.id),
            repository=repository,
            schema=schema,
            actor=actor,
            now=now,
            request_id=request_id,
            fact_ordinals=(),
        ),
    )
