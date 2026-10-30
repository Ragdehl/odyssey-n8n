"""Bound a reviewed continuation write to one user-selected canonical identity.

This Core-owned preflight verifies the selected identity and exact original
reference at the last possible moment. It does not prove that a model's plan
preserves the event, date, polarity or source candidate meaning. Production
activation must wait for a separate semantic gate and pending completion flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
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
class SelectedCandidateWriteGuard:
    """Reject a linked Core plan not targeting the exact chosen, still-current note."""

    pending: CandidatePendingRepository
    conversation_id: str
    original_request_id: str
    selected_note_id: str
    selected_guard: str
    pending_reference_text: str
    original_captured_at: str
    pending_source_text: str

    def validate_request_plan(self, plan: RequestPlan) -> None:
        """Reject extra actions or wrong event/date before any Core write begins.

        This opt-in pilot handles only the exact frozen F14/F27 pending cinema
        phrase. A broader source grammar will require independent semantic
        evidence; an arbitrary model paraphrase must not acquire write access.
        """
        if (
            not isinstance(plan, RequestPlan)
            or len(plan.actions) != 1
            or not isinstance(plan.actions[0], WriteAction)
            or plan.limitations
            or plan.presentation_intent != "answer"
            or self.pending_source_text != "Mañana iré al cine con él"
            or self.pending_reference_text != "él"
        ):
            raise WritePreflightGuardError("CANDIDATE_CONTINUATION_UNSUPPORTED_PLAN")
        try:
            expected_date = (
                datetime.fromisoformat(self.original_captured_at).date() + timedelta(days=1)
            ).isoformat()
        except (TypeError, ValueError, OverflowError) as error:
            raise WritePreflightGuardError("CANDIDATE_CONTINUATION_INVALID_CLOCK") from error
        action = plan.actions[0]
        if len(action.units) != 2:
            raise WritePreflightGuardError("CANDIDATE_CONTINUATION_UNSUPPORTED_WRITE_SHAPE")
        consumers = [item for item in action.units if item.facts]
        helpers = [item for item in action.units if item.reference_lookup_only]
        if len(consumers) != 1 or len(helpers) != 1 or consumers[0] == helpers[0]:
            raise WritePreflightGuardError("CANDIDATE_CONTINUATION_UNSUPPORTED_WRITE_SHAPE")
        fact, helper = consumers[0], helpers[0]
        target = fact.target
        if (
            fact.intent != "record"
            or fact.force_create
            or fact.reference_lookup_only
            or fact.cardinality != "one"
            or fact.properties
            or fact.tag_changes
            or fact.destination_type is not None
            or fact.facts != ("Iré al cine con {{ref:0}}.",)
            or len(fact.references) != 1
            or fact.references[0].mention != self.pending_reference_text
            or len(fact.fact_temporal_anchors) != 1
            or len(fact.fact_temporal_anchors[0]) != 1
            or fact.fact_temporal_anchors[0][0].value != expected_date
            or target.type != "calendar_day"
            or target.query != expected_date
            or target.entity is not None
            or target.filters
            or target.link_scope is not None
            or target.self_target is not None
            or target.relational_reference is not None
            or target.semantic_set is not None
            or target.collection_subject is not None
            or helper.force_create
            or not helper.reference_lookup_only
            or helper.intent != "record"
            or helper.facts
            or helper.references
            or helper.properties
            or helper.tag_changes
            or helper.destination_type is not None
            or helper.cardinality != "one"
        ):
            raise WritePreflightGuardError("CANDIDATE_CONTINUATION_SOURCE_OR_DATE_MISMATCH")

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
        ):
            raise WritePreflightGuardError("CANDIDATE_CONTINUATION_IDENTITY_MISMATCH")
        _verify_selected_reference_preflight(
            action,
            preflight,
            reference_text=self.pending_reference_text,
            selected_note_id=self.selected_note_id,
        )


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
        record["pending"][0]["text"],
    )


@dataclass(frozen=True, slots=True)
class ReviewedCandidateContinuationWriteGuard:
    """Experimental E3 preflight for a complete, independently checked Core plan.

    It has no runtime wiring or model authorization. This exists solely to
    exercise the eventual write boundary with synthetic reviewed decisions.
    Live adoption additionally needs fresh model-semantic acceptance, a
    durable completion receipt and replay/readback lifecycle.
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
        if repository is not self._bound_vault or schema is not self._bound_schema:
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
