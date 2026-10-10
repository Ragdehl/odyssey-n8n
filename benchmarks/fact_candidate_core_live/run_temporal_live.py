"""Reviewed staged F14/F27 Core live diagnostic; no vault or write access.

Each run permits exactly ONE GPT-5.6 Luna/low call. The second call can run
only after the first result is saved, charged against its actual token use,
and the conservative remaining upper bound fits the authorized $0.07 total.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any

from benchmarks.fact_candidate_core_live.run_live import (
    AUTHORIZED_CUMULATIVE_CAP_USD,
    HERE,
    ROOT,
    RUN_ENV,
    _context,
    _stable,
)
from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from odyssey_apps.fact_temporal import bind_temporal_to_fact_candidates
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.request_planning import RequestPlan
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from tests.runtime.test_fact_candidate_planning_vertical import _exact_date, _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA

SNAPSHOT = HERE / "reviewed_temporal_requests.json"
PARTIAL_SNAPSHOT = HERE / "reviewed_temporal_partial_requests.json"
RESULTS = HERE / "results"
BASELINE_ROUTER_AND_CORE_ESTIMATE_USD = 0.0082176
FIRST_CASE = "F14"
SECOND_CASE = "F27"


def temporal_evidence(source: str):
    """Prepare fixed synthetic date interpretations, no provider date call."""
    fake, requests = _sdk_fake(
        {"mentions": [_exact_date("Ayer", "2026-10-03"), _exact_date("Mañana", "2026-10-05")]}
    )
    interpreted = OpenAITemporalInterpreter(fake, CLOCK).interpret(source)
    if len(requests) != 1:
        raise ValueError("Unexpected Temporal request count")
    return interpreted


def reviewed_case(case_id: str, *, partial_guidance: bool = False):
    """Recover a hash-pinned, production-generated Core call for one synthetic case."""
    if case_id not in {FIRST_CASE, SECOND_CASE}:
        raise ValueError("Only F14/F27 are approved")
    source, context = _context(case_id)
    temporal = temporal_evidence(source)
    router_raw = json.loads(
        (ROOT / "benchmarks/fact_candidate_v2_live/results/20261010T193754Z.json").read_text()
    )
    proposal = validate_fact_candidate_proposal(source, router_raw["raw_router_json"][case_id])
    bindings = bind_temporal_to_fact_candidates(proposal, temporal)
    expected = 2 if case_id == FIRST_CASE else 3
    if len(bindings) != expected or any(
        e.role != "date" or e.resolution is None or e.resolution.exact_date is None
        for e in bindings
    ):
        raise ValueError("Temporal evidence did not cover all Router date scopes")
    fake, calls = _sdk_fake(
        {
            "result": {
                "outcome": "ESCALATE",
                "actions": None,
                "limitations": None,
                "clarification_code": None,
            }
        }
    )
    OpenAILunaExperimentalPlanner(
        fake,
        SCHEMA,
        CLOCK,
        domain_interpretation=temporal.core_domain_interpretation(),
        candidate_context=context,
        partial_candidate_guidance=partial_guidance,
    ).plan(source)
    if len(calls) != 1:
        raise ValueError("Core planner request drift")
    request = calls[0]
    snapshot = PARTIAL_SNAPSHOT if partial_guidance else SNAPSHOT
    frozen = json.loads(snapshot.read_text(encoding="utf-8"))
    encoded = _stable(request)
    if (
        frozen.get("cases") != [FIRST_CASE, SECOND_CASE]
        or frozen["sha256"].get(case_id) != hashlib.sha256(encoded).hexdigest()
        or frozen["bytes"].get(case_id) != len(encoded)
        or request.get("model") != "gpt-5.6-luna"
        or request.get("reasoning") != {"effort": "low"}
        or request.get("store") is not False
        or request.get("max_output_tokens") != 2048
        or request.get("text", {}).get("format", {}).get("strict") is not True
        or request["input"][1]["content"] != source
    ):
        raise ValueError("Revised request differs from reviewed Core/Temporal contract")
    rate = json.loads((ROOT / "config/runtime-pricing-snapshot.json").read_text())["models"][
        "gpt-5.6-luna"
    ]
    request_bytes = len(json.dumps(request, ensure_ascii=False, default=str).encode())
    upper = (
        (request_bytes * 2 + 200)
        * max(rate["input_per_million"], rate.get("cache_write_per_million", 0))
        + request["max_output_tokens"] * rate["output_per_million"]
    ) / 1_000_000
    return source, context, temporal, request, round(upper, 8)


def _observed_first_cost(*, partial_guidance: bool = False) -> float:
    """Verify exactly one saved real F14 result before charging its token usage."""
    evidence = sorted(RESULTS.glob("*-P-F14.json" if partial_guidance else "*-F14.json"))
    if len(evidence) != 1:
        raise ValueError("Exactly one saved F14 live receipt required before F27")
    data = json.loads(evidence[0].read_text(encoding="utf-8"))
    if data.get("case") != FIRST_CASE or data.get("mode") != "LIVE_CORE_PLAN_ONLY":
        raise ValueError("First live run identity mismatch")
    usage = data.get("usage")
    if not isinstance(usage, dict) or any(
        not isinstance(usage.get(field), int) or usage[field] < 0
        for field in ("input_tokens", "output_tokens")
    ):
        raise ValueError("First live run has no validated usage record")
    # The provider's reported usage is less than or equal to real cost at the
    # pinned noncached standard rates (any cached input is cheaper).
    rates = json.loads((ROOT / "config/runtime-pricing-snapshot.json").read_text())["models"][
        "gpt-5.6-luna"
    ]
    return (
        usage["input_tokens"] * rates["input_per_million"]
        + usage["output_tokens"] * rates["output_per_million"]
    ) / 1_000_000


def _observed_case_cost(case_id: str) -> float:
    """Count exactly one frozen original Core result at full standard rates."""
    if case_id not in {FIRST_CASE, SECOND_CASE}:
        raise ValueError("Unrecognized historical Core case")
    files = list(RESULTS.glob(f"*-{case_id}.json"))
    if len(files) != 1:
        raise ValueError("Expected one original Core provider receipt")
    data = json.loads(files[0].read_text(encoding="utf-8"))
    usage = data.get("usage")
    if (
        data.get("case") != case_id
        or data.get("mode") != "LIVE_CORE_PLAN_ONLY"
        or not isinstance(usage, dict)
        or any(
            not isinstance(usage.get(key), int) or usage[key] < 0
            for key in ("input_tokens", "output_tokens")
        )
    ):
        raise ValueError("Historical Core receipt is not trustworthy")
    rates = json.loads((ROOT / "config/runtime-pricing-snapshot.json").read_text())["models"][
        "gpt-5.6-luna"
    ]
    return (
        usage["input_tokens"] * rates["input_per_million"]
        + usage["output_tokens"] * rates["output_per_million"]
    ) / 1_000_000


def preflight(case_id: str, *, partial_guidance: bool = False):
    """Fail closed before provider access when the stage cannot fit total budget."""
    source, context, temporal, request, upper = reviewed_case(
        case_id, partial_guidance=partial_guidance
    )
    previous = BASELINE_ROUTER_AND_CORE_ESTIMATE_USD
    if partial_guidance:
        # Count the original F14/F27 provider runs at their observed standard
        # noncached rates before reserving a fresh reviewed prompt revision.
        previous += _observed_first_cost()
        previous += _observed_case_cost("F27")
    if case_id == SECOND_CASE:
        previous += _observed_first_cost(partial_guidance=partial_guidance)
    if previous + upper > AUTHORIZED_CUMULATIVE_CAP_USD:
        raise ValueError("Case exceeds previously approved cumulative ceiling")
    return source, context, temporal, request, upper, round(previous, 8)


def run_case(
    case_id: str,
    *,
    live: bool,
    client: Any | None = None,
    partial_guidance: bool = False,
) -> dict[str, Any]:
    """Run at most one source-only model request; never execute its WriteAction."""
    source, context, temporal, _request, upper, previous = preflight(
        case_id, partial_guidance=partial_guidance
    )
    result: dict[str, Any] = {
        "mode": "LIVE_CORE_PLAN_ONLY" if live else "DRY_RUN_NO_PROVIDER",
        "case": case_id,
        "model": "gpt-5.6-luna",
        "single_call_only": True,
        "conservative_call_reservation_usd": upper,
        "previous_test_estimated_usd": previous,
        "authorized_cumulative_cap_usd": AUTHORIZED_CUMULATIVE_CAP_USD,
        "may_authorize_writes": False,
        "model_semantics_verified": False,
        "prompt_revision": "opt_in_scoped_partial" if partial_guidance else "original",
    }
    if not live:
        return result
    if os.getenv(RUN_ENV) != "1":
        raise ValueError("Explicit Core live approval flag required")
    if partial_guidance and list(RESULTS.glob(f"*-P-{case_id}.json")):
        raise ValueError("This partial Core case has already consumed a live call")
    if client is None:
        from openai import OpenAI

        client = OpenAI(max_retries=0, timeout=50.0)
    captured: dict[str, Any] = {}

    class Recorder:
        def __init__(self, responses):
            self.responses = responses

        def create(self, **payload):
            reply = self.responses.create(**payload)
            usage = getattr(reply, "usage", None)
            captured["usage"] = {
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            }
            captured["provider_status"] = getattr(reply, "status", None)
            captured["raw_model_response"] = getattr(reply, "output_text", None)
            return reply

    planner = OpenAILunaExperimentalPlanner(
        type("WrappedClient", (), {"responses": Recorder(client.responses)})(),
        SCHEMA,
        CLOCK,
        domain_interpretation=temporal.core_domain_interpretation(),
        candidate_context=context,
        partial_candidate_guidance=partial_guidance,
    )
    try:
        compiled = planner.plan(source)
        captured["outcome"] = (
            "PLAN"
            if isinstance(compiled, RequestPlan)
            else getattr(compiled, "outcome", type(compiled).__name__)
        )
        captured["plan_repr"] = repr(compiled) if isinstance(compiled, RequestPlan) else None
        captured["action_count"] = len(compiled.actions) if isinstance(compiled, RequestPlan) else 0
        captured["validation"] = "locally_valid"
    except Exception as error:
        captured["validation"] = "error"
        captured["error_type"] = type(error).__name__
        captured["error_stage"] = planner.last_validation_stage
        captured["error_code"] = planner.last_validation_code
    result.update(captured)
    return result


def main():
    """Parse one case, persist its synthetic receipt, and report safe summaries."""
    parser = argparse.ArgumentParser(description="Staged, bounded F14/F27 Core model test")
    parser.add_argument("--case", required=True, choices=[FIRST_CASE, SECOND_CASE])
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--partial",
        action="store_true",
        help="Use explicitly reviewed scoped partial-plan guidance",
    )
    args = parser.parse_args()
    result = run_case(args.case, live=args.live, partial_guidance=args.partial)
    if args.live:
        RESULTS.mkdir(exist_ok=True)
        target = RESULTS / (
            datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            + (f"-P-{args.case}.json" if args.partial else f"-{args.case}.json")
        )
        target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print("SYNTHETIC_CORE_RESULT_FILE=" + str(target))
        print(
            json.dumps(
                {k: v for k, v in result.items() if k not in {"raw_model_response", "plan_repr"}},
                ensure_ascii=False,
            )
        )
    else:
        print(json.dumps(result, indent=2))
    return (
        0
        if not args.live
        or (result.get("validation") == "locally_valid" and result.get("outcome") == "PLAN")
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
