"""Core-only lexical dependency projection; no semantic or write authority.

Only already-grounded Router roles and explicitly proposed backwards
inheritance are traced. Pronouns, 'same hour', and missing noun ellipsis
remain unresolved until the relevant Core/Temporal capability verifies them.
"""

from __future__ import annotations

from dataclasses import dataclass

from .candidate_context import CoreCandidateContext, CoreSourceSpan


class CandidateDependencyError(ValueError):
    """A Router dependency cannot be proved from the original source."""


@dataclass(frozen=True, slots=True)
class CoreDependencyRole:
    """Carry original source wording and the actual unit where it appeared."""

    role: str
    span: CoreSourceSpan
    source_candidate_id: str
    inherited: bool


@dataclass(frozen=True, slots=True)
class CoreDependencyUnit:
    """Show original explicit and inherited roles without resolving references."""

    candidate_id: str
    roles: tuple[CoreDependencyRole, ...]

    def for_role(self, role: str) -> tuple[CoreDependencyRole, ...]:
        """Return only traced source spans with a requested role."""
        return tuple(entry for entry in self.roles if entry.role == role)

    @property
    def unresolved_references(self) -> tuple[CoreSourceSpan, ...]:
        """Keep all proposed anaphoric source roles unresolved by default."""
        return tuple(item.span for item in self.for_role("reference"))


def trace_core_candidate_dependencies(
    source: str, context: CoreCandidateContext
) -> tuple[CoreDependencyUnit, ...]:
    """Project source role origin for each candidate without inventing content.

    Args:
        source: The full immutable original user message.
        context: Independently source-validated Router candidate hints.

    Returns:
        One source-role trace per candidate, retaining origin IDs and
        literal original source spans. Same-role explicit evidence overrides
        inherited hints; multi-member roles remain separate.

    Raises:
        CandidateDependencyError: An inherited role lacks actual evidence
        in its declared predecessor chain. Nothing is persisted or planned.
    """
    context.validate(source)
    resolved: list[CoreDependencyUnit] = []
    for candidate in context.candidates:
        own = tuple(
            CoreDependencyRole(role.role, role.span, candidate.candidate_id, False)
            for role in candidate.roles
        )
        own_roles = {role.role for role in own}
        inherited: list[CoreDependencyRole] = []
        for edge in candidate.inherits:
            if edge.role in own_roles:
                continue
            parent = resolved[edge.from_unit - 1]
            origins = parent.for_role(edge.role)
            if not origins:
                raise CandidateDependencyError(
                    "Inherited source role has no evidence in its predecessor chain"
                )
            inherited.extend(
                CoreDependencyRole(item.role, item.span, item.source_candidate_id, True)
                for item in origins
            )
        # A role may be inherited via multiple distinct paths. Retain exactly
        # one original span+role+source origin without claiming new ownership.
        seen = {
            (item.role, item.span.start, item.span.end, item.source_candidate_id) for item in own
        }
        result = list(own)
        for item in inherited:
            key = (item.role, item.span.start, item.span.end, item.source_candidate_id)
            if key not in seen:
                seen.add(key)
                result.append(item)
        resolved.append(CoreDependencyUnit(candidate.candidate_id, tuple(result)))
    return tuple(resolved)
