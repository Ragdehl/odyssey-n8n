"""Narrow final-intention proof for a two-part source correction.

Source grounding, Temporal authority and independently reviewed coverage are
all mandatory. This does NOT authorize the superseded event, arbitrary
negative statements or conditional occurrences.
"""

from __future__ import annotations

from .candidate_context import CoreCandidateContext
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
    if (
        len(context.candidates) != 2
        or candidate_index != 1
        or len(claims) != 2
        or (claims[0].disposition, claims[0].pending_reason)
        != ("pending", "superseded_by_correction")
        or claims[1].disposition != "planned_fact"
        or claims[1].fact_ordinal != 0
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
    discarded, retained = context.candidates
    first = {r.role: r.span.text for r in discarded.roles}
    second = {r.role: r.span.text for r in retained.roles}
    if (
        "polarity" not in first
        or "object" not in first
        or "time" not in first
        or "predicate" not in first
        or "replacement" not in second
        or "object" not in second
        or "time" not in second
        or second["replacement"] != first["object"]
        or second["object"] == first["object"]
        or not any(edge.role == "predicate" and edge.from_unit == 1 for edge in retained.inherits)
        or not any(edge.role == "date" and edge.from_unit == 1 for edge in retained.inherits)
        or "date" not in first
        or any(r.role in {"condition", "modality"} for c in context.candidates for r in c.roles)
    ):
        raise ValueError("Source does not prove the final action supersedes the first")
    lexical = normalized_words(fact)
    required = normalized_words(second["object"]) | normalized_words(first["predicate"])
    if (
        not required <= lexical
        or ((normalized_words(first["object"]) - normalized_words(second["object"])) & lexical)
        or (normalized_words(first["time"]) - normalized_words(second["time"])) & lexical
        or normalized_words(first["polarity"]) & lexical
    ):
        raise ValueError("Cancelled action, clock, polarity or predicate leaked to final fact")
    anchors = unit.fact_temporal_anchors[0]
    if len(anchors) not in (1, 2):
        raise ValueError("Final corrected plan needs exact target time")
    timed = [a for a in anchors if a.time is not None]
    if len(timed) != 1 or timed[0].date != unit.target.query:
        raise ValueError("Final corrected plan time does not match its Day Note")
    references = tuple(proof.temporal_references())
    if (second["time"], timed[0].value) not in {
        (entry.source_text, entry.value) for entry in references
    } or not any(
        entry.source_text == first["date"] and entry.value == unit.target.query
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
