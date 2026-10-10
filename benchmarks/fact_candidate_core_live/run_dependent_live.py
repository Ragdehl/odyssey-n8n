"""One-at-a-time F23/F26 source-grounded GPT-5.6 Core planner evaluation.

This gate evaluates the EXISTING Core planner, no Note actions. Router's real
saved hints are validated, and each original fact remains a separate task.
Dependent second tasks quote prior context as non-operative linguistic data.
The frozen request SHA, stage order, pricing and no-retry policy are mandatory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from benchmarks.fact_candidate_core_live.run_live import ROOT, _stable
from odyssey_core.candidate_dependent_scope import preview_dependent_clause_scopes
from odyssey_core.domain_interpretation import (
    TEMPORAL_REFERENCE_EVIDENCE,
    DomainEvidence,
    DomainInterpretation,
)
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.request_planning import RequestPlan, WriteAction
from tests.core.test_candidate_dependencies_observed import _observed
from tests.runtime.test_fact_candidate_planning_vertical import _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA

STAGES = (
    ("F23", "candidate-1"),
    ("F23", "candidate-2"),
    ("F26", "candidate-1"),
    ("F26", "candidate-2"),
)
HERE = Path(__file__).resolve().parent
FREEZE = HERE / "reviewed_dependent_requests.json"
RECEIPTS = HERE / "dependent_results"
FLAG = "ODYSSEY_CORE_DEPENDENT_LIVE_APPROVED"
RATE_MODEL = "gpt-5.6-luna"
PREVIOUS_FOCUSED_USD = 0.0339488
APPROVED_CAP = 0.07


def _request(case_id: str, unit_id: str):
    """Capture the unchanged existing Core planner request via injected SDK."""
    if (case_id, unit_id) not in STAGES:
        raise ValueError("Unsupported synthetic source candidate")
    source, context = _observed(case_id)
    preview = preview_dependent_clause_scopes(source, context)
    unit = next((u for u in preview.units if u.candidate_id == unit_id), None)
    if unit is None:
        raise ValueError("Missing one selected unit")
    request = unit.planner_request()
    temporal = None
    if case_id == "F26":
        # Pinned fixed 2026-10-04 clock; original source 'ayer'/'hoy'
        # are separately grounded in the full Router source.
        import json as _json

        from benchmarks.fact_candidate_v2_live import run_remaining
        from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
        from odyssey_apps.fact_temporal import bind_temporal_to_fact_candidates
        from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
        from tests.runtime.test_fact_candidate_planning_vertical import _exact_date

        file = next(run_remaining.RESULTS.glob("*--F26.json"))
        proposal = validate_fact_candidate_proposal(
            source, _json.loads(_json.loads(file.read_text())["raw_model_response"])
        )
        # Route through exactly the same *existing* Temporal adapter with a
        # separately disclosed deterministic synthetic response (not live).
        fake_temporal, _ = _sdk_fake(
            {
                "mentions": [
                    _exact_date("ayer", "2026-10-03"),
                    _exact_date("hoy", "2026-10-04"),
                ]
            }
        )
        interpretation = OpenAITemporalInterpreter(fake_temporal, CLOCK).interpret(source)
        edges = bind_temporal_to_fact_candidates(proposal, interpretation)
        selected = [
            edge
            for edge in edges
            if edge.candidate_id == unit_id
            and edge.role == "date"
            and edge.status == "matched"
            and edge.has_exact_source_shape
        ]
        if len(selected) != 1:
            raise ValueError("No uniquely verified scoped synthetic Temporal evidence")
        evidence = selected[0]
        date = evidence.resolution.exact_date
        if date is None or evidence.source.text not in request:
            raise ValueError("Scoped date is not source-grounded")
        temporal = DomainInterpretation(
            "temporal",
            request,
            "TEMPORAL_RESOLUTION",
            (DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, evidence.source.text, date),),
        )
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
    planner = OpenAILunaExperimentalPlanner(fake, SCHEMA, CLOCK, domain_interpretation=temporal)
    # F26's output ceiling is deliberately lower than the previous pilot's;
    # its full prompt, Core model and strict schema remain unchanged.
    if case_id == "F26":
        planner.max_output_tokens = 1280
    planner.plan(request)
    if len(calls) != 1:
        raise ValueError("Existing Core planner must make exactly one call")
    return unit, request, temporal, calls[0]


def reviewed(case_id: str, unit_id: str):
    """Reject request/contract drift before a paid call is even considered."""
    unit, request, temporal, wire = _request(case_id, unit_id)
    pins = json.loads(FREEZE.read_text())
    digest = _stable(wire)
    key = f"{case_id}/{unit_id}"
    if (
        pins.get("stages") != [list(s) for s in STAGES]
        or pins.get("sha256", {}).get(key) != hashlib.sha256(digest).hexdigest()
        or pins.get("bytes", {}).get(key) != len(digest)
        or wire.get("model") != RATE_MODEL
        or wire.get("reasoning") != {"effort": "low"}
        or wire.get("store") is not False
        or wire.get("max_output_tokens") != (1280 if case_id == "F26" else 2048)
        or wire.get("text", {}).get("format", {}).get("strict") is not True
        or wire["input"][1]["content"] != request
    ):
        raise ValueError("Unreviewed dependent Core request")
    return unit, request, temporal, wire


def _prior(stage):
    """Charge saved real receipts; prohibit missing, duplicated or retried calls."""
    if stage not in STAGES:
        raise ValueError("Invalid stage")
    receipts = sorted(RECEIPTS.glob("*.json")) if RECEIPTS.exists() else []
    data = {}
    for receipt in receipts:
        record = json.loads(receipt.read_text())
        key = (record.get("case"), record.get("unit"))
        if (
            key not in STAGES
            or key in data
            or record.get("mode") != "LIVE_CORE_DEPENDENT_PLAN_ONLY"
            or not receipt.name.endswith(f"--{key[0]}--{key[1]}.json")
        ):
            raise ValueError("Unrecognized or duplicate paid-call receipt")
        data[key] = record
    if set(data) != set(STAGES[: len(data)]):
        raise ValueError("Paid-call receipts must be ordered without gaps")
    if stage in data:
        raise ValueError("Paid provider attempt already saved; no retries")
    if stage != STAGES[len(data)]:
        raise ValueError("Out-of-order Core provider call")
    price = json.loads((ROOT / "config/runtime-pricing-snapshot.json").read_text())["models"][
        RATE_MODEL
    ]
    amount = PREVIOUS_FOCUSED_USD
    for entry in data.values():
        if entry.get("provider_status") != "completed":
            raise ValueError("Previous call incomplete; requires manual review")
        usage = entry.get("usage")
        if not isinstance(usage, dict) or any(
            type(usage.get(x)) is not int or usage[x] < 0 for x in ("input_tokens", "output_tokens")
        ):
            raise ValueError("Previous provider usage is unverified")
        amount += (
            usage["input_tokens"] * price["input_per_million"]
            + usage["output_tokens"] * price["output_per_million"]
        ) / 1_000_000
    return amount, price


def preflight(case_id, unit_id):
    """Conservatively reserve an entire Core call inside the cumulative cap."""
    unit, request, temporal, wire = reviewed(case_id, unit_id)
    previous, price = _prior((case_id, unit_id))
    # The request is a fixed, hashed JSON envelope. A byte-level tokenizer
    # consumes >=1 serialized UTF-8 byte per token, so serialized escaped
    # request bytes are an upper bound on source token count. Add another
    # 4,096 tokens for provider-side framing/schema transport not represented
    # in the SDK request. This remains far above the actually observed
    # 10,204–10,598 input tokens on the same unchanged Core prompt/schema.
    # The previous 2x byte estimate was unnecessarily loose, stopping a
    # fourth 10k-token test even though the approved 0.07 cap had ample space.
    max_input_tokens = len(json.dumps(wire, ensure_ascii=True, default=str).encode("utf-8")) + 4096
    maximum = (
        max_input_tokens * max(price["input_per_million"], price.get("cache_write_per_million", 0))
        + wire["max_output_tokens"] * price["output_per_million"]
    ) / 1_000_000
    if previous + maximum > APPROVED_CAP:
        raise ValueError("Approved cumulative USD 0.07 limit would be exceeded")
    return unit, request, temporal, wire, round(previous, 8), round(maximum, 8)


def run(case_id, unit_id, *, live=False, client=None):
    """Compile one fact with existing Core model; record provider failures once."""
    unit, request, temporal, wire, spent, bound = preflight(case_id, unit_id)
    result = {
        "case": case_id,
        "unit": unit_id,
        "mode": "LIVE_CORE_DEPENDENT_PLAN_ONLY" if live else "OFFLINE_DRY_RUN",
        "model": RATE_MODEL,
        "max_calls": 1,
        "may_write_notes": False,
        "semantically_authorized": False,
        "previous_estimated_usd": spent,
        "maximum_reserved_usd": bound,
        "approved_cumulative_usd": APPROVED_CAP,
    }
    if not live:
        return result
    if os.getenv(FLAG) != "1":
        raise ValueError("Explicit approved live gate flag required")
    if client is None:
        from openai import OpenAI

        client = OpenAI(max_retries=0, timeout=50)
    wrapper = {}

    class Recorder:
        def __init__(self, remote):
            self.remote = remote

        def create(self, **args):
            response = self.remote.create(**args)
            usage = getattr(response, "usage", None)
            wrapper["provider_status"] = getattr(response, "status", None)
            wrapper["usage"] = {
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            }
            wrapper["raw_model_response"] = getattr(response, "output_text", None)
            return response

    fake = SimpleNamespace(responses=Recorder(client.responses))
    planner = OpenAILunaExperimentalPlanner(fake, SCHEMA, CLOCK, domain_interpretation=temporal)
    if case_id == "F26":
        planner.max_output_tokens = 1280
    try:
        answer = planner.plan(request)
        wrapper["outcome"] = "PLAN" if isinstance(answer, RequestPlan) else type(answer).__name__
        wrapper["action_count"] = len(answer.actions) if isinstance(answer, RequestPlan) else 0
        wrapper["fact_count"] = (
            sum(len(u.facts) for a in answer.actions if isinstance(a, WriteAction) for u in a.units)
            if isinstance(answer, RequestPlan)
            else 0
        )
        wrapper["plan_repr"] = repr(answer)[:15000] if isinstance(answer, RequestPlan) else None
        wrapper["validation"] = "local_compiler_accepted"
    except Exception as error:
        wrapper["validation"] = "provider_or_compiler_error"
        wrapper["error_type"] = type(error).__name__
        wrapper["error_stage"] = planner.last_validation_stage
    result.update(wrapper)
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    filename = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + f"--{case_id}--{unit_id}.json"
    with (RECEIPTS / filename).open("x", encoding="utf-8") as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=["F23", "F26"], required=True)
    parser.add_argument("--unit", choices=["candidate-1", "candidate-2"], required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    result = run(args.case, args.unit, live=args.live)
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"raw_model_response", "plan_repr"}},
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.live and result.get("validation") != "local_compiler_accepted":
        raise SystemExit(1)
