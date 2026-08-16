"""Deterministic entity lookup over validated Odyssey notes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, cast

from odyssey_core.notes import NoteFormatError, NoteValidationError, parse_note, validate_note
from odyssey_core.storage import VaultRepository


class EntitySearchError(RuntimeError):
    """Indicate that a vault note could not safely participate in entity lookup."""


class MatchKind(Enum):
    """Describe the deterministic identity signal that matched a candidate."""

    PRIMARY_NAME = "primary_name"
    ALIAS = "alias"


class ResolutionOutcome(Enum):
    """Describe the normal domain outcome of resolving one entity reference."""

    RESOLVED = "resolved"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class EntityCandidate:
    """Expose the useful identity evidence for one matching validated note.

    Attributes:
        path: Vault-relative POSIX path of the note.
        id: Stable logical note identifier from canonical metadata.
        type: Canonical note type from validated metadata.
        primary_name: Human-readable lookup name derived from the filename stem.
        match_kind: Whether the query matched the primary name or an alias.
        matched_value: Exact stored primary name or alias that matched after normalization.
    """

    path: str
    id: str
    type: str
    primary_name: str
    match_kind: MatchKind
    matched_value: str


@dataclass(frozen=True, slots=True)
class EntityResolution:
    """Represent a conservative entity-resolution outcome and its evidence.

    Attributes:
        outcome: Resolved, not-found, or ambiguous domain outcome.
        query: Trimmed entity reference evaluated by the resolver.
        type: Optional canonical type constraint applied to the lookup.
        candidates: Deterministically ordered exact identity candidates.
    """

    outcome: ResolutionOutcome
    query: str
    type: str | None
    candidates: tuple[EntityCandidate, ...]

    @property
    def candidate(self) -> EntityCandidate | None:
        """Return the uniquely resolved candidate, or ``None`` for other outcomes."""
        if self.outcome is ResolutionOutcome.RESOLVED:
            return self.candidates[0]
        return None


def _normalize_reference(value: str) -> str:
    """Normalize one identity value for exact Unicode-aware comparison.

    Args:
        value: Query, filename stem, or alias to normalize.

    Returns:
        Surrounding-whitespace-trimmed and case-folded text.

    Raises:
        ValueError: If the value is not text.
    """
    if not isinstance(value, str):
        raise ValueError("Entity reference must be text")
    return value.strip().casefold()


def _canonical_types(schema: dict[str, Any]) -> set[str]:
    """Return the canonical type IDs available to the identity layer.

    Args:
        schema: Parsed canonical Odyssey note schema.

    Returns:
        Set of canonical note type identifiers.

    Raises:
        ValueError: If the supplied schema does not expose usable type definitions.
    """
    try:
        type_ids = {definition["id"] for definition in schema["types"]}
    except (KeyError, TypeError):
        raise ValueError("Supplied schema is not a usable canonical schema") from None
    if not type_ids or not all(isinstance(type_id, str) for type_id in type_ids):
        raise ValueError("Supplied schema is not a usable canonical schema")
    return type_ids


def find_entity_candidates(
    repository: VaultRepository,
    schema: dict[str, Any],
    query: str,
    *,
    type: str | None = None,
) -> tuple[EntityCandidate, ...]:
    """Find deterministic exact-name and exact-alias candidates in a Markdown vault.

    Every listed note is read, parsed, and validated before a result is returned. This
    fail-closed policy prevents a malformed existing note from being silently ignored and
    producing an unsafe ``NOT_FOUND`` decision in duplicate-prevention workflows.

    Args:
        repository: Raw filesystem boundary used to list and read Markdown text.
        schema: Parsed canonical schema used to validate every parsed note.
        query: Already-extracted entity name, such as ``"Carrefour"``.
        type: Optional canonical note type, such as ``"store"``.

    Returns:
        Deterministically ordered exact identity candidates. The tuple is empty when no
        primary name or alias matches. Partial and semantic matches are deliberately absent.

    Raises:
        ValueError: If the query is empty or the type/schema is not canonical.
        EntitySearchError: If a Markdown note cannot be parsed or validated safely.
        VaultRepository exceptions: If listing or raw note access fails.

    Example:
        ``find_entity_candidates(repository, schema, " carrefour ", type="store")`` can return a
        filename match for ``stores/Carrefour.md`` or an alias match on another store.
    """
    normalized_query = _normalize_reference(query)
    if not normalized_query:
        raise ValueError("Entity reference must not be empty")
    canonical_types = _canonical_types(schema)
    if type is not None and (not isinstance(type, str) or type not in canonical_types):
        raise ValueError(f"Unknown canonical note type: {type!r}")

    candidates: list[EntityCandidate] = []
    for path in repository.list_markdown_paths():
        try:
            note = parse_note(repository.read_text(path))
            validate_note(note, schema)
        except (NoteFormatError, NoteValidationError) as error:
            raise EntitySearchError(f"Cannot safely inspect invalid note: {path}") from error

        note_type = cast(str, note.metadata["type"])
        if type is not None and note_type != type:
            continue

        primary_name = PurePosixPath(path).stem
        match_kind: MatchKind | None = None
        matched_value = primary_name
        if _normalize_reference(primary_name) == normalized_query:
            match_kind = MatchKind.PRIMARY_NAME
        else:
            aliases = cast(list[str], note.metadata.get("aliases", []))
            for alias in aliases:
                # Canonical validation guarantees that aliases are strings.
                if _normalize_reference(alias) == normalized_query:
                    match_kind = MatchKind.ALIAS
                    matched_value = alias
                    break

        if match_kind is not None:
            candidates.append(
                EntityCandidate(
                    path=path,
                    id=cast(str, note.metadata["id"]),
                    type=note_type,
                    primary_name=primary_name,
                    match_kind=match_kind,
                    matched_value=matched_value,
                )
            )

    candidates.sort(
        key=lambda candidate: (
            0 if candidate.match_kind is MatchKind.PRIMARY_NAME else 1,
            candidate.primary_name.casefold(),
            candidate.path,
            candidate.id,
        )
    )
    return tuple(candidates)


def resolve_entity(
    repository: VaultRepository,
    schema: dict[str, Any],
    query: str,
    *,
    type: str | None = None,
) -> EntityResolution:
    """Resolve an already-extracted entity reference using exact identity evidence.

    Args:
        repository: Raw filesystem boundary for the Markdown vault.
        schema: Parsed canonical schema used by deterministic candidate discovery.
        query: Entity name extracted by a higher-level caller, not a full user request.
        type: Optional canonical type constraint used to avoid cross-type collisions.

    Returns:
        ``RESOLVED`` for one exact candidate, ``NOT_FOUND`` for none, or ``AMBIGUOUS``
        for several. All matching candidates remain available as evidence.

    Raises:
        ValueError: If the query, type, or schema is invalid.
        EntitySearchError: If an existing note cannot safely participate in lookup.
        VaultRepository exceptions: If listing or raw note access fails.
    """
    normalized_query = query.strip() if isinstance(query, str) else query
    candidates = find_entity_candidates(repository, schema, query, type=type)
    if not candidates:
        outcome = ResolutionOutcome.NOT_FOUND
    elif len(candidates) == 1:
        outcome = ResolutionOutcome.RESOLVED
    else:
        outcome = ResolutionOutcome.AMBIGUOUS
    return EntityResolution(
        outcome=outcome,
        query=normalized_query,
        type=type,
        candidates=candidates,
    )
