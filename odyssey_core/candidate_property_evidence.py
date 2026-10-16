"""Core-owned evidence for assigning one independent source property to a Note.

This is a conservative source provenance check, not proof of semantic truth or
authorization to resolve a person. The ordinary Core target preflight remains
responsible for reusing/creating canonical identities safely.
"""

from __future__ import annotations

from .candidate_context import CoreCandidate
from .candidate_semantic_veto import normalized_words
from .request_planning import KnowledgeUnit
from .scoped_subject_evidence import CoreVerifiedInheritedSubject


class CandidatePropertyEvidenceError(ValueError):
    """Core cannot prove that this source property belongs to this target."""


def validate_subject_property_fact(
    source: str,
    candidate: CoreCandidate,
    unit: KnowledgeUnit,
    fact: str,
    *,
    other_source_subjects: tuple[str, ...] = (),
    inherited_subject: CoreVerifiedInheritedSubject | None = None,
    self_owner_quote: str | None = None,
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
    if not subjects and inherited_subject is not None:
        inherited_subject.validate()
        if (
            any(
                role.role in {"subject", "reference", "condition", "polarity", "replacement"}
                for role in candidate.roles
            )
            or unit.target.entity != inherited_subject.canonical_name
            or unit.target.type != inherited_subject.canonical_type
            or unit.target.query
            not in {inherited_subject.canonical_name, inherited_subject.source_text}
            or len(candidate.anchors) < 1
            or any(
                anchor
                not in {
                    role.span
                    for role in candidate.roles
                    if role.role in {"object", "location", "predicate", "transaction"}
                }
                for anchor in candidate.anchors
            )
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
            raise CandidatePropertyEvidenceError(
                "Inherited property target lacks verified Core subject"
            )
        words = normalized_words(fact)
        local_roles = [role for role in candidate.roles if role.role in {"object", "location"}]
        if not local_roles or any(
            not normalized_words(role.span.text) <= words for role in local_roles
        ):
            raise CandidatePropertyEvidenceError("Inherited property changed local source content")
        permitted = (
            normalized_words(source)
            | normalized_words(inherited_subject.source_text)
            | normalized_words(inherited_subject.predecessor_fact)
        )
        if not words <= permitted:
            raise CandidatePropertyEvidenceError("Inherited property adds unknown lexical material")
        return inherited_subject.source_text + " " + fact
    direct_self = unit.target.self_target == "self"
    supported_anchors = {
        role.span
        for role in candidate.roles
        if role.role
        in {"subject", "participants", "object", "location", "predicate", "transaction"}
    }
    if any(anchor not in supported_anchors for anchor in candidate.anchors) or any(
        role.role in {"reference", "condition", "polarity"} for role in candidate.roles
    ):
        raise CandidatePropertyEvidenceError("Property subject is not individually grounded")
    if direct_self:
        # Experiencers can be indirect objects, not grammatical subjects.
        # The INDEPENDENT Core source review chooses exactly one source span,
        # and it must be present as an original role on this very candidate.
        owners = tuple(
            dict.fromkeys(
                role.span
                for role in candidate.roles
                if role.role in {"subject", "participants", "object"}
                and role.span.text == self_owner_quote
            )
        )
        if len(owners) != 1 or not any(
            anchor.start <= owners[0].start and owners[0].end <= anchor.end
            for anchor in candidate.anchors
        ):
            raise CandidatePropertyEvidenceError(
                "SELF experiencer source is not independently grounded"
            )
        subject = owners[0]
    else:
        if len(subjects) != 1 or subjects[0] not in candidate.anchors:
            raise CandidatePropertyEvidenceError("Property subject is not individually grounded")
        subject = subjects[0]
    if direct_self:
        # The independently reviewed Core speaker/experiencer attestation is
        # required for a direct Person target. Router's lexical subject role
        # or the authenticated write actor alone can NEVER select SELF.
        target_owned_by_source = (
            unit.target.entity is None
            and unit.target.type == "person"
            and isinstance(self_owner_quote, str)
            and self_owner_quote == subject.text
        )
    else:
        target_owned_by_source = (
            self_owner_quote is None
            and (
                unit.target.entity == subject.text
                or (
                    isinstance(unit.target.entity, str)
                    and unit.target.entity.strip()
                    and subject.text.casefold().endswith(" " + unit.target.entity.casefold())
                )
            )
            and unit.target.query == subject.text
            and unit.target.self_target is None
        )
    if (
        source[subject.start : subject.end] != subject.text
        or not target_owned_by_source
        or not unit.target.type
        or unit.target.filters
        or unit.target.link_scope is not None
        or unit.target.semantic_set is not None
        or unit.target.relational_reference is not None
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
    if direct_self and any(
        not normalized_words(role.span.text) <= words
        for role in candidate.roles
        if role.role == "subject" and role.span != subject
    ):
        raise CandidatePropertyEvidenceError("SELF property drops the original grammatical subject")
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
        if direct_self and role.role == "object" and role.span == subject:
            # The independently attested first-person EXPERIENCER may be
            # grammatical indirect object, which the fact can inflect (mí→me).
            # Other object/location roles still require exact source coverage.
            continue
        if role.role in {"location", "object"} and not normalized_words(role.span.text) <= words:
            raise CandidatePropertyEvidenceError("Property changed its original location/object")
    if not any(
        {word for word in normalized_words(role.span.text) if len(word) >= 3} & words
        for role in supported
    ):
        raise CandidatePropertyEvidenceError("Property fact lacks grounded non-subject content")
    return subject.text + " " + fact
