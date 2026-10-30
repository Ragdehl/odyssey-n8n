"""Fail-closed local validation of an independent continuation semantic verdict.

Reuses the existing full-source *review verdict shape* but not its assumption
that every original assertion must be written again. The previous E3 facts
are already physically verified by the separate pending context. A reviewer
judges only the proposed remainder against the FULL original request.
No result here authorizes E3; actual model behavior remains unproven.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .candidate_continuation_context import CoreCandidateContinuationContext
from .candidate_continuation_plan import (
    CandidateContinuationPlanError,
    CoreContinuationPlanInspection,
    validate_inspected_candidate_plan_current,
)
from .candidate_pending_state import CandidatePendingRepository
from .request_planning import RequestPlan
from .storage import VaultRepository
from .temporal import normalize_iso_date


class CandidateContinuationSemanticError(ValueError):
    """Independent semantics are absent, inconsistent or not approved."""


@dataclass(frozen=True, slots=True)
class CoreContinuationSemanticVerdict:
    """Proposal-bound independent review evidence; never a write permit."""

    source_digest: str
    pending_record_digest: str
    plan_digest: str
    reviewer_digest: str
    reviewed_ordinals: tuple[int, ...]

    @property
    def may_execute(self) -> bool:
        return False


def validate_independent_continuation_verdict(
    context: CoreCandidateContinuationContext,
    inspection: CoreContinuationPlanInspection,
    review: dict[str, Any],
) -> CoreContinuationSemanticVerdict:
    """Reject missing/partial/reordered/contradictory model review results.

    The expected output follows the existing REVIEW_CORE_ANCHORED_SCHEMA from
    the full-source route: approved, complete, reason, and an exhaustive list
    of {ordinal,kind,reviewed_text,date,reference_names,supported}. The source
    quote is deliberately NOT returned by the reviewer: Core already owns
    original source offsets. This validator cannot judge human-language truth
    and must not be used as an E3 guard without a separately accepted provider
    evaluation and a completed canonical-write lifecycle.
    """
    if not isinstance(context, CoreCandidateContinuationContext) or not isinstance(
        inspection, CoreContinuationPlanInspection
    ):
        raise CandidateContinuationSemanticError("Typed Core review input required")
    try:
        inspection.review_payload(context)
    except CandidateContinuationPlanError as error:
        raise CandidateContinuationSemanticError("Source or plan evidence changed") from error
    if (
        not isinstance(review, dict)
        or set(review) != {"approved", "complete", "reason", "facts"}
        or type(review["approved"]) is not bool
        or type(review["complete"]) is not bool
        or not (review["approved"] and review["complete"])
        or (
            review["reason"] is not None
            and (not isinstance(review["reason"], str) or len(review["reason"]) > 512)
        )
        or not isinstance(review["facts"], list)
        or len(review["facts"]) != len(inspection.proposed_facts)
    ):
        raise CandidateContinuationSemanticError(
            "Independent reviewer did not approve completeness"
        )
    reviewed: list[int] = []
    for expected, claim in zip(inspection.proposed_facts, review["facts"], strict=True):
        if (
            not isinstance(claim, dict)
            or set(claim)
            != {"ordinal", "kind", "reviewed_text", "date", "reference_names", "supported"}
            or type(claim["ordinal"]) is not int
            or claim["ordinal"] != expected.ordinal
            or claim["kind"] != "record"
            or type(claim["supported"]) is not bool
            or not claim["supported"]
            or claim["reviewed_text"] != expected.text
            or not isinstance(claim["reference_names"], list)
            or any(
                not isinstance(name, str) or not name or len(name) > 160
                for name in claim["reference_names"]
            )
            or len(claim["reference_names"]) > 8
            or len(set(claim["reference_names"])) != len(claim["reference_names"])
            or tuple(claim["reference_names"]) != expected.reference_names
        ):
            raise CandidateContinuationSemanticError("Independent atomic fact review disagrees")
        # The inherited whole-source schema only carries one date. Complex
        # multiple/partial time spans remain pending, not silently dropped.
        if len(expected.temporal_values) > 1:
            raise CandidateContinuationSemanticError("Multi-temporal meaning needs separate review")
        date = expected.temporal_values[0] if expected.temporal_values else None
        if date is not None:
            try:
                date = normalize_iso_date(date)
            except (TypeError, ValueError) as error:
                raise CandidateContinuationSemanticError(
                    "Unsupported date semantics require separate review"
                ) from error
        if claim["date"] != date:
            raise CandidateContinuationSemanticError("Reviewer and plan disagree on time")
        selected = expected.ordinal in inspection.selected_identity_reference_ordinals
        has_name = context.selected_name in claim["reference_names"]
        if selected != has_name:
            raise CandidateContinuationSemanticError(
                "Reviewed identity differs from selected source reference"
            )
        # Names and link slots must match the typed Core plan exactly; an
        # entity named in a DIFFERENT source sentence does not become a
        # participant of this fact. Canonical identity proof stays in Core.
        reviewed.append(expected.ordinal)
    try:
        encoded = json.dumps(
            review, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CandidateContinuationSemanticError("Malformed semantic review") from error
    if len(encoded) > 32_768:
        raise CandidateContinuationSemanticError("Semantic review exceeds resource bound")
    return CoreContinuationSemanticVerdict(
        context.source_digest,
        context.pending_record_digest,
        inspection.plan_digest,
        hashlib.sha256(encoded).hexdigest(),
        tuple(reviewed),
    )


def validate_independent_continuation_verdict_current(
    verdict: CoreContinuationSemanticVerdict,
    context: CoreCandidateContinuationContext,
    inspection: CoreContinuationPlanInspection,
    review: dict[str, Any],
    plan: RequestPlan,
    repository: CandidatePendingRepository,
    *,
    vault: VaultRepository,
    schema: dict[str, Any],
) -> None:
    """Recheck reviewer, exact plan and canonical persisted evidence after delay.

    A valid result is still ONLY evidence for an unactivated future E3 gate.
    """
    if not isinstance(verdict, CoreContinuationSemanticVerdict):
        raise CandidateContinuationSemanticError("Typed independent review required")
    try:
        validate_inspected_candidate_plan_current(
            inspection, context, plan, repository, vault=vault, schema=schema
        )
        current = validate_independent_continuation_verdict(context, inspection, review)
    except (CandidateContinuationPlanError, CandidateContinuationSemanticError) as error:
        raise CandidateContinuationSemanticError(
            "Independent semantic review is no longer current"
        ) from error
    if current != verdict:
        raise CandidateContinuationSemanticError("Independent semantic verdict changed")
