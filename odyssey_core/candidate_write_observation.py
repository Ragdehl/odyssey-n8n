"""Read-only, bounded Core write receipts beside unverified Router fact candidates.

A candidate has no verified mapping to a Core action or persisted atomic fact in
Router v1. This module deliberately never infers one from order, shared dates,
matching names or numerical equality between candidate count and fact count.
"""

from __future__ import annotations

from dataclasses import dataclass

from .application import ActionResult, ApplicationResult
from .candidate_context import CoreCandidateContext
from .request_planning import RequestPlan, WriteAction, plan_fact_ordinals

MAX_OBSERVED_CORE_ACTIONS = 32
MAX_OBSERVED_CORE_WRITE_UNITS = 128


@dataclass(frozen=True, slots=True)
class ObservedCoreWriteUnit:
    """Record an actual Core write-unit outcome without claiming candidate identity."""

    action_index: int
    unit_index: int
    fact_ordinals: tuple[int, ...]
    status: str
    reference_lookup_only: bool


@dataclass(frozen=True, slots=True)
class CandidateWriteObservation:
    """Separate Core-confirmed write outcomes from unverified source candidates."""

    candidate_ids: tuple[str, ...]
    attribution_status: str
    ambiguous_candidate_ids: tuple[str, ...]
    core_request_status: str
    observed_core_write_units: tuple[ObservedCoreWriteUnit, ...]


def observe_candidate_write_outcomes(
    source: str,
    context: CoreCandidateContext,
    plan: RequestPlan,
    result: ApplicationResult,
) -> CandidateWriteObservation:
    """Observe a real Core execution without inventing a candidate→fact mapping.

    Args:
        source: Exactly the unchanged current user request.
        context: Independently revalidated, Core-owned candidate source packet.
        plan: Core's validated request-level plan, not a Router-derived rewrite.
        result: Result returned by ordinary Core execution for that plan.

    Returns:
        Bounded per-Core-unit statuses and an explicit ``unattributed`` marker
        for *all* proposed fact candidates. This is not write authorization.

    Raises:
        ValueError: If request sources, action order/types, or unit outcomes
            cannot be correlated safely with the actual Core result.
    """
    if not isinstance(context, CoreCandidateContext):
        raise ValueError("Core candidate context is invalid")
    context.validate(source)
    if not isinstance(plan, RequestPlan) or not isinstance(result, ApplicationResult):
        raise ValueError("A validated Core plan and execution result are required")
    if len(plan.actions) > MAX_OBSERVED_CORE_ACTIONS:
        raise ValueError("Core write observation exceeds action budget")
    if (
        sum(len(a.units) for a in plan.actions if isinstance(a, WriteAction))
        > MAX_OBSERVED_CORE_WRITE_UNITS
    ):
        raise ValueError("Core write observation exceeds write-unit budget")
    if len(plan.actions) != len(result.action_results):
        raise ValueError("Core plan/result actions differ; outcomes cannot be correlated")
    all_ordinals = plan_fact_ordinals(plan)
    next_write_unit = 0
    receipts: list[ObservedCoreWriteUnit] = []
    for action_index, (action, outcome) in enumerate(
        zip(plan.actions, result.action_results, strict=True)
    ):
        if (
            not isinstance(outcome, ActionResult)
            or outcome.action_index != action_index
            or outcome.kind != action.kind
        ):
            raise ValueError("Core action outcome does not correspond to the plan")
        if not isinstance(action, WriteAction):
            continue
        by_unit: dict[int, str] = {}
        for observed in outcome.unit_results:
            ordinal = observed.unit_index
            if (
                not isinstance(ordinal, int)
                or isinstance(ordinal, bool)
                or not 0 <= ordinal < len(action.units)
                or ordinal in by_unit
            ):
                raise ValueError("Core unit outcomes cannot be uniquely correlated")
            by_unit[ordinal] = observed.status.value
        for unit_index, unit in enumerate(action.units):
            receipts.append(
                ObservedCoreWriteUnit(
                    action_index=action_index,
                    unit_index=unit_index,
                    fact_ordinals=all_ordinals[next_write_unit],
                    status=by_unit.get(unit_index, "not_observed"),
                    reference_lookup_only=unit.reference_lookup_only,
                )
            )
            next_write_unit += 1
    return CandidateWriteObservation(
        candidate_ids=tuple(item.candidate_id for item in context.candidates),
        attribution_status="unattributed",
        ambiguous_candidate_ids=tuple(
            item.candidate_id for item in context.candidates if item.state == "ambiguous_identity"
        ),
        core_request_status=result.status.value,
        observed_core_write_units=tuple(receipts),
    )
