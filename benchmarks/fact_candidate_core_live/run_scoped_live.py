"""Bounded ONE-UNIT real GPT-5.6 Core planning gate, no Note writes.

The inherited Core planner receives one separately derived source fact.
The immutable original and full candidate provenance are audited offline.
No Core action is executed and no app/routing configuration is changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any

from benchmarks.fact_candidate_core_live import run_temporal_live as older
from benchmarks.fact_candidate_core_live.run_live import (
    AUTHORIZED_CUMULATIVE_CAP_USD,
    HERE,
    ROOT,
    RUN_ENV,
    _context,
    _stable,
)
from odyssey_core.candidate_scoped_handoff import preview_independent_candidate_scopes
from odyssey_core.domain_interpretation import (
    TEMPORAL_REFERENCE_EVIDENCE,
    DomainEvidence,
    DomainInterpretation,
)
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.request_planning import RequestPlan
from tests.runtime.test_fact_candidate_planning_vertical import _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA

STAGES = (("F14", "candidate-1"), ("F27", "candidate-1"), ("F27", "candidate-2"))
PIN = HERE / "reviewed_scoped_requests.json"
RESULTS = HERE / "results"
HISTORIC = (
    "20261010T202736Z-F14.json",
    "20261010T202803Z-F27.json",
    "20261010T203404Z-P-F14.json",
    "20261010T203640Z-P-F27.json",
)
BASELINE_ESTIMATE_USD = 0.0082176


def _receipt_cost(saved: dict[str, Any], rate: dict[str, float]) -> float:
    usage = saved.get("usage")
    if not isinstance(usage, dict) or any(
        not isinstance(usage.get(k), int) or isinstance(usage[k], bool) or usage[k] < 0
        for k in ("input_tokens", "output_tokens")
    ):
        raise ValueError("No trustworthy provider usage receipt")
    return (
        usage["input_tokens"] * rate["input_per_million"]
        + usage["output_tokens"] * rate["output_per_million"]
    ) / 1_000_000


def _stage_input(case_id: str, unit_id: str):
    if (case_id, unit_id) not in STAGES:
        raise ValueError("Scoped Core gate only permits three approved synthetic units")
    source, context = _context(case_id)
    original_temporal = older.temporal_evidence(source).core_domain_interpretation()
    preview = preview_independent_candidate_scopes(source, context)
    if original_temporal.source_text != source:
        raise ValueError("Trusted Temporal does not match original request")
    dates = original_temporal.temporal_references()
    past = [d for d in dates if d.source_text == "Ayer"]
    future = [d for d in dates if d.source_text == "Mañana"]
    if len(dates) != 2 or len(past) != 1 or len(future) != 1:
        raise ValueError("Missing Core original Temporal evidence")
    unit = next((u for u in preview.units if u.candidate_id == unit_id), None)
    if unit is None or not unit.date_evidence or unit.date_evidence[0].text != "Ayer":
        raise ValueError("Selected unit has no original Temporal scope")
    request = unit.scoped_request()
    domain = DomainInterpretation(
        "temporal",
        request,
        "TEMPORAL_RESOLUTION",
        (DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, "Ayer", past[0].value),),
    )
    return source, context, unit, domain, request


def _request(case_id: str, unit_id: str):
    source, context, unit, domain, task = _stage_input(case_id, unit_id)
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
    OpenAILunaExperimentalPlanner(fake, SCHEMA, CLOCK, domain_interpretation=domain).plan(task)
    if len(calls) != 1:
        raise ValueError("Core attempted extra provider requests")
    return unit, domain, task, calls[0]


def _reviewed(case_id: str, unit_id: str):
    unit, domain, task, req = _request(case_id, unit_id)
    freeze = json.loads(PIN.read_text(encoding="utf-8"))
    name = case_id + "/" + unit_id
    payload = _stable(req)
    if (
        freeze.get("stages") != [list(stage) for stage in STAGES]
        or freeze["sha256"].get(name) != hashlib.sha256(payload).hexdigest()
        or freeze["bytes"].get(name) != len(payload)
        or req.get("model") != "gpt-5.6-luna"
        or req.get("reasoning") != {"effort": "low"}
        or req.get("store") is not False
        or req.get("max_output_tokens") != 2048
        or req.get("text", {}).get("format", {}).get("strict") is not True
        or req["input"][1]["content"] != task
    ):
        raise ValueError("Core single-fact request differs from reviewed immutable input")
    return unit, domain, task, req


def _charged_previous(stage: tuple[str, str]) -> float:
    rates = json.loads((ROOT / "config/runtime-pricing-snapshot.json").read_text(encoding="utf-8"))[
        "models"
    ]["gpt-5.6-luna"]
    total = BASELINE_ESTIMATE_USD
    for name in HISTORIC:
        path = RESULTS / name
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if (
            receipt.get("mode") != "LIVE_CORE_PLAN_ONLY"
            or receipt.get("provider_status") != "completed"
        ):
            raise ValueError("Historical Core receipt is not a completed provider result")
        total += _receipt_cost(receipt, rates)
    position = STAGES.index(stage)
    for earlier_case, earlier_unit in STAGES[:position]:
        filename = f"*--{earlier_case}--{earlier_unit}.json"
        prior = list(RESULTS.glob(filename))
        if len(prior) != 1:
            raise ValueError("Prior one-unit Core stage missing or duplicated")
        receipt = json.loads(prior[0].read_text(encoding="utf-8"))
        if (
            receipt.get("case") != earlier_case
            or receipt.get("unit") != earlier_unit
            or receipt.get("mode") != "LIVE_SCOPED_CORE_PLAN_ONLY"
            or receipt.get("provider_status") != "completed"
        ):
            raise ValueError("Invalid prior scoped Core call receipt")
        total += _receipt_cost(receipt, rates)
    if list(RESULTS.glob(f"*--{stage[0]}--{stage[1]}.json")):
        raise ValueError("This one-unit provider test already ran; no retry")
    return total


def preflight(case_id: str, unit_id: str):
    unit, domain, task, req = _reviewed(case_id, unit_id)
    rates = json.loads((ROOT / "config/runtime-pricing-snapshot.json").read_text(encoding="utf-8"))[
        "models"
    ]["gpt-5.6-luna"]
    # Same conservative provider envelope previously approved.
    request_bytes = len(json.dumps(req, ensure_ascii=False, default=str).encode())
    max_cost = (
        (2 * request_bytes + 200)
        * max(rates["input_per_million"], rates.get("cache_write_per_million", 0))
        + req["max_output_tokens"] * rates["output_per_million"]
    ) / 1_000_000
    previous = _charged_previous((case_id, unit_id))
    if previous + max_cost > AUTHORIZED_CUMULATIVE_CAP_USD:
        raise ValueError("Approved cumulative Core test ceiling would be exceeded")
    return unit, domain, task, round(max_cost, 8), round(previous, 8)


def run(case_id: str, unit_id: str, *, live: bool, client: Any = None):
    unit, domain, task, maximum, charged = preflight(case_id, unit_id)
    output: dict[str, Any] = {
        "case": case_id,
        "unit": unit_id,
        "mode": "LIVE_SCOPED_CORE_PLAN_ONLY" if live else "OFFLINE_DRY_RUN",
        "model": "gpt-5.6-luna",
        "max_calls": 1,
        "may_authorize_writes": False,
        "reservation_usd": maximum,
        "previous_estimated_usd": charged,
        "authorized_total_usd": AUTHORIZED_CUMULATIVE_CAP_USD,
    }
    if not live:
        return output
    if os.getenv(RUN_ENV) != "1":
        raise ValueError("Scoped Core provider execution requires explicit approval flag")
    if client is None:
        from openai import OpenAI

        client = OpenAI(max_retries=0, timeout=50.0)
    captured = {}

    class Recorder:
        def __init__(self, responses):
            self.responses = responses

        def create(self, **payload):
            response = self.responses.create(**payload)
            usage = getattr(response, "usage", None)
            captured["usage"] = {
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            }
            captured["provider_status"] = getattr(response, "status", None)
            captured["raw_model_response"] = getattr(response, "output_text", None)
            return response

    planner = OpenAILunaExperimentalPlanner(
        type("Adapter", (), {"responses": Recorder(client.responses)})(),
        SCHEMA,
        CLOCK,
        domain_interpretation=domain,
    )
    try:
        reply = planner.plan(task)
        captured["outcome"] = (
            "PLAN"
            if isinstance(reply, RequestPlan)
            else getattr(reply, "outcome", type(reply).__name__)
        )
        captured["plan_repr"] = repr(reply) if isinstance(reply, RequestPlan) else None
        captured["validation"] = "locally_valid"
    except Exception as exc:
        captured["validation"] = "error"
        captured["error_type"] = type(exc).__name__
        captured["error_stage"] = planner.last_validation_stage
    output.update(captured)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=["F14", "F27"], required=True)
    parser.add_argument("--unit", choices=["candidate-1", "candidate-2"], required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    result = run(args.case, args.unit, live=args.live)
    if args.live:
        RESULTS.mkdir(exist_ok=True)
        file = RESULTS / (
            datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + f"--{args.case}--{args.unit}.json"
        )
        file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("SYNTHETIC_SCOPED_RESULT_FILE=" + str(file))
        print(
            json.dumps(
                {k: v for k, v in result.items() if k not in {"raw_model_response", "plan_repr"}},
                ensure_ascii=False,
            )
        )
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return (
        0
        if not args.live
        or (result.get("validation") == "locally_valid" and result.get("outcome") == "PLAN")
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
