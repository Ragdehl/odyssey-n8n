"""Production orchestration for resolving an already-extracted entity reference."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Any

from odyssey_core.contextual import (
    ContextualCandidate,
    ContextualReasoner,
    ContextualResolutionRequest,
    validate_contextual_decision,
)
from odyssey_core.identity import (
    ExactEntityCandidate,
    ExactResolutionOutcome,
    resolve_exact_entity,
)
from odyssey_core.notes import Note, NoteFormatError, NoteValidationError, parse_note, validate_note
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
        usage: Provider counters only; never prompt, response, or credential content.
    """

    outcome: ExistingEntityOutcome
    id: str | None
    source: ResolutionSource
    candidate_ids: tuple[str, ...] = ()
    usage: Mapping[str, Any] | None = None


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
        path: Vault-relative Markdown path whose stem is the canonical display name.

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

    lines = [f"Name: {PurePosixPath(path).stem}"]
    aliases = note.metadata.get("aliases")
    if isinstance(aliases, list) and aliases:
        lines.append("Aliases: " + ", ".join(str(value) for value in aliases))
    lines.append(f"Type: {note_type}")
    for key in sorted(note.metadata):
        if (
            key in _TECHNICAL_METADATA
            or key in _NON_IDENTITY_FACETS
            or key in {"id", "aliases", "type"}
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

    Returns:
        A typed local or contextual production result.

    Raises:
        ExistingEntityResolutionError: If a retrieved candidate cannot be safely loaded.
        ContextualResolutionError: If contextual output is malformed or provider access fails.
        ValueError: If local resolution inputs violate existing contracts.
    """
    exact = resolve_exact_entity(repository, schema, reference, type=type)
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
    candidates = _merge_candidates(semantic_candidates, exact.candidates)
    if not candidates:
        return ExistingEntityResolution(
            outcome=ExistingEntityOutcome.UNRESOLVED,
            id=None,
            source=ResolutionSource.LOCAL_NO_CANDIDATES,
            candidate_ids=(),
        )

    contextual_candidates = tuple(
        ContextualCandidate(
            candidate.id, _load_provider_evidence(repository, schema, candidate.path)
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
    return ExistingEntityResolution(
        outcome=ExistingEntityOutcome(decision.outcome),
        id=decision.id,
        source=ResolutionSource.CONTEXTUAL,
        candidate_ids=tuple(candidate.id for candidate in candidates),
        usage=_safe_usage(usage),
    )


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


def _load_provider_evidence(repository: VaultRepository, schema: dict[str, Any], path: str) -> str:
    """Read, parse, and validate one candidate before constructing external evidence."""
    try:
        note = parse_note(repository.read_text(path))
        validate_note(note, schema)
    except (NoteFormatError, NoteValidationError, OSError) as error:
        raise ExistingEntityResolutionError(
            "Cannot safely load a contextual candidate note"
        ) from error
    return build_provider_evidence(note, path)


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
