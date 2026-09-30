"""Resolve planner-preserved relational intent against current canonical Markdown."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from odyssey_core.clarification_presentation import (
    MAX_CLARIFICATION_EVIDENCE_CHARS,
    ClarificationCandidateEvidence,
    ClarificationPresentation,
)
from odyssey_core.contextual import (
    ContextualCandidate,
    ContextualResolutionRequest,
    validate_contextual_decision,
)
from odyssey_core.identity_boundary import (
    AuthenticatedActorContext,
    SelfBindingError,
    SelfBindingRepository,
)
from odyssey_core.notes import NoteFormatError, NoteValidationError, parse_note, validate_note
from odyssey_core.relationship_evidence import (
    CanonicalFact,
    CanonicalIdentity,
    EvidenceDirection,
    RelationshipEvidenceProjector,
    TargetProjectionStatus,
)
from odyssey_core.request_planning import SelectionCriteria
from odyssey_core.resolution import (
    ExistingEntityOutcome,
    build_provider_evidence,
    resolve_existing_entity,
)
from odyssey_core.semantic_sets import (
    DEFAULT_SEMANTIC_SET_BOUNDS,
    SemanticSetCandidate,
    SemanticSetCandidateView,
    SemanticSetResolution,
    SemanticSetSelectionRequest,
    SetEvidenceSelection,
    partition_semantic_set_candidates,
)
from odyssey_core.storage import VaultRepository

_WIKILINK_DISPLAY = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


class RelationalResolutionError(RuntimeError):
    """Signal that one relational identity or complete member set cannot be authorized."""

    def __init__(
        self,
        reason: str,
        candidate_ids: tuple[str, ...] = (),
        evidence_guard: str | None = None,
        clarification: ClarificationPresentation | None = None,
    ) -> None:
        """Carry only Core-grounded bounded identity options when clarification is safe."""
        super().__init__(reason)
        self.candidate_ids = candidate_ids
        self.evidence_guard = evidence_guard
        self.clarification = clarification


@dataclass(frozen=True, slots=True)
class ResolvedRelationalReference:
    """Carry a current source fact locator and its exact grounded target identities."""

    source: CanonicalIdentity
    evidence_source: CanonicalIdentity
    fact_locator: str
    direction: EvidenceDirection
    targets: tuple[CanonicalIdentity, ...]
    evidence_guard: str


def resolve_relational_reference(
    selection: SelectionCriteria,
    *,
    repository: VaultRepository,
    schema: dict[str, Any],
    semantic_index: Any,
    embedder: Any,
    contextual_reasoner: Any,
    semantic_limit: int,
    authenticated_actor: AuthenticatedActorContext | None,
    self_binding_repository: SelfBindingRepository | None,
    semantic_set_selector: Any | None = None,
    allow_identity_clarification: bool = False,
    chosen_identity_id: str | None = None,
    refine_singular_with_query: bool = False,
) -> ResolvedRelationalReference:
    """Resolve one source and every semantically relevant current fact through Core grounding.

    Read-side relevance selection may choose only supplied canonical fact locators. Core then
    re-reads every selected fact, projects each complete one-hop target set, and decides identity
    only after stable target deduplication. Bare writes retain the established direct relational
    path; qualified singular writes may instead use the relationship as a bounded candidate anchor
    and apply the complete preserved query only inside that grounded identity universe.
    """
    relation = selection.relational_reference
    if relation is None:
        raise ValueError("Selection has no relational reference")
    projector = RelationshipEvidenceProjector(repository, schema)
    if relation.source_kind == "self":
        if authenticated_actor is None or self_binding_repository is None:
            raise RelationalResolutionError("relational_source_unavailable")
        try:
            source_id = self_binding_repository.resolve(
                authenticated_actor.stable_user_id
            ).person_note_id
        except SelfBindingError as error:
            raise RelationalResolutionError("relational_source_unavailable") from error
    else:
        assert relation.source_query is not None
        source_resolution = resolve_existing_entity(
            relation.source_query,
            relation.reference,
            repository=repository,
            schema=schema,
            semantic_index=semantic_index,
            embedder=embedder,
            contextual_reasoner=contextual_reasoner,
            semantic_limit=semantic_limit,
        )
        if source_resolution.outcome is not ExistingEntityOutcome.RESOLVED:
            raise RelationalResolutionError("relational_source_unresolved")
        assert source_resolution.id is not None
        source_id = source_resolution.id
    outgoing = tuple(
        (fact, EvidenceDirection.OUTGOING) for fact in projector.facts_for_source(source_id)
    )
    incoming_projection = projector.project_entity_evidence_candidates(source_id)
    incoming = (
        tuple((item.fact, EvidenceDirection.INCOMING) for item in incoming_projection.incoming)
        if incoming_projection is not None and relation.members == "one"
        else ()
    )
    candidates: tuple[tuple[CanonicalFact, EvidenceDirection], ...] = (*outgoing, *incoming)
    if not candidates:
        raise RelationalResolutionError("relational_evidence_unavailable")
    evidence_guard = _candidate_evidence_guard(candidates)
    if (
        refine_singular_with_query
        and relation.members == "one"
        and not _same_wording(selection.query, relation.reference)
    ):
        return _resolve_qualified_singular_write(
            selection,
            source_id,
            projector,
            incoming_projection,
            candidates,
            evidence_guard,
            repository=repository,
            schema=schema,
            contextual_reasoner=contextual_reasoner,
            semantic_set_selector=semantic_set_selector,
            semantic_limit=semantic_limit,
            chosen_identity_id=chosen_identity_id,
        )
    if allow_identity_clarification:
        selected_candidates = _select_relevant_read_facts(
            selection.query,
            candidates,
            semantic_set_selector,
        )
        if not selected_candidates:
            raise RelationalResolutionError(
                "relational_evidence_unavailable", evidence_guard=evidence_guard
            )
        return _resolve_selected_read_facts(
            selection,
            source_id,
            projector,
            incoming_projection,
            selected_candidates,
            evidence_guard,
            chosen_identity_id,
        )
    decision, _usage = contextual_reasoner.resolve(
        ContextualResolutionRequest(
            reference=relation.reference,
            context=selection.query,
            entity_type="canonical_fact",
            candidates=tuple(
                ContextualCandidate(fact.locator, _humanize_fact_links(fact.text))
                for fact, _direction in candidates
            ),
        )
    )
    # Mutations retain their existing stricter preflight: repeating the literal
    # relation in more than one fact is not enough authority to edit either.
    # Retrieval may instead offer grounded bounded identities through the
    # established clarification continuation.
    if (
        not allow_identity_clarification
        and sum(
            relation.reference.casefold() in fact.text.casefold() for fact, _direction in candidates
        )
        > 1
    ):
        raise RelationalResolutionError(
            "relational_evidence_ambiguous", evidence_guard=evidence_guard
        )
    selected = validate_contextual_decision(
        decision, frozenset(fact.locator for fact, _direction in candidates)
    )
    if selected.ambiguous_ids:
        selected_facts = tuple(
            (fact, direction)
            for fact, direction in candidates
            if fact.locator in selected.ambiguous_ids
        )
        grounded: list[CanonicalIdentity] = []
        evidence_by_id: dict[str, list[str]] = {}
        for fact, direction in selected_facts:
            projection = projector.project_targets(fact.source.id, fact.locator)
            if projection.status is not TargetProjectionStatus.COMPLETE:
                continue
            targets = (
                (projection.source,)
                if direction is EvidenceDirection.INCOMING and projection.source is not None
                else projection.targets
            )
            for target in targets:
                if target is None:
                    continue
                if target.id not in {item.id for item in grounded}:
                    grounded.append(target)
                evidence_by_id.setdefault(target.id, []).append(_bounded_fact_evidence(fact))
        options = tuple(target.id for target in grounded)
        if relation.members == "one" and 1 < len(options) <= 4:
            raise RelationalResolutionError(
                "relational_evidence_ambiguous",
                options,
                evidence_guard,
                _identity_presentation(
                    relation.reference,
                    tuple(grounded),
                    {
                        target.id: _combine_fact_evidence(evidence_by_id[target.id])
                        for target in grounded
                    },
                ),
            )
        raise RelationalResolutionError(
            "relational_evidence_ambiguous", evidence_guard=evidence_guard
        )
    if selected.outcome != "RESOLVED" or selected.id is None:
        raise RelationalResolutionError(
            "relational_evidence_ambiguous", evidence_guard=evidence_guard
        )
    selected_fact, direction = next(
        (fact, direction) for fact, direction in candidates if fact.locator == selected.id
    )
    projection = projector.project_targets(selected_fact.source.id, selected.id)
    if projection.status is not TargetProjectionStatus.COMPLETE or projection.source is None:
        raise RelationalResolutionError(
            "relational_evidence_incomplete", evidence_guard=evidence_guard
        )
    if direction is EvidenceDirection.INCOMING:
        if not any(target.id == source_id for target in projection.targets):
            raise RelationalResolutionError(
                "relational_evidence_incomplete", evidence_guard=evidence_guard
            )
        targets = (projection.source,)
    else:
        targets = projection.targets
    if relation.members == "one" and len(targets) != 1:
        options = tuple(target.id for target in targets)
        identities = tuple(targets)
        fact_evidence = _bounded_fact_evidence(selected_fact)
        raise RelationalResolutionError(
            "relational_singular_ambiguous",
            options if allow_identity_clarification and 1 < len(options) <= 4 else (),
            evidence_guard,
            _identity_presentation(
                relation.reference,
                identities,
                {target.id: fact_evidence for target in identities},
            )
            if allow_identity_clarification and 1 < len(options) <= 4
            else None,
        )
    if selection.type is not None and any(target.type != selection.type for target in targets):
        raise RelationalResolutionError(
            "relational_target_type_mismatch", evidence_guard=evidence_guard
        )
    source = incoming_projection.entity if incoming_projection is not None else projection.source
    return ResolvedRelationalReference(
        source, projection.source, selected.id, direction, targets, evidence_guard
    )


def current_singular_relational_evidence_guard(
    projector: RelationshipEvidenceProjector, source_id: str
) -> str | None:
    """Return the current complete one-hop evidence guard for one singular relation source.

    The scope matches singular relational resolution: every current outgoing fact on the source plus
    every current incoming fact that links to it. Callers use this only to prove that the candidate
    universe has not changed between semantic resolution and mutation preflight.
    """
    outgoing = tuple(
        (fact, EvidenceDirection.OUTGOING) for fact in projector.facts_for_source(source_id)
    )
    projection = projector.project_entity_evidence_candidates(source_id)
    incoming = (
        tuple((item.fact, EvidenceDirection.INCOMING) for item in projection.incoming)
        if projection is not None
        else ()
    )
    candidates = (*outgoing, *incoming)
    return _candidate_evidence_guard(candidates) if candidates else None


def _same_wording(left: str, right: str) -> bool:
    """Compare planner wording after only whitespace and case normalization."""
    return " ".join(left.split()).casefold() == " ".join(right.split()).casefold()


def _resolve_qualified_singular_write(
    selection: SelectionCriteria,
    source_id: str,
    projector: RelationshipEvidenceProjector,
    incoming_projection: Any,
    candidates: tuple[tuple[CanonicalFact, EvidenceDirection], ...],
    evidence_guard: str,
    *,
    repository: VaultRepository,
    schema: dict[str, Any],
    contextual_reasoner: Any,
    semantic_set_selector: Any | None,
    semantic_limit: int,
    chosen_identity_id: str | None,
) -> ResolvedRelationalReference:
    """Use a canonical relationship as a candidate anchor, then apply the full WRITE description.

    The relationship selector may identify several current source facts and therefore several linked
    identities. Those identities form an authoritative candidate universe; the full target query is
    then evaluated only inside that universe, using each candidate's own canonical note plus incoming
    backlink evidence. No global semantic candidate can enter the decision at this stage.
    """
    relation = selection.relational_reference
    assert relation is not None and relation.members == "one"
    selected_facts = _select_relevant_read_facts(
        relation.reference,
        candidates,
        semantic_set_selector,
        require_occurrences=False,
    )
    if not selected_facts:
        raise RelationalResolutionError(
            "relational_evidence_unavailable", evidence_guard=evidence_guard
        )

    targets: list[CanonicalIdentity] = []
    grounding: dict[str, tuple[CanonicalFact, EvidenceDirection, Any]] = {}
    seen: set[str] = set()
    for fact, direction in selected_facts:
        projection = projector.project_targets(fact.source.id, fact.locator)
        if projection.status is TargetProjectionStatus.INACTIVE_TARGETS:
            # A tombstoned canonical identity is not a current relationship candidate. Keep the
            # fact in the evidence guard, but ignore its inactive members for singular narrowing.
            if not projection.targets:
                continue
        elif projection.status is not TargetProjectionStatus.COMPLETE:
            raise RelationalResolutionError(
                "relational_evidence_incomplete", evidence_guard=evidence_guard
            )
        if projection.source is None:
            raise RelationalResolutionError(
                "relational_evidence_incomplete", evidence_guard=evidence_guard
            )
        if direction is EvidenceDirection.INCOMING:
            if not any(target.id == source_id for target in projection.targets):
                raise RelationalResolutionError(
                    "relational_evidence_incomplete", evidence_guard=evidence_guard
                )
            projected_targets = (projection.source,)
        else:
            projected_targets = projection.targets
        for target in projected_targets:
            if selection.type is not None and target.type != selection.type:
                raise RelationalResolutionError(
                    "relational_target_type_mismatch", evidence_guard=evidence_guard
                )
            if target.id not in seen:
                seen.add(target.id)
                targets.append(target)
                grounding[target.id] = (fact, direction, projection)

    if not targets:
        raise RelationalResolutionError(
            "relational_evidence_unavailable", evidence_guard=evidence_guard
        )
    if len(targets) > semantic_limit:
        raise RelationalResolutionError(
            "relational_candidate_scope_too_large", evidence_guard=evidence_guard
        )

    contextual_candidates = tuple(
        ContextualCandidate(
            target.id,
            _qualified_target_evidence(projector, repository, schema, target),
        )
        for target in targets
    )
    raw_decision, _usage = contextual_reasoner.resolve(
        ContextualResolutionRequest(
            reference=selection.query,
            context=selection.query,
            entity_type=selection.type or targets[0].type,
            candidates=contextual_candidates,
        )
    )
    decision = validate_contextual_decision(raw_decision, {target.id for target in targets})
    if decision.outcome != "RESOLVED" or decision.id is None:
        plausible = tuple(target for target in targets if target.id in decision.ambiguous_ids)
        options = tuple(target.id for target in plausible)
        if chosen_identity_id is not None and chosen_identity_id in options:
            selected_target = next(
                target for target in plausible if target.id == chosen_identity_id
            )
            fact, direction, projection = grounding[selected_target.id]
            source = (
                incoming_projection.entity if incoming_projection is not None else projection.source
            )
            assert source is not None
            return ResolvedRelationalReference(
                source,
                projection.source,
                fact.locator,
                direction,
                (selected_target,),
                evidence_guard,
            )
        has_clarification_options = 1 < len(options) <= 4
        reason = "relational_evidence_ambiguous"
        if decision.outcome == "UNRESOLVED" and not has_clarification_options:
            reason = "relational_qualified_target_unresolved"
        presentation = None
        if has_clarification_options:
            presentation = _identity_presentation(
                selection.query,
                plausible,
                {
                    target.id: _bounded_fact_evidence(grounding[target.id][0])
                    for target in plausible
                },
            )
        raise RelationalResolutionError(
            reason,
            options if has_clarification_options else (),
            evidence_guard,
            presentation,
        )

    selected_target = next(target for target in targets if target.id == decision.id)
    fact, direction, projection = grounding[selected_target.id]
    source = incoming_projection.entity if incoming_projection is not None else projection.source
    assert source is not None
    return ResolvedRelationalReference(
        source,
        projection.source,
        fact.locator,
        direction,
        (selected_target,),
        evidence_guard,
    )


def _qualified_target_evidence(
    projector: RelationshipEvidenceProjector,
    repository: VaultRepository,
    schema: dict[str, Any],
    target: CanonicalIdentity,
) -> str:
    """Build candidate evidence from its note plus current incoming backlink facts.

    Outgoing facts are already present in the candidate note body. Incoming facts live in other notes,
    so they are appended explicitly with source identity provenance; this makes backlinks first-class
    evidence without turning the derived backlink index into an authority.
    """
    try:
        note = parse_note(repository.read_text(target.path))
        validate_note(note, schema)
    except (OSError, NoteFormatError, NoteValidationError) as error:
        raise RelationalResolutionError("relational_candidate_unavailable") from error
    evidence = build_provider_evidence(note, target.path)
    projection = projector.project_entity_evidence_candidates(target.id)
    if projection is None or not projection.incoming:
        return evidence
    incoming = []
    for item in projection.incoming:
        source = item.fact.source
        incoming.append(
            f"[incoming; source={source.name} ({source.type})] "
            f"{_humanize_fact_links(item.fact.text).strip()}"
        )
    return evidence + "\nRelated canonical incoming evidence:\n" + "\n".join(incoming)


def _bounded_fact_evidence(fact: CanonicalFact) -> str:
    """Render one current canonical fact as a short neutral public snippet."""
    evidence = _humanize_fact_links(fact.text).strip()
    if len(evidence) > MAX_CLARIFICATION_EVIDENCE_CHARS:
        return evidence[: MAX_CLARIFICATION_EVIDENCE_CHARS - 1].rstrip() + "…"
    return evidence


def _combine_fact_evidence(snippets: list[str]) -> str:
    """Dedupe selected canonical fact snippets and keep their public evidence bounded."""
    unique = tuple(dict.fromkeys(snippet.strip() for snippet in snippets if snippet.strip()))
    evidence = " · ".join(unique)
    if len(evidence) > MAX_CLARIFICATION_EVIDENCE_CHARS:
        return evidence[: MAX_CLARIFICATION_EVIDENCE_CHARS - 1].rstrip() + "…"
    return evidence


def _identity_presentation(
    reference: str,
    identities: tuple[CanonicalIdentity, ...],
    evidence_by_id: dict[str, str],
) -> ClarificationPresentation:
    """Build a bounded explanation from re-projected current canonical identities and facts."""
    return ClarificationPresentation(
        reference.strip(),
        tuple(
            ClarificationCandidateEvidence(
                identity.id,
                identity.name,
                identity.type,
                evidence_by_id[identity.id],
            )
            for identity in identities
        ),
    )


def _select_relevant_read_facts(
    query: str,
    candidates: tuple[tuple[CanonicalFact, EvidenceDirection], ...],
    selector: Any | None,
    *,
    require_occurrences: bool = True,
) -> tuple[tuple[CanonicalFact, EvidenceDirection], ...]:
    """Return every bounded selector-proposed read fact, never a single contextual winner.

    The existing semantic-set selector already returns a bounded set of supplied fact IDs.  Its
    exact occurrences demonstrate direct textual support; their text is not used to grant target
    identity authority.  Every selected locator is still re-grounded below.
    """
    if not callable(getattr(selector, "select", None)):
        raise RelationalResolutionError("relational_relevance_unavailable")
    selector_candidates = tuple(
        SemanticSetCandidate(f"relational-{index}", fact)
        for index, (fact, _direction) in enumerate(candidates)
    )
    batches = partition_semantic_set_candidates(selector_candidates)
    if isinstance(batches, SemanticSetResolution):
        # The public batching helper returns a structured failure for an oversized item or invalid
        # payload bound. Do not silently omit it from a singular identity decision.
        raise RelationalResolutionError("relational_evidence_incomplete")
    assert isinstance(batches, tuple)
    selected: list[tuple[CanonicalFact, EvidenceDirection]] = []
    candidate_lookup = {
        candidate.id: candidates[index] for index, candidate in enumerate(selector_candidates)
    }
    for batch in batches:
        try:
            proposed = selector.select(
                SemanticSetSelectionRequest(
                    query=query,
                    intent=None,
                    candidates=tuple(
                        SemanticSetCandidateView(
                            candidate.id, _humanize_fact_links(candidate.fact.text)
                        )
                        for candidate in batch
                    ),
                )
            )
            _validate_relational_selection(proposed, batch, require_occurrences=require_occurrences)
        except RelationalResolutionError:
            raise
        except (TypeError, ValueError):
            raise RelationalResolutionError("relational_evidence_incomplete") from None
        except Exception:
            raise RelationalResolutionError("relational_relevance_unavailable") from None
        if proposed.scope_uncertain:
            raise RelationalResolutionError("relational_evidence_ambiguous")
        selected.extend(
            candidate_lookup[candidate_id] for candidate_id in proposed.supplied_fact_ids
        )
    return tuple(selected)


def _validate_relational_selection(
    proposed: SetEvidenceSelection,
    batch: tuple[SemanticSetCandidate, ...],
    *,
    require_occurrences: bool = True,
) -> None:
    """Validate bounded relevance IDs and, when required, their direct occurrence spans."""
    if not isinstance(proposed, SetEvidenceSelection) or not isinstance(
        proposed.scope_uncertain, bool
    ):
        raise ValueError("Relational relevance selection is invalid")
    supplied = set(proposed.supplied_fact_ids)
    allowed = {candidate.id for candidate in batch}
    if (
        len(supplied) != len(proposed.supplied_fact_ids)
        or not supplied <= allowed
        or len(proposed.member_occurrences) > DEFAULT_SEMANTIC_SET_BOUNDS.members
    ):
        raise ValueError("Relational relevance selection is outside its batch")
    if not require_occurrences:
        return
    by_id = {candidate.id: candidate for candidate in batch}
    supported_ids: set[str] = set()
    for occurrence in proposed.member_occurrences:
        if occurrence.candidate_id not in supplied or occurrence.kind not in {"literal", "link"}:
            raise ValueError("Relational relevance occurrence is invalid")
        text = _humanize_fact_links(by_id[occurrence.candidate_id].fact.text)
        if occurrence.start < 0 or occurrence.end <= occurrence.start or occurrence.end > len(text):
            raise ValueError("Relational relevance occurrence is outside its fact")
        supported_ids.add(occurrence.candidate_id)
    if supplied != supported_ids:
        raise ValueError("Every relational fact requires direct selected evidence")


def _resolve_selected_read_facts(
    selection: SelectionCriteria,
    source_id: str,
    projector: RelationshipEvidenceProjector,
    incoming_projection: Any,
    selected_candidates: tuple[tuple[CanonicalFact, EvidenceDirection], ...],
    evidence_guard: str,
    chosen_identity_id: str | None,
) -> ResolvedRelationalReference:
    """Project complete target sets for all relevant facts before deciding a singular identity."""
    unique_targets: list[CanonicalIdentity] = []
    seen_target_ids: set[str] = set()
    evidence_by_id: dict[str, list[str]] = {}
    first_projection = None
    first_direction = None
    for fact, direction in selected_candidates:
        projection = projector.project_targets(fact.source.id, fact.locator)
        if projection.status is not TargetProjectionStatus.COMPLETE or projection.source is None:
            raise RelationalResolutionError(
                "relational_evidence_incomplete", evidence_guard=evidence_guard
            )
        if direction is EvidenceDirection.INCOMING:
            if not any(target.id == source_id for target in projection.targets):
                raise RelationalResolutionError(
                    "relational_evidence_incomplete", evidence_guard=evidence_guard
                )
            targets = (projection.source,)
        else:
            targets = projection.targets
        if not targets:
            raise RelationalResolutionError(
                "relational_evidence_incomplete", evidence_guard=evidence_guard
            )
        if first_projection is None:
            first_projection, first_direction = projection, direction
        for target in targets:
            evidence_by_id.setdefault(target.id, []).append(_bounded_fact_evidence(fact))
            if target.id not in seen_target_ids:
                seen_target_ids.add(target.id)
                unique_targets.append(target)
    if selection.type is not None and any(
        target.type != selection.type for target in unique_targets
    ):
        raise RelationalResolutionError(
            "relational_target_type_mismatch", evidence_guard=evidence_guard
        )
    relation = selection.relational_reference
    assert relation is not None and first_projection is not None and first_direction is not None
    if relation.members == "one" and len(unique_targets) != 1:
        options = tuple(target.id for target in unique_targets)
        if chosen_identity_id is not None:
            if not (1 < len(options) <= 4 and chosen_identity_id in options):
                raise RelationalResolutionError(
                    "clarification_scope_changed", evidence_guard=evidence_guard
                )
            unique_targets = [
                target for target in unique_targets if target.id == chosen_identity_id
            ]
        elif 1 < len(options) <= 4:
            reason = (
                "relational_singular_ambiguous"
                if len(selected_candidates) == 1
                else "relational_evidence_ambiguous"
            )
            raise RelationalResolutionError(
                reason,
                options,
                evidence_guard,
                _identity_presentation(
                    relation.reference,
                    tuple(unique_targets),
                    {
                        target.id: _combine_fact_evidence(evidence_by_id[target.id])
                        for target in unique_targets
                    },
                ),
            )
        else:
            raise RelationalResolutionError(
                "relational_evidence_ambiguous", evidence_guard=evidence_guard
            )
    source = (
        incoming_projection.entity if incoming_projection is not None else first_projection.source
    )
    assert source is not None
    return ResolvedRelationalReference(
        source,
        first_projection.source,
        selected_candidates[0][0].locator,
        first_direction,
        tuple(unique_targets),
        evidence_guard,
    )


def _candidate_evidence_guard(
    candidates: tuple[tuple[CanonicalFact, EvidenceDirection], ...],
) -> str:
    """Hash the exact current candidate locator/revision scope without retaining its text."""
    payload = "\n".join(
        f"{fact.source.id}\0{fact.source.source_hash}\0{fact.locator}\0{direction.value}"
        for fact, direction in candidates
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _humanize_fact_links(text: str) -> str:
    """Show a model the visible linked fact wording without vault-relative path components."""
    return _WIKILINK_DISPLAY.sub(
        lambda match: (match.group(2) or PurePosixPath(match.group(1)).name).strip(), text
    )
