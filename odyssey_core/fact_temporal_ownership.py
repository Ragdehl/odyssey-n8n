"""Core-only plan-bound correspondence between source time roles and fact ordinals.

The binding is *not* itself a new model authority: it can be derived only from
an already validated Core coverage manifest, source roles, and unchanged plan.
A Core review must still establish semantics; this typed projection will never
infer a fact owner from its list position or date alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .candidate_context import CoreCandidateContext
from .candidate_coverage import CoreCandidateCoverageManifest, validate_candidate_coverage_manifest
from .execution_context import ContextContractError, ExecutionContext
from .request_planning import RequestPlan, plan_fact_ordinals


@dataclass(frozen=True, slots=True)
class CoreFactTemporalOwnership:
    """One source-qualified fact edge reviewed against one immutable Core plan."""

    qualifier_index: int
    fact_ordinal: int
    source_digest: str
    plan_digest: str


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
    for index, qualifier in enumerate(context.qualitative_times):
        matches = []
        for candidate, claim in zip(source_context.candidates, manifest.claims, strict=True):
            if claim.disposition != "planned_fact":
                continue
            spans = [r.span for r in candidate.roles if r.role == "time_approx"]
            if not any(
                span.text == qualifier.qualifier
                and span.text in qualifier.source_text
                and context.source[span.start : span.end] == qualifier.qualifier
                for span in spans
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
