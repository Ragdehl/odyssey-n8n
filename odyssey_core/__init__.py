"""Odyssey's Python application and domain core."""

from .identity import (
    EntityResolution,
    EntitySearchError,
    MatchKind,
    ResolutionOutcome,
    SearchCandidate,
    resolve_entity,
    search,
)

__all__ = [
    "EntityResolution",
    "EntitySearchError",
    "MatchKind",
    "ResolutionOutcome",
    "SearchCandidate",
    "resolve_entity",
    "search",
]
