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


@dataclass(frozen=True, slots=True)
class CoreDependencyPlanningTask:
    """One selected *literal* source fragment with earlier contextual evidence.

    Core, not Router, may interpret omitted nouns and pronoun antecedents.
    This carrier never supplies a fabricated expansion or canonical target.
    """

    source_digest: str
    candidate_id: str
    selected_quote: str
    prior_context_quote: str | None
    effective_roles: tuple[CoreDependencyRole, ...]
    unresolved_reference_quotes: tuple[str, ...]
    may_authorize_writes: bool = False

    def scoped_request(self) -> str:
        """Ask the existing Core planner about only this selected assertion.

        This is Core-constructed planning text, NOT a purported exact user
        quote. Previously expressed facts are read-only interpretive context.
        """
        if self.prior_context_quote is None:
            return self.selected_quote + "."
        return (
            "Contexto anterior del mismo mensaje (solo para entender referencias, "
            "no registrar de nuevo): «" + self.prior_context_quote + "». "
            "Registra exclusivamente el siguiente hecho del mensaje original, "
            "si puede interpretarse sin inventar información: «" + self.selected_quote + "»."
        )


def preview_contextual_dependency_tasks(
    source: str, context: CoreCandidateContext
) -> tuple[CoreDependencyPlanningTask, ...]:
    """Preview separately selected fact work using exact original source spans.

    The source may contain one explicitly selected unit and its preceding
    dependent unit. Each target clause retains only its own explicit
    anchors/roles; earlier wording is context, never an instruction to write.
    This conservative first slice accepts only two material clauses linked by
    a coordinating conjunction. Unsupported structures, conditions,
    corrections, polarity and ambiguous identity fail closed.

    The result is a provider-only experiment. Full original candidate
    coverage, canonical identity and actual Markdown writes remain prohibited
    by this boundary even if the planner produces PLAN.
    """
    from hashlib import sha256

    context.validate(source)
    if len(source) > 360 or len(context.candidates) != 2:
        raise CandidateDependencyError("Unsupported number of source clauses")
    if any(
        c.state != "candidate"
        or c.kind in {"conditional", "negative"}
        or any(r.role in {"condition", "polarity", "replacement", "modality"} for r in c.roles)
        for c in context.candidates
    ):
        raise CandidateDependencyError("Conditional, correction or ambiguous scope")
    traced = trace_core_candidate_dependencies(source, context)
    selected_ranges = []
    for candidate in context.candidates:
        spans = (*candidate.anchors, *(r.span for r in candidate.roles))
        if not spans:
            raise CandidateDependencyError("No actual selected source spans")
        start, end = min(s.start for s in spans), max(s.end for s in spans)
        if not source[start:end].strip():
            raise CandidateDependencyError("Empty selected source clause")
        selected_ranges.append((start, end))
    (first_start, first_end), (second_start, second_end) = selected_ranges
    if first_start != 0 or second_start <= first_end:
        raise CandidateDependencyError("Overlapping, reversed or ungrounded clauses")
    if source[first_end:second_start] not in {" y ", ". ", "; "}:
        raise CandidateDependencyError("Unreviewed cross-clause dependency")
    if source[second_end:].strip() not in {"", "."}:
        raise CandidateDependencyError("Unassigned source after second candidate")
    if any(
        x in source.casefold()
        for x in (
            "en realidad",
            "mejor ",
            "rectifico",
            "corrijo",
            "pero ",
            "aunque ",
            "sino ",
            "excepto ",
            "salvo ",
        )
    ):
        raise CandidateDependencyError("Potential cross-clause override")
    digest = sha256(source.encode("utf-8")).hexdigest()
    quotes = tuple(source[start:end] for start, end in selected_ranges)
    return tuple(
        CoreDependencyPlanningTask(
            source_digest=digest,
            candidate_id=candidate.candidate_id,
            selected_quote=quotes[index],
            prior_context_quote=quotes[0] if index else None,
            effective_roles=traced[index].roles,
            unresolved_reference_quotes=tuple(
                span.text for span in traced[index].unresolved_references
            ),
        )
        for index, candidate in enumerate(context.candidates)
    )
