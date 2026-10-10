"""Read-only Core-owned handoff: one independently scoped planning task per fact.

Opt-in, not yet wired into runtime or provider. Original source spans, inherited
date evidence and omitted pending units remain available to Core's full-source
coverage and durable-pending guards. Router never grants write permission.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .candidate_context import CoreCandidateContext, CoreSourceSpan

_FORBIDDEN_ROLES = frozenset({"condition", "polarity", "replacement", "modality"})
# This narrow pilot deliberately rejects plausible cross-clause revisions.
_CROSS_CLAUSE_TERMS = (
    "en realidad",
    "rectifico",
    "corrijo",
    "corrección",
    "perdón",
    "me equivoqué",
    "olvida",
    "quise decir",
    "pero ",
    "aunque ",
    "salvo ",
    "excepto ",
    "sino ",
    "no fue",
    "no era",
)


class CandidateScopeSafetyError(ValueError):
    """Source does not prove independent safely scoped planning."""


@dataclass(frozen=True)
class CoreScopedPlanningUnit:
    """Single-unit task and exact original evidence for a future Core call."""

    candidate_id: str
    source_digest: str
    original_clause: str
    clause_start: int
    clause_end: int
    anchors: tuple[CoreSourceSpan, ...]
    date_evidence: tuple[CoreSourceSpan, ...]
    subject_predicate_evidence: CoreSourceSpan
    roles: tuple[tuple[str, CoreSourceSpan], ...]
    sibling_candidate_ids: tuple[str, ...]
    inherited_from: tuple[str, ...]

    def source_for_planner(self) -> str:
        """Return shared literal context only (not a complete isolated task)."""
        return self.original_clause

    def task_payload(self) -> dict:
        """One selected unit with Core-owned grammatical/date evidence.

        A future planner adapter must send this *whole* envelope, not just
        the shared clause. Every plan still needs full-source provenance,
        identity checks and candidate coverage before any canonical write.
        """
        return {
            "selected_candidate_id": self.candidate_id,
            "original_safe_clause": self.original_clause,
            "original_source_sha256": self.source_digest,
            "source_subject_predicate": self.subject_predicate_evidence.text,
            "original_date_text": [span.text for span in self.date_evidence],
            "selected_source_roles": [
                {"role": role, "text": span.text} for role, span in self.roles
            ],
            "shared_clause_other_candidates_not_targets": list(self.sibling_candidate_ids),
            "inherited_source_from": list(self.inherited_from),
            "write_authorized": False,
        }


@dataclass(frozen=True)
class CoreScopedPlanningPreview:
    """Non-authoritative preview for safe scopes and unresolved original work."""

    full_source_digest: str
    units: tuple[CoreScopedPlanningUnit, ...]
    pending_candidate_ids: tuple[str, ...]

    @property
    def can_auto_execute(self) -> bool:
        return False


def preview_independent_candidate_scopes(
    source: str,
    context: CoreCandidateContext,
) -> CoreScopedPlanningPreview:
    """Accept only a bounded two-clause safe/pending source shape.

    This is not a general sentence segmenter; any unsupported grammatical
    shape or cross-clause correction MUST fail closed, not omit a fact.
    The future source is not sent to the planner but is still in the original
    context for full-coverage, pending persistence and follow-up.
    """
    context.validate(source)
    if len(source) > 400 or source.count(". ") != 1:
        raise CandidateScopeSafetyError("Cannot prove a two-clause scope boundary")
    if any(x in source.casefold() for x in _CROSS_CLAUSE_TERMS):
        raise CandidateScopeSafetyError("Potential cross-clause correction or dependency")
    first, future_clause = source.split(". ", 1)
    boundary = len(first) + 1
    if not first or not future_clause or any(mark in first for mark in ";!?\n\r"):
        raise CandidateScopeSafetyError("Unsupported source clause structure")
    # One terminal period is ordinary punctuation, not a third clause.
    if any(mark in future_clause.rstrip(".") for mark in ".;!?\n\r"):
        raise CandidateScopeSafetyError("Unsafe additional source clause")
    safe = [c for c in context.candidates if c.state == "candidate"]
    pending = [c for c in context.candidates if c.state == "ambiguous_identity"]
    if not safe or len(pending) != 1 or safe != list(context.candidates[:-1]):
        raise CandidateScopeSafetyError("Exactly one final ambiguous unit required")
    if any(c.kind != "occurrence" for c in context.candidates):
        raise CandidateScopeSafetyError("This pilot only supports independent occurrences")
    if any(role.role in _FORBIDDEN_ROLES for c in context.candidates for role in c.roles):
        raise CandidateScopeSafetyError("Source needs condition/correction owner")
    future = pending[0]
    if not (
        any(role.role == "reference" for role in future.roles)
        and any(role.role == "date" for role in future.roles)
        and all(a.start > boundary for a in future.anchors)
        and all(role.span.start > boundary for role in future.roles)
        and not future.inherits
    ):
        raise CandidateScopeSafetyError("Future identity/date pending scope is not independent")

    dig = sha256(source.encode("utf-8")).hexdigest()
    safe_ids = tuple(c.candidate_id for c in safe)
    result = []
    for index, candidate in enumerate(safe):
        if any(a.end > boundary for a in candidate.anchors) or any(
            role.span.end > boundary for role in candidate.roles
        ):
            raise CandidateScopeSafetyError("Past evidence overlaps unresolved clause")
        if not any(role.role == "participants" for role in candidate.roles):
            raise CandidateScopeSafetyError("Past contact participants not grounded")
        if candidate.inherits and any(
            inheritance.from_unit > index for inheritance in candidate.inherits
        ):
            raise CandidateScopeSafetyError("Inheritance crosses the current unit")
        if any(inheritance.from_unit > len(safe) for inheritance in candidate.inherits):
            raise CandidateScopeSafetyError("Cannot inherit from ambiguous future")
        dates = tuple(role.span for role in candidate.roles if role.role == "date")
        inherited_ids = tuple(
            dict.fromkeys(safe[e.from_unit - 1].candidate_id for e in candidate.inherits)
        )
        if not dates and candidate.inherits:
            # Inherit the shared date only when literal source evidence
            # independently proves "A y después con B" in one dated clause.
            parents = [safe[e.from_unit - 1] for e in candidate.inherits if e.role == "predicate"]
            current_people = [role.span for role in candidate.roles if role.role == "participants"]
            preceding_people = [
                role.span
                for parent in parents
                for role in parent.roles
                if role.role == "participants"
            ]
            if (
                len(parents) != 1
                or len(current_people) != 1
                or len(preceding_people) != 1
                or not any(
                    role.role == "order" and role.span.text == "después" for role in candidate.roles
                )
                or source[preceding_people[0].end : current_people[0].start] != " y después con "
            ):
                raise CandidateScopeSafetyError("Date inheritance needs exact sequential evidence")
            dates = tuple(
                role.span for parent in parents for role in parent.roles if role.role == "date"
            )
        if len(dates) != 1 or dates[0].start != 0:
            raise CandidateScopeSafetyError("One original shared past date required")
        if dates[0].text.casefold() != "ayer":
            raise CandidateScopeSafetyError("Pilot has only verified explicit yesterday")
        if index > 0 and not any(role.role == "order" for role in candidate.roles):
            raise CandidateScopeSafetyError("Separate contact order is not source-grounded")
        predicate_sources = [role.span for role in candidate.roles if role.role == "predicate"]
        if not predicate_sources and candidate.inherits:
            predicate_sources = [
                role.span
                for edge in candidate.inherits
                if edge.role == "predicate"
                for role in safe[edge.from_unit - 1].roles
                if role.role == "predicate"
            ]
        first_person_predicates = [
            span for span in predicate_sources if "hablé" in span.text.casefold()
        ]
        if len(first_person_predicates) != 1:
            raise CandidateScopeSafetyError("Grammatical source subject is not proven")
        result.append(
            CoreScopedPlanningUnit(
                candidate.candidate_id,
                dig,
                source[:boundary],
                0,
                boundary,
                candidate.anchors,
                dates,
                first_person_predicates[0],
                tuple((role.role, role.span) for role in candidate.roles),
                tuple(other for other in safe_ids if other != candidate.candidate_id),
                inherited_ids,
            )
        )
    return CoreScopedPlanningPreview(dig, tuple(result), (future.candidate_id,))
