"""Sequential immutable P1 evidence runner with a mandatory whole-request cost gate."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from .budget import BudgetGuard, CaseEnvelope
from .report import format_request_report


@dataclass(frozen=True, slots=True)
class CaseResult:
    """Keep a bounded semantic outcome and supported actual API estimate for one case."""

    semantic_passed: bool
    status: str
    estimated_cost_usd: Decimal | None
    operational: dict[str, Any]


def run_cases(
    cases: Sequence[dict[str, Any]],
    envelopes: dict[str, CaseEnvelope],
    executor: Callable[[dict[str, Any]], CaseResult],
    guard: BudgetGuard,
    evidence_path: Path,
    *,
    confirmed: bool,
) -> None:
    """Run once per frozen case after confirmation, persisting each completed row immediately.

    Args:
        cases: Frozen synthetic cases in the order to execute.
        envelopes: Reviewed worst-case cost bound for every case.
        executor: Injected single-attempt request path; production wiring remains a separate gate.
        guard: The USD 0.20 reservation ledger for this run.
        evidence_path: New immutable JSONL artifact; an existing file is never overwritten.
        confirmed: Explicit live-call authorization supplied by the command line.

    Raises:
        ValueError: If confirmation, a semantic result, or evidence is unsafe.
        BudgetError: If the next request cannot fit under the hard ceiling.
    """
    if not confirmed:
        raise ValueError("live provider calls require explicit confirmation")
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with evidence_path.open("x", encoding="utf-8") as stream:
        for case in cases:
            case_id = case.get("id")
            if not isinstance(case_id, str) or case_id not in envelopes:
                raise ValueError("case has no reviewed cost envelope")
            reserved = guard.reserve(envelopes[case_id])
            result = executor(case)
            if (
                not isinstance(result, CaseResult)
                or not isinstance(result.semantic_passed, bool)
                or result.status not in {"completed", "needs_attention", "failed"}
                or not isinstance(result.operational, dict)
            ):
                raise ValueError("case returned malformed evidence")
            format_request_report(case_id, result.operational, guard.pricing)
            charged = guard.finish(result.estimated_cost_usd)
            row = {
                "case_id": case_id,
                "status": result.status,
                "semantic_passed": result.semantic_passed,
                "estimated_cost_usd": (
                    str(result.estimated_cost_usd)
                    if result.estimated_cost_usd is not None
                    else None
                ),
                "reserved_usd": str(reserved),
                "budget_charged_usd": str(charged),
                "operational": result.operational,
            }
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            if not result.semantic_passed or result.status == "failed":
                raise ValueError("case failed closed after incremental evidence was persisted")
