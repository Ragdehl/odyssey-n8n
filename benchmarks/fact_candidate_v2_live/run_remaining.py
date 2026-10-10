"""Frozen, staged 23-case real GPT-6 Router gate (no notes, no Core writes).

Exactly one provider call per untouched synthetic design case. Offline is
always the default. Actual token-cost receipts from each completed stage
are charged before reserving the NEXT call's entire conservative envelope.
No automatic SDK retries and no case retries after any saved response.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.fact_candidate_core_live.run_scoped_live import (
    _receipt_cost,
)
from benchmarks.fact_candidate_v2_live.run_live import HERE, ROOT
from odyssey_apps.fact_candidates import (
    OpenAIFactCandidateRouter,
    validate_fact_candidate_proposal,
)
from tests.apps.test_fact_candidates import CASES, _from_design
from tests.runtime.test_fact_candidate_planning_vertical import _sdk_fake

PIN = HERE / "reviewed_remaining_requests.json"
RESULTS = HERE / "remaining_results"
FULL_REVIEWED_IDS = tuple(case["id"] for case in CASES)
FOCUSED_IDS = frozenset({"F09", "F10", "F14", "F27"})
IDS = tuple(case_id for case_id in FULL_REVIEWED_IDS if case_id not in FOCUSED_IDS)
AUTHORIZATION_ENV = "ODYSSEY_ROUTER_V2_LIVE_APPROVED"
MODEL = "gpt-6-luna"
BUDGET_USD = 0.07
OBSERVED_PRIOR_USD = 0.0259652  # Frozen FULL Router+Core scoped run total.
MAX_RESPONSES = len(IDS)


def frozen_request(case_id: str) -> dict[str, Any]:
    """Capture the one authentic Router v3 request without provider/network."""
    if case_id not in IDS:
        raise ValueError("Not one of the 23 remaining accepted design cases")
    case = next(case for case in CASES if case["id"] == case_id)
    fake, calls = _sdk_fake(_from_design(case))
    OpenAIFactCandidateRouter(fake, prompt_revision="v3").propose(case["source"])
    if len(calls) != 1:
        raise ValueError("Exactly one Router request expected")
    return calls[0]


def checked_request(case_id: str) -> dict[str, Any]:
    """Require reviewed SHA-256 pins and established model/security fields."""
    request = frozen_request(case_id)
    freeze = json.loads(PIN.read_text(encoding="utf-8"))
    encoded = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    if (
        freeze.get("case_ids") != list(IDS)
        or freeze["sha256"].get(case_id) != hashlib.sha256(encoded).hexdigest()
        or freeze["bytes"].get(case_id) != len(encoded)
        or request.get("model") != MODEL
        or request.get("reasoning") != {"effort": "low"}
        or request.get("store") is not False
        or request.get("max_output_tokens") != 4096
        or request.get("text", {}).get("format", {}).get("strict") is not True
        or len(request.get("input", [])) != 2
        or request["input"][1]["content"]
        != next(case["source"] for case in CASES if case["id"] == case_id)
    ):
        raise ValueError("Unreviewed Router model request or schema drift")
    return request


def _rates() -> dict[str, Any]:
    return json.loads((ROOT / "config/runtime-pricing-snapshot.json").read_text(encoding="utf-8"))[
        "models"
    ][MODEL]


def _existing_receipts() -> dict[str, dict[str, Any]]:
    """Refuse gaps, duplicates, or unrelated data before any paid call."""
    receipts: dict[str, dict[str, Any]] = {}
    if not RESULTS.exists():
        return receipts
    for path in RESULTS.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        cid = data.get("case")
        if (
            cid not in IDS
            or cid in receipts
            or data.get("mode") != "SYNTHETIC_ROUTER_V3_REMAINING"
            or data.get("model") != MODEL
            or data.get("provider_status") not in {"completed", "incomplete", "unknown"}
            or not path.name.endswith(f"--{cid}.json")
        ):
            raise ValueError("Unexpected, duplicate, or invalid saved Router receipt")
        receipts[cid] = data
    if set(receipts) != set(IDS[: len(receipts)]):
        raise ValueError("Previously attempted Router cases are not a contiguous prefix")
    if any(data.get("provider_status") != "completed" for data in receipts.values()):
        raise ValueError("A failed or incomplete provider call requires review, no retry")
    return receipts


def preflight(case_id: str) -> tuple[dict[str, Any], float, float]:
    """Reserve next call ONLY after all preceding receipts are charged."""
    request = checked_request(case_id)
    recorded = _existing_receipts()
    if case_id in recorded:
        raise ValueError("This synthetic Router case already called provider; no retry")
    if len(recorded) == len(IDS):
        raise ValueError("All 23 model calls already recorded")
    if case_id != IDS[len(recorded)]:
        raise ValueError("Must execute Router cases in the accepted staged order")
    price = _rates()
    previous = OBSERVED_PRIOR_USD + sum(_receipt_cost(x, price) for x in recorded.values())
    request_bytes = len(json.dumps(request, ensure_ascii=False, default=str).encode("utf-8"))
    maximum = (
        (2 * request_bytes + 200)
        * max(price["input_per_million"], price.get("cache_write_per_million", 0))
        + request["max_output_tokens"] * price["output_per_million"]
    ) / 1_000_000
    if previous + maximum > BUDGET_USD:
        raise ValueError("Previously approved cumulative USD 0.07 would be exceeded")
    return request, round(maximum, 8), round(previous, 8)


def run_case(
    case_id: str,
    *,
    live: bool = False,
    client: Any | None = None,
) -> dict[str, Any]:
    """Make one single source-only provider request and save factual evidence."""
    request, maximum, previous = preflight(case_id)
    record: dict[str, Any] = {
        "case": case_id,
        "model": MODEL,
        "mode": "SYNTHETIC_ROUTER_V3_REMAINING" if live else "OFFLINE_REVIEW_ONLY",
        "maximum_reserved_usd": maximum,
        "estimated_prior_usd": previous,
        "budget_ceiling_usd": BUDGET_USD,
        "may_write_notes": False,
        "core_acceptance_verified": False,
    }
    if not live:
        return record
    if os.getenv(AUTHORIZATION_ENV) != "1":
        raise ValueError("Explicitly reviewed Router live approval flag required")
    if client is None:
        from openai import OpenAI

        client = OpenAI(max_retries=0, timeout=50.0)
    try:
        reply = client.responses.create(**request)
    except Exception as error:
        # Even an uncertain billable failed attempt must be saved and blocked
        # from retry, rather than silently paid twice.
        record["provider_status"] = "unknown"
        record["validation"] = "provider_exception"
        record["error_type"] = type(error).__name__
        record["usage"] = None
        return record
    usage = getattr(reply, "usage", None)
    record["provider_status"] = getattr(reply, "status", "unknown")
    record["usage"] = {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
    }
    record["raw_model_response"] = getattr(reply, "output_text", None)
    if record["provider_status"] == "completed":
        try:
            parsed = json.loads(record["raw_model_response"])
            original = next(case["source"] for case in CASES if case["id"] == case_id)
            proposal = validate_fact_candidate_proposal(original, parsed)
            record["validation"] = "source_valid"
            record["candidate_count"] = len(proposal.candidates)
            record["kinds"] = [c.kind for c in proposal.candidates]
            record["states"] = [c.state for c in proposal.candidates]
        except Exception as exc:
            record["validation"] = "source_rejected"
            record["validation_error_type"] = type(exc).__name__
    else:
        record["validation"] = "not_completed"
    return record


def save_record(record: dict[str, Any]) -> Path:
    """Keep each attempted provider result on disk before proceeding."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    cid = record["case"]
    if list(RESULTS.glob(f"*--{cid}.json")):
        raise ValueError("Existing receipt prevents duplicate synthetic provider result")
    path = RESULTS / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + f"--{cid}.json")
    with path.open("x", encoding="utf-8") as out:
        json.dump(record, out, ensure_ascii=False, indent=2)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="23 original synthetic GPT-6 Router cases")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--one", choices=IDS, help="One particular next case, never skip")
    args = parser.parse_args()
    if args.live and os.getenv(AUTHORIZATION_ENV) != "1":
        raise ValueError("Explicitly reviewed Router live approval flag required")
    requested = (args.one,) if args.one else IDS
    for cid in requested:
        if cid in _existing_receipts():
            if args.one:
                raise ValueError("Already attempted; no retry")
            continue
        record = run_case(cid, live=args.live)
        if args.live:
            path = save_record(record)
            print(
                "SCOPED_ROUTER_RECEIPT=" + path.name,
                "status=" + record.get("provider_status", "unknown"),
                "validation=" + record["validation"],
                "units=" + str(record.get("candidate_count")),
                flush=True,
            )
            if record["provider_status"] != "completed":
                return 1
        else:
            print(
                f"REVIEW {cid} reserved={record['maximum_reserved_usd']} "
                f"previous={record['estimated_prior_usd']}",
                flush=True,
            )
            # Dry-run only previews the next eligible case.
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
