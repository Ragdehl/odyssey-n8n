"""Narrow, content-free helpers for OpenAI explicit prompt-cache boundaries.

The helper owns only provider transport metadata.  Callers retain responsibility for
proving that their supplied prefix is stable for their own capability.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# This is deliberately a conservative byte proxy, not a token estimate.  It prevents a
# short instruction block from opting into explicit-only caching when no tokenizer is present.
CONSERVATIVE_EXPLICIT_PREFIX_BYTES = 8192
_EXPLICIT_CACHE_MODEL = re.compile(r"^gpt-(?:5\.(?:[6-9]|[1-9]\d+)|[6-9](?:[.-]|$))")


@dataclass(frozen=True, slots=True)
class CacheBoundaryDiagnostics:
    """Describe cache-boundary eligibility without retaining prompt or user content."""

    model: str
    outcome: str
    stable_prefix_bytes: int
    prefix_sha256: str | None
    evidence: str

    def as_safe_mapping(self) -> dict[str, str | int | None]:
        """Return bounded diagnostic fields suitable for transient request evidence."""
        return {
            "model": self.model,
            "outcome": self.outcome,
            "stable_prefix_bytes": self.stable_prefix_bytes,
            "prefix_sha256": self.prefix_sha256,
            "evidence": self.evidence,
        }


def explicit_cache_transport(
    *, model: str, capability: str, stable_prefix: str, proven_reusable: bool
) -> tuple[dict[str, Any] | None, CacheBoundaryDiagnostics]:
    """Build one explicit-cache transport fragment only for a proven stable prefix.

    Args:
        model: Exact provider model selected by the caller.
        capability: Constant capability/version identifier; it must contain no user content.
        stable_prefix: Exact original text before the caller's dynamic boundary.
        proven_reusable: Caller-owned evidence that the prefix has no request-specific content.

    Returns:
        ``(transport, diagnostics)``.  ``transport`` is ``None`` unless the prefix passes
        the conservative visible-length gate and the caller proved it reusable.

    Raises:
        ValueError: If the provider identifiers or stable prefix are malformed.
    """
    if not isinstance(model, str) or not model.strip():
        raise ValueError("OpenAI cache model must be non-empty")
    if not isinstance(capability, str) or not capability.strip():
        raise ValueError("OpenAI cache capability must be non-empty")
    if not isinstance(stable_prefix, str):
        raise ValueError("OpenAI cache stable prefix must be text")
    prefix_bytes = len(stable_prefix.encode("utf-8"))
    prefix_hash = hashlib.sha256(stable_prefix.encode("utf-8")).hexdigest()
    if not _EXPLICIT_CACHE_MODEL.match(model.strip()):
        return None, CacheBoundaryDiagnostics(
            model=model,
            outcome="implicit_model_unsupported",
            stable_prefix_bytes=prefix_bytes,
            prefix_sha256=prefix_hash,
            evidence="explicit breakpoints require GPT-5.6 or later",
        )
    if not proven_reusable:
        return None, CacheBoundaryDiagnostics(
            model=model,
            outcome="implicit_unproven_stability",
            stable_prefix_bytes=prefix_bytes,
            prefix_sha256=None,
            evidence="caller did not prove a reusable stable prefix",
        )
    if prefix_bytes < CONSERVATIVE_EXPLICIT_PREFIX_BYTES:
        return None, CacheBoundaryDiagnostics(
            model=model,
            outcome="implicit_prefix_too_short",
            stable_prefix_bytes=prefix_bytes,
            prefix_sha256=prefix_hash,
            evidence="conservative byte gate; not a token estimate",
        )
    cache_key = f"odyssey-{capability}-{prefix_hash[:32]}"
    return {
        "prompt_cache_key": cache_key,
        "prompt_cache_options": {"mode": "explicit", "ttl": "30m"},
    }, CacheBoundaryDiagnostics(
        model=model,
        outcome="explicit",
        stable_prefix_bytes=prefix_bytes,
        prefix_sha256=prefix_hash,
        evidence="caller-proven stable prefix passed conservative byte gate",
    )


def explicit_system_content(stable_prefix: str, dynamic_suffix: str) -> list[Mapping[str, Any]]:
    """Preserve exact flattened system text while marking only its stable leading block."""
    return [
        {
            "type": "input_text",
            "text": stable_prefix,
            "prompt_cache_breakpoint": {"mode": "explicit"},
        },
        {"type": "input_text", "text": dynamic_suffix},
    ]
