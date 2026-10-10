"""Non-executing, opt-in per-candidate use of Odyssey's EXISTING Core planner.

Core (not Router) selects one source-grounded task, gives that individual
derived task to the standard planner, and retains full original-source
provenance for subsequent all-candidate coverage and pending validation.
No writes, note type decisions or alternative LLM planners live here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Protocol

from .candidate_context import CoreCandidateContext
from .candidate_scoped_handoff import (
    CandidateScopeSafetyError,
    CoreScopedPlanningUnit,
    preview_independent_candidate_scopes,
)
from .domain_interpretation import (
    TEMPORAL_REFERENCE_EVIDENCE,
    DomainEvidence,
    DomainInterpretation,
)
from .request_planning import RequestPlan, WriteAction, plan_fact_ordinals


class ScopedCorePlanner(Protocol):
    def plan(self, request: str) -> object: ...


@dataclass(frozen=True)
class CoreScopedPlanEvidence:
    candidate_id: str
    scoped_request: str
    source_digest: str
    plan: RequestPlan


@dataclass(frozen=True)
class CoreScopedPlanningResult:
    source_digest: str
    planned: tuple[CoreScopedPlanEvidence, ...]
    pending_candidate_ids: tuple[str, ...]
    fully_reviewed_for_write: bool = False


def plan_independent_core_units(
    source: str,
    context: CoreCandidateContext,
    temporal: DomainInterpretation,
    planner_factory: Callable[[CoreScopedPlanningUnit, DomainInterpretation], ScopedCorePlanner],
) -> CoreScopedPlanningResult:
    """Call the existing Core planner ONCE PER independently verified source unit.

    temporal is the already verified original-source Temporal interpretation,
    not a Router date guess. The future date is excluded from isolated plans.
    The full original
    source and every pending candidate remain bound until a different,
    reviewed integration performs global coverage and durable pending.
    """
    preview = preview_independent_candidate_scopes(source, context)
    if (
        not isinstance(temporal, DomainInterpretation)
        or temporal.capability_id != "temporal"
        or temporal.source_text != source
        or temporal.intent != "TEMPORAL_RESOLUTION"
    ):
        raise CandidateScopeSafetyError("Temporal evidence must match full original source")
    evidence = temporal.temporal_references()
    past = [item for item in evidence if item.source_text == "Ayer"]
    future = [item for item in evidence if item.source_text == "Mañana"]
    if len(evidence) != 2 or len(past) != 1 or len(future) != 1:
        raise CandidateScopeSafetyError("Missing exact original Temporal scopes")
    anchor = past[0].temporal_anchor()
    later = future[0].temporal_anchor()
    if anchor.time is not None or later.time is not None or anchor.date >= later.date:
        raise CandidateScopeSafetyError("Original past/future Temporal evidence is invalid")
    if not callable(planner_factory):
        raise TypeError("The existing Core planner factory is required")
    planned: list[CoreScopedPlanEvidence] = []
    for unit in preview.units:
        request = unit.scoped_request()
        domain = DomainInterpretation(
            "temporal",
            request,
            "TEMPORAL_RESOLUTION",
            (DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, "Ayer", anchor.value),),
        )
        planner = planner_factory(unit, domain)
        result = planner.plan(request)
        if not isinstance(result, RequestPlan):
            raise CandidateScopeSafetyError(
                f"Core did not produce a safe per-fact plan for {unit.candidate_id}"
            )
        writes = [action for action in result.actions if isinstance(action, WriteAction)]
        if len(result.actions) != 1 or len(writes) != 1:
            raise CandidateScopeSafetyError("One independent source task must produce one write")
        actual_facts = sum(len(operation.facts) for operation in writes[0].units)
        if actual_facts != 1 or sum(len(batch) for batch in plan_fact_ordinals(result)) != 1:
            raise CandidateScopeSafetyError("One source candidate cannot produce several facts")
        operation = next((item for item in writes[0].units if item.facts), None)
        if operation is None or operation.target.query != anchor.value:
            raise CandidateScopeSafetyError("Scoped Core fact must use its Temporal date")
        expected_names = [
            role_span.text for role, role_span in unit.roles if role == "participants"
        ]
        linked_names = [reference.mention for reference in operation.references]
        if (
            len(expected_names) != len(linked_names)
            or set(expected_names) != set(linked_names)
            or len(set(linked_names)) != len(linked_names)
        ):
            raise CandidateScopeSafetyError("Core plan does not match selected source participants")
        if not operation.fact_temporal_anchors or not operation.fact_temporal_anchors[0]:
            raise CandidateScopeSafetyError("Every planned fact needs its original date")
        planned.append(
            CoreScopedPlanEvidence(unit.candidate_id, request, preview.full_source_digest, result)
        )
    return CoreScopedPlanningResult(
        preview.full_source_digest, tuple(planned), preview.pending_candidate_ids
    )


def merge_scoped_core_plans_for_review(
    source: str,
    context: CoreCandidateContext,
    scoped: CoreScopedPlanningResult,
) -> RequestPlan:
    """Join same-Day independently compiled Core writes for full-source review.

    This is a Core-only mechanical reduction, NOT a semantic planner:
    it never invents identity, dates, facts or targets. The only edits
    reindex the second already-approved identity placeholder and align
    both facts to the same Core Day target. The unchanged full-source
    candidate coverage still must accept the merged plan before a write.
    """
    preview = preview_independent_candidate_scopes(source, context)
    if (
        not isinstance(scoped, CoreScopedPlanningResult)
        or scoped.source_digest != preview.full_source_digest
        or scoped.source_digest != sha256(source.encode("utf-8")).hexdigest()
        or scoped.pending_candidate_ids != preview.pending_candidate_ids
        or len(scoped.planned) != len(preview.units)
        or any(
            item.candidate_id != unit.candidate_id
            or item.source_digest != preview.full_source_digest
            or item.scoped_request != unit.scoped_request()
            for item, unit in zip(scoped.planned, preview.units, strict=True)
        )
    ):
        raise CandidateScopeSafetyError("Scoped plans cannot be joined to the original source")
    if len(scoped.planned) == 1:
        return scoped.planned[0].plan
    if len(scoped.planned) != 2:
        raise CandidateScopeSafetyError("Unreviewed scoped plan cardinality")
    first, second = (item.plan for item in scoped.planned)
    if any(
        len(plan.actions) != 1
        or not isinstance(plan.actions[0], WriteAction)
        or len(plan.actions[0].units) != 2
        for plan in (first, second)
    ):
        raise CandidateScopeSafetyError("Only one linked Day fact per scoped plan is supported")
    first_day, first_helper = first.actions[0].units
    second_day, second_helper = second.actions[0].units
    if (
        first_day.target != second_day.target
        or first_day.target.type != "calendar_day"
        or first_day.reference_lookup_only
        or second_day.reference_lookup_only
        or len(first_day.facts) != 1
        or len(second_day.facts) != 1
        or len(first_day.references) != 1
        or len(second_day.references) != 1
        or first_day.references[0].target_index != 1
        or second_day.references[0].target_index != 1
        or first_day.references[0].mention == second_day.references[0].mention
        or not first_helper.reference_lookup_only
        or not second_helper.reference_lookup_only
        or first_helper.facts
        or second_helper.facts
        or first_day.properties != second_day.properties
        or first_day.tag_changes != second_day.tag_changes
        or first_day.intent != second_day.intent
        or not first_day.fact_temporal_anchors
        or not second_day.fact_temporal_anchors
        or first_day.fact_temporal_anchors[0] != second_day.fact_temporal_anchors[0]
        or "{{ref:0}}" not in second_day.facts[0]
    ):
        raise CandidateScopeSafetyError("Cannot safely merge unrelated Core targets or helpers")
    merged = replace(
        first_day,
        facts=(first_day.facts[0], second_day.facts[0].replace("{{ref:0}}", "{{ref:1}}")),
        references=(
            first_day.references[0],
            replace(second_day.references[0], target_index=2),
        ),
        fact_temporal_anchors=(
            first_day.fact_temporal_anchors[0],
            second_day.fact_temporal_anchors[0],
        ),
    )
    return RequestPlan(
        (WriteAction((merged, first_helper, second_helper)),),
        first.limitations + second.limitations,
        first.presentation_intent,
    )
