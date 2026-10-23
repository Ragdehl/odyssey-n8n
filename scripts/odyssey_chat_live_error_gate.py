#!/usr/bin/env python3
"""Bounded fresh real-model C4 post-error prompt test with synthetic receipts only."""

from __future__ import annotations

import hashlib
import json
import os
from time import monotonic

from odyssey_runtime.conversation_gateway import (
    ERROR_INSTRUCTIONS,
    ErrorAdvice,
    GuidanceKind,
    OpenAIConversationGateway,
    RecoveryHint,
    VerifiedFailure,
)

CASES = (
    (
        "date-es",
        "failed",
        "TEMPORAL_COHORT_UNRESOLVED",
        None,
        GuidanceKind.SPECIFY_DATE,
        RecoveryHint.ASK_USER,
    ),
    (
        "person-es",
        "needs_attention",
        "AMBIGUOUS_REFERENCE",
        None,
        GuidanceKind.SPECIFY_IDENTITY,
        RecoveryHint.ASK_USER,
    ),
    (
        "unsupported",
        "failed",
        "ROUTER_NEEDS_CAPABILITY",
        None,
        GuidanceKind.UNSUPPORTED,
        RecoveryHint.EXPLAIN,
    ),
    (
        "operational-unknown-write",
        "failed",
        "OPERATIONAL_FAILURE",
        None,
        GuidanceKind.RETRY_LATER,
        RecoveryHint.REVIEW_RETRY,
    ),
    (
        "partial-verified",
        "partial",
        "OPERATIONAL_FAILURE",
        2,
        GuidanceKind.RETRY_LATER,
        RecoveryHint.REVIEW_RETRY,
    ),
    (
        "reformulation",
        "needs_attention",
        "UNREPRESENTABLE_REQUEST",
        None,
        GuidanceKind.CLARIFY_REQUEST,
        RecoveryHint.ASK_USER,
    ),
)


def main() -> int:
    if os.environ.get("ODYSSEY_CHAT_LIVE_APPROVED") != "1":
        print("C4_LIVE_REFUSED_NO_APPROVAL")
        return 2
    if not os.environ.get("OPENAI_API_KEY"):
        print("C4_LIVE_REFUSED_NO_PROVIDER")
        return 2
    if len(CASES) != 6 or any(case[3] not in (None, 2) for case in CASES):
        print("C4_LIVE_REFUSED_INVALID_BUDGET")
        return 2
    gate = OpenAIConversationGateway.from_environment()
    results = []
    print(
        "C4_LIVE_PREFLIGHT",
        json.dumps(
            {
                "prompt_sha256": hashlib.sha256(ERROR_INSTRUCTIONS.encode()).hexdigest(),
                "model": gate.model,
                "effort": gate.reasoning_effort,
                "store": False,
                "max_calls": len(CASES),
                "max_output_tokens_per_case": 550,
                "max_aggregate_budgeted_output_tokens": 3300,
                "synthetic_only": True,
            }
        ),
        flush=True,
    )
    for index, (name, status, code, writes, kind, hint) in enumerate(CASES):
        started = monotonic()
        actual = None
        error_type = None
        try:
            receipt = VerifiedFailure("synthetic-" + str(index), status, code, writes)
            actual = gate.explain_error(receipt)
            passed = (
                isinstance(actual, ErrorAdvice)
                and actual.guidance_kind is kind
                and actual.hint is hint
                and actual.retry_authorized is False
                and (writes is not None) == (receipt.written_count is not None)
            )
        except Exception as error:
            error_type = type(error).__name__
            passed = False
        record = {
            "case": name,
            "passed": passed,
            "guidance": actual.guidance_kind.value if actual else None,
            "hint": actual.hint.value if actual else None,
            "error_type": error_type,
            "elapsed_ms": round((monotonic() - started) * 1000),
        }
        results.append(record)
        print("C4_LIVE_CASE", json.dumps(record), flush=True)
    print(
        "C4_LIVE_RESULT",
        json.dumps(
            {
                "total": len(results),
                "passed": sum(item["passed"] for item in results),
                "fresh_real_provider": True,
                "app_e2e_verified": False,
            }
        ),
        flush=True,
    )
    return 0 if all(item["passed"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
