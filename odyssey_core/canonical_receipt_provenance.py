"""Verify action-bound, physically current Core dependency receipts.

A current Markdown digest is necessary but cannot by itself prove that the
claimed action actually materialized the referenced identity.
"""

from __future__ import annotations

from typing import Any

from .application import (
    ActionResult,
    ApplicationResult,
    CanonicalReferenceEvidence,
    UnitStatus,
    _dependent_evidence_is_current,
)
from .storage import VaultRepository


def materialized_core_receipt(
    proof: CanonicalReferenceEvidence,
    action: ActionResult,
    predecessor: ApplicationResult,
    repository: VaultRepository,
    schema: dict[str, Any],
) -> bool:
    """Require an action's successful unit and a live canonical source/target.

    Direct receipts must come from an actual CREATE of their own source Note;
    linked receipts must come from a materialized source unit in that action.
    Inspect *every* matching receipt, not merely the selected representative.
    """
    if (
        not isinstance(proof, CanonicalReferenceEvidence)
        or proof.action_index != action.action_index
        or proof.source_unit_index < 0
        or proof.source_reference_index < -1
        or proof.source_note_id not in predecessor.affected_stable_note_ids
        or not _dependent_evidence_is_current(proof, repository, schema)
    ):
        return False
    units = tuple(
        unit for unit in action.unit_results if unit.unit_index == proof.source_unit_index
    )
    if len(units) != 1:
        return False
    unit = units[0]
    if (
        unit.status is not UnitStatus.SUCCEEDED
        or not unit.materially_affected
        or unit.stable_note_id != proof.source_note_id
    ):
        return False
    if proof.source_reference_index == -1:
        return (
            proof in action.canonical_direct_target_evidence
            and unit.operation == "CREATED"
            and proof.source_note_id == proof.stable_note_id
            and proof.source_content_guard == proof.canonical_content_guard
        )
    return proof in action.canonical_reference_evidence
