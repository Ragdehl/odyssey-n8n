"""Core-only plan-bound correspondence between source time roles and fact ordinals.

The binding is *not* itself a new model authority: it can be derived only from
an already validated Core coverage manifest, source roles, and unchanged plan.
A Core review must still establish semantics; this typed projection will never
infer a fact owner from its list position or date alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256

from .candidate_context import CoreCandidateContext, CoreSourceSpan
from .candidate_coverage import CoreCandidateCoverageManifest, validate_candidate_coverage_manifest
from .execution_context import ContextContractError, ExecutionContext
from .request_planning import RequestPlan, WriteAction, plan_fact_ordinals
from .temporal_qualifier_handoff import qualitative_source_time_role


@dataclass(frozen=True, slots=True)
class CoreFactTemporalOwnership:
    """One source-qualified fact edge reviewed against one immutable Core plan."""

    qualifier_index: int
    fact_ordinal: int
    source_digest: str
    plan_digest: str


def _qualifier_in_unique_original_temporal_span(
    context: ExecutionContext, qualifier_index: int, span: CoreSourceSpan
) -> bool:
    """Require one physical occurrence of the date quote enclosing this role.

    Identical dayparts in different clauses cannot be disambiguated by substring
    equality or candidate list order; the current QualitativeTime carrier has
    no independently certified source offsets for such repetitions.
    """
    qualifier = context.qualitative_times[qualifier_index]
    start = context.source.find(qualifier.source_text)
    return bool(
        start >= 0
        and context.source.find(qualifier.source_text, start + 1) < 0
        and start <= span.start < span.end <= start + len(qualifier.source_text)
        and span.text == qualifier.qualifier
        and context.source[span.start : span.end] == qualifier.qualifier
    )


def reviewed_fact_temporal_ownership(
    context: ExecutionContext,
    source_context: CoreCandidateContext,
    plan: RequestPlan,
    manifest: CoreCandidateCoverageManifest,
) -> tuple[CoreFactTemporalOwnership, ...]:
    """Project existing Core-reviewed candidate→fact edges, never Router guesses.

    Requires every qualifier to be scoped to exactly ONE candidate that owns a
    single fact under the *unchanged* and fully validated coverage manifest.
    A graph claim involving multiple facts does not establish fact ownership.
    """
    if context.source != source_context.source or context.candidates != source_context:
        raise ContextContractError("Temporal owner source/context is mismatched")
    validate_candidate_coverage_manifest(context.source, source_context, plan, manifest)
    ordinals = [ordinal for row in plan_fact_ordinals(plan) for ordinal in row]
    if len(ordinals) > 128:
        raise ContextContractError("Temporal owner exceeds bounded fact coverage")
    result = []
    for index, _qualifier in enumerate(context.qualitative_times):
        matches = []
        for candidate, claim in zip(source_context.candidates, manifest.claims, strict=True):
            if claim.disposition != "planned_fact":
                continue
            spans = [
                r.span for r in candidate.roles if qualitative_source_time_role(r.role, r.span.text)
            ]
            if not any(
                _qualifier_in_unique_original_temporal_span(context, index, span) for span in spans
            ):
                continue
            claimed = (
                claim.fact_ordinals if claim.fact_ordinals is not None else (claim.fact_ordinal,)
            )
            if len(claimed) != 1 or claimed[0] not in ordinals:
                raise ContextContractError("One source qualifier owns several facts")
            matches.append(claimed[0])
        if len(matches) != 1:
            raise ContextContractError("Qualitative qualifier lacks a single Core-reviewed fact")
        result.append(
            CoreFactTemporalOwnership(
                qualifier_index=index,
                fact_ordinal=matches[0],
                source_digest=sha256(context.source.encode()).hexdigest(),
                plan_digest=sha256(repr(plan).encode()).hexdigest(),
            )
        )
    if len({edge.fact_ordinal for edge in result}) != len(result):
        raise ContextContractError("Two source qualifiers claim the same fact")
    return tuple(result)


_DISTINCTIVE_SOURCE_ROLES = frozenset(
    {"predicate", "participants", "object", "location", "transaction"}
)


def _source_role_fits_original_fact(
    plan: RequestPlan,
    source_context: CoreCandidateContext,
    candidate_index: int,
    fact_ordinal: int,
) -> bool:
    """Reject a swapped graph BEFORE appending daypart evidence to its fact.

    Candidate graph semantic claims aren't proof: require an independently
    quoted, discriminating lexical predicate/participant/object/location role
    in the ORIGINAL fact, before the qualifier could conceal an error. The
    candidate-role text must not fit any sibling fact either. This is a safe
    lower bound, not a multilingual semantic equivalence algorithm.
    """
    rendered: dict[int, str] = {}
    index = 0
    for action in plan.actions:
        if not isinstance(action, WriteAction):
            continue
        for unit in action.units:
            for fact in unit.facts:
                value = fact
                for ref_index, ref in enumerate(unit.references):
                    value = value.replace(f"{{{{ref:{ref_index}}}}}", ref.mention)
                rendered[index] = value.casefold()
                index += 1
    if fact_ordinal not in rendered:
        return False
    candidates = source_context.candidates
    own = candidates[candidate_index]
    siblings = {
        role.span.text.casefold()
        for other_index, other in enumerate(candidates)
        if other_index != candidate_index
        for role in other.roles
        if role.role in _DISTINCTIVE_SOURCE_ROLES
    }
    evidence = [
        role.span.text.casefold()
        for role in own.roles
        if role.role in _DISTINCTIVE_SOURCE_ROLES and role.span.text.casefold() not in siblings
    ]
    if not evidence:
        return False

    def exact_piece(piece: str, text: str) -> bool:
        return re.search(r"(?<!\w)" + re.escape(piece) + r"(?!\w)", text) is not None

    # Require at least one original distinctive semantic role in exactly ONE
    # of the facts. Any repeated signal or missing signal leaves ownership
    # ambiguous. This intentionally refuses paraphrases rather than guessing.
    return any(
        exact_piece(piece, rendered[fact_ordinal])
        and all(not exact_piece(piece, other) for i, other in rendered.items() if i != fact_ordinal)
        for piece in evidence
    )


def proposed_fact_temporal_ownership(
    context: ExecutionContext,
    source_context: CoreCandidateContext,
    plan: RequestPlan,
    graph: object,
) -> tuple[CoreFactTemporalOwnership, ...]:
    """Bind untrusted but schema-checked candidate graph edges for prewrite review.

    This is specifically a *proposal*, not semantic certification. It can only
    be used as INPUT to immutable text enrichment; Core must then validate the
    FINAL plan through full coverage and normal preflight before any write.
    """
    from .candidate_attribution import CandidateFactGraph

    if (
        not isinstance(graph, CandidateFactGraph)
        or not graph.matches_original_plan(context.source, plan)
        or graph.may_authorize_writes
        or context.candidates != source_context
        or context.source != source_context.source
    ):
        raise ContextContractError("Unverified candidate graph cannot bind a temporal owner")
    source_context.validate(context.source)
    pairs: list[CoreFactTemporalOwnership] = []
    for i, _qualifier in enumerate(context.qualitative_times):
        found: list[int] = []
        for candidate_index, (candidate, link) in enumerate(
            zip(source_context.candidates, graph.links, strict=True)
        ):
            if not link.fact_ordinals:
                continue
            for role in candidate.roles:
                if role.role in {
                    "time",
                    "time_approx",
                } and _qualifier_in_unique_original_temporal_span(context, i, role.span):
                    # Both validated and proposed paths require the SAME
                    # unique literal temporal quote and exact physical role.
                    if len(link.fact_ordinals) != 1:
                        raise ContextContractError("Several facts claim one temporal qualifier")
                    if not _source_role_fits_original_fact(
                        plan, source_context, candidate_index, link.fact_ordinals[0]
                    ):
                        raise ContextContractError(
                            "Source fact has no independent discriminating role proof"
                        )
                    found.append(link.fact_ordinals[0])
        if len(found) != 1:
            raise ContextContractError("No unique reviewed temporal fact owner")
        pairs.append(
            CoreFactTemporalOwnership(
                i,
                found[0],
                sha256(context.source.encode()).hexdigest(),
                sha256(repr(plan).encode()).hexdigest(),
            )
        )
    if len({p.fact_ordinal for p in pairs}) != len(pairs):
        raise ContextContractError("Several temporal phrases claim one fact")
    return tuple(pairs)
