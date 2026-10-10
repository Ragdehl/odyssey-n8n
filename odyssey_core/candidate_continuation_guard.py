"""Bound a reviewed continuation write to one user-selected canonical identity.

This Core-owned preflight verifies the selected identity and exact original
reference at the last possible moment. It does not prove that a model's plan
preserves the event, date, polarity or source candidate meaning. Production
activation must wait for a separate semantic gate and pending completion flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .application import WritePreflightGuardError
from .candidate_pending_state import CandidatePendingRepository
from .reference_preflight import UnitTargetPreflight
from .request_planning import WriteAction
from .storage import VaultRepository
from .write_target import WriteTargetOutcome


@dataclass(frozen=True, slots=True)
class SelectedCandidateWriteGuard:
    """Reject a linked Core plan not targeting the exact chosen, still-current note."""

    pending: CandidatePendingRepository
    conversation_id: str
    original_request_id: str
    selected_note_id: str
    selected_guard: str
    pending_reference_text: str
    original_captured_at: str

    def __call__(
        self,
        action: WriteAction,
        preflight: tuple[UnitTargetPreflight, ...],
        repository: VaultRepository,
        schema: dict[str, Any],
    ) -> None:
        """Check ordinary Core target resolution without allocating another identity."""
        ready = self.pending.selected_for_core_review(
            conversation_id=self.conversation_id,
            request_id=self.original_request_id,
            vault=repository,
            schema=schema,
        )
        if (
            ready.outcome != "choice_ready_for_core_review"
            or ready.selected_note_id != self.selected_note_id
            or ready.selected_guard != self.selected_guard
            or ready.captured_at != self.original_captured_at
            or not isinstance(action, WriteAction)
            or len(action.units) != 2
            or len(preflight) != 2
        ):
            raise WritePreflightGuardError("CANDIDATE_SELECTED_EVIDENCE_STALE")
        consumers = [i for i, unit in enumerate(action.units) if unit.facts]
        helpers = [i for i, unit in enumerate(action.units) if unit.reference_lookup_only]
        if len(consumers) != 1 or len(helpers) != 1 or consumers[0] == helpers[0]:
            raise WritePreflightGuardError("CANDIDATE_CONTINUATION_UNSUPPORTED_WRITE_SHAPE")
        fact_index, helper_index = consumers[0], helpers[0]
        fact_unit, helper_unit = action.units[fact_index], action.units[helper_index]
        identity_target = preflight[helper_index]
        if (
            len(fact_unit.facts) != 1
            or fact_unit.intent != "record"
            or fact_unit.properties
            or fact_unit.tag_changes
            or len(fact_unit.references) != 1
            or fact_unit.references[0].target_index != helper_index
            or fact_unit.references[0].mention != self.pending_reference_text
            or "{{ref:0}}" not in fact_unit.facts[0]
            or helper_unit.facts
            or helper_unit.references
            or helper_unit.properties
            or helper_unit.tag_changes
            or helper_unit.intent != "record"
            or identity_target.unit_index != helper_index
            or identity_target.outcome is not WriteTargetOutcome.UPDATE
            or identity_target.stable_id != self.selected_note_id
            or not identity_target.reference_only
        ):
            raise WritePreflightGuardError("CANDIDATE_CONTINUATION_IDENTITY_MISMATCH")


def build_selected_candidate_guard(
    pending: CandidatePendingRepository,
    *,
    conversation_id: str,
    request_id: str,
    vault: VaultRepository,
    schema: dict[str, Any],
) -> SelectedCandidateWriteGuard | None:
    """Return a narrow last-moment guard only for one originally scoped reference.

    The chosen identity is durable Core clarification evidence; the requested
    event still requires an independently reviewed Core plan. Never feed raw
    selected IDs to Router, Temporal, or an app-side mini planner.
    """
    decision = pending.selected_for_core_review(
        conversation_id=conversation_id,
        request_id=request_id,
        vault=vault,
        schema=schema,
    )
    if decision.outcome != "choice_ready_for_core_review":
        return None
    record = pending.read(request_id)
    if len(record["pending"]) != 1 or not record["pending"][0]["reference_text"]:
        return None
    ref = record["pending"][0]["reference_text"]
    if (
        len(ref) > 160
        or not decision.selected_note_id
        or not decision.selected_guard
        or not decision.captured_at
    ):
        return None
    return SelectedCandidateWriteGuard(
        pending,
        conversation_id,
        request_id,
        decision.selected_note_id,
        decision.selected_guard,
        ref,
        decision.captured_at,
    )
