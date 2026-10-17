"""Deterministic exact entity lookup over validated Odyssey notes."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from odyssey_core.notes import NoteFormatError, NoteValidationError, parse_note, validate_note
from odyssey_core.schema_types import referenceable_type_ids
from odyssey_core.storage import VaultRepository
from odyssey_core.verified_metadata_catalog import VerifiedCatalogError, verified_catalog_if_active


class ExactEntityLookupError(RuntimeError):
    """Indicate that a vault note could not safely participate in entity lookup."""


class MatchKind(Enum):
    """Describe the deterministic identity signal that matched a candidate."""

    PRIMARY_NAME = "primary_name"
    ALIAS = "alias"


class ExactResolutionOutcome(Enum):
    """Describe the outcome of exact deterministic identity resolution."""

    EXACT_MATCH = "exact_match"
    NO_EXACT_MATCH = "no_exact_match"
    AMBIGUOUS_EXACT_MATCH = "ambiguous_exact_match"


@dataclass(frozen=True, slots=True)
class ExactEntityCandidate:
    """Expose the useful identity evidence for one matching validated note.

    Attributes:
        path: Vault-relative POSIX path of the note.
        id: Stable logical note identifier from canonical metadata.
        type: Canonical note type from validated metadata.
        primary_name: Canonical human-readable name from note metadata. The historical field name is
            retained in this evidence type for API compatibility.
        match_kind: Whether the query matched the primary name or an alias.
        matched_value: Exact stored primary name or alias that matched after normalization.
    """

    path: str
    id: str
    type: str
    primary_name: str
    match_kind: MatchKind
    matched_value: str
    # Core-only prompt hint: excluded from identity comparisons and repr so
    # normal exact resolution and public identifiers have unchanged semantics.
    content_excerpt: str = field(default="", compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class ExactEntityResolution:
    """Represent an exact deterministic resolution outcome and its evidence.

    Attributes:
        outcome: Unique, absent, or ambiguous exact-match outcome.
        query: Trimmed entity reference evaluated by the resolver.
        type: Optional canonical type constraint applied to the lookup.
        candidates: Deterministically ordered exact identity candidates.
    """

    outcome: ExactResolutionOutcome
    query: str
    type: str | None
    candidates: tuple[ExactEntityCandidate, ...]

    @property
    def candidate(self) -> ExactEntityCandidate | None:
        """Return the unique exact candidate, or ``None`` for other outcomes."""
        if self.outcome is ExactResolutionOutcome.EXACT_MATCH:
            return self.candidates[0]
        return None


def _normalize_reference(value: str) -> str:
    """Normalize one identity value for exact Unicode-aware comparison.

    Args:
        value: Query, canonical name, or alias to normalize.

    Returns:
        Surrounding-whitespace-trimmed and case-folded text.

    Raises:
        ValueError: If the value is not text.
    """
    if not isinstance(value, str):
        raise ValueError("Entity reference must be text")
    # NFC joins canonically equivalent Unicode sequences without erasing accents,
    # punctuation, or other identity-bearing text.
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def _canonical_types(schema: dict[str, Any]) -> set[str]:
    """Return referenceable semantic type IDs available to generic identity resolution."""
    try:
        type_ids = set(referenceable_type_ids(schema))
    except ValueError:
        raise ValueError("Supplied schema is not a usable canonical schema") from None
    if not type_ids:
        raise ValueError("Supplied schema is not a usable canonical schema")
    return type_ids


def find_exact_entity_candidates(
    repository: VaultRepository,
    schema: dict[str, Any],
    query: str,
    *,
    type: str | None = None,
    include_deleted: bool = False,
) -> tuple[ExactEntityCandidate, ...]:
    """Find deterministic exact-name and exact-alias candidates in a Markdown vault.

    Every listed note is read, parsed, and validated before a result is returned. This
    fail-closed policy prevents a malformed existing note from being silently ignored and
    producing an unsafe ``NO_EXACT_MATCH`` decision in duplicate-prevention workflows.

    Args:
        repository: Raw filesystem boundary used to list and read Markdown text.
        schema: Parsed canonical schema used to validate every parsed note.
        query: Already-extracted entity name, such as ``"Carrefour"``.
        type: Optional canonical note type, such as ``"store"``.
        include_deleted: Whether retired notes participate. Ordinary resolution keeps this false.

    Returns:
        Deterministically ordered exact identity candidates. The tuple is empty when no
        primary name or alias matches. Partial and semantic matches are deliberately absent.

    Raises:
        ValueError: If the query is empty or the type/schema is not canonical.
        ExactEntityLookupError: If a Markdown note cannot be parsed or validated safely.
        VaultRepository exceptions: If listing or raw note access fails.

    Example:
        ``find_exact_entity_candidates(repository, schema, " carrefour ", type="store")`` can
        return a filename match for ``stores/Carrefour.md`` or an alias match on another store.
    """
    return find_exact_entity_candidates_batch(
        repository, schema, ((query, type),), include_deleted=include_deleted
    )[0]


def find_exact_entity_candidates_batch(
    repository: VaultRepository,
    schema: dict[str, Any],
    queries: tuple[tuple[str, str | None], ...],
    *,
    include_deleted: bool = False,
) -> tuple[tuple[ExactEntityCandidate, ...], ...]:
    """Resolve multiple exact canonical Note names/aliases in ONE validated vault scan.

    This is the same canonical identity logic as `find_exact_entity_candidates`,
    not a competing search algorithm. Results preserve query order and multiple
    homonyms. A malformed Note fails the whole batch; nothing is partially
    returned or used to authorize a write.
    """
    if (
        not isinstance(queries, tuple)
        or not 1 <= len(queries) <= 12
        or any(not isinstance(item, tuple) or len(item) != 2 for item in queries)
    ):
        raise ValueError("Exact Note batch requires 1-12 typed queries")
    canonical_types = _canonical_types(schema)
    parsed: list[tuple[str, str | None]] = []
    for query, note_type in queries:
        normalized = _normalize_reference(query)
        if not normalized:
            raise ValueError("Entity reference must not be empty")
        if note_type is not None and (
            not isinstance(note_type, str) or note_type not in canonical_types
        ):
            raise ValueError(f"Unknown canonical note type: {note_type!r}")
        parsed.append((normalized, note_type))

    results: list[list[ExactEntityCandidate]] = [[] for _ in parsed]
    try:
        verified = verified_catalog_if_active(repository, schema)
    except VerifiedCatalogError as error:
        raise ExactEntityLookupError("Cannot safely inspect canonical source metadata") from error
    if verified is None:

        def source_notes():
            for path in repository.list_markdown_paths():
                try:
                    note = parse_note(repository.read_text(path))
                    validate_note(note, schema)
                except (NoteFormatError, NoteValidationError) as error:
                    raise ExactEntityLookupError(
                        f"Cannot safely inspect invalid note: {path}"
                    ) from error
                yield (
                    path,
                    note.metadata["id"],
                    note.metadata["type"],
                    note.metadata["name"],
                    tuple(note.metadata.get("aliases", [])),
                    note.content.strip()[:320],
                    note.metadata.get("deleted") is True,
                )

        candidates = source_notes()
    else:
        candidates = (
            (row.path, row.id, row.type, row.name, row.aliases, row.content_excerpt, row.deleted)
            for row in verified.rows
        )
    for path, note_id, note_type, primary_name, aliases, excerpt, deleted in candidates:
        if note_type not in canonical_types:
            continue
        if deleted and not include_deleted:
            continue
        primary_key = _normalize_reference(primary_name)
        alias_by_key: dict[str, str] = {}
        for alias in aliases:
            alias_by_key.setdefault(_normalize_reference(alias), alias)
        for index, (normalized_query, requested_type) in enumerate(parsed):
            if requested_type is not None and note_type != requested_type:
                continue
            matched = None
            if primary_key == normalized_query:
                matched = MatchKind.PRIMARY_NAME, primary_name
            elif normalized_query in alias_by_key:
                matched = MatchKind.ALIAS, alias_by_key[normalized_query]
            if matched is None:
                continue
            kind, value = matched
            results[index].append(
                ExactEntityCandidate(
                    path=path,
                    id=note_id,
                    type=note_type,
                    primary_name=primary_name,
                    match_kind=kind,
                    matched_value=value,
                    content_excerpt=excerpt,
                )
            )
    return tuple(
        tuple(
            sorted(
                candidates,
                key=lambda candidate: (
                    0 if candidate.match_kind is MatchKind.PRIMARY_NAME else 1,
                    candidate.primary_name.casefold(),
                    candidate.path,
                    candidate.id,
                ),
            )
        )
        for candidates in results
    )


def resolve_exact_entities_batch(
    repository: VaultRepository,
    schema: dict[str, Any],
    queries: tuple[tuple[str, str | None], ...],
) -> tuple[ExactEntityResolution, ...]:
    """Return ordinary Core exact-resolution outcomes in one read-only batch."""
    candidates_by_query = find_exact_entity_candidates_batch(repository, schema, queries)
    return tuple(
        ExactEntityResolution(
            ExactResolutionOutcome.NO_EXACT_MATCH
            if not candidates
            else ExactResolutionOutcome.EXACT_MATCH
            if len(candidates) == 1
            else ExactResolutionOutcome.AMBIGUOUS_EXACT_MATCH,
            query.strip(),
            note_type,
            candidates,
        )
        for (query, note_type), candidates in zip(queries, candidates_by_query, strict=True)
    )


def resolve_exact_entity(
    repository: VaultRepository,
    schema: dict[str, Any],
    query: str,
    *,
    type: str | None = None,
) -> ExactEntityResolution:
    """Resolve an already-extracted entity reference using exact identity evidence.

    Args:
        repository: Raw filesystem boundary for the Markdown vault.
        schema: Parsed canonical schema used by deterministic candidate discovery.
        query: Entity name extracted by a higher-level caller, not a full user request.
        type: Optional canonical type constraint used to avoid cross-type collisions.

    Returns:
        ``EXACT_MATCH`` for one exact candidate, ``NO_EXACT_MATCH`` for none, or
        ``AMBIGUOUS_EXACT_MATCH`` for several. All exact candidates remain available as evidence.
        ``NO_EXACT_MATCH`` does not establish that the entity is absent from Odyssey.

    Raises:
        ValueError: If the query, type, or schema is invalid.
        ExactEntityLookupError: If an existing note cannot safely participate in lookup.
        VaultRepository exceptions: If listing or raw note access fails.
    """
    normalized_query = query.strip() if isinstance(query, str) else query
    candidates = find_exact_entity_candidates(repository, schema, query, type=type)
    if not candidates:
        outcome = ExactResolutionOutcome.NO_EXACT_MATCH
    elif len(candidates) == 1:
        outcome = ExactResolutionOutcome.EXACT_MATCH
    else:
        outcome = ExactResolutionOutcome.AMBIGUOUS_EXACT_MATCH
    return ExactEntityResolution(
        outcome=outcome,
        query=normalized_query,
        type=type,
        candidates=candidates,
    )


def find_deleted_exact_entity_candidates(
    repository: VaultRepository, schema: dict[str, Any], query: str, *, type: str | None = None
) -> tuple[ExactEntityCandidate, ...]:
    """Find only deleted notes with exact canonical-name or alias evidence.

    This narrow safety lookup shares ordinary exact normalization but never consults embeddings or
    a contextual provider.
    """
    candidates = find_exact_entity_candidates(
        repository, schema, query, type=type, include_deleted=True
    )
    deleted: list[ExactEntityCandidate] = []
    for candidate in candidates:
        note = parse_note(repository.read_text(candidate.path))
        validate_note(note, schema)
        if note.metadata.get("deleted") is True:
            deleted.append(candidate)
    return tuple(deleted)
