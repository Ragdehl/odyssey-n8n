"""Odyssey's Python application and domain core."""

from .identity import (
    ExactEntityCandidate,
    ExactEntityLookupError,
    ExactEntityResolution,
    ExactResolutionOutcome,
    MatchKind,
    find_exact_entity_candidates,
    resolve_exact_entity,
)

__all__ = [
    "ExactEntityCandidate",
    "ExactEntityLookupError",
    "ExactEntityResolution",
    "ExactResolutionOutcome",
    "MatchKind",
    "find_exact_entity_candidates",
    "resolve_exact_entity",
]
