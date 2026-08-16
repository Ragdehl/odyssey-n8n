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
from .semantic import (
    DEFAULT_EMBEDDING_MODEL,
    FastEmbedTextEmbedder,
    SemanticEntityCandidate,
    SemanticEntityIndex,
    SemanticIndexError,
    TextEmbedder,
    build_semantic_retrieval_text,
    find_semantic_entity_candidates,
)

__all__ = [
    "ExactEntityCandidate",
    "ExactEntityLookupError",
    "ExactEntityResolution",
    "ExactResolutionOutcome",
    "MatchKind",
    "find_exact_entity_candidates",
    "resolve_exact_entity",
    "DEFAULT_EMBEDDING_MODEL",
    "FastEmbedTextEmbedder",
    "SemanticEntityCandidate",
    "SemanticEntityIndex",
    "SemanticIndexError",
    "TextEmbedder",
    "build_semantic_retrieval_text",
    "find_semantic_entity_candidates",
]
