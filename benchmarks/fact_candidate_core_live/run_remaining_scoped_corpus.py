"""Budgeted sequential batch of remaining F01..F27 with disposable canonical Notes.

Usage: python -m benchmarks.fact_candidate_core_live.run_remaining_scoped_corpus
       python -m benchmarks.fact_candidate_core_live.run_remaining_scoped_corpus --live
No background execution. Provider calls require the existing explicit
ODYSSEY_ROUTE_SCOPED_025_APPROVED gate and a fresh one-shot receipt per case.
"""

from __future__ import annotations

import argparse
import json
import os

from benchmarks.fact_candidate_core_live.run_scoped_route_live import (
    FLAG,
    MAX_USD,
    RECEIPTS,
    previous_spend,
    run_one,
)
from tests.apps.test_fact_candidates import CASES

ORDER = (
    "F10",
    "F12",
    "F16",
    "F23",
    "F25",
    "F06",
    "F11",
    "F01",
    "F02",
    "F03",
    "F04",
    "F05",
    "F07",
    "F08",
    "F14",
    "F15",
    "F17",
    "F18",
    "F19",
    "F20",
    "F21",
    "F22",
    "F24",
    "F26",
    "F27",
)
REPORT = RECEIPTS / "remaining-25-summary.txt"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    arguments = parser.parse_args()
    expected = {row["id"] for row in CASES} - {"F09", "F13"}
    if set(ORDER) != expected or len(ORDER) != len(expected):
        raise ValueError("Exactly the 25 remaining frozen cases are required")
    if arguments.live and os.environ.get(FLAG) != "1":
        raise ValueError("Live requires the explicitly authorized scoped provider gate")
    if not arguments.live:
        print(
            json.dumps(
                {
                    "mode": "offline",
                    "cases": list(ORDER),
                    "budget_remaining": round(MAX_USD - previous_spend(), 8),
                    "provider_calls": 0,
                },
                ensure_ascii=False,
            )
        )
        return

    RECEIPTS.mkdir(parents=True, exist_ok=True, mode=0o700)
    if REPORT.exists():
        raise ValueError("Remaining-25 batch was already started; avoid duplicate billing")
    REPORT.write_text(
        "Scoped Router→Temporal→Core→Writer 25-case test batch\n"
        f"Authorized cumulative cap: USD {MAX_USD}\n"
        f"Starting estimated spend: USD {previous_spend():.8f}\n",
        encoding="utf-8",
    )
    summary: list[dict] = []
    for case in ORDER:
        spent = previous_spend()
        if MAX_USD - spent < 0.004:
            print(f"STOP_BUDGET spent={spent:.8f} remaining={MAX_USD - spent:.8f}", flush=True)
            break
        receipt = RECEIPTS / f"{case}.json"
        if receipt.exists():
            # Existing successful F09/F13 are excluded above. All 25 are
            # one-shot; an existing receipt means rerun is not authorized.
            print(f"STOP_EXISTING_RECEIPT case={case}", flush=True)
            break
        print(f"CASE_START {case} spent={spent:.8f} remaining={MAX_USD - spent:.8f}", flush=True)
        try:
            outcome = run_one(case, live=True, attempt=1)
        except Exception as exc:
            print(f"STOP_UNCERTAIN {case} {type(exc).__name__}: {str(exc)[:100]}", flush=True)
            break
        summary.append(outcome)
        label = outcome.get("application_status") or outcome.get("error_category") or "unknown"
        routes = ",".join(x.get("status", "?") for x in outcome.get("route_summaries", []))
        record = (
            f"{case}\t{label}\troutes={routes}\tcalls={len(outcome['provider_calls'])}"
            f"\twritten_notes={outcome.get('written_notes', 0)}"
            f"\tspent_usd={outcome['new_estimated_usd']:.8f}"
            f"\tremaining_usd={MAX_USD - outcome['estimated_cumulative_usd']:.8f}"
        )
        print("CASE_DONE " + record, flush=True)
        with REPORT.open("a", encoding="utf-8") as handle:
            handle.write(record + "\n")
        if outcome.get("error_message", "").startswith("Provider cap reached"):
            print("STOP_PROVIDER_CAP", flush=True)
            break
    completed = {item["case"] for item in summary}
    with REPORT.open("a", encoding="utf-8") as handle:
        handle.write(
            "UNTESTED\t" + ",".join(item for item in ORDER if item not in completed) + "\n"
        )
        handle.write(f"FINAL_ESTIMATED_CUMULATIVE_USD\t{previous_spend():.8f}\n")
    print(
        f"BATCH_DONE tested={len(summary)} of 25 remaining={MAX_USD - previous_spend():.8f}",
        flush=True,
    )


if __name__ == "__main__":
    main()
