"""Source, Temporal and Core target agreement for shared-clock occurrences.

Only a Core-validated DomainInterpretation supplied by the opt-in hybrid
Temporal composition path can authorize the omitted weekday in a Day fact.
The independently proposed candidate/fact graph and ordinary Day Writer
preflight remain mandatory.
"""

from __future__ import annotations

from datetime import date

from .candidate_context import CoreCandidateContext
from .candidate_semantic_veto import normalized_words
from .request_planning import KnowledgeUnit
from .temporal_group_composition import _weekday


def validate_grouped_dated_occurrence(
    source: str,
    context: CoreCandidateContext,
    candidate_index: int,
    unit: KnowledgeUnit,
    fact: str,
) -> None:
    temporal = context.verified_group_temporal
    if temporal is None or temporal.source_text != source:
        raise ValueError("Grouped event has no verified Temporal evidence")
    if (
        not 2 <= len(context.candidates)
        or len(context.candidates) * 2 > 16
        or any(c.kind != "occurrence" or c.state != "candidate" for c in context.candidates)
        or any(
            role.role in {"condition", "polarity", "replacement", "modality", "time_approx"}
            for c in context.candidates
            for role in c.roles
        )
        or unit.target.type != "calendar_day"
        or unit.target.entity is not None
        or not isinstance(unit.target.query, str)
        or unit.target.filters
        or unit.target.link_scope is not None
        or unit.target.relational_reference is not None
        or unit.target.self_target is not None
        or unit.target.semantic_set is not None
        or unit.intent != "record"
        or unit.references
        or unit.reference_lookup_only
        or unit.force_create
        or unit.properties
        or unit.tag_changes
        or unit.destination_type is not None
        or len(unit.facts) != 1
        or len(unit.fact_temporal_anchors) != 1
    ):
        raise ValueError("Shared clock occurrence requires one independently dated fact")
    shared_time_roles = [[r.span for r in c.roles if r.role == "time"] for c in context.candidates]
    if (
        any(len(roles) != 1 for roles in shared_time_roles)
        or len({(roles[0].start, roles[0].end, roles[0].text) for roles in shared_time_roles}) != 1
    ):
        raise ValueError("Every occurrence must own one same-source time phrase")
    clock_text = shared_time_roles[0][0].text
    date_roles = [[r.span for r in c.roles if r.role == "date"] for c in context.candidates]
    if any(len(roles) != 1 for roles in date_roles):
        raise ValueError("Each occurrence needs one independently quoted weekday")
    allowed = {(x.source_text, x.value) for x in temporal.temporal_references()}
    verified_dates: set[str] = set()
    for roles in date_roles:
        weekday = _weekday(roles[0].text)
        matching = [
            proof
            for proof in temporal.temporal_references()
            if proof.temporal_anchor().time is None and roles[0].text in proof.source_text
        ]
        if len(matching) != 1 or weekday is None:
            raise ValueError("Grouped weekday has no unique verified date")
        exact_day = matching[0].value
        if date.fromisoformat(exact_day).weekday() != weekday or exact_day in verified_dates:
            raise ValueError("Grouped weekday/date is conflicting or duplicated")
        verified_dates.add(exact_day)
    own_date = date_roles[candidate_index][0].text
    date_match = [
        proof
        for proof in temporal.temporal_references()
        if proof.temporal_anchor().time is None and own_date in proof.source_text
    ]
    if len(date_match) != 1 or unit.target.query != date_match[0].value:
        raise ValueError("Core event target does not match its own Temporal weekday")
    anchors = unit.fact_temporal_anchors[0]
    if len(anchors) != 2:
        raise ValueError("Each shared-clock fact must retain its date and instant")
    timed = [anchor for anchor in anchors if anchor.time is not None]
    date_only = [anchor for anchor in anchors if anchor.time is None]
    if (
        len(timed) != 1
        or len(date_only) != 1
        or date_only[0].value != unit.target.query
        or timed[0].date != unit.target.query
        or (clock_text, timed[0].value) not in allowed
    ):
        raise ValueError("Core event time differs from verified shared Temporal clock")
    if not fact.startswith(timed[0].display_time + " — ") or not normalized_words(
        " ".join(
            r.span.text for r in context.candidates[candidate_index].roles if r.role == "predicate"
        )
    ) <= normalized_words(fact):
        raise ValueError("Grouped event lost its predicate or visible exact clock")
    residual = fact.split(" — ", 1)[1]
    if not normalized_words(residual) <= normalized_words(source):
        raise ValueError("Grouped event fact invents unrelated source content")
    if normalized_words(fact) & {"no", "nunca", "jamás", "not", "never"}:
        raise ValueError("Grouped event fact has unsupported negative scope")
