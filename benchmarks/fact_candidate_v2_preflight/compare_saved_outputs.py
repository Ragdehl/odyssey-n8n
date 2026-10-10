"""Offline triage of saved Router v1 candidate JSON against reviewed v2 fixtures.

No provider client, credential, runtime, network or canonical-write access exists
in this module. Exact fixture matches are NOT proof of semantic model quality.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from odyssey_apps.router import RouterError

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "benchmarks/application_router/fact_units_v2.design.json"
FOCUSED_IDS = frozenset({"F09", "F10", "F14", "F27"})
MAX_INPUT_BYTES = 128_000


def _oracle_payload(case: dict[str, Any]) -> dict[str, Any]:
    """Convert the immutable design's source roles to the exact adapter shape."""
    return {
        "version": 1,
        "units": [
            {
                "kind": unit["kind"],
                "state": unit["state"],
                "anchors": [{"text": text, "occurrence": 0} for text in unit["source_anchors"]],
                "scoped_source": [
                    {"role": item["role"], "anchor": {"text": item["text"], "occurrence": 0}}
                    for item in unit["scoped_source"]
                ],
                "inheritance": unit["inheritance"],
            }
            for unit in case["expected_units"]
        ],
    }


def _signature(item: Any) -> dict[str, Any]:
    """Render non-authoritative source evidence for strict fixture comparison."""
    return {
        "kind": item.kind,
        "state": item.state,
        "anchors": sorted((a.text, a.occurrence) for a in item.anchors),
        "scopes": sorted((s.role, s.anchor.text, s.anchor.occurrence) for s in item.scopes),
        "inheritance": sorted((e.role, e.from_unit) for e in item.inheritance),
    }


def compare_saved_proposals(responses: dict[str, Any]) -> dict[str, Any]:
    """Triage a bounded map of saved synthetic model outputs without invoking a model.

    Args:
        responses: Map of approved case ID to one untrusted Router output JSON.

    Returns:
        Read-only mismatch diagnostics. Even exact fixture matches require an
        independent human semantic review before acceptance.
    """
    if not isinstance(responses, dict) or not responses or set(responses) - FOCUSED_IDS:
        raise ValueError("Only nonempty subsets of F09/F10/F14/F27 are permitted")
    cases = {case["id"]: case for case in json.loads(MATRIX.read_text())["cases"]}
    results = {}
    for case_id in sorted(responses):
        case = cases[case_id]
        try:
            actual = validate_fact_candidate_proposal(case["source"], responses[case_id])
            oracle = validate_fact_candidate_proposal(case["source"], _oracle_payload(case))
        except (RouterError, TypeError, ValueError, KeyError) as error:
            # Return its type, never source text or untrusted provider output.
            results[case_id] = {
                "fixture_match": False,
                "differences": ["invalid_output"],
                "error_type": type(error).__name__,
            }
            continue
        differences = []
        if len(actual.candidates) != len(oracle.candidates):
            differences.append("candidate_count")
        for index, (got, expected) in enumerate(
            zip(actual.candidates, oracle.candidates, strict=False), start=1
        ):
            a, b = _signature(got), _signature(expected)
            for field in ("kind", "state", "anchors", "scopes", "inheritance"):
                if a[field] != b[field]:
                    differences.append(f"candidate_{index}_{field}")
        results[case_id] = {"fixture_match": not differences, "differences": differences}
    return {
        "mode": "OFFLINE_SAVED_RESULTS_ONLY",
        "cases": results,
        "all_fixture_matches": all(result["fixture_match"] for result in results.values()),
        "human_semantic_review_required": True,
        "live_model_quality_verified": False,
    }


def main() -> int:
    """Read at most 128 KiB of local JSON and print non-executable diagnostics."""
    parser = argparse.ArgumentParser(description="Offline review of saved synthetic Router outputs")
    parser.add_argument(
        "saved_results", type=Path, help="JSON map of case IDs to model output objects"
    )
    args = parser.parse_args()
    if args.saved_results.stat().st_size > MAX_INPUT_BYTES:
        parser.error("Saved results exceed the input size limit")
    try:
        payload = json.loads(args.saved_results.read_text(encoding="utf-8"))
        report = compare_saved_proposals(payload)
    except (OSError, ValueError, TypeError) as error:
        parser.error(f"Invalid saved results: {type(error).__name__}")
    print(json.dumps(report, indent=2))
    return 0 if report["all_fixture_matches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
