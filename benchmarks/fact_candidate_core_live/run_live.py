"""Reviewable two-case GPT-5.6 Core plan-only gate for saved synthetic Router v3.

Offline by default. Never loads a personal vault, mutates Notes, or creates
identities. A separate, explicitly authorized cost cap is required for live.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.request_planning import RequestPlan
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_fact_candidate_planning_vertical import _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ROUTER_RESULT = ROOT / "benchmarks/fact_candidate_v2_live/results/20261010T193754Z.json"
SNAPSHOT = HERE / "reviewed_requests.json"
CASES_RUN = ("F09", "F10")
AUTHORIZED_CUMULATIVE_CAP_USD = 0.07
OLDER_ROUTER_ESTIMATED_USD = 0.0032356
RUN_ENV = "ODYSSEY_CORE_FACT_LIVE_APPROVED"


def _stable(request: dict[str, Any]) -> bytes:
    """Serialize the complete production request deterministically for audit."""
    return json.dumps(
        request, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def _context(case_id: str):
    """Use only source-validated, previously saved synthetic GPT-6 responses."""
    saved = json.loads(ROUTER_RESULT.read_text(encoding="utf-8"))
    if saved["prompt_revision"] != "v3":
        raise ValueError("Router v3 evidence missing")
    case = next(c for c in CASES if c["id"] == case_id)
    proposal = validate_fact_candidate_proposal(case["source"], saved["raw_router_json"][case_id])
    return case["source"], to_core_candidate_context(proposal)


def _recording_requests():
    """Generate exact planner requests through the real Core model adapter, offline."""
    reply = {
        "result": {
            "outcome": "ESCALATE",
            "actions": None,
            "limitations": None,
            "clarification_code": None,
        }
    }
    captured = []
    for case_id in CASES_RUN:
        source, context = _context(case_id)
        fake, calls = _sdk_fake(reply)
        OpenAILunaExperimentalPlanner(fake, SCHEMA, CLOCK, candidate_context=context).plan(source)
        if len(calls) != 1:
            raise ValueError("Core planner request count drifted")
        captured.append((case_id, source, context, calls[0]))
    return captured


def reviewed_requests():
    """Pin requests and conservative cost before allowing a real model call."""
    entries = _recording_requests()
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    if snapshot.get("cases") != list(CASES_RUN):
        raise ValueError("Reviewed Core case list has changed")
    rates = json.loads((ROOT / "config/runtime-pricing-snapshot.json").read_text(encoding="utf-8"))[
        "models"
    ]
    estimated_upper = 0.0
    for case_id, _source, _context, req in entries:
        envelope = _stable(req)
        if (
            req.get("model") != "gpt-5.6-luna"
            or req.get("reasoning") != {"effort": "low"}
            or req.get("store") is not False
            or req.get("max_output_tokens") != 2048
            or req.get("text", {}).get("format", {}).get("strict") is not True
            or req["input"][1]["content"] != _source
            or snapshot["sha256"].get(case_id) != hashlib.sha256(envelope).hexdigest()
            or snapshot["bytes"].get(case_id) != len(envelope)
        ):
            raise ValueError("Core provider request diverges from reviewed contract")
        rate = rates[req["model"]]
        # Conservative overestimate, not provider token counts or a billed price.
        bytes_count = len(json.dumps(req, ensure_ascii=False, default=str).encode())
        estimated_upper += (
            (bytes_count * 2 + 200)
            * max(rate["input_per_million"], rate.get("cache_write_per_million", 0))
            + req["max_output_tokens"] * rate["output_per_million"]
        ) / 1_000_000
    estimated_upper = round(estimated_upper, 8)
    if OLDER_ROUTER_ESTIMATED_USD + estimated_upper > AUTHORIZED_CUMULATIVE_CAP_USD:
        raise ValueError("Core gate conservative reservation exceeds proposed total cap")
    return entries, estimated_upper


def run(*, live: bool, client: Any | None = None) -> dict[str, Any]:
    """Return dry-run evidence or run two capped, source-only Core model calls."""
    entries, reservation = reviewed_requests()
    result: dict[str, Any] = {
        "mode": "LIVE_CORE_PLAN_ONLY" if live else "DRY_RUN_NO_PROVIDER",
        "cases": list(CASES_RUN),
        "model": "gpt-5.6-luna",
        "effort": "low",
        "max_calls": len(entries),
        "new_conservative_reservation_usd": reservation,
        "previous_router_estimated_spend_usd": OLDER_ROUTER_ESTIMATED_USD,
        "proposed_cumulative_cap_usd": AUTHORIZED_CUMULATIVE_CAP_USD,
        "may_authorize_writes": False,
        "core_semantics_verified": False,
    }
    if not live:
        return result
    if os.getenv(RUN_ENV) != "1":
        raise ValueError("Separate Core-provider spending authorization required")
    if client is None:
        from openai import OpenAI

        client = OpenAI(max_retries=0, timeout=45.0)
    rows = []
    for case_id, source, context, _req in entries:
        capture: dict[str, Any] = {"case": case_id}

        class RecordingResponses:
            def __init__(self, original, record):
                self.original = original
                self.record = record

            def create(self, **request):
                response = self.original.create(**request)
                self.record["raw_model_response"] = getattr(response, "output_text", None)
                usage = getattr(response, "usage", None)
                self.record["usage"] = {
                    "input_tokens": getattr(usage, "input_tokens", None),
                    "output_tokens": getattr(usage, "output_tokens", None),
                }
                self.record["provider_status"] = getattr(response, "status", None)
                return response

        planner = OpenAILunaExperimentalPlanner(
            type("Client", (), {"responses": RecordingResponses(client.responses, capture)})(),
            SCHEMA,
            CLOCK,
            candidate_context=context,
        )
        try:
            outcome = planner.plan(source)
            capture["outcome"] = (
                "PLAN"
                if isinstance(outcome, RequestPlan)
                else getattr(outcome, "outcome", type(outcome).__name__)
            )
            capture["action_count"] = (
                len(outcome.actions) if isinstance(outcome, RequestPlan) else 0
            )
            capture["compiled_plan_repr"] = (
                repr(outcome) if isinstance(outcome, RequestPlan) else None
            )
            capture["validation"] = "source_and_local_plan_valid"
        except Exception as error:
            capture["validation"] = "error"
            capture["error_type"] = type(error).__name__
            capture["error_stage"] = planner.last_validation_stage
            capture["error_code"] = planner.last_validation_code
        rows.append(capture)
    result["results"] = rows
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="F09/F10 isolated GPT-5.6 Core-only gate")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    data = run(live=args.live)
    if args.live:
        path = HERE / "results"
        path.mkdir(exist_ok=True)
        output = path / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".json")
        output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print("CORE_SYNTHETIC_RESULT_FILE=" + str(output))
        for item in data["results"]:
            print(
                json.dumps(
                    {
                        k: v
                        for k, v in item.items()
                        if k not in {"compiled_plan_repr", "raw_model_response"}
                    },
                    ensure_ascii=False,
                )
            )
    else:
        print(json.dumps(data, indent=2))
    # A locally valid ESCALATE/CLARIFY is useful evidence, not passing Core writes.
    return (
        0
        if not args.live
        or all(
            row["validation"] == "source_and_local_plan_valid" and row["outcome"] == "PLAN"
            for row in data["results"]
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
