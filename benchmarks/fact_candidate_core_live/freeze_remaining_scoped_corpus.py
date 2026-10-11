"""Freeze all completed scoped-provider trials as source-bound offline regressions.

Never invent missing model responses, never persist tokens, bearer secrets,
real Notes, or live credentials. Only the user-approved 27 synthetic messages
and provider's structured non-streaming outputs are accepted.
"""

from __future__ import annotations

import argparse
import hashlib
import json

from benchmarks.fact_candidate_core_live.run_remaining_scoped_corpus import ORDER
from benchmarks.fact_candidate_core_live.run_scoped_route_live import (
    RECEIPTS,
    ROOT,
)
from tests.apps.test_fact_candidates import CASES

FROZEN = ROOT / "benchmarks/application_router/scoped_routing_v1"


def freeze_remaining() -> dict:
    FROZEN.mkdir(parents=True, exist_ok=True)
    case_sources = {item["id"]: item["source"] for item in CASES}
    frozen = []
    missing = []
    for case_id in ORDER:
        receipt_path = RECEIPTS / f"{case_id}.json"
        if not receipt_path.exists():
            missing.append(case_id)
            continue
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("case") != case_id or receipt.get("status") != "finished":
            raise ValueError(f"Unsettled or mismatched provider trial for {case_id}")
        replies = receipt.get("provider_outputs")
        if not isinstance(replies, list) or not replies:
            raise ValueError(f"Missing real provider replies for {case_id}")
        for reply in replies:
            if (
                not isinstance(reply, dict)
                or set(reply) != {"model", "status", "output_text"}
                or not isinstance(reply["output_text"], str)
            ):
                raise ValueError(f"Incomplete or nonreplayable provider output for {case_id}")
            # Preserve malformed provider replies for faithful failure replay.
        item = {
            "version": 1,
            "case_id": case_id,
            "original_source_sha256": hashlib.sha256(
                case_sources[case_id].encode("utf-8")
            ).hexdigest(),
            "captured_application_status": receipt.get("application_status"),
            "route_summaries": receipt.get("route_summaries", []),
            "written_notes": receipt.get("written_notes", 0),
            "error_category": receipt.get("error_category"),
            "responses": replies,
        }
        dest = FROZEN / f"{case_id}.json"
        payload = json.dumps(item, ensure_ascii=False, indent=2) + "\n"
        if dest.exists():
            if dest.read_text(encoding="utf-8") != payload:
                raise ValueError(f"Previously frozen capture has changed for {case_id}")
        else:
            dest.write_text(payload, encoding="utf-8")
        frozen.append(case_id)
    return {"frozen": frozen, "not_tested_live": missing}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    if not args.freeze:
        print(
            json.dumps(
                {"would_freeze": len([x for x in ORDER if (RECEIPTS / f"{x}.json").exists()])}
            )
        )
        return
    print(json.dumps(freeze_remaining(), ensure_ascii=False))


if __name__ == "__main__":
    main()
