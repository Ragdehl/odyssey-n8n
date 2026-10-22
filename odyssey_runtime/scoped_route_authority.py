"""One route-local source and caller-integrity check for Core and registered apps.

This is a narrow runtime boundary around already-validated Router groups,
not a source of identity, Temporal resolution, semantic meaning or permission
to mutate. Different apps retain their own E2 handoff/lifecycle policies.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_runtime.source_scope_compiler import ScopedCandidateRoute


@dataclass(frozen=True, slots=True)
class ScopedRouteAuthority:
    """Bind all routed calls to one original source and authenticated snapshot."""

    original_source: str
    scopes: Mapping[str, tuple[int, ScopedCandidateRoute]]
    actor: AuthenticatedActorContext | None
    conversation: tuple[Mapping[str, str], ...]

    def verify(
        self,
        *,
        source: str,
        locator: str,
        capability: str,
        actor: AuthenticatedActorContext | None,
        conversation: Sequence[Mapping[str, str]],
    ) -> tuple[int, ScopedCandidateRoute]:
        """Check caller correlation before a planner, app or repository is used.

        The original group compiler is the source of these scopes. Its Router
        hints are never upgraded to canonical identity or write authority.
        """
        if (
            not isinstance(locator, str)
            or locator not in self.scopes
            or actor != self.actor
            or not isinstance(conversation, (tuple, list))
            or tuple(conversation) != self.conversation
        ):
            raise ValueError("Routed source, actor or conversation snapshot changed")
        ordinal, scoped = self.scopes[locator]
        if (
            scoped.route.capability_id != capability
            or scoped.route.source_text != source
            or scoped.context.source != source
            or not 0 <= scoped.original_start < scoped.original_end <= len(self.original_source)
            or self.original_source[scoped.original_start : scoped.original_end] != source
        ):
            raise ValueError("Routed scope does not match validated original source")
        return ordinal, scoped


_TEMPORAL_PROVENANCE_ROLES = frozenset({"date", "date_scope", "time", "time_approx"})


def missing_inherited_temporal_spans(context, inherited) -> frozenset[tuple[int, int]]:
    """Return source offsets not proved by a previous exact Temporal handoff.

    This checks only E2 transport coverage, not app-specific authorization.
    Core, Tasks and Events each decide whether or how to consume the proof.
    """
    required = {
        (role.original_start, role.original_end)
        for role in context.source_provenance
        if role.role in _TEMPORAL_PROVENANCE_ROLES
    }
    proven = {(proof.original_start, proof.original_end) for proof in inherited}
    return frozenset(required - proven)
