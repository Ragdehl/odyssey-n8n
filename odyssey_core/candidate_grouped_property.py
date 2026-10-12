"""Strict source evidence for several positive property facts on one target.

This is *only* the source/fact attribution gate. The independent Core graph
reviewer still proposes the correspondence, and ordinary canonical preflight
must resolve the target and verify every write/readback. A mention of Router
or Temporal is NOT automatically a canonical identity link.
"""

from __future__ import annotations

from .candidate_context import CoreCandidateContext
from .candidate_semantic_veto import normalized_words
from .request_planning import KnowledgeUnit


def validate_shared_subject_property(
    source: str,
    context: CoreCandidateContext,
    candidate_index: int,
    unit: KnowledgeUnit,
    fact: str,
) -> str:
    candidate = context.candidates[candidate_index]
    if (
        len(context.candidates) < 2
        or any(item.kind != "property" or item.state != "candidate" for item in context.candidates)
        or candidate.kind != "property"
        or candidate.state != "candidate"
        or any(
            role.role in {"reference", "condition", "polarity", "replacement", "modality"}
            for item in context.candidates
            for role in item.roles
        )
        or unit.intent != "record"
        or unit.properties
        or unit.tag_changes
        or unit.references
        or unit.reference_lookup_only
        or unit.force_create
        or unit.destination_type is not None
        or unit.fact_temporal_anchors
        or unit.target.filters
        or unit.target.link_scope is not None
        or unit.target.relational_reference is not None
        or unit.target.semantic_set is not None
        or unit.target.self_target is not None
        or not unit.target.type
        or not unit.facts
    ):
        raise ValueError("Grouped property requires positive, reference-free Core evidence")
    explicit = [
        (i, role.span)
        for i, item in enumerate(context.candidates)
        for role in item.roles
        if role.role == "subject"
    ]
    if len(explicit) != 1:
        raise ValueError("Grouped property does not have exactly one explicit subject")
    origin, subject = explicit[0]
    if (
        subject not in context.candidates[origin].anchors
        or unit.target.query != subject.text
        or not (
            unit.target.entity == subject.text
            or (
                isinstance(unit.target.entity, str)
                and subject.text.casefold().endswith(" " + unit.target.entity.casefold())
            )
        )
    ):
        raise ValueError("Grouped property target changed the common source subject")
    if candidate_index != origin:
        if len(candidate.inherits) != 2 or {
            (item.role, item.from_unit) for item in candidate.inherits
        } != {("subject", origin + 1), ("predicate", origin + 1)}:
            raise ValueError("Grouped property has no source-verified subject/predicate dependence")
        if any(role.role == "subject" for role in candidate.roles):
            raise ValueError("Grouped property repeated an unrelated subject")
    elif candidate.inherits:
        raise ValueError("Initial grouped source property cannot itself inherit the subject")
    current_tokens = normalized_words(fact)
    all_tokens = normalized_words(source)
    if not current_tokens or not current_tokens <= all_tokens:
        raise ValueError("Grouped property invents words not contained in user source")
    other_discriminators: set[str] = set()
    for other_index, other in enumerate(context.candidates):
        if other_index == candidate_index:
            continue
        for role in other.roles:
            if role.role in {"location", "object"}:
                other_discriminators.update(normalized_words(role.span.text))
    own = [role for role in candidate.roles if role.role in {"location", "object"}]
    if not own or any(not normalized_words(role.span.text) <= current_tokens for role in own):
        raise ValueError("Grouped property lacks its own distinctive object/location")
    own_location = set().union(
        *(normalized_words(role.span.text) for role in candidate.roles if role.role == "location")
    )
    other_locations = set().union(
        *(
            normalized_words(role.span.text)
            for other_index, other in enumerate(context.candidates)
            if other_index != candidate_index
            for role in other.roles
            if role.role == "location"
        )
    )
    if own_location and other_locations & current_tokens:
        raise ValueError("Grouped property mixes a different candidate location")
    if not own_location and not (current_tokens & (all_tokens - other_discriminators)):
        raise ValueError("Grouped property cannot distinguish its fact from a sibling")
    return subject.text + " " + fact
