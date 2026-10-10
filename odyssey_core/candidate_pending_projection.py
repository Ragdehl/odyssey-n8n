"""Read-only preview of candidate pending work after actual Core execution.

Phase 17B stores planned incomplete actions; unplanned Router-v1 candidates
cannot be replayed through that format. Keep them explicit and non-executable
until a separately approved durable state and continuation contract exists.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .application import ApplicationResult, ApplicationStatus
from .atomic_facts import normalize_atomic_fact
from .candidate_context import CoreCandidateContext
from .candidate_coverage import (
    CoreCandidateCoverageManifest,
    CoreCandidateCoverageReview,
    review_candidate_coverage,
    validate_candidate_coverage_manifest,
)
from .candidate_fact_readback import CandidateFactReadback
from .request_planning import RequestPlan, WriteAction, plan_fact_ordinals


class CandidatePendingProjectionError(ValueError):
    """The request's evidence is stale, incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class CandidatePendingItem:
    """One source-grounded, non-executable pending task for later clarification."""

    candidate_id: str
    source_text: str
    source_start: int
    source_end: int
    reason: str
    reference_text: str | None = None
    reference_start: int | None = None
    reference_end: int | None = None
    resumable: bool = False


@dataclass(frozen=True, slots=True)
class CandidatePendingPreview:
    """Explicitly non-durable diagnostic for outstanding source candidates."""

    request_id: str
    original_request: str
    request_status: str
    pending: tuple[CandidatePendingItem, ...]
    physically_verified_fact_count: int
    completed_fact_markers: tuple[tuple[int, str, str], ...] = ()
    candidate_semantics_verified: bool = False
    persisted: bool = False
    resumable: bool = False


def project_unresolved_candidate_preview(
    source: str,
    context: CoreCandidateContext,
    plan: RequestPlan,
    manifest: CoreCandidateCoverageManifest,
    result: ApplicationResult,
    readback: CandidateFactReadback,
) -> CandidatePendingPreview:
    """Describe only pending candidates; never reconstruct a write plan from prose.

    This is an in-memory preview, not a pending-work record, user-facing
    clarification, semantic approval, or a continuation capability. Only the
    original source anchors are included, without canonical note IDs.

    Raises:
        CandidatePendingProjectionError: Core result, readback and candidate
            evidence do not describe exactly the same partially handled request.
    """
    try:
        validate_candidate_coverage_manifest(source, context, plan, manifest)
        if (
            not isinstance(result, ApplicationResult)
            or result.status not in {ApplicationStatus.PARTIAL, ApplicationStatus.NEEDS_ATTENTION}
            or not isinstance(readback, CandidateFactReadback)
            or result.request_id != readback.request_id
        ):
            raise CandidatePendingProjectionError("Candidate pending request identity mismatched")
        review: CoreCandidateCoverageReview = review_candidate_coverage(
            source, context, plan, manifest, readback
        )
        if not review.pending_candidate_ids:
            raise CandidatePendingProjectionError("No pending candidates were observed")
        pending: list[CandidatePendingItem] = []
        for candidate, claim, progress in zip(
            context.candidates, manifest.claims, review.items, strict=True
        ):
            if claim.disposition == "pending":
                if progress.status != "pending":
                    raise CandidatePendingProjectionError("Candidate pending status mismatched")
                if len(candidate.anchors) != 1:
                    raise CandidatePendingProjectionError(
                        "Multiple-anchor candidate needs a different clarification UI"
                    )
                anchor = candidate.anchors[0]
                references = [role.span for role in candidate.roles if role.role == "reference"]
                if (
                    len(references) > 1
                    or references
                    and (references[0].start < anchor.start or references[0].end > anchor.end)
                ):
                    raise CandidatePendingProjectionError(
                        "Pending reference is not locally sourced"
                    )
                reference = references[0] if references else None
                pending.append(
                    CandidatePendingItem(
                        candidate.candidate_id,
                        anchor.text,
                        anchor.start,
                        anchor.end,
                        claim.pending_reason,
                        reference.text if reference else None,
                        reference.start if reference else None,
                        reference.end if reference else None,
                    )
                )
        if not pending:
            raise CandidatePendingProjectionError(
                "Unverified Core facts require reconciliation, not a fabricated user clarification"
            )
    except (TypeError, ValueError, AttributeError) as error:
        raise CandidatePendingProjectionError(
            "Unable to project validated candidate pending evidence"
        ) from error
    # Preserve exact original successful Core provenance for later staleness
    # checks. This is not a new knowledge store or a replayable Core plan.
    fact_texts: dict[int, str] = {}
    by_unit = iter(plan_fact_ordinals(plan))
    for action in plan.actions:
        if isinstance(action, WriteAction):
            for unit in action.units:
                for ordinal, fact_text in zip(next(by_unit), unit.facts, strict=True):
                    fact_texts[ordinal] = fact_text
    confirmed = tuple(
        (
            fact.ordinal,
            fact.note_id,
            hashlib.sha256(
                normalize_atomic_fact(fact_texts[fact.ordinal]).encode("utf-8")
            ).hexdigest(),
        )
        for fact in readback.persisted_facts
        if fact.status == "verified_in_markdown" and fact.note_id is not None
    )
    return CandidatePendingPreview(
        request_id=result.request_id,
        original_request=source,
        request_status=result.status.value,
        pending=tuple(pending),
        physically_verified_fact_count=len(confirmed),
        completed_fact_markers=confirmed,
    )
