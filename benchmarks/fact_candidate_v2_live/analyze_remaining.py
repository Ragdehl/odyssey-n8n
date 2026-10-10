"""Offline-only analysis of the frozen 23 Router v3 live synthetic results.

Differentiates genuine unit-count/kind/state discrepancies from harmless
valid quote-span variants. This report does NOT certify model semantics.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from benchmarks.fact_candidate_v2_live import run_remaining
from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from tests.apps.test_fact_candidates import CASES, _from_design


def analyze() -> dict[str, Any]:
    """Review each saved result against the unmodified 27-case design oracle."""
    case_map = {item["id"]: item for item in CASES}
    recorded = run_remaining._existing_receipts()
    report = []
    for case_id in run_remaining.IDS:
        data = recorded.get(case_id)
        expected = validate_fact_candidate_proposal(
            case_map[case_id]["source"], _from_design(case_map[case_id])
        )
        item: dict[str, Any] = {
            "id": case_id,
            "source": case_map[case_id]["source"],
            "expected_count": len(expected.candidates),
            "expected_kinds": [c.kind for c in expected.candidates],
            "expected_states": [c.state for c in expected.candidates],
            "result": "not_run",
        }
        if data is None:
            report.append(item)
            continue
        item["provider_status"] = data.get("provider_status")
        item["source_validation"] = data.get("validation")
        item["usage"] = data.get("usage")
        if data.get("validation") != "source_valid":
            item["result"] = "invalid_output"
            report.append(item)
            continue
        actual = validate_fact_candidate_proposal(
            case_map[case_id]["source"], json.loads(data["raw_model_response"])
        )
        kinds = [c.kind for c in actual.candidates]
        states = [c.state for c in actual.candidates]
        item.update(
            {
                "count": len(actual.candidates),
                "kinds": kinds,
                "states": states,
                "candidates": [
                    {
                        "kind": c.kind,
                        "state": c.state,
                        "anchors": [a.text for a in c.anchors],
                        "roles": [(r.role, r.anchor.text) for r in c.scopes],
                        "inherits": [(i.role, i.from_unit) for i in c.inheritance],
                    }
                    for c in actual.candidates
                ],
            }
        )
        differences = []
        if len(actual.candidates) != len(expected.candidates):
            differences.append("count")
        for i, (found, oracle) in enumerate(
            zip(actual.candidates, expected.candidates, strict=False), start=1
        ):
            if found.kind != oracle.kind:
                differences.append(f"{i}:kind")
            if found.state != oracle.state:
                differences.append(f"{i}:state")
            got_roles = {(r.role, r.anchor.text) for r in found.scopes}
            want_roles = {(r.role, r.anchor.text) for r in oracle.scopes}
            for role, _text in sorted(want_roles - got_roles):
                differences.append(f"{i}:missing_{role}")
            for role, _text in sorted(got_roles - want_roles):
                differences.append(f"{i}:extra_{role}")
            expected_inherits = {(e.role, e.from_unit) for e in oracle.inheritance}
            got_inherits = {(e.role, e.from_unit) for e in found.inheritance}
            if expected_inherits != got_inherits:
                differences.append(f"{i}:inheritance")
            if {a.text for a in oracle.anchors} != {a.text for a in found.anchors}:
                differences.append(f"{i}:quote_variation")
        item["differences"] = differences
        if "count" in differences or any(x.endswith((":kind", ":state")) for x in differences):
            item["result"] = "material_structure_mismatch"
        elif differences:
            item["result"] = "role_or_quote_review"
        else:
            item["result"] = "matches_reference"
        report.append(item)
    from collections import Counter

    summary = Counter(row["result"] for row in report)
    price = run_remaining._rates()
    cost = sum(
        (
            item["usage"]["input_tokens"] * price["input_per_million"]
            + item["usage"]["output_tokens"] * price["output_per_million"]
        )
        / 1_000_000
        for item in report
        if item.get("usage")
    )
    return {
        "mode": "FROZEN_REAL_OUTPUTS_OFFLINE_ONLY",
        "model": run_remaining.MODEL,
        "prompt_revision": "v3",
        "total": len(report),
        "completed": len(recorded),
        "classification_counts": dict(summary),
        "estimated_new_usd": round(cost, 9),
        "estimated_cumulative_usd": round(run_remaining.OBSERVED_PRIOR_USD + cost, 9),
        "authorized_total_usd": run_remaining.BUDGET_USD,
        "semantic_human_review_required": True,
        "core_plans_verified": False,
        "items": report,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = analyze()
    if args.output:
        args.output.parent.mkdir(exist_ok=True, parents=True)
        args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"OFFLINE_ANALYSIS={args.output}")
    print(
        json.dumps(
            {key: value for key, value in data.items() if key != "items"},
            ensure_ascii=False,
            indent=2,
        )
    )
    for row in data["items"]:
        print(
            row["id"],
            row["result"],
            "count",
            row.get("count"),
            "/",
            row["expected_count"],
            "types",
            row.get("kinds"),
            "differences",
            ",".join(row.get("differences", [])),
        )


if __name__ == "__main__":
    main()
