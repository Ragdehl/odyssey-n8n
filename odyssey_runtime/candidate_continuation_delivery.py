"""Source-only coordinator for a reviewed candidate's existing Core/E3 delivery.

Reuses actor-local CandidatePendingRepository and LocalDeliveryResultStore,
plus the *ordinary* Core executor and shared physical readback. It is NOT
connected to RuntimeComposition, n8n or any live provider. In particular, an
accepted synthetic review is not proof that an LLM preserves source meaning.
Enable a product caller only after the bounded fresh semantic provider gate.
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from odyssey_core.application import (
    ApplicationResult,
    ApplicationStatus,
    UnitStatus,
    WritePreflightGuardError,
)
from odyssey_core.candidate_continuation_context import (
    CandidateContinuationContextError,
    CoreCandidateContinuationContext,
    prepare_selected_candidate_continuation,
)
from odyssey_core.candidate_continuation_plan import (
    CandidateContinuationPlanError,
    inspect_selected_candidate_plan,
)
from odyssey_core.candidate_continuation_semantic import (
    CandidateContinuationSemanticError,
    validate_independent_continuation_verdict,
)
from odyssey_core.candidate_fact_readback import readback_core_write_plan_facts
from odyssey_core.candidate_pending_state import CandidatePendingRepository
from odyssey_core.request_planning import RequestPlan, WriteAction
from odyssey_core.reviewed_continuation_guard import ReviewedCandidateContinuationWriteGuard
from odyssey_core.storage import VaultRepository

from .delivery_results import DeliveryResultError, LocalDeliveryResultStore


class CandidateContinuationPrewriteError(ValueError):
    """Independent model planning/review blocked before ANY E3 claim or write."""


RunExistingCore = Callable[
    [CoreCandidateContinuationContext, RequestPlan, str, ReviewedCandidateContinuationWriteGuard],
    ApplicationResult,
]


def deliver_reviewed_candidate_continuation(
    *,
    pending: CandidatePendingRepository,
    deliveries: LocalDeliveryResultStore,
    conversation_id: str,
    original_request_id: str,
    plan: RequestPlan,
    independent_review: dict[str, Any],
    vault: VaultRepository,
    schema: dict[str, Any],
    run_existing_core: RunExistingCore,
    completed_at: str | None = None,
) -> dict[str, Any]:
    """Idempotently coordinate one already-reviewed remainder, NOT plan it.

    A matching completed receipt replays without Core execution. For a new
    delivery, reserve the deterministic answer-scoped ID before E3; any crash
    between claim and durable result leaves the attempt blocked, never retried
    automatically. The *same* Markdown readback verifier used by the
    whole-message candidate path must prove every fact before final receipt.
    """
    if (
        not isinstance(pending, CandidatePendingRepository)
        or not isinstance(deliveries, LocalDeliveryResultStore)
        or not isinstance(vault, VaultRepository)
        or not isinstance(schema, dict)
        or not callable(run_existing_core)
    ):
        raise ValueError("Canonical continuation owners are required")
    record = pending.read(original_request_id)
    if record["conversation_id"] != conversation_id or record["status"] != "selected":
        raise ValueError("No selected candidate for this conversation")
    answer_id = record["answer_id"]
    if not isinstance(answer_id, str) or not answer_id:
        raise ValueError("Selected candidate lacks answer correlation")
    # The only identifier namespace is the existing actor-scoped delivery
    # store. Never tie this ID to a model-generated plan (which may vary on
    # retry), or reuse the user reply's already-finalized delivery ID.
    delivery_id = (
        "e5-"
        + hashlib.sha256(
            repr((conversation_id, original_request_id, answer_id)).encode("utf-8")
        ).hexdigest()[:40]
    )
    fingerprint = deliveries.fingerprint(
        record["original_request"], conversation_id, reply_to_request_id=original_request_id
    )
    saved = deliveries.load(delivery_id, fingerprint)
    if saved is not None:
        if (
            saved.get("kind") != "reviewed_candidate_continuation"
            or saved.get("original_request_id") != original_request_id
            or saved.get("request_id") != delivery_id
        ):
            raise DeliveryResultError("Continuation delivery receipt has another owner")
        return {**saved, "delivery_replayed": True}
    if deliveries.inspect_mutation_claim(delivery_id, fingerprint)["state"] == "unresolved_attempt":
        raise DeliveryResultError("Continuation has an unresolved prior E3 attempt")

    try:
        context = prepare_selected_candidate_continuation(
            pending,
            conversation_id=conversation_id,
            request_id=original_request_id,
            vault=vault,
            schema=schema,
        )
        inspection = inspect_selected_candidate_plan(context, plan)
        review = copy.deepcopy(independent_review)
        verdict = validate_independent_continuation_verdict(context, inspection, review)
        guard = ReviewedCandidateContinuationWriteGuard(
            pending,
            context,
            inspection,
            verdict,
            review,
            plan,
            vault,
            schema,
        )
        guard.validate_request_plan(plan)
    except (
        CandidateContinuationContextError,
        CandidateContinuationPlanError,
        CandidateContinuationSemanticError,
        WritePreflightGuardError,
    ) as error:
        # Every operation above precedes the durable mutation claim. The
        # exact same exception AFTER claim must never be reclassified.
        raise CandidateContinuationPrewriteError(
            "Continuation source/plan/independent review is not current"
        ) from error
    # This immutable claim is the recovery boundary. Never execute Core
    # without it; on a timeout or uncertain write the claim stays unresolved.
    deliveries.claim_mutation(delivery_id, fingerprint)
    result = run_existing_core(context, plan, delivery_id, guard)
    if (
        not isinstance(result, ApplicationResult)
        or result.status is not ApplicationStatus.COMPLETED
        or result.request_id != delivery_id
        or result.core_source_digest
        != hashlib.sha256(context.pending_source.encode("utf-8")).hexdigest()
    ):
        raise DeliveryResultError("Reviewed continuation Core result is incomplete")
    # The physical readback checks each canonical wikilink, but the selected
    # pronoun must ALSO be linked to the *exact user-chosen stable ID*. That
    # is a post-execution assertion, not a second identity resolver.
    chosen_verified = False
    for action_index, action in enumerate(plan.actions):
        if not isinstance(action, WriteAction):
            raise DeliveryResultError("Continuation wrote an unsupported action")
        outcome = result.action_results[action_index]
        for unit in action.units:
            for reference in unit.references:
                if reference.mention != context.reference_text:
                    continue
                matches = [
                    item
                    for item in outcome.unit_results
                    if item.unit_index == reference.target_index
                ]
                if (
                    len(matches) != 1
                    or matches[0].status is not UnitStatus.SUCCEEDED
                    or matches[0].operation != "REFERENCE_BOUND"
                    or matches[0].stable_note_id != context.selected_note_id
                    or matches[0].materially_affected
                ):
                    raise DeliveryResultError("Continuation selected identity receipt disagrees")
                chosen_verified = True
    if not chosen_verified:
        raise DeliveryResultError("Continuation lacks selected identity receipt")
    receipts = readback_core_write_plan_facts(plan, result, vault, schema)
    if (
        len(receipts) != len(inspection.proposed_facts)
        or any(
            item.status not in {"verified_in_markdown", "verified_existing_knowledge"}
            for item in receipts
        )
        or any(item.note_id is None or item.rendered_fact_digest is None for item in receipts)
    ):
        raise DeliveryResultError("Reviewed continuation physical readback is incomplete")
    response = {
        "request_id": delivery_id,
        "original_request_id": original_request_id,
        "kind": "reviewed_candidate_continuation",
        "status": "completed",
        "review_digest": verdict.reviewer_digest,
        "plan_digest": inspection.plan_digest,
        "facts": [
            {
                "ordinal": item.ordinal,
                "note_id": item.note_id,
                "fact_sha256": item.rendered_fact_digest,
                "status": item.status,
            }
            for item in receipts
        ],
    }
    deliveries.save(
        delivery_id,
        fingerprint,
        response,
        completed_at if completed_at is not None else datetime.now(UTC).isoformat(),
    )
    deliveries.finish_mutation_claim(delivery_id)
    return response
