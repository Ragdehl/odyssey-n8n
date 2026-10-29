"""C4: receipt-bound, non-executing post-Core error explanation.

This is a presentation adapter over a trusted ApplicationResult. No model can
change canonical writes, request routing, retry policy or persisted evidence.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from odyssey_core.application import ApplicationResult
from odyssey_core.stage_presentation import stage_view_for

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


def diagnose_trusted_execution_graph(
    result: ApplicationResult,
    response: Mapping[str, Any],
    ledger: Mapping[str, Any],
    gateway: OpenAIConversationGateway,
    *,
    original_message: str = "",
    semantic_review: bool = False,
) -> dict[str, object] | None:
    """Let C4 AI interpret the existing observed graph, with no execution authority.

    Source is actor-bound through the existing request, E3 and checkpoint
    contract. A model may explain observed failure evidence but cannot infer
    unobserved stages, physical write absence, canonical identities or retries.
    """
    if (
        not isinstance(result, ApplicationResult)
        or not isinstance(response, Mapping)
        or not isinstance(ledger, Mapping)
        or not isinstance(gateway, OpenAIConversationGateway)
        or response.get("request_id") != result.request_id
        or response.get("status") != result.status.value
        or response.get("product_outcome") not in {"CLARIFY", "CANNOT_ANSWER"}
        or result.status.value not in {"failed", "partial", "needs_attention"}
        or ledger.get("request_id") != result.request_id
        or ledger.get("status") != result.status.value
    ):
        return None
    code = response.get("product_reason") or response.get("clarification_code")
    if not isinstance(code, str) or not _CODE.fullmatch(code):
        code = "UNKNOWN_FAILURE"
    raw_stages = ledger.get("stages")
    raw_events = ledger.get("events")
    raw_routes = ledger.get("routes")
    if not all(isinstance(data, list) for data in (raw_stages, raw_events, raw_routes)):
        return None
    stages: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    routes: list[dict[str, object]] = []
    known_stages = {("unattributed", None)}
    failed_children: set[tuple[str, int | None]] = set()
    for item in raw_routes[:32]:
        if not isinstance(item, Mapping):
            continue
        capability, status = item.get("capability"), item.get("status")
        if (
            isinstance(capability, str)
            and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,39}", capability)
            and isinstance(status, str)
            and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,39}", status)
        ):
            routes.append(
                {
                    "route_index": item.get("route_index"),
                    "depends_on": item.get("depends_on"),
                    "capability": capability,
                    "status": status,
                }
            )
    for item in raw_stages[:32]:
        if not isinstance(item, Mapping):
            continue
        name, outcome, error = (item.get("name"), item.get("outcome"), item.get("error_category"))
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,79}", name):
            continue
        if outcome not in {"completed", "failed", "skipped", "not_called", "unavailable"}:
            continue
        if error is not None and (not isinstance(error, str) or len(error) > 120):
            continue
        index = item.get("route_index")
        if index is not None and (type(index) is not int or index < 0 or index >= len(routes)):
            continue
        parent = item.get("parent_stage")
        if parent is not None and (
            not isinstance(parent, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,79}", parent)
            or parent == name
        ):
            continue
        if outcome in {"failed", "unavailable"}:
            known_stages.add((name, index))
            if parent is not None:
                failed_children.add((parent, index))
        stages.append(
            {
                "name": name,
                "outcome": outcome,
                "error_category": error,
                "route_index": index,
                "parent_stage": parent,
            }
        )
    for item in raw_events[-32:]:
        if not isinstance(item, Mapping):
            continue
        name, outcome = item.get("stage"), item.get("outcome")
        if (
            isinstance(name, str)
            and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,79}", name)
            and outcome
            in {
                "milestone_observed",
                "result_persisted",
                "processing_returned",
                "failed_or_unknown",
            }
        ):
            if outcome == "failed_or_unknown":
                known_stages.add((name, None))
            events.append({"stage": name, "outcome": outcome})
    write_evidence = "SOME" if result.affected_stable_note_ids else "UNKNOWN"
    # The caller is the product Router path, not an idle chat prompt. This
    # proves save/operation *routing*, not that the chosen writer was correct
    # or any specific Person/Event/Task identity was verified.
    observed_failed_substages = [
        {"name": stage["name"], "route_index": stage["route_index"]}
        for stage in stages
        if stage["outcome"] in {"failed", "unavailable"} and stage["name"].startswith("provider.")
    ]
    evidence = {
        "status": result.status.value,
        "reason_code": code,
        "write_evidence": write_evidence,
        "entry_intent": "ROUTED_PERSONAL_INFORMATION_OR_OPERATION",
        "prewrite_recovery_proven": result.prewrite_recovery_proven is True,
        "failed_provider_substages": observed_failed_substages,
        "original_message": original_message[:2048] if isinstance(original_message, str) else "",
        "source_truncated": isinstance(original_message, str) and len(original_message) > 2048,
        "events": events,
        "stages": stages,
        "routes": routes,
    }
    try:
        proposal = gateway.diagnose_execution_graph(evidence)
    except (ConversationGateError, OSError, ValueError, TypeError):
        return None
    stage = proposal.get("evidence_stage")
    route_index = proposal.get("route_index")
    explanation = proposal.get("explanation")
    question = proposal.get("user_question")
    next_step = proposal.get("next_step")
    if (
        not isinstance(stage, str)
        or (route_index is not None and (type(route_index) is not int or route_index < 0))
        or (stage, route_index) not in known_stages
        or (stage, route_index) in failed_children  # prefer observed failing child
        or not isinstance(explanation, str)
        or not 12 <= len(explanation.strip()) <= 420
        or not isinstance(question, str)
        or len(question) > 240
        or next_step not in {"ASK_USER", "REVIEW_SAFE_RETRY", "CHECK_SYSTEM", "INSPECT_RESULT"}
        or (next_step == "ASK_USER") != bool(question.strip())
        or any("\n" in text or "\r" in text for text in (explanation, question))
    ):
        return None
    # The second model need not be called when Core proof has already made
    # this proposed step ineligible for the evidence-only presentation.
    if semantic_review and (
        next_step == "ASK_USER"
        or (next_step == "REVIEW_SAFE_RETRY" and result.prewrite_recovery_proven is not True)
    ):
        return None
    # Optional second AI pass checks ENTIRE meaning rather than banning
    # substrings such as "escri" (a writer-stage failure is not a claim that
    # Markdown was written). Off by default pending real-model quality/cost.
    if semantic_review:
        try:
            if not gateway.review_execution_diagnosis(evidence, proposal):
                return None
        except (ConversationGateError, OSError, TypeError, ValueError):
            return None
    # The second AI may veto an unsupported cause/step but cannot grant its
    # own free text material-fact authority. A typed-only interpretation is
    # rendered using verified graph evidence by n8n. No model prose crosses
    # this boundary even when two correlated models say SUPPORTED.
    if semantic_review:
        if next_step == "REVIEW_SAFE_RETRY" and result.prewrite_recovery_proven is not True:
            # This typed presentation implies a possible safe second pass;
            # positive source-executor proof, not the model reviewer, owns it.
            return None
        if next_step == "ASK_USER":
            # Core owns verified clarification text/options; arbitrary AI
            # questions cannot invent a missing identity or date.
            return None
        return {
            "status": result.status.value,
            "reason_code": code,
            "write_evidence": write_evidence,
            "evidence_stage": stage,
            "route_index": route_index,
            "stage_view": stage_view_for(stage).to_response(),
            "next_step": next_step,
            "verified_stage_only": True,
        }
    # Legacy one-pass free text stays behind its old conservative veto.
    if any(
        fragment in (explanation + " " + question).casefold()
        for fragment in (
            "nota",
            "file",
            "archivo",
            "ficher",
            "bóveda",
            "vault",
            "cambio",
            "cambi",
            "alter",
            "ningún dato",
            "datos nuevos",
            "register",
            "registro",
            "dossier",
            "intact",
            "unchang",
            "no hay",
            "sin cambios",
            "ninguna nueva",
            "no new",
            "guard",
            "escri",
            "salvad",
            "modific",
            "actualiz",
            "cread",
            "elimin",
            "borrad",
            "añad",
            "persist",
            "enregistr",
            "écri",
            "save",
            "writ",
            "delet",
            "updat",
        )
    ):
        return None
    return {
        "status": result.status.value,
        "reason_code": code,
        "write_evidence": write_evidence,
        "evidence_stage": stage,
        "route_index": route_index,
        "explanation": explanation.strip(),
        "next_step": next_step,
        "user_question": question.strip(),
        # Only validated write receipts, not model output, control retries.
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
