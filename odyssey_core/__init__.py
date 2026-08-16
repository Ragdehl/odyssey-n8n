"""Odyssey's Python application and domain core."""

from .identity import (
    EntityCandidate,
    EntityLookupError,
    EntityResolution,
    MatchKind,
    ResolutionOutcome,
    find_entity_candidates,
    resolve_entity,
)

__all__ = [
    "EntityCandidate",
    "EntityLookupError",
    "EntityResolution",
    "MatchKind",
    "ResolutionOutcome",
    "find_entity_candidates",
    "resolve_entity",
]
