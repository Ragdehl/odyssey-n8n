"""Read-only preview of candidate pending work after actual Core execution.

Phase 17B stores planned incomplete actions; unplanned Router-v1 candidates
cannot be replayed through that format. Keep them explicit and non-executable
until a separately approved durable state and continuation contract exists.
"""

from __future__ import annotations

from dataclasses import dataclass

from .application import ApplicationResult, ApplicationStatus
from .candidate_context import CoreCandidateContext
from .candidate_coverage import (
    CoreCandidateCoverageManifest,
    CoreCandidateCoverageReview,
    review_candidate_coverage,
    validate_candidate_coverage_manifest,
)
from .candidate_fact_readback import CandidateFactReadback
from .request_planning import RequestPlan


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
        if any(
            claim.disposition == "planned_fact" and item.status != "physically_written_claim"
            for claim, item in zip(manifest.claims, review.items, strict=True)
        ):
            raise CandidatePendingProjectionError(
                "Cannot record candidate pending work while previous Core writes lack physical proof"
            )
        pending: list[CandidatePendingItem] = []
        for candidate, claim, progress in zip(
            context.candidates, manifest.claims, review.items, strict=True
        ):
            if claim.disposition == "pending":
                if progress.status != "pending":
                    raise CandidatePendingProjectionError("Candidate pending status mismatched")
                references = [role.span for role in candidate.roles if role.role == "reference"]
                if len(references) > 1:
                    raise CandidatePendingProjectionError(
                        "Pending reference is not locally sourced"
                    )
                reference = references[0] if references else None
                # A single enclosing anchor already has complete source evidence.
                # For a model's shorter/disjoint quotes, reconstruct only a
                # single original clause whose exact source roles include the
                # unresolved pronoun. Never combine unrelated sentences or
                # carry a model-invented rewrite into durable pending state.
                if len(candidate.anchors) == 1 and (
                    reference is None
                    or candidate.anchors[0].start <= reference.start
                    and reference.end <= candidate.anchors[0].end
                ):
                    start, end = candidate.anchors[0].start, candidate.anchors[0].end
                else:
                    if reference is None or candidate.state != "ambiguous_identity":
                        raise CandidatePendingProjectionError(
                            "Disjoint pending source needs independently anchored reference"
                        )
                    spans = [
                        *candidate.anchors,
                        *(
                            role.span
                            for role in candidate.roles
                            if role.role
                            in {"date", "date_scope", "time", "predicate", "object", "reference"}
                        ),
                    ]
                    start = min(span.start for span in spans)
                    end = max(span.end for span in spans)
                    if (
                        end - start > 400
                        or any(char in source[start:end] for char in ".;!?\n\r")
                        or not start <= reference.start < reference.end <= end
                        or any(
                            anchor.start < end and anchor.end > start
                            for other in context.candidates
                            if other is not candidate
                            for anchor in other.anchors
                        )
                    ):
                        raise CandidatePendingProjectionError(
                            "Disjoint source spans do not prove one pending clause"
                        )
                if reference and not (start <= reference.start and reference.end <= end):
                    raise CandidatePendingProjectionError(
                        "Pending reference is not locally sourced"
                    )
                pending.append(
                    CandidatePendingItem(
                        candidate.candidate_id,
                        source[start:end],
                        start,
                        end,
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
    # The trusted readback owns the digest of the fact *actually written*.
    # For a Core-linked fact that string contains canonical wikilinks rather
    # than the source plan's transient {{ref:N}} markers.
    confirmed = tuple(
        (fact.ordinal, fact.note_id, fact.rendered_fact_digest)
        for fact in readback.persisted_facts
        if fact.status == "verified_in_markdown"
        and fact.note_id is not None
        and fact.rendered_fact_digest is not None
    )
    if sum(item.status == "verified_in_markdown" for item in readback.persisted_facts) != len(
        confirmed
    ):
        raise CandidatePendingProjectionError(
            "Verified Core fact is missing its durable rendered proof"
        )
    return CandidatePendingPreview(
        request_id=result.request_id,
        original_request=source,
        request_status=result.status.value,
        pending=tuple(pending),
        physically_verified_fact_count=len(confirmed),
        completed_fact_markers=confirmed,
    )
