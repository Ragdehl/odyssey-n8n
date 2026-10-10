"""Offline-only request-envelope audit for the approved v2 semantic cases.

This module NEVER creates an OpenAI client, accesses secrets or invokes a
provider. It exercises production request construction with local fake replies.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from tests.apps.test_fact_candidates import CASES, _from_design
from tests.core.test_candidate_attribution import _f14_group
from tests.runtime.test_fact_candidate_planning_vertical import _exact_date, _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import _raw_semantic_plan
from tests.runtime.test_temporal_user_path_e2e import SCHEMA

ROOT = Path(__file__).resolve().parents[2]
CLOCK = {"date": "2026-10-04", "time": "17:35", "timezone": "Europe/Paris"}
LIMIT_USD = 0.02
MAX_CALLS = 9
ALLOWED_MODELS = {"gpt-6-luna", "gpt-5.6-luna"}
ALLOWED_FORMATS = {
    "odyssey_fact_candidate_proposal_v1",
    "odyssey_temporal_interpretation",
    "odyssey_luna_first_planner_result",
    "odyssey_core_candidate_attribution_proposal_v1",
}


def captured_requests() -> list[tuple[str, str, dict[str, Any]]]:
    """Capture nine real production request envelopes without network access."""
    captured: list[tuple[str, str, dict[str, Any]]] = []
    contexts = {}
    for case_id in ("F14", "F27", "F09", "F10"):
        case = next(item for item in CASES if item["id"] == case_id)
        fake, calls = _sdk_fake(_from_design(case))
        proposal = OpenAIFactCandidateRouter(fake).propose(case["source"])
        contexts[case_id] = to_core_candidate_context(proposal)
        captured.extend((case_id, "router", call) for call in calls)
    for case_id in ("F14", "F27"):
        case = next(item for item in CASES if item["id"] == case_id)
        temporal_fake, temporal_calls = _sdk_fake(
            {
                "mentions": [
                    _exact_date("Ayer", "2026-10-03"),
                    _exact_date("Mañana", "2026-10-05"),
                ]
            }
        )
        domain = (
            OpenAITemporalInterpreter(temporal_fake, CLOCK)
            .interpret(case["source"])
            .core_domain_interpretation()
        )
        captured.extend((case_id, "temporal", call) for call in temporal_calls)
        if case_id == "F14":
            plan_data = _raw_semantic_plan()
        else:
            plan_data = {
                "result": {
                    "outcome": "ESCALATE",
                    "actions": None,
                    "limitations": None,
                    "clarification_code": None,
                }
            }
        planner_fake, planner_calls = _sdk_fake(plan_data)
        OpenAILunaExperimentalPlanner(
            planner_fake,
            SCHEMA,
            CLOCK,
            domain_interpretation=domain,
            candidate_context=contexts[case_id],
        ).plan(case["source"])
        captured.extend((case_id, "luna_core", call) for call in planner_calls)
    source, context, plan, proposal_data = _f14_group()
    fake, calls = _sdk_fake(proposal_data)
    OpenAICoreCandidateAttributor(fake).propose(source, context, plan)
    captured.extend(("F14", "attribution", call) for call in calls)
    return captured


def audit() -> dict[str, Any]:
    """Calculate a conservative per-call budget envelope for approved models."""
    rates = json.loads((ROOT / "config/runtime-pricing-snapshot.json").read_text())["models"]
    calls = captured_requests()
    assert len(calls) == MAX_CALLS
    rows = []
    for case_id, stage, request in calls:
        assert request.get("model") in ALLOWED_MODELS
        assert request.get("store") is False
        assert request.get("reasoning", {}).get("effort") == "low"
        fmt = request.get("text", {}).get("format", {})
        assert fmt.get("name") in ALLOWED_FORMATS
        assert fmt.get("strict") is True and fmt.get("type") == "json_schema"
        output_cap = request.get("max_output_tokens")
        assert isinstance(output_cap, int) and 0 < output_cap <= 4096
        payload_bytes = len(json.dumps(request, ensure_ascii=False, default=str).encode())
        assert payload_bytes <= 100_000
        price = rates[request["model"]]
        upper = (
            (2 * payload_bytes + 200)
            * max(price["input_per_million"], price.get("cache_write_per_million", 0))
            + output_cap * price["output_per_million"]
        ) / 1_000_000
        rows.append(
            {
                "case": case_id,
                "stage": stage,
                "model": request["model"],
                "payload_bytes": payload_bytes,
                "output_cap": output_cap,
                "cost_upper_usd": round(upper, 8),
            }
        )
    total = sum(row["cost_upper_usd"] for row in rows)
    # The safe first wave deliberately has no Luna/Core provider call. It is
    # a planning result, NOT permission to retry a platform-blocked live gate.
    first_wave = [row for row in rows if row["stage"] in {"router", "temporal"}]
    first_wave_upper = sum(row["cost_upper_usd"] for row in first_wave)
    return {
        "mode": "OFFLINE_ONLY_NO_PROVIDER",
        "calls": rows,
        "ceiling_usd": LIMIT_USD,
        "total_upper_usd": round(total, 8),
        "fits_ceiling": total <= LIMIT_USD,
        "first_wave": {
            "cases": ["F14", "F27", "F09", "F10"],
            "stages": ["router", "temporal"],
            "calls": len(first_wave),
            "upper_usd": round(first_wave_upper, 8),
            "fits_ceiling": first_wave_upper <= LIMIT_USD,
            "requires_separate_allowed_live_workflow": True,
        },
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
