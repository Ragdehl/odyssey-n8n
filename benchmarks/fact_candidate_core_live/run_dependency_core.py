"""Four-stage reviewed Core GPT-5.6 planning diagnostic for F23/F26.

The inherited Core planner is unchanged. Each provider call contains just
one selected lexical source unit with preceding literal context when needed.
No Note access. All stages require pinned SDK request and budget headroom.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from benchmarks.fact_candidate_core_live.run_live import _stable
from benchmarks.fact_candidate_core_live.run_scoped_live import _receipt_cost
from benchmarks.fact_candidate_v2_live import run_remaining
from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from odyssey_core.candidate_dependencies import preview_contextual_dependency_tasks
from odyssey_core.domain_interpretation import (
    TEMPORAL_REFERENCE_EVIDENCE,
    DomainEvidence,
    DomainInterpretation,
)
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.request_planning import RequestPlan
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_fact_candidate_planning_vertical import _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
STAGES = (
    ("F23", "candidate-1"),
    ("F23", "candidate-2"),
    ("F26", "candidate-1"),
    ("F26", "candidate-2"),
)
PIN = HERE / "reviewed_dependency_core_requests.json"
RESULTS = HERE / "dependency_core_results"
FLAG = "ODYSSEY_CORE_FACT_LIVE_APPROVED"
MODEL = "gpt-5.6-luna"
APPROVED_CAP_USD = 0.07
PRIOR_SPEND_USD = 0.0339488


def _context(case_id: str):
    case = next(x for x in CASES if x["id"] == case_id)
    receipt_file = next(run_remaining.RESULTS.glob(f"*--{case_id}.json"))
    receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    if receipt.get("provider_status") != "completed" or receipt.get("validation") != "source_valid":
        raise ValueError("Frozen Router v3 provider receipt is invalid")
    raw = json.loads(receipt["raw_model_response"])
    context = to_core_candidate_context(validate_fact_candidate_proposal(case["source"], raw))
    return case["source"], context


def _task(case_id: str, unit_id: str):
    if (case_id, unit_id) not in STAGES:
        raise ValueError("Unreviewed source unit")
    source, context = _context(case_id)
    tasks = preview_contextual_dependency_tasks(source, context)
    task = next(t for t in tasks if t.candidate_id == unit_id)
    request = task.scoped_request()
    if case_id == "F26":
        values = {"ayer": "2026-10-03", "hoy": "2026-10-04"}
        evidence = tuple(
            DomainEvidence(TEMPORAL_REFERENCE_EVIDENCE, text, value)
            for text, value in values.items()
            if text in request
        )
        domain = DomainInterpretation("temporal", request, "TEMPORAL_RESOLUTION", evidence)
    else:
        domain = None
    return task, request, domain


def _request(case_id: str, unit_id: str):
    task, request, domain = _task(case_id, unit_id)
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
    OpenAILunaExperimentalPlanner(fake, SCHEMA, CLOCK, domain_interpretation=domain).plan(request)
    if len(calls) != 1:
        raise ValueError("Only one existing Core planner request is permitted")
    return task, request, domain, calls[0]


def reviewed(case_id: str, unit_id: str):
    task, request, domain, spec = _request(case_id, unit_id)
    pins = json.loads(PIN.read_text(encoding="utf-8"))
    key = case_id + "/" + unit_id
    encoded = _stable(spec)
    if (
        pins.get("stages") != [list(x) for x in STAGES]
        or pins["sha256"].get(key) != hashlib.sha256(encoded).hexdigest()
        or pins["bytes"].get(key) != len(encoded)
        or spec.get("model") != MODEL
        or spec.get("reasoning") != {"effort": "low"}
        or spec.get("store") is not False
        or spec.get("max_output_tokens") != 2048
        or spec.get("text", {}).get("format", {}).get("strict") is not True
        or spec["input"][1]["content"] != request
        or task.may_authorize_writes
    ):
        raise ValueError("Changed Core request is not reviewed")
    return task, request, domain, spec


def _existing():
    found: dict[tuple[str, str], dict] = {}
    for path in RESULTS.glob("*.json"):
        data = json.loads(path.read_text())
        key = (data.get("case"), data.get("unit"))
        if (
            key not in STAGES
            or key in found
            or path.name != f"{key[0]}--{key[1]}.json"
            or data.get("mode") != "LIVE_DEPENDENCY_CORE_PLAN_ONLY"
            or data.get("provider_status") != "completed"
            or data.get("usage") is None
            or data.get("validation") != "locally_valid"
            or data.get("outcome") != "PLAN"
        ):
            raise ValueError("Unreviewed, duplicated, or incomplete provider receipt")
        found[key] = data
    if set(found) != set(STAGES[: len(found)]):
        raise ValueError("Out-of-order provider responses")
    return found


def preflight(case_id: str, unit_id: str):
    task, request, domain, spec = reviewed(case_id, unit_id)
    found = _existing()
    key = case_id, unit_id
    if key in found:
        raise ValueError("Already tested: provider call cannot be repeated")
    if len(found) == len(STAGES) or key != STAGES[len(found)]:
        raise ValueError("Must run next approved stage")
    rates = json.loads((ROOT / "config/runtime-pricing-snapshot.json").read_text())["models"][MODEL]
    previous = PRIOR_SPEND_USD + sum(_receipt_cost(x, rates) for x in found.values())
    # Reserve original maximum output and conservative double request bytes.
    data_size = len(json.dumps(spec, ensure_ascii=False, default=str).encode())
    worst = (
        (data_size * 2 + 200)
        * max(rates["input_per_million"], rates.get("cache_write_per_million", 0))
        + spec["max_output_tokens"] * rates["output_per_million"]
    ) / 1_000_000
    if previous + worst > APPROVED_CAP_USD:
        raise ValueError("Next provider stage exceeds authorized cumulative ceiling")
    return task, request, domain, spec, round(previous, 8), round(worst, 8)


def run(case_id: str, unit_id: str, *, live: bool = False, client: Any = None):
    task, request, domain, spec, previous, reserved = preflight(case_id, unit_id)
    output: dict[str, Any] = {
        "case": case_id,
        "unit": unit_id,
        "mode": "LIVE_DEPENDENCY_CORE_PLAN_ONLY" if live else "OFFLINE_DRY_RUN",
        "model": MODEL,
        "may_write_notes": False,
        "previous_estimated_usd": previous,
        "reserved_max_usd": reserved,
        "approved_total_usd": APPROVED_CAP_USD,
        "source_digest": task.source_digest,
        "selected_literal_quote": task.selected_quote,
        "unresolved_references": task.unresolved_reference_quotes,
    }
    if not live:
        return output
    if os.environ.get(FLAG) != "1":
        raise ValueError("Reviewed Core live gate authorization flag missing")
    if client is None:
        from openai import OpenAI

        client = OpenAI(max_retries=0, timeout=50)
    try:
        response = client.responses.create(**spec)
        usage = getattr(response, "usage", None)
        output["provider_status"] = getattr(response, "status", "unknown")
        output["usage"] = {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
        }
        output["raw_model_response"] = getattr(response, "output_text", None)
        if output["provider_status"] == "completed":
            parsed = json.loads(output["raw_model_response"])
            fake, _ = _sdk_fake(parsed)
            planner = OpenAILunaExperimentalPlanner(
                fake, SCHEMA, CLOCK, domain_interpretation=domain
            )
            plan = planner.plan(request)
            output["outcome"] = "PLAN" if isinstance(plan, RequestPlan) else type(plan).__name__
            output["validation"] = "locally_valid"
            output["plan_repr"] = repr(plan) if isinstance(plan, RequestPlan) else None
        else:
            output["validation"] = "incomplete"
    except Exception as error:
        output["validation"] = "provider_or_local_error"
        output["error_type"] = type(error).__name__
        output.setdefault("provider_status", "unknown")
    RESULTS.mkdir(exist_ok=True, parents=True)
    path = RESULTS / f"{case_id}--{unit_id}.json"
    with path.open("x", encoding="utf-8") as out:
        json.dump(output, out, ensure_ascii=False, indent=2)
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True, choices=("F23", "F26"))
    parser.add_argument("--unit", required=True, choices=("candidate-1", "candidate-2"))
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
    return 0 if not args.live or result.get("validation") == "locally_valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
