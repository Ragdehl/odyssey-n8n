"""Generic semantic-reviewed E3 continuation guard, separate from the F14/F27 pilot.

This Core-owned gate validates a previously inspected and independently
reviewed full plan before any write, then checks the canonical selected target
at Core's ordinary preflight. Importing it must NOT import the legacy
phrase-specific continuation validator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .application import WritePreflightGuardError
from .candidate_continuation_context import CoreCandidateContinuationContext
from .candidate_continuation_plan import CoreContinuationPlanInspection
from .candidate_continuation_semantic import (
    CandidateContinuationSemanticError,
    CoreContinuationSemanticVerdict,
    validate_independent_continuation_verdict_current,
)
from .candidate_pending_state import CandidatePendingRepository
from .reference_preflight import UnitTargetPreflight
from .request_planning import RequestPlan, WriteAction
from .storage import VaultRepository
from .write_target import WriteTargetOutcome


def _verify_selected_reference_preflight(
    action: WriteAction,
    preflight: tuple[UnitTargetPreflight, ...],
    *,
    reference_text: str,
    selected_note_id: str,
) -> None:
    """One canonical-target proof shared by the frozen pilot and reviewed path.

    The plan-level semantic guards remain separate: the old test-only pilot
    permits its exact historical shape, whereas the general route requires a
    source-bound independent review. Neither guard resolves an identity itself.
    """
    if not isinstance(action, WriteAction) or len(action.units) != len(preflight):
        raise WritePreflightGuardError("CANDIDATE_CONTINUATION_PREFLIGHT_MISMATCH")
    found_selected = False
    for index, unit in enumerate(action.units):
        if unit.reference_lookup_only:
            resolved = preflight[index]
            if (
                resolved.unit_index != index
                or not resolved.reference_only
                or resolved.outcome is not WriteTargetOutcome.UPDATE
                or not resolved.stable_id
            ):
                raise WritePreflightGuardError("CANDIDATE_CONTINUATION_HELPER_NOT_VERIFIED")
        for reference in unit.references:
            target_index = reference.target_index
            if (
                type(target_index) is not int
                or not 0 <= target_index < len(action.units)
                or not action.units[target_index].reference_lookup_only
            ):
                raise WritePreflightGuardError("CANDIDATE_CONTINUATION_REFERENCE_NOT_GROUNDED")
            if reference.mention == reference_text:
                found_selected = True
                if preflight[target_index].stable_id != selected_note_id:
                    raise WritePreflightGuardError("CANDIDATE_CONTINUATION_SELECTED_ID_CHANGED")
    if not found_selected:
        raise WritePreflightGuardError("CANDIDATE_CONTINUATION_SELECTED_REF_MISSING")


@dataclass(frozen=True, slots=True)
class ReviewedCandidateContinuationWriteGuard:
    """Experimental E3 preflight for a complete, independently checked Core plan.

    Used by the optional DEV source-continuation callback and synthetic
    product tests. It never invokes a model or grants independent write
    authority: actual Core/E3 execution additionally requires fresh semantic
    review, an actor-bound delivery claim and physical readback/replay.
    """

    pending: CandidatePendingRepository
    context: CoreCandidateContinuationContext
    inspection: CoreContinuationPlanInspection
    verdict: CoreContinuationSemanticVerdict
    review: dict[str, Any]
    original_plan: RequestPlan
    _bound_vault: VaultRepository
    _bound_schema: dict[str, Any]

    def validate_request_plan(self, plan: RequestPlan) -> None:
        """Veto the *entire* altered plan before the first Core write action."""
        if (
            not isinstance(plan, RequestPlan)
            or plan != self.original_plan
            or len(plan.actions) != 1
            or not isinstance(plan.actions[0], WriteAction)
        ):
            raise WritePreflightGuardError("CANDIDATE_CONTINUATION_PLAN_CHANGED")
        try:
            # No semantic authority is granted by this local validity check.
            validate_independent_continuation_verdict_current(
                self.verdict,
                self.context,
                self.inspection,
                self.review,
                plan,
                self.pending,
                vault=self._bound_vault,
                schema=self._bound_schema,
            )
        except CandidateContinuationSemanticError as error:
            raise WritePreflightGuardError("CANDIDATE_CONTINUATION_REVIEW_STALE") from error

    def __call__(
        self,
        action: WriteAction,
        preflight: tuple[UnitTargetPreflight, ...],
        repository: VaultRepository,
        schema: dict[str, Any],
    ) -> None:
        """Recheck current selection and actual Core target IDs after preflight."""
        # Core intentionally deep-copies the canonical schema for its
        # capability-scoped plan/execution snapshot. Identity would reject
        # this exact, unchanged copy during ordinary E3 execution; content
        # equality still vetoes a changed schema while vault identity stays
        # strict to prevent actor/storage swaps.
        if (
            repository is not self._bound_vault
            or not isinstance(schema, dict)
            or schema != self._bound_schema
        ):
            raise WritePreflightGuardError("CANDIDATE_CONTINUATION_CONTEXT_MISMATCH")
        self.validate_request_plan(self.original_plan)
        if (
            not isinstance(action, WriteAction)
            or action != self.original_plan.actions[0]
            or len(action.units) != len(preflight)
        ):
            raise WritePreflightGuardError("CANDIDATE_CONTINUATION_ACTION_CHANGED")
        _verify_selected_reference_preflight(
            action,
            preflight,
            reference_text=self.context.reference_text,
            selected_note_id=self.context.selected_note_id,
        )
