"""Bounded, inactive real GPT-5.6 test for unchanged complete-source Core planning.

Reuses genuine archived GPT-6 Router evidence. Dates in this specific synthetic
benchmark are deterministic Temporal fixtures; no personal notes are opened.
This runner is NOT a production route and has no mutation capability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from benchmarks.fact_candidate_core_live.run_dependent_live import (
    APPROVED_CAP,
    PREVIOUS_FOCUSED_USD,
)
from benchmarks.fact_candidate_core_live.run_live import ROOT, _stable
from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.request_planning import RequestPlan, WriteAction
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.complete_source_handoff import (
    collect_complete_source_evidence,
    plan_complete_source_with_core,
)
from tests.apps.test_fact_candidates import CASES
from tests.benchmarks.test_recorded_real_models_source_replay import _saved_router_outputs
from tests.runtime.test_fact_candidate_planning_vertical import _exact_date, _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA

HERE = Path(__file__).resolve().parent
FREEZE = HERE / "reviewed_full_source_requests.json"
RESULTS = HERE / "full_source_results"
HISTORICAL = HERE / "dependent_results"
STAGES = ("F23", "F26", "F13")
APPROVAL_FLAG = "ODYSSEY_CORE_FACT_LIVE_APPROVED"
MODEL = "gpt-5.6-luna"
# Test-only independent date resolution; neither Router nor Core chooses these.
DATES = {
    "F23": (),
    "F26": (("ayer", "2026-10-03"), ("hoy", "2026-10-04")),
    "F13": (
        ("Ayer", "2026-10-03"),
        ("Mañana", "2026-10-05"),
        ("Hoy", "2026-10-04"),
    ),
}


def request_for(case_id: str):
    """Generate a REAL Core SDK envelope from the original complete message."""
    if case_id not in STAGES:
        raise ValueError("Unreviewed synthetic case")
    source = next(c["source"] for c in CASES if c["id"] == case_id)
    source_sdk, source_calls = _sdk_fake(_saved_router_outputs()[case_id])
    # The synthetic case without date words needs no Temporal date binding.
    temporal = None
    temporal_calls = []
    if DATES[case_id]:
        temporal_sdk, temporal_calls = _sdk_fake(
            {"mentions": [_exact_date(word, day) for word, day in DATES[case_id]]}
        )
        temporal = OpenAITemporalInterpreter(temporal_sdk, CLOCK)
    evidence = collect_complete_source_evidence(
        source,
        router=OpenAIFactCandidateRouter(source_sdk, prompt_revision="v3"),
        temporal=temporal,
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
    plan_complete_source_with_core(
        evidence,
        core_planner_factory=lambda ctx, dom: OpenAILunaExperimentalPlanner(
            fake, SCHEMA, CLOCK, candidate_context=ctx, domain_interpretation=dom
        ),
    )
    if (
        len(source_calls) != 1
        or len(calls) != 1
        or (temporal is not None and len(temporal_calls) != 1)
    ):
        raise ValueError("Source, Temporal or full Core call count drift")
    wire = calls[0]
    if (
        wire.get("model") != MODEL
        or wire.get("reasoning") != {"effort": "low"}
        or wire.get("store") is not False
        or wire.get("max_output_tokens") != 2048
        or wire.get("text", {}).get("format", {}).get("strict") is not True
        or wire["input"][1]["content"] != source
    ):
        raise ValueError("Production Core model or original full source changed")
    return source, evidence, wire


def prepare_review() -> dict:
    """Compute full request hashes for review; never calls any provider."""
    requests = {case: request_for(case)[2] for case in STAGES}
    return {
        "stages": list(STAGES),
        "model": MODEL,
        "sha256": {
            case: hashlib.sha256(_stable(wire)).hexdigest() for case, wire in requests.items()
        },
        "bytes": {case: len(_stable(wire)) for case, wire in requests.items()},
        "approved_cumulative_usd": APPROVED_CAP,
    }


def prior_cost(case_id: str):
    """Validate all four historical dependent receipts and any preceding full runs."""
    pos = STAGES.index(case_id)
    old_expected = (
        ("F23", "candidate-1"),
        ("F23", "candidate-2"),
        ("F26", "candidate-1"),
        ("F26", "candidate-2"),
    )
    old = sorted(HISTORICAL.glob("*.json"))
    if len(old) != 4:
        raise ValueError("Missing historical provider receipts")
    rates = json.loads((ROOT / "config/runtime-pricing-snapshot.json").read_text())["models"][MODEL]
    actual = PREVIOUS_FOCUSED_USD
    for expected, path in zip(old_expected, old, strict=True):
        item = json.loads(path.read_text(encoding="utf-8"))
        if (
            (item.get("case"), item.get("unit")) != expected
            or item.get("mode") != "LIVE_CORE_DEPENDENT_PLAN_ONLY"
            or item.get("provider_status") != "completed"
        ):
            raise ValueError("Historical provider receipt mismatch")
        actual += _charged(item, rates)
    receipts = sorted(RESULTS.glob("*.json"))
    if len(receipts) != pos:
        raise ValueError("Full-source receipts must be executed once, in reviewed order")
    for expected, path in zip(STAGES[:pos], receipts, strict=True):
        item = json.loads(path.read_text(encoding="utf-8"))
        if (
            item.get("case") != expected
            or item.get("mode") != "LIVE_COMPLETE_SOURCE_PLAN_ONLY"
            or item.get("provider_status") != "completed"
            or item.get("request_sha256") != prepare_review()["sha256"][expected]
        ):
            raise ValueError("Previous live case failed or changed; manual review required")
        actual += _charged(item, rates)
    return actual, rates


def _charged(receipt, rates):
    """Charge actual measured tokens at worst-case noncached standard prices."""
    usage = receipt.get("usage")
    if not isinstance(usage, dict) or any(
        type(usage.get(k)) is not int or usage[k] < 0 for k in ("input_tokens", "output_tokens")
    ):
        raise ValueError("Unverifiable real provider usage")
    return (
        usage["input_tokens"] * rates["input_per_million"]
        + usage["output_tokens"] * rates["output_per_million"]
    ) / 1_000_000


def preflight(case_id: str):
    """Require frozen full-source request and conservative existing-budget fit."""
    source, evidence, wire = request_for(case_id)
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))
    actual = prepare_review()
    if frozen != actual:
        raise ValueError("Unreviewed request drift")
    previous, price = prior_cost(case_id)
    # UTF-8 JSON bytes plus 4096 provider-framing tokens conservatively bound
    # this exact request, consistent with the previously approved live gate.
    maximum_input = len(json.dumps(wire, ensure_ascii=True).encode("utf-8")) + 4096
    bound = (
        maximum_input * max(price["input_per_million"], price.get("cache_write_per_million", 0))
        + wire["max_output_tokens"] * price["output_per_million"]
    ) / 1_000_000
    if previous + bound > APPROVED_CAP:
        raise ValueError("Existing cumulative USD 0.07 approval insufficient; stop")
    return source, evidence, wire, round(previous, 8), round(bound, 8)


def run(case_id: str, *, live: bool = False, client=None) -> dict:
    """Observe ONE provider plan, without Core execute_request or vault access."""
    source, evidence, wire, spent, reserved = preflight(case_id)
    record = {
        "case": case_id,
        "mode": "LIVE_COMPLETE_SOURCE_PLAN_ONLY" if live else "OFFLINE_DRY_RUN",
        "model": MODEL,
        "candidate_count": len(evidence.context.candidates),
        "source_was_complete": True,
        "request_sha256": hashlib.sha256(_stable(wire)).hexdigest(),
        "previous_estimated_usd": spent,
        "maximum_reserved_usd": reserved,
        "approved_cumulative_usd": APPROVED_CAP,
        "may_write_notes": False,
        "semantic_coverage_verified": False,
    }
    if not live:
        return record
    if os.getenv(APPROVAL_FLAG) != "1":
        raise ValueError("Explicit live gate permission missing")
    if client is None:
        from openai import OpenAI

        client = OpenAI(max_retries=0, timeout=50)
    observed = {}

    class Recorder:
        """Capture the only real provider reply and its measured usage."""

        def __init__(self, responses):
            self.responses = responses

        def create(self, **request):
            response = self.responses.create(**request)
            observed["provider_status"] = getattr(response, "status", None)
            observed["raw_model_response"] = getattr(response, "output_text", None)
            usage = getattr(response, "usage", None)
            observed["usage"] = {
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            }
            return response

    try:
        output = plan_complete_source_with_core(
            evidence,
            core_planner_factory=lambda ctx, dom: OpenAILunaExperimentalPlanner(
                type("Client", (), {"responses": Recorder(client.responses)})(),
                SCHEMA,
                CLOCK,
                candidate_context=ctx,
                domain_interpretation=dom,
            ),
        )
        record["outcome"] = (
            "PLAN"
            if isinstance(output, RequestPlan)
            else getattr(output, "outcome", type(output).__name__)
        )
        record["atomic_fact_count"] = (
            sum(
                len(unit.facts)
                for action in output.actions
                if isinstance(action, WriteAction)
                for unit in action.units
            )
            if isinstance(output, RequestPlan)
            else 0
        )
        record["validation"] = "compiled"
    except Exception as exc:
        record["validation"] = "error"
        record["error_type"] = type(exc).__name__
        record["error_detail"] = str(exc)[:300]
    record.update(observed)
    RESULTS.mkdir(exist_ok=True)
    output_file = RESULTS / (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "--" + case_id + ".json"
    )
    output_file.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    return record


def main():
    """Offline default; no runtime activation or personal-data authority."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=STAGES)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--prepare-review", action="store_true")
    opts = parser.parse_args()
    if opts.prepare_review:
        if opts.live or opts.case is not None:
            parser.error("--prepare-review must run alone, offline")
        FREEZE.write_text(json.dumps(prepare_review(), indent=2) + "\n")
        print("Synthetic request hashes prepared for review (NO provider calls)")
        return
    if opts.case is None:
        parser.error("--case required")
    report = run(opts.case, live=opts.live)
    print(json.dumps({k: v for k, v in report.items() if k != "raw_model_response"}, indent=2))


if __name__ == "__main__":
    main()
