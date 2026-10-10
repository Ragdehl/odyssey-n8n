"""Generic, fail-closed lexical clause-scoping for dependent Core candidates.

Router only proposed source roles. Core selects original source substrings
as individual planner tasks; a sibling clause may be quoted as linguistic
context, but never given a second operation or mutation authority. This
preview handles a bounded unambiguous two-unit coordination shape, not
arbitrary text segmentation or coreference interpretation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256

from .candidate_context import CoreCandidateContext, CoreSourceSpan
from .candidate_dependencies import CoreDependencyRole, trace_core_candidate_dependencies

_SENSITIVE_ROLES = frozenset({"condition", "polarity", "replacement", "modality"})
_SENSITIVE_CONNECTORS = re.compile(
    r"\b(?:pero|sino|aunque|excepto|salvo|rectifico|corrijo|perdón|"
    r"no|nunca|si|cuando|mientras|antes|después)\b",
    re.IGNORECASE,
)
_COORDINATION = re.compile(r"\s+y\s+", re.IGNORECASE)


class CoreDependentScopeError(ValueError):
    """Source evidence cannot support isolated per-unit planning safely."""


@dataclass(frozen=True, slots=True)
class CoreDependentFactScope:
    """An original literal source clause and optional preceding context."""

    candidate_id: str
    full_source_digest: str
    selected_quote: str
    preceding_quote: str | None
    explicit_roles: tuple[CoreDependencyRole, ...]
    inherited_roles: tuple[CoreDependencyRole, ...]
    unresolved_references: tuple[CoreSourceSpan, ...]
    selected_source_start: int
    selected_source_end: int

    @property
    def is_semantically_authorized(self) -> bool:
        """Do not infer that source-role hints authorize identity or writes."""
        return False

    def planner_request(self) -> str:
        """Create ONE Core-owned work request with non-operative prior context.

        Direct-source first clauses are kept as originally written except for
        terminal punctuation. Dependent clauses carry only exact original
        quotes: semantic completion is left to the same existing Core LLM,
        not to a custom string-expansion or an application planner.
        """
        if self.preceding_quote is None:
            return self.selected_quote.rstrip(".") + "."
        prior = self.preceding_quote.rstrip(".")
        current = self.selected_quote.rstrip(".")
        return (
            "Registra únicamente la afirmación del SEGMENTO ACTUAL. "
            "El CONTEXTO ANTERIOR es información lingüística para entender "
            "referencias y elementos omitidos; NO debes registrarlo otra vez.\n"
            f"CONTEXTO ANTERIOR (cita literal): «{prior}».\n"
            f"SEGMENTO ACTUAL (cita literal): «{current}».\n"
            "Usa la interpretación semántica habitual de Core para entender "
            "el segmento actual; no inventes hechos, identidades ni fechas."
        )


@dataclass(frozen=True, slots=True)
class CoreDependentScopePreview:
    """Two original units prepared for optional Core planning, never writes."""

    full_source_digest: str
    units: tuple[CoreDependentFactScope, ...]
    executable: bool = False


def preview_dependent_clause_scopes(
    source: str, context: CoreCandidateContext
) -> CoreDependentScopePreview:
    """Identify bounded source-proven 'CLAUSE y CLAUSE' task boundaries.

    Args:
        source: Exact complete user input.
        context: Independent source-validated model suggestions.

    Returns:
        Source-backed unit quotes, their role origins, and unresolved
        reference spans. No rewritten factual information or Note targets.

    Raises:
        CoreDependentScopeError: Source/role evidence is overlapping, a
        correction/condition is present, or no safe unique split is proven.
    """
    context.validate(source)
    if len(context.candidates) != 2 or len(source) > 300:
        raise CoreDependentScopeError("Two source candidates required for this reviewed boundary")
    if any(candidate.state != "candidate" for candidate in context.candidates):
        raise CoreDependentScopeError("Unresolved candidate is not independently writable")
    if any(
        role.role in _SENSITIVE_ROLES
        for candidate in context.candidates
        for role in candidate.roles
    ):
        raise CoreDependentScopeError(
            "Conditional/correction/negative semantics need independent review"
        )
    if _SENSITIVE_CONNECTORS.search(source):
        raise CoreDependentScopeError("Source may contain a cross-clause modifier")
    separators = list(_COORDINATION.finditer(source))
    if len(separators) != 1 or source.count(".") > 1 or any(c in source for c in "!?;\n\r"):
        raise CoreDependentScopeError("Unproven independent coordination boundary")
    boundary = separators[0]
    left = source[: boundary.start()]
    right = source[boundary.end() :]
    if not left.strip() or not right.strip():
        raise CoreDependentScopeError("Empty source span")
    candidates = context.candidates
    if not all(
        span.end <= boundary.start()
        for span in (*candidates[0].anchors, *(r.span for r in candidates[0].roles))
    ) or not all(
        span.start >= boundary.end()
        for span in (*candidates[1].anchors, *(r.span for r in candidates[1].roles))
    ):
        raise CoreDependentScopeError("Candidate evidence crosses selected clause boundary")
    traced = trace_core_candidate_dependencies(source, context)
    if any(role.span.start < boundary.end() for role in traced[1].roles if not role.inherited):
        raise CoreDependentScopeError("Second source role not contained in its clause")
    digest = sha256(source.encode("utf-8")).hexdigest()
    result = []
    for i, candidate in enumerate(candidates):
        explicit = tuple(x for x in traced[i].roles if not x.inherited)
        inherited = tuple(x for x in traced[i].roles if x.inherited)
        if not explicit:
            raise CoreDependentScopeError("Candidate lacks independent source evidence")
        if i == 0 and inherited:
            raise CoreDependentScopeError("Initial clause has inherited roles")
        if i == 1 and any(edge.from_unit != 1 for edge in candidate.inherits):
            raise CoreDependentScopeError("Invalid backwards dependency")
        selected = left if i == 0 else right
        start = 0 if i == 0 else boundary.end()
        end = boundary.start() if i == 0 else len(source)
        result.append(
            CoreDependentFactScope(
                candidate.candidate_id,
                digest,
                selected.strip(),
                left.strip() if i == 1 else None,
                explicit,
                inherited,
                traced[i].unresolved_references,
                start,
                end,
            )
        )
    return CoreDependentScopePreview(digest, tuple(result))
