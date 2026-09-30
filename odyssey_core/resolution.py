"""Production orchestration for resolving an already-extracted entity reference."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Any

from odyssey_core.clarification_presentation import (
    MAX_CLARIFICATION_EVIDENCE_CHARS,
    ClarificationCandidateEvidence,
    ClarificationPresentation,
)
from odyssey_core.contextual import (
    ContextualCandidate,
    ContextualReasoner,
    ContextualResolutionRequest,
    validate_contextual_decision,
)
from odyssey_core.identity import (
    ExactEntityCandidate,
    ExactEntityResolution,
    ExactResolutionOutcome,
    resolve_exact_entity,
)
from odyssey_core.notes import Note, NoteFormatError, NoteValidationError, parse_note, validate_note
from odyssey_core.relationship_evidence import (
    RelationshipEvidence,
    RelationshipEvidenceProjector,
    TargetProjectionStatus,
)
from odyssey_core.semantic import (
    SemanticEntityCandidate,
    SemanticEntityIndex,
    TextEmbedder,
    find_semantic_entity_candidates,
)
from odyssey_core.storage import VaultRepository


class ExistingEntityResolutionError(RuntimeError):
    """Indicate that an existing-note resolution could not be completed safely."""


class ResolutionSource(Enum):
    """Identify whether contextual-provider disclosure occurred for a result."""

    EXACT_LOCAL = "exact_local"
    LOCAL_NO_CANDIDATES = "local_no_candidates"
    CONTEXTUAL = "contextual"


class ExistingEntityOutcome(Enum):
    """Represent the production outcomes for an already-extracted entity reference."""

    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class ExistingEntityResolution:
    """Return a validated existing-note resolution without creating or updating a note.

    Attributes:
        outcome: Resolved, ambiguous, or unresolved semantic outcome.
        id: The selected canonical note ID, or ``None`` when abstaining.
        source: Local exact, local no-candidate, or contextual decision source.
        candidate_ids: IDs supplied to the contextual reasoner, or empty for local results.
        has_ambiguous_exact_evidence: Whether the local exact lookup found more than one eligible
            primary-name/alias candidate before contextual reasoning.
        usage: Provider counters only; never prompt, response, or credential content.
    """

    outcome: ExistingEntityOutcome
    id: str | None
    source: ResolutionSource
    candidate_ids: tuple[str, ...] = ()
    usage: Mapping[str, Any] | None = None
    has_ambiguous_exact_evidence: bool = False
    clarification: ClarificationPresentation | None = None


_TECHNICAL_METADATA = frozenset(
    {
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "revision",
        "schema_version",
        "source_hash",
        "path",
    }
)
# Knowledge-classification facets are intentionally outside identity evidence.
_NON_IDENTITY_FACETS = frozenset({"tags"})
_WIKILINK_PATTERN = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]")


def build_provider_evidence(note: Note, path: str) -> str:
    """Build deterministic, minimized identity evidence for one validated note.

    The complete Markdown body is retained for now because relationships, negative evidence, and
    context-dependent identity facts can be decisive. Lifecycle, filesystem, source-integrity,
    schema, and retrieval-ranking data are intentionally excluded from the provider boundary.

    Args:
        note: Parsed note already validated against the canonical schema.
        path: Vault-relative Markdown path used only to load the validated note; canonical display
            identity comes from ``note.metadata["name"]``.

    Returns:
        Stable textual identity evidence containing no semantic score or rank.

    Raises:
        ValueError: If the note path or required identity metadata is unusable.
    """
    if not isinstance(path, str) or not path.endswith(".md"):
        raise ValueError("Provider evidence requires a Markdown note path")
    note_id = note.metadata.get("id")
    note_type = note.metadata.get("type")
    if not isinstance(note_id, str) or not isinstance(note_type, str):
        raise ValueError("Provider evidence requires validated note identity")

    name = note.metadata.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Provider evidence requires canonical note name")
    lines = [f"Name: {name}"]
    aliases = note.metadata.get("aliases")
    if isinstance(aliases, list) and aliases:
        lines.append("Aliases: " + ", ".join(str(value) for value in aliases))
    lines.append(f"Type: {note_type}")
    for key in sorted(note.metadata):
        if (
            key in _TECHNICAL_METADATA
            or key in _NON_IDENTITY_FACETS
            or key in {"id", "name", "aliases", "type"}
        ):
            continue
        value = note.metadata[key]
        rendered = ", ".join(str(item) for item in value) if isinstance(value, list) else str(value)
        lines.append(f"{key.replace('_', ' ').title()}: {rendered}")
    body = _WIKILINK_PATTERN.sub(
        _humanize_wikilink,
        note.content,
    )
    if body.strip():
        lines.append("Body: " + body.strip())
    return "\n".join(lines)


def _humanize_wikilink(match: re.Match[str]) -> str:
    """Render a wikilink as a display name without exposing vault path components."""
    alias = match.group(2)
    if alias is not None:
        return alias.strip()
    target = match.group(1).split("#", 1)[0].rstrip("/")
    return PurePosixPath(target).name.strip()


def resolve_existing_entity(
    reference: str,
    context: str,
    *,
    type: str | None = None,
    repository: VaultRepository,
    schema: dict[str, Any],
    semantic_index: SemanticEntityIndex,
    embedder: TextEmbedder,
    contextual_reasoner: ContextualReasoner,
    semantic_limit: int,
    allowed_candidate_ids: frozenset[str] | None = None,
    expand_relationship_context: bool = False,
    self_note_id: str | None = None,
) -> ExistingEntityResolution:
    """Resolve one extracted entity reference against existing validated notes.

    Exact unique matches return locally with no provider call. Otherwise, local semantic candidates
    are combined with every ambiguous exact candidate, notes are parsed and schema-validated, and
    exactly one contextual reasoner call is made when the set is non-empty. This function never
    creates or updates notes; provider failures propagate as system failures rather than becoming
    ``UNRESOLVED``.

    Args:
        reference: Already-extracted entity wording, not a full conversation.
        context: Only the surrounding context needed for this reference.
        type: Optional canonical note type constraint.
        repository: Authoritative Markdown repository.
        schema: Canonical note schema used for local validation.
        semantic_index: Existing Phase 10 derived retrieval index.
        embedder: Matching local Phase 10 query embedder.
        contextual_reasoner: Provider-independent one-call contextual boundary.
        semantic_limit: Explicit maximum semantic candidates before exact-collision union. No
            production default is chosen because Phase 11B.1c showed that Top-5 recall is not a
            safe large-vault assumption; callers must make this retrieval decision explicitly.
        allowed_candidate_ids: Optional authoritative deterministic restriction of eligible note
            IDs. It narrows exact and semantic evidence before any candidate is selected.
        expand_relationship_context: Whether to enrich semantic identity candidates with bounded
            one-hop canonical relationship evidence and co-targets before the contextual decision.
        self_note_id: Optional authenticated self identity used only to label canonical relationship
            evidence for first-person contextual resolution; it never selects a candidate directly.

    Returns:
        A typed local or contextual production result.

    Raises:
        ExistingEntityResolutionError: If a retrieved candidate cannot be safely loaded.
        ContextualResolutionError: If contextual output is malformed or provider access fails.
        ValueError: If local resolution inputs violate existing contracts.
    """
    if allowed_candidate_ids is not None and (
        not all(isinstance(note_id, str) and note_id for note_id in allowed_candidate_ids)
    ):
        raise ValueError("Allowed candidate IDs must be non-empty strings")
    if self_note_id is not None and (not isinstance(self_note_id, str) or not self_note_id):
        raise ValueError("Self note ID must be a non-empty string")
    exact = _restrict_exact_resolution(
        resolve_exact_entity(repository, schema, reference, type=type), allowed_candidate_ids
    )
    if exact.outcome is ExactResolutionOutcome.EXACT_MATCH:
        candidate = exact.candidate
        assert candidate is not None
        return ExistingEntityResolution(
            outcome=ExistingEntityOutcome.RESOLVED,
            id=candidate.id,
            source=ResolutionSource.EXACT_LOCAL,
            candidate_ids=(),
        )

    semantic_candidates = find_semantic_entity_candidates(
        semantic_index,
        embedder,
        reference,
        context=context,
        type=type,
        limit=semantic_limit,
    )
    if allowed_candidate_ids is not None:
        semantic_candidates = tuple(
            candidate for candidate in semantic_candidates if candidate.id in allowed_candidate_ids
        )
    semantic_candidates = tuple(
        candidate
        for candidate in semantic_candidates
        if _is_current_active_candidate(repository, schema, candidate.path, candidate.id)
    )
    candidates = _merge_candidates(semantic_candidates, exact.candidates)
    relationship_evidence: dict[str, tuple[str, ...]] = {}
    if expand_relationship_context and candidates:
        candidates, relationship_evidence = _expand_relationship_candidates(
            repository,
            schema,
            candidates,
            note_type=type,
            expansion_limit=semantic_limit,
            allowed_candidate_ids=allowed_candidate_ids,
            self_note_id=self_note_id,
        )
    if not candidates:
        return ExistingEntityResolution(
            outcome=ExistingEntityOutcome.UNRESOLVED,
            id=None,
            source=ResolutionSource.LOCAL_NO_CANDIDATES,
            candidate_ids=(),
        )

    contextual_candidates = tuple(
        ContextualCandidate(
            candidate.id,
            _load_provider_evidence(
                repository,
                schema,
                candidate.path,
                relationship_evidence=relationship_evidence.get(candidate.id, ()),
            ),
        )
        for candidate in candidates
    )
    request = ContextualResolutionRequest(
        reference=reference,
        context=context,
        entity_type=type or "unspecified",
        candidates=contextual_candidates,
    )
    raw_decision, usage = contextual_reasoner.resolve(request)
    decision = validate_contextual_decision(
        raw_decision, {candidate.id for candidate in candidates}
    )
    candidate_ids = _decision_candidate_ids(decision, candidates, exact)
    clarification = _decision_clarification(
        reference, candidate_ids, candidates, repository, schema
    )
    return ExistingEntityResolution(
        outcome=ExistingEntityOutcome(decision.outcome),
        id=decision.id,
        source=ResolutionSource.CONTEXTUAL,
        candidate_ids=candidate_ids,
        has_ambiguous_exact_evidence=(
            exact.outcome is ExactResolutionOutcome.AMBIGUOUS_EXACT_MATCH
        ),
        usage=_safe_usage(usage),
        clarification=clarification,
    )


def _decision_candidate_ids(
    decision: Any, candidates, exact: ExactEntityResolution
) -> tuple[str, ...]:
    """Preserve resolved evidence while narrowing only an ambiguous decision subset."""
    if decision.outcome == "RESOLVED":
        return tuple(candidate.id for candidate in candidates)
    if decision.outcome in {"AMBIGUOUS", "UNRESOLVED"} and decision.ambiguous_ids:
        return decision.ambiguous_ids
    if exact.outcome is ExactResolutionOutcome.AMBIGUOUS_EXACT_MATCH:
        return tuple(candidate.id for candidate in exact.candidates)
    return ()


def _decision_clarification(
    reference: str,
    candidate_ids: tuple[str, ...],
    candidates,
    repository: VaultRepository,
    schema: dict[str, Any],
) -> ClarificationPresentation | None:
    """Create public ambiguity evidence only for the bounded safe option count."""
    if not 1 < len(candidate_ids) <= 4:
        return None
    return _build_note_clarification_presentation(
        reference, candidate_ids, candidates, repository, schema
    )


def _build_note_clarification_presentation(
    reference: str,
    candidate_ids: tuple[str, ...],
    candidates: tuple[SemanticEntityCandidate | ExactEntityCandidate, ...],
    repository: VaultRepository,
    schema: dict[str, Any],
) -> ClarificationPresentation:
    """Re-read the exact validated subset and derive neutral canonical snippets."""
    paths = {candidate.id: candidate.path for candidate in candidates}
    options: list[ClarificationCandidateEvidence] = []
    for candidate_id in candidate_ids:
        path = paths.get(candidate_id)
        if path is None:
            raise ExistingEntityResolutionError("Clarification candidate is no longer supplied")
        try:
            note = parse_note(repository.read_text(path))
            validate_note(note, schema)
        except (NoteFormatError, NoteValidationError, OSError) as error:
            raise ExistingEntityResolutionError(
                "Cannot safely load a clarification candidate note"
            ) from error
        if note.metadata.get("id") != candidate_id or note.metadata.get("deleted") is True:
            raise ExistingEntityResolutionError("Clarification candidate is no longer current")
        name = note.metadata.get("name")
        note_type = note.metadata.get("type")
        if not isinstance(name, str) or not isinstance(note_type, str):
            raise ExistingEntityResolutionError("Clarification candidate identity is invalid")
        visible_body = _WIKILINK_PATTERN.sub(_humanize_wikilink, note.content).strip()
        first_line = next(
            (
                line.strip()
                for line in visible_body.splitlines()
                if line.strip()
                and re.match(r"^#{1,6}(?:\s|$)", line.strip()) is None
                and not line.strip().startswith("<!--")
            ),
            "",
        )
        evidence = first_line or f"Nombre canónico: {name}."
        if len(evidence) > MAX_CLARIFICATION_EVIDENCE_CHARS:
            evidence = evidence[: MAX_CLARIFICATION_EVIDENCE_CHARS - 1].rstrip() + "…"
        options.append(ClarificationCandidateEvidence(candidate_id, name, note_type, evidence))
    return ClarificationPresentation(reference.strip(), tuple(options))


def _restrict_exact_resolution(
    exact: ExactEntityResolution, allowed_candidate_ids: frozenset[str] | None
) -> ExactEntityResolution:
    """Apply an authoritative candidate-ID restriction to exact identity evidence."""
    if allowed_candidate_ids is None:
        return exact
    candidates = tuple(
        candidate for candidate in exact.candidates if candidate.id in allowed_candidate_ids
    )
    if not candidates:
        outcome = ExactResolutionOutcome.NO_EXACT_MATCH
    elif len(candidates) == 1:
        outcome = ExactResolutionOutcome.EXACT_MATCH
    else:
        outcome = ExactResolutionOutcome.AMBIGUOUS_EXACT_MATCH
    return ExactEntityResolution(outcome, exact.query, exact.type, candidates)


def _merge_candidates(
    semantic_candidates: tuple[SemanticEntityCandidate, ...],
    exact_candidates: tuple[ExactEntityCandidate, ...],
) -> tuple[SemanticEntityCandidate | ExactEntityCandidate, ...]:
    """Union ranked semantic and exact-collision candidates in deterministic order."""
    merged: list[SemanticEntityCandidate | ExactEntityCandidate] = list(semantic_candidates)
    seen = {candidate.id for candidate in merged}
    for candidate in exact_candidates:
        if candidate.id not in seen:
            merged.append(candidate)
            seen.add(candidate.id)
    return tuple(merged)


def _expand_relationship_candidates(
    repository: VaultRepository,
    schema: dict[str, Any],
    candidates: tuple[SemanticEntityCandidate | ExactEntityCandidate, ...],
    *,
    note_type: str | None,
    expansion_limit: int,
    allowed_candidate_ids: frozenset[str] | None,
    self_note_id: str | None,
) -> tuple[
    tuple[SemanticEntityCandidate | ExactEntityCandidate, ...],
    dict[str, tuple[str, ...]],
]:
    """Expand ranked identities through bounded one-hop canonical relationship evidence.

    Expansion never selects an identity. It adds at most ``expansion_limit`` current co-target/source
    identities that are explicitly connected by the same canonical facts as the locally retrieved
    candidates. The contextual reasoner still decides whether exactly one supplied candidate is
    supported by the user's wording.
    """
    projector = RelationshipEvidenceProjector(repository, schema)
    ordered: list[SemanticEntityCandidate | ExactEntityCandidate] = list(candidates)
    seen = {candidate.id for candidate in ordered}
    evidence_by_id: dict[str, list[str]] = {candidate.id: [] for candidate in ordered}
    added = 0

    def eligible(identity: Any) -> bool:
        return (note_type is None or identity.type == note_type) and (
            allowed_candidate_ids is None or identity.id in allowed_candidate_ids
        )

    def add_identity(identity: Any) -> None:
        nonlocal added
        if identity.id in seen or added >= expansion_limit or not eligible(identity):
            return
        ordered.append(
            SemanticEntityCandidate(identity.id, identity.path, identity.type, identity.name, 0.0)
        )
        seen.add(identity.id)
        evidence_by_id.setdefault(identity.id, [])
        added += 1

    for candidate in candidates:
        projection = projector.project_entity_evidence_candidates(candidate.id)
        if projection is None:
            continue
        for item in (*projection.incoming, *projection.outgoing):
            rendered = _render_relationship_evidence(item, self_note_id=self_note_id)
            if rendered not in evidence_by_id[candidate.id]:
                evidence_by_id[candidate.id].append(rendered)
            target_projection = projector.project_targets(item.fact.source.id, item.fact.locator)
            if target_projection.status is not TargetProjectionStatus.COMPLETE:
                continue
            if target_projection.source is not None and target_projection.source.id != self_note_id:
                add_identity(target_projection.source)
                if target_projection.source.id in evidence_by_id:
                    if rendered not in evidence_by_id[target_projection.source.id]:
                        evidence_by_id[target_projection.source.id].append(rendered)
            for target in target_projection.targets:
                add_identity(target)
                if target.id in evidence_by_id and rendered not in evidence_by_id[target.id]:
                    evidence_by_id[target.id].append(rendered)

    return tuple(ordered), {
        note_id: tuple(values) for note_id, values in evidence_by_id.items() if values
    }


def _render_relationship_evidence(
    evidence: RelationshipEvidence, *, self_note_id: str | None
) -> str:
    """Render one canonical relationship fact with explicit source provenance for Luna."""
    source = evidence.fact.source
    source_label = (
        "authenticated self"
        if self_note_id is not None and source.id == self_note_id
        else f"{source.name} ({source.type})"
    )
    visible = _WIKILINK_PATTERN.sub(_humanize_wikilink, evidence.fact.text).strip()
    direction = evidence.direction.value
    return f"[{direction}; source={source_label}] {visible}"


def _load_provider_evidence(
    repository: VaultRepository,
    schema: dict[str, Any],
    path: str,
    *,
    relationship_evidence: tuple[str, ...] = (),
) -> str:
    """Read, validate, and minimally enrich one candidate before contextual resolution."""
    try:
        note = parse_note(repository.read_text(path))
        validate_note(note, schema)
    except (NoteFormatError, NoteValidationError, OSError) as error:
        raise ExistingEntityResolutionError(
            "Cannot safely load a contextual candidate note"
        ) from error
    evidence = build_provider_evidence(note, path)
    if relationship_evidence:
        evidence += "\nRelated canonical evidence:\n" + "\n".join(relationship_evidence)
    return evidence


def _is_current_active_candidate(
    repository: VaultRepository, schema: dict[str, Any], path: str, expected_id: str
) -> bool:
    """Return whether derived evidence still names the current active source note."""
    try:
        note = parse_note(repository.read_text(path))
        validate_note(note, schema)
    except (NoteFormatError, NoteValidationError, OSError) as error:
        raise ExistingEntityResolutionError(
            "Cannot safely ground a semantic candidate note"
        ) from error
    return note.metadata.get("id") == expected_id and note.metadata.get("deleted") is not True


def _safe_usage(usage: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Keep only the fixed operational usage contract and discard all other provider fields."""
    if usage is None:
        return None
    allowed = frozenset(
        {
            "response_id",
            "input_tokens",
            "cached_input_tokens",
            "cache_write_tokens",
            "output_tokens",
            "reasoning_tokens",
        }
    )
    return {
        str(key): value for key, value in usage.items() if key in allowed and isinstance(key, str)
    }
