"""Reviewed, bounded synthetic GPT-6 Router v2 evaluation (not a deployment).

Offline by default; production Router request bytes are recovered through fake
clients. This script does not read personal notes, open secret files, or write
canonical data. Its only optional external side effect is four authorized
synthetic Responses API calls with no SDK retries, store=False and low effort.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.fact_candidate_v2_preflight.check import audit, captured_requests
from benchmarks.fact_candidate_v2_preflight.compare_saved_outputs import (
    compare_saved_proposals,
)
from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from tests.apps.test_fact_candidates import CASES

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MAX_SPEND_USD = 0.02
CASE_IDS = ("F14", "F27", "F09", "F10")
RUN_ENV = "ODYSSEY_ROUTER_V2_LIVE_APPROVED"


def reviewed_calls() -> tuple[list[tuple[str, dict[str, Any]]], float]:
    """Use exact production-shaped requests; fail if pricing/configuration drifts."""
    rows = [(case_id, req) for case_id, stage, req in captured_requests() if stage == "router"]
    if tuple(case_id for case_id, _req in rows) != CASE_IDS:
        raise ValueError("Unexpected Router test cases")
    reference = json.loads(
        (ROOT / "benchmarks/fact_candidate_v2_preflight/playground_router_requests.json").read_text(
            encoding="utf-8"
        )
    )
    snapshots = reference["calls"]
    snapshot_by_id = {item["id"]: item["request"] for item in snapshots}
    if len(snapshots) != 4 or any(snapshot_by_id.get(case_id) != req for case_id, req in rows):
        raise ValueError("Router request changed since independently reviewed snapshot")
    costs = audit()["calls"]
    limits = {(row["case"], row["stage"]): row for row in costs}
    total = 0.0
    for case_id, req in rows:
        if (
            req["model"] != "gpt-6-luna"
            or req["reasoning"] != {"effort": "low"}
            or req["store"] is not False
            or req["max_output_tokens"] != 4096
            or req["text"]["format"]["strict"] is not True
            or req["text"]["format"]["type"] != "json_schema"
            or len(req["input"]) != 2
            or req["input"][1]["content"] != next(c["source"] for c in CASES if c["id"] == case_id)
        ):
            raise ValueError("Router request violates reviewed execution contract")
        total += limits[(case_id, "router")]["cost_upper_usd"]
    total = round(total, 8)
    if total > MAX_SPEND_USD or total > 0.011819:
        raise ValueError("Conservative Router cost ceiling exceeded")
    return rows, total


def run_once(*, live: bool, client: Any | None = None) -> dict[str, Any]:
    """Only live=True with explicit permission may construct a network client."""
    calls, reserved = reviewed_calls()
    summary: dict[str, Any] = {
        "mode": "LIVE_SYNTHETIC_ROUTER" if live else "DRY_RUN_NO_PROVIDER",
        "model": "gpt-6-luna",
        "reasoning": "low",
        "cases": list(CASE_IDS),
        "call_limit": len(calls),
        "conservative_reservation_usd": reserved,
        "budget_ceiling_usd": MAX_SPEND_USD,
        "live_model_quality_verified": False,
    }
    if not live:
        return summary
    if os.getenv(RUN_ENV) != "1":
        raise ValueError("Explicit approved live flag is required")
    if client is None:
        from openai import OpenAI

        client = OpenAI(max_retries=0, timeout=35.0)
    answers: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    case_sources = {c["id"]: c["source"] for c in CASES}
    for case_id, request in calls:
        record: dict[str, Any] = {"case": case_id}
        try:
            response = client.responses.create(**request)
            usage = getattr(response, "usage", None)
            record["usage"] = (
                {
                    "input_tokens": getattr(usage, "input_tokens", None),
                    "output_tokens": getattr(usage, "output_tokens", None),
                }
                if usage is not None
                else None
            )
            record["status"] = getattr(response, "status", "unknown")
            if record["status"] != "completed":
                record["result"] = "incomplete"
            else:
                raw = json.loads(response.output_text)
                answers[case_id] = raw  # Retain synthetic evidence even if validation fails.
                proposal = validate_fact_candidate_proposal(case_sources[case_id], raw)
                record["result"] = "source_valid"
                record["candidate_count"] = len(proposal.candidates)
                record["kinds"] = [candidate.kind for candidate in proposal.candidates]
                record["states"] = [candidate.state for candidate in proposal.candidates]
        except Exception as exc:
            # Exceptions can contain endpoint/credential context. Record only type.
            record["result"] = "error"
            record["error_type"] = type(exc).__name__
        records.append(record)
    summary["results"] = records
    if answers:
        summary["oracle_comparison"] = compare_saved_proposals(answers)
    summary["raw_router_json"] = answers  # Synthetic source only, no personal data.
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded v2 synthetic Router gate")
    parser.add_argument("--live", action="store_true", help="Run exactly four approved calls")
    args = parser.parse_args()
    result = run_once(live=args.live)
    if args.live:
        folder = HERE / "results"
        folder.mkdir(exist_ok=True)
        name = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output = folder / f"{name}.json"
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"SYNTHETIC_ROUTER_RESULT_FILE={output}")
        # Only safe summary, never environment values or model raw source.
        for row in result["results"]:
            print(json.dumps(row, ensure_ascii=False))
        print(
            "ORACLE_MATCHES=" + str(result.get("oracle_comparison", {}).get("all_fixture_matches"))
        )
    else:
        print(json.dumps(result, indent=2))
    return (
        0
        if not args.live or all(row["result"] == "source_valid" for row in result["results"])
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
