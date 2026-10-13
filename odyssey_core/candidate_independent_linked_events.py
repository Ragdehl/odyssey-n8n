"""Prove independent canonically linked Day events inside one Core write unit.

One grammatical source group can contain several events with distinct named
actors and clocks. Neither source Router anchors nor the reviewer alone grant
link/write authority; this checks each source-owned actor/action/time against
Core's unchanged plan, typed Temporal evidence and reference-only helpers.
"""

from __future__ import annotations

from .candidate_context import CoreCandidateContext
from .candidate_dependencies import trace_core_candidate_dependencies
from .candidate_semantic_veto import normalized_words
from .request_planning import RequestPlan, WriteAction

_BOUNDARY_ROLES = {"condition", "polarity", "replacement", "modality"}
_TIME_ROLES = {"time", "time_relation"}


def validate_independent_linked_event_fact(
    source: str,
    context: CoreCandidateContext,
    plan: RequestPlan,
    action_index: int,
    unit_index: int,
    fact_index: int,
    candidate_index: int,
) -> int:
    """Return the single authorized reference helper index for one candidate/fact.

    Full source graph coverage and all helpers are checked separately by Core.
    This proof does not authorize creating any Note, and cannot bind a pronoun
    or collective group to a named individual.
    """
    context.validate(source)
    temporal = context.verified_route_temporal
    if (
        temporal is None
        or len(context.candidates) < 2
        or any(c.kind != "occurrence" or c.state != "candidate" for c in context.candidates)
        or any(role.role in _BOUNDARY_ROLES for c in context.candidates for role in c.roles)
        or not 0 <= candidate_index < len(context.candidates)
        or not isinstance(plan, RequestPlan)
        or not 0 <= action_index < len(plan.actions)
    ):
        raise ValueError("Independent Day events need positive verified group/time scope")
    action = plan.actions[action_index]
    if not isinstance(action, WriteAction) or not 0 <= unit_index < len(action.units):
        raise ValueError("Independent events require one ordinary Core write action")
    unit = action.units[unit_index]
    if (
        unit.target.type != "calendar_day"
        or unit.target.entity is not None
        or not unit.target.query
        or unit.target.filters
        or unit.target.link_scope is not None
        or unit.target.relational_reference is not None
        or unit.target.self_target is not None
        or unit.target.semantic_set is not None
        or unit.intent != "record"
        or unit.reference_lookup_only
        or unit.force_create
        or unit.properties
        or unit.tag_changes
        or unit.destination_type is not None
        or len(unit.facts) != len(context.candidates)
        or len(unit.references) != len(context.candidates)
        or len(action.units) != len(context.candidates) + 1
        or len(unit.fact_temporal_anchors) != len(unit.facts)
        or not 0 <= fact_index < len(unit.facts)
    ):
        raise ValueError("Independent linked Day events have unreviewed mutation shape")
    candidate = context.candidates[candidate_index]
    named = [role.span for role in candidate.roles if role.role == "subject"]
    if (
        len(named) != 1
        or named[0] not in candidate.anchors
        or not 1 <= len(named[0].text) <= 100
        or any(
            x.role == "reference"
            and not any(
                clock.role == "time_relation" and clock.span == x.span for clock in candidate.roles
            )
            for x in candidate.roles
        )
    ):
        raise ValueError("Independent linked actor must be an explicit named source subject")
    name = named[0].text
    fact = unit.facts[fact_index]
    owned = [i for i, ref in enumerate(unit.references) if fact.count(f"{{{{ref:{i}}}}}") == 1]
    if len(owned) != 1 or "{{ref:" in fact.replace(f"{{{{ref:{owned[0]}}}}}", "") or "[[" in fact:
        raise ValueError("Each independent event may link exactly one source actor")
    reference_index = owned[0]
    reference = unit.references[reference_index]
    helper_index = reference.target_index
    if (
        reference.mention != name
        or reference.role not in {"identity", "person"}
        or not isinstance(helper_index, int)
        or isinstance(helper_index, bool)
        or not 0 <= helper_index < len(action.units)
        or helper_index == unit_index
    ):
        raise ValueError("Linked actor does not own the source participant")
    helper = action.units[helper_index]
    if (
        not helper.reference_lookup_only
        or helper.intent != "record"
        or helper.force_create
        or helper.facts
        or helper.references
        or helper.properties
        or helper.tag_changes
        or helper.destination_type is not None
        or helper.target.type != "person"
        or helper.target.entity != name
        or helper.target.query != name
        or helper.target.filters
        or helper.target.link_scope is not None
        or helper.target.relational_reference is not None
        or helper.target.self_target is not None
        or helper.target.semantic_set is not None
    ):
        raise ValueError("The canonical helper is not limited to this exact named actor")

    roles = trace_core_candidate_dependencies(source, context)[candidate_index]
    predicates = roles.for_role("predicate")
    objects = roles.for_role("object")
    own_words = normalized_words(fact.replace(f"{{{{ref:{reference_index}}}}}", name))
    if (
        len(predicates) != 1
        or not normalized_words(predicates[0].span.text) <= own_words
        or not objects
        or any(not normalized_words(role.span.text) <= own_words for role in objects)
    ):
        raise ValueError("Independent event lost its inherited verb or own object")
    dates = roles.for_role("date")
    if not dates:
        dates = roles.for_role("date_scope")
    if len(dates) != 1:
        raise ValueError("Independent event lacks one source-proven date")
    references = temporal.temporal_references()
    matching_days = {
        item.value
        for item in references
        if item.temporal_anchor().time is None
        and (dates[0].span.text == item.source_text or dates[0].span.text in item.source_text)
    }
    if matching_days != {unit.target.query}:
        raise ValueError("Independent event date differs from verified source day")
    # Router can label the SAME original phrase as both a source clock
    # and a time relation. This is one temporal mention, not two clocks.
    time_roles = {
        (role.span.start, role.span.end, role.span.text)
        for role in candidate.roles
        if role.role in _TIME_ROLES
    }
    if len(time_roles) != 1:
        raise ValueError("Independent event requires exactly one source clock ownership")
    time_text = next(iter(time_roles))[2]
    clock_values = {
        item.value
        for item in references
        if item.temporal_anchor().time is not None
        and (time_text == item.source_text or time_text in item.source_text)
    }
    if len(clock_values) != 1:
        raise ValueError("Independent source clock has no unique Temporal resolution")
    clock = next(iter(clock_values))
    anchors = unit.fact_temporal_anchors[fact_index]
    if (
        clock not in {anchor.value for anchor in anchors}
        or any(anchor.date != unit.target.query for anchor in anchors)
        or not fact.startswith(
            next(
                item.temporal_anchor().display_time
                for item in references
                if item.value == clock and item.temporal_anchor().time is not None
            )
            + " — "
        )
    ):
        raise ValueError("Independent Core fact has a swapped or unsupported clock")
    return helper_index
