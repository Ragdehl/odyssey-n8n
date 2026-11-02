"""Core proof of a bounded self-owned relationship from current Markdown.

No Router-provided names or model-generated canonical IDs are authoritative.
The caller supplies an *exact original source relation span*, Core checks
it against one current self Note fact, projects all literal linked members
and preserves its provenance for re-grounding before the write.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .identity_boundary import AuthenticatedActorContext, SelfBindingRepository
from .relationship_evidence import RelationshipEvidenceProjector, TargetProjectionStatus
from .storage import VaultRepository


class WholeSourceRelationshipError(ValueError):
    """Relationship membership cannot be proven from current canonical facts."""


@dataclass(frozen=True, slots=True)
class VerifiedSelfRelationship:
    source_id: str
    source_hash: str
    fact_locator: str
    original_relation_span: str
    members: tuple[tuple[str, str], ...]
    member_types: tuple[tuple[str, str], ...] = ()


def verify_self_relationship(
    source: str,
    relation_span: str,
    *,
    repository: VaultRepository,
    schema: dict,
    actor: AuthenticatedActorContext,
    bindings: SelfBindingRepository,
) -> VerifiedSelfRelationship:
    """Ground exact relation wording against precisely one fresh SELF fact."""
    if (
        not isinstance(source, str)
        or not isinstance(relation_span, str)
        or not relation_span.strip()
        or len(relation_span) > 128
        or relation_span not in source
        or re.search(r"\w+\s+\w+", relation_span) is None
    ):
        raise WholeSourceRelationshipError("Missing explicit original relationship anchor")
    source_id = bindings.resolve(actor.stable_user_id).person_note_id
    projector = RelationshipEvidenceProjector(repository, schema)
    # A matched source-fact must use the exact multi-word relation phrase,
    # not a surname, a single token, or a model-generated list of members.
    matching = [
        fact
        for fact in projector.facts_for_source(source_id)
        if re.search(r"(?<!\w)" + re.escape(relation_span) + r"(?!\w)", fact.text, re.I)
    ]
    if len(matching) != 1:
        raise WholeSourceRelationshipError("Relationship source fact absent or ambiguous")
    fact = matching[0]
    projected = projector.project_targets(source_id, fact.locator)
    if (
        projected.status is not TargetProjectionStatus.COMPLETE
        or len(projected.targets) < 1
        or any(not isinstance(t.type, str) or not t.type for t in projected.targets)
        or projected.source is None
        or projected.source.source_hash != fact.source.source_hash
    ):
        raise WholeSourceRelationshipError("Relationship target set unavailable")
    return VerifiedSelfRelationship(
        source_id,
        fact.source.source_hash,
        fact.locator,
        relation_span,
        tuple((t.id, t.name) for t in projected.targets),
        tuple((t.id, t.type) for t in projected.targets),
    )


def verify_proposed_source_relationships(
    source: str,
    proposed_spans: tuple[str, ...],
    *,
    repository: VaultRepository,
    schema: dict,
    actor: AuthenticatedActorContext,
    bindings: SelfBindingRepository,
) -> tuple[tuple[VerifiedSelfRelationship, ...], dict[str, str], tuple[str, ...]]:
    """Core-owned grouping of current, source-grounded relationship evidence.

    Unverified phrases remain literal; no model or Runtime step may invent a
    canonical target. A single canonical fact cannot prove separate membership
    for two different relationship phrases inside it. This logic is neutral to
    relationship labels, names, message examples and App lifecycle.
    """
    proofs: list[VerifiedSelfRelationship] = []
    members: dict[str, str] = {}
    unverified: list[str] = []
    for span in proposed_spans:
        try:
            proof = verify_self_relationship(
                source,
                span,
                repository=repository,
                schema=schema,
                actor=actor,
                bindings=bindings,
            )
        except WholeSourceRelationshipError:
            # A failed membership proof does not make the user's text false.
            unverified.append(span)
            continue
        if any(
            previous.source_id == proof.source_id
            and previous.fact_locator == proof.fact_locator
            and previous.original_relation_span != proof.original_relation_span
            for previous in proofs
        ):
            raise WholeSourceRelationshipError("Groups share an indivisible source fact")
        proofs.append(proof)
        for note_id, name in proof.members:
            if note_id in members and members[note_id] != name:
                raise WholeSourceRelationshipError("Conflicting member proof")
            members[note_id] = name
    if len(set(members.values())) != len(members):
        raise WholeSourceRelationshipError("Ambiguous member names")
    return tuple(proofs), members, tuple(unverified)


def recheck_self_relationship(
    evidence: VerifiedSelfRelationship,
    *,
    repository: VaultRepository,
    schema: dict,
    actor: AuthenticatedActorContext,
    bindings: SelfBindingRepository,
) -> None:
    """Invalidate if either the binding, owning fact or member set changed."""
    if not isinstance(evidence, VerifiedSelfRelationship):
        raise WholeSourceRelationshipError("Missing typed relationship evidence")
    if bindings.resolve(actor.stable_user_id).person_note_id != evidence.source_id:
        raise WholeSourceRelationshipError("SELF binding changed")
    projected = RelationshipEvidenceProjector(repository, schema).project_targets(
        evidence.source_id, evidence.fact_locator
    )
    if (
        projected.status is not TargetProjectionStatus.COMPLETE
        or projected.source is None
        or projected.source.source_hash != evidence.source_hash
        or tuple((t.id, t.name) for t in projected.targets) != evidence.members
        or tuple((t.id, t.type) for t in projected.targets) != evidence.member_types
    ):
        raise WholeSourceRelationshipError("Relationship evidence changed before write")
