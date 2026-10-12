"""Narrow final-intention proof for a linear source correction chain.

Source grounding, Temporal authority and independently reviewed coverage are
all mandatory. This does NOT authorize the superseded event, arbitrary
negative statements or conditional occurrences.
"""

from __future__ import annotations

from .candidate_context import CoreCandidateContext
from .candidate_correction_chain import correction_chain
from .candidate_semantic_veto import normalized_words
from .request_planning import KnowledgeUnit


def validate_corrected_plan_fact(
    source: str,
    context: CoreCandidateContext,
    candidate_index: int,
    unit: KnowledgeUnit,
    fact: str,
    claims: tuple[object, ...],
) -> None:
    proof = context.verified_correction_temporal
    if proof is None or proof.source_text != source or not context.hybrid_interpretation_mode:
        raise ValueError("Corrected plan requires exact Temporal/source evidence")
    chain = correction_chain(context.candidates)
    if (
        chain is None
        or candidate_index != len(context.candidates) - 1
        or len(claims) != len(context.candidates)
        or any(
            (claim.disposition, claim.pending_reason) != ("pending", "superseded_by_correction")
            for claim in claims[:-1]
        )
        or claims[-1].disposition != "planned_fact"
        or claims[-1].fact_ordinal != 0
        or any(c.kind != "occurrence" or c.state != "candidate" for c in context.candidates)
        or unit.intent != "record"
        or unit.target.type != "calendar_day"
        or unit.target.entity is not None
        or unit.references
        or unit.reference_lookup_only
        or unit.properties
        or unit.tag_changes
        or unit.force_create
        or unit.destination_type is not None
        or len(unit.facts) != 1
        or len(unit.fact_temporal_anchors) != 1
        or unit.cardinality != "one"
    ):
        raise ValueError("Only independently reviewed final plan can replace a cancelled event")
    final_object = chain.objects[-1].text
    final_time = chain.times[-1].text
    lexical = normalized_words(fact)
    required = normalized_words(final_object) | normalized_words(chain.predicate.text)
    cancelled_objects = set().union(*(normalized_words(item.text) for item in chain.objects[:-1]))
    cancelled_objects -= normalized_words(final_object)
    cancelled_times = set().union(*(normalized_words(item.text) for item in chain.times[:-1]))
    cancelled_times -= normalized_words(final_time)
    if (
        not required <= lexical
        or (cancelled_objects & lexical)
        or (cancelled_times & lexical)
        or normalized_words(chain.polarity.text) & lexical
    ):
        raise ValueError("Cancelled action, clock, polarity or predicate leaked to final fact")
    anchors = unit.fact_temporal_anchors[0]
    if len(anchors) not in (1, 2):
        raise ValueError("Final corrected plan needs exact target time")
    timed = [a for a in anchors if a.time is not None]
    if len(timed) != 1 or timed[0].date != unit.target.query:
        raise ValueError("Final corrected plan time does not match its Day Note")
    references = tuple(proof.temporal_references())
    if (final_time, timed[0].value) not in {
        (entry.source_text, entry.value) for entry in references
    } or not any(
        entry.source_text == chain.date.text and entry.value == unit.target.query
        for entry in references
    ):
        raise ValueError("Cancelled or invented clock/day is not Temporal-authorized")
    for anchor in anchors:
        if anchor.time is None and anchor.value != unit.target.query:
            raise ValueError("Final plan carries contradictory date")
    # Temporal's exact rendered hour is the only permissible source-external
    # formatting, e.g. "12:00" instead of "12".
    normalized_fact = fact.replace(timed[0].display_time, str(int(timed[0].time[:2])))
    if not normalized_words(normalized_fact) <= normalized_words(source):
        raise ValueError("Final plan introduced words not in the original source")
