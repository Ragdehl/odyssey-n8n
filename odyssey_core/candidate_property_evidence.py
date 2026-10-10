"""Core-owned evidence for assigning one independent source property to a Note.

This is a conservative source provenance check, not proof of semantic truth or
authorization to resolve a person. The ordinary Core target preflight remains
responsible for reusing/creating canonical identities safely.
"""

from __future__ import annotations

from .candidate_context import CoreCandidate
from .candidate_semantic_veto import normalized_words
from .request_planning import KnowledgeUnit


class CandidatePropertyEvidenceError(ValueError):
    """Core cannot prove that this source property belongs to this target."""


def validate_subject_property_fact(
    source: str,
    candidate: CoreCandidate,
    unit: KnowledgeUnit,
    fact: str,
    *,
    other_source_subjects: tuple[str, ...] = (),
) -> str:
    """Return source-grounded lexical evidence including a verified target name.

    Args:
        source: Exact user text validated at the Core boundary.
        candidate: Source-only property proposed by Router.
        unit: Independently generated Core write target and fact.
        fact: Lexicalized fact with no provider-only placeholders.

    Raises:
        CandidatePropertyEvidenceError: No unique source subject, wrong target,
            ungrounded changed content, or unsupported write intent.

    The returned text only supports the preexisting lexical veto. It does not
    assert that target resolution or the property itself is semantically right.
    """
    if candidate.kind != "property" or candidate.state != "candidate":
        raise CandidatePropertyEvidenceError("Independent source property required")
    subjects = [role.span for role in candidate.roles if role.role == "subject"]
    if (
        len(subjects) != 1
        or len(candidate.anchors) != 1
        or candidate.anchors[0] != subjects[0]
        or any(role.role in {"reference", "condition", "polarity"} for role in candidate.roles)
    ):
        raise CandidatePropertyEvidenceError("Property subject is not individually grounded")
    subject = subjects[0]
    if (
        source[subject.start : subject.end] != subject.text
        or unit.target.entity != subject.text
        or unit.target.query != subject.text
        or not unit.target.type
        or unit.target.filters
        or unit.target.link_scope is not None
        or unit.target.semantic_set is not None
        or unit.target.relational_reference is not None
        or unit.target.self_target is not None
        or unit.reference_lookup_only
        or unit.force_create
        or unit.intent != "record"
        or unit.properties
        or unit.tag_changes
        or unit.references
        or len(unit.facts) != 1
        or unit.destination_type is not None
        or unit.fact_temporal_anchors != ()
    ):
        raise CandidatePropertyEvidenceError("Property target or write shape mismatches source")
    # A name alone must not launder "Marta vive en París" from "Marta vive
    # en Lyon." Exact explicit location/object content must still agree.
    words = normalized_words(fact)
    if any(normalized_words(other) & words for other in other_source_subjects):
        raise CandidatePropertyEvidenceError(
            "Independent property fact contains another source candidate's subject"
        )
    supported = [
        role
        for role in candidate.roles
        if role.role in {"predicate", "location", "object", "transaction"}
    ]
    if not supported:
        raise CandidatePropertyEvidenceError("Property lacks independent predicate evidence")
    for role in supported:
        if role.role in {"location", "object"} and not normalized_words(role.span.text) <= words:
            raise CandidatePropertyEvidenceError("Property changed its original location/object")
    if not any(
        {word for word in normalized_words(role.span.text) if len(word) >= 3} & words
        for role in supported
    ):
        raise CandidatePropertyEvidenceError("Property fact lacks grounded non-subject content")
    return subject.text + " " + fact
