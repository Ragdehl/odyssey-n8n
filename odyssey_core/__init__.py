"""Odyssey's Python application and domain core."""

from .identity import (
    EntityCandidate,
    EntityResolution,
    EntitySearchError,
    MatchKind,
    ResolutionOutcome,
    find_entity_candidates,
    resolve_entity,
)

__all__ = [
    "EntityCandidate",
    "EntityResolution",
    "EntitySearchError",
    "MatchKind",
    "ResolutionOutcome",
    "find_entity_candidates",
    "resolve_entity",
]
