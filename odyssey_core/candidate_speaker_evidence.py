"""One shared, Core-owned prewrite contract for source-proposed speaker links.

The model reviews grammatical person; this bounded structural guard checks its
original source anchor and exact symbolic SELF fact reference. Neither Router
nor the persistence actor is permitted to assert a speaker on its own.
"""

from __future__ import annotations

from dataclasses import dataclass

from .candidate_context import CoreCandidateContext
from .request_planning import RequestPlan, WriteAction, plan_fact_ordinals


@dataclass(frozen=True, slots=True)
class CoreSpeakerEvidence:
    """Core-reviewed source candidate, fact ordinal and exact grammatical anchor."""

    candidate_id: str
    fact_ordinal: int
    source_quote: str


def speaker_fact_references(plan: RequestPlan) -> dict[int, tuple[int, int, int]]:
    """Locate SELF participants; do not interpret the source or resolve a Person."""
    result: dict[int, tuple[int, int, int]] = {}
    numbers = iter(plan_fact_ordinals(plan))
    for action_index, action in enumerate(plan.actions):
        if not isinstance(action, WriteAction):
            continue
        for unit_index, unit in enumerate(action.units):
            ordinals = next(numbers)
            for ordinal in ordinals:
                speaker_refs = [
                    ref_index
                    for ref_index, reference in enumerate(unit.references)
                    if reference.target_index is not None
                    and 0 <= reference.target_index < len(action.units)
                    and action.units[reference.target_index].target.self_target == "self"
                ]
                if not speaker_refs:
                    continue
                if (
                    len(speaker_refs) != 1
                    or len(unit.references) != 1
                    or len(unit.facts) != 1
                    or unit.reference_lookup_only
                    or unit.target.self_target is not None
                    or unit.target.type != "calendar_day"
                    or unit.facts[0].count(f"{{{{ref:{speaker_refs[0]}}}}}") != 1
                ):
                    raise ValueError(
                        "Source speaker needs one Day fact with one pure SELF reference"
                    )
                ref_index = speaker_refs[0]
                helper_index = unit.references[ref_index].target_index
                if helper_index is None:
                    raise ValueError("Speaker lookup target is missing")
                helper = action.units[helper_index]
                if (
                    not helper.reference_lookup_only
                    or helper.facts
                    or helper.references
                    or helper.force_create
                    or helper.target.type != "person"
                    or helper.target.entity is not None
                    or helper.target.filters
                    or helper.target.relational_reference is not None
                    or helper.target.link_scope is not None
                    or helper.target.semantic_set is not None
                ):
                    raise ValueError("Speaker helper cannot carry a mutation or a named identity")
                result[ordinal] = (action_index, unit_index, helper_index)
    return result


def direct_self_property_fact_ordinals(
    plan: RequestPlan, context: CoreCandidateContext
) -> frozenset[int]:
    """Require independent Core speaker proof for direct SELF Person properties.

    This is NOT the existing symbolic Day speaker-reference shape: SELF is
    the write target itself, so no fictional reference-only helper is needed.
    Ordinary Core authentication still resolves this target on write.
    """
    # Preserve ordinary event/conditional semantics. A Core plan targeting
    # SELF does not automatically describe a timeless Person property; in
    # particular a future conditional first-person occurrence must still run
    # through its original model reviewer and fail its original safety gate.
    if (
        not context.hybrid_interpretation_mode
        or not context.candidates
        or any(candidate.kind != "property" for candidate in context.candidates)
    ):
        return frozenset()
    result: set[int] = set()
    numbers = iter(plan_fact_ordinals(plan))
    for action in plan.actions:
        if not isinstance(action, WriteAction):
            continue
        for unit in action.units:
            ordinals = next(numbers)
            # A reference-only SELF lookup helper belongs to the existing
            # symbolic Day speaker path, not a direct Person write target.
            if unit.target.self_target != "self" or unit.reference_lookup_only:
                continue
            if (
                unit.target.type != "person"
                or len(unit.facts) != 1
                or unit.intent != "record"
                or unit.reference_lookup_only
                or unit.force_create
                or unit.references
                or unit.properties
                or unit.tag_changes
                or unit.fact_temporal_anchors
                or unit.destination_type is not None
            ):
                raise ValueError("Direct SELF property needs one ordinary Person fact")
            result.update(ordinals)
    return frozenset(result)


def validate_speaker_evidence(
    source: str,
    context: CoreCandidateContext,
    plan: RequestPlan,
    evidence: tuple[CoreSpeakerEvidence, ...],
) -> dict[int, tuple[int, int, int]]:
    """Require source-attested speaker role for every symbolic SELF participant.

    The independent Core graph reviewer must identify an exact candidate-owned
    grammatical predicate/subject, not an invented first-person label. Explicit
    other subjects cannot be overridden by a predicate-only speaker claim.
    This is a semantic *proposal* checked against source and plan, not proof
    that a language model cannot misunderstand an ambiguous utterance.
    """
    references = speaker_fact_references(plan)
    self_properties = direct_self_property_fact_ordinals(plan, context)
    expected_ordinals = frozenset(references) | self_properties
    if not isinstance(evidence, tuple) or len(evidence) != len(expected_ordinals):
        raise ValueError(
            "Every speaker reference or direct SELF fact requires Core source attestation"
        )
    if evidence and not (context.hybrid_interpretation_mode and context.scoped_route_source):
        raise ValueError("Symbolic source speaker requires reviewed hybrid scope")
    checked: set[int] = set()
    candidate_ids = {c.candidate_id: c for c in context.candidates}
    for proof in evidence:
        if (
            not isinstance(proof, CoreSpeakerEvidence)
            or proof.fact_ordinal not in expected_ordinals
            or proof.fact_ordinal in checked
            or not isinstance(proof.source_quote, str)
            or not proof.source_quote.strip()
            or len(proof.source_quote) > 256
            or proof.candidate_id not in candidate_ids
        ):
            raise ValueError("Untrusted speaker proof is missing or duplicated")
        candidate = candidate_ids[proof.candidate_id]
        # Day speaker links can be attested by a first-person verbal predicate.
        # A direct SELF property instead needs a separately reviewed
        # *first-person owner/experiencer* span. Some languages express an
        # experiencer as a grammatical OBJECT ("a mí me gusta"), so rejecting
        # every non-subject role would systematically exclude ordinary
        # preferences. An event predicate alone never proves that the
        # authenticated human experiences another person's property.
        allowed_roles = (
            {"subject", "object", "participants"}
            if proof.fact_ordinal in self_properties
            else {"predicate", "subject"}
        )
        role_spans = (
            role.span
            for role in candidate.roles
            if role.role in allowed_roles and role.span.text == proof.source_quote
        )
        if not any(
            span.text in source
            and source[span.start : span.end] == span.text
            and any(
                anchor.start <= span.start and span.end <= anchor.end
                for anchor in candidate.anchors
            )
            for span in role_spans
        ):
            raise ValueError("Speaker proof is not an exact source-owned grammatical anchor")
        subjects = [role.span for role in candidate.roles if role.role == "subject"]
        if (
            proof.fact_ordinal not in self_properties
            and subjects
            and not any(span.text == proof.source_quote for span in subjects)
        ):
            raise ValueError("A distinct explicit source subject cannot become the speaker")
        # For SELF properties, the independently reviewed experiencer can be
        # an indirect object while the grammatical subject is the liked thing.
        # Coverage verifies that such a subject is retained in the actual fact.

        checked.add(proof.fact_ordinal)
    return references
