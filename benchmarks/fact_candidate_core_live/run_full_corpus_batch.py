"""Batch the approved 27-case isolated live corpus without rerunning paid receipts.

All provider requests use the single already-authorized cumulative USD 0.25
ceiling, the same four existing adapters, and disposable canonical Notes.
"""

from __future__ import annotations

import argparse
import json

from benchmarks.fact_candidate_core_live.run_full_message_corpus_live import (
    RESULTS,
    case_ids,
    previous_spend,
    run,
)


def main() -> None:
    """Emit one concise durable progress result per case and stop on budget errors."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--count", type=int, default=27)
    args = parser.parse_args()
    cases = case_ids()
    if args.start < 1 or args.count < 1 or args.start + args.count - 1 > len(cases):
        raise ValueError("Batch range must be within the approved 27-case corpus")
    for cid in cases[args.start - 1 : args.start - 1 + args.count]:
        if (RESULTS / f"{cid}.json").exists():
            print(json.dumps({"case": cid, "status": "existing_receipt_no_retry"}), flush=True)
            continue
        try:
            result = run(cid, live=True)
        except Exception as error:
            print(
                json.dumps(
                    {
                        "case": cid,
                        "status": "batch_stopped_before_provider",
                        "category": type(error).__name__,
                        "reason": str(error)[:180],
                        "estimated_cumulative_usd": round(previous_spend(), 8),
                    }
                ),
                flush=True,
            )
            break
        print(
            json.dumps(
                {
                    "case": cid,
                    "outcome": result["outcome"],
                    "application_status": result.get("application_status"),
                    "clarification_code": result.get("clarification_code"),
                    "error_type": result.get("error_type"),
                    "planning_error": result.get("planning_error"),
                    "stages": result.get("operational_stages"),
                    "model_calls": len(result["provider_calls"]),
                    "written_notes": result["written_notes"],
                    "core_facts_verified": result["core_facts_verified"],
                    "estimated_cumulative_usd": result["estimated_total_usd"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
