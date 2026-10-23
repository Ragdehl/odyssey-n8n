"""C4: receipt-bound, non-executing post-Core error explanation.

This is a presentation adapter over a trusted ApplicationResult. No model can
change canonical writes, request routing, retry policy or persisted evidence.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from odyssey_core.application import ApplicationResult

from .conversation_gateway import (
    ConversationGateError,
    ErrorAdvice,
    GuidanceKind,
    OpenAIConversationGateway,
    RecoveryHint,
    VerifiedFailure,
)

_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,99}\Z")

# These codes already have product-owned semantics. Unknown codes never become
# new diagnoses just because a model can select an impressive-sounding label.
_REASON_KIND: dict[str, GuidanceKind] = {
    "AMBIGUOUS_REFERENCE": GuidanceKind.SPECIFY_IDENTITY,
    "WORK_SESSION_TASK_UNRESOLVED": GuidanceKind.SPECIFY_IDENTITY,
    "WORK_SESSION_TASK_AMBIGUOUS": GuidanceKind.SPECIFY_IDENTITY,
    "TEMPORAL_UNRESOLVED": GuidanceKind.SPECIFY_DATE,
    "TEMPORAL_COHORT_UNRESOLVED": GuidanceKind.SPECIFY_DATE,
    "TEMPORAL_COHORT_YEAR_CONFLICT": GuidanceKind.SPECIFY_DATE,
    "ROUTER_CLARIFY": GuidanceKind.CLARIFY_REQUEST,
    "UNREPRESENTABLE_REQUEST": GuidanceKind.CLARIFY_REQUEST,
    "INCOMPLETE_EVIDENCE": GuidanceKind.CLARIFY_REQUEST,
    "ROUTER_NEEDS_CAPABILITY": GuidanceKind.UNSUPPORTED,
    "STALE_EVIDENCE": GuidanceKind.RETRY_LATER,
    "OPERATIONAL_FAILURE": GuidanceKind.RETRY_LATER,
}
_HINT: dict[GuidanceKind, RecoveryHint] = {
    GuidanceKind.SPECIFY_IDENTITY: RecoveryHint.ASK_USER,
    GuidanceKind.SPECIFY_DATE: RecoveryHint.ASK_USER,
    GuidanceKind.CLARIFY_REQUEST: RecoveryHint.ASK_USER,
    GuidanceKind.UNSUPPORTED: RecoveryHint.EXPLAIN,
    GuidanceKind.RETRY_LATER: RecoveryHint.REVIEW_RETRY,
    GuidanceKind.UNKNOWN: RecoveryHint.EXPLAIN,
}


def explain_trusted_product_failure(
    result: ApplicationResult,
    response: Mapping[str, Any],
    gateway: OpenAIConversationGateway | None,
) -> dict[str, object] | None:
    """Attach only advice supported by this exact Core result, never a new action.

    Unknown/contradictory counts are *not* interpreted as zero. A Core-reported
    affected Note ID is positive write evidence; missing positive IDs do not
    prove that a failed or interrupted write had no physical effects.
    """
    if not isinstance(result, ApplicationResult) or not isinstance(response, Mapping):
        raise TypeError("Trusted typed execution evidence required")
    if (
        response.get("request_id") != result.request_id
        or response.get("status") != result.status.value
        or response.get("product_outcome") != "CANNOT_ANSWER"
        or result.status.value not in {"failed", "partial", "needs_attention"}
    ):
        return None
    reason = response.get("product_reason")
    code = reason if isinstance(reason, str) and _CODE.fullmatch(reason) else "UNKNOWN_FAILURE"
    # Even Core's affected-ID list does not attest zero when empty.
    ids = result.affected_stable_note_ids
    # The gateway only needs SOME vs UNKNOWN. Preserve positive evidence for
    # arbitrarily many affected notes; clamp the private witness to the
    # VerifiedFailure bound (do not present it as an exact count).
    count = min(len(ids), 64) if ids else None
    receipt = VerifiedFailure(result.request_id, result.status.value, code, count)
    expected = _REASON_KIND.get(code, GuidanceKind.UNKNOWN)
    fallback = ErrorAdvice(expected, _HINT[expected])
    advice = fallback
    if gateway is not None and expected is not GuidanceKind.UNKNOWN:
        try:
            proposal = gateway.explain_error(receipt)
            if (
                proposal.guidance_kind is expected
                and proposal.hint is _HINT[expected]
                and not proposal.retry_authorized
            ):
                advice = proposal
        except (ConversationGateError, OSError, ValueError, TypeError):
            pass  # A failed optional model cannot invalidate a Core result.
    write_evidence = "SOME" if count is not None else "UNKNOWN"
    return {
        "status": receipt.status,
        "reason_code": code,
        "write_evidence": write_evidence,
        "guidance_kind": advice.guidance_kind.value,
        "hint": advice.hint.value,
    }
