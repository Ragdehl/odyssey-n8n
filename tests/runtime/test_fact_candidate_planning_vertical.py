"""Opt-in Router v1 -> Temporal -> Core Luna plan, with provider fakes only.

This proves the existing planner can inspect grounded candidate evidence, not
that a live model understands all fact units or that writes are ready to run.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_apps.fact_temporal import bind_temporal_to_fact_candidates
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner, PlannerEscalation
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from tests.apps.test_fact_candidates import CASES, _from_design

ROOT = Path(__file__).resolve().parents[2]
CLOCK = {"date": "2026-10-09", "time": "13:15", "timezone": "Europe/Paris"}


def _sdk_fake(result: dict[str, Any]) -> tuple[SimpleNamespace, list[dict[str, Any]]]:
    """Return an injected Responses-shaped provider with deterministic offline result."""
    calls: list[dict[str, Any]] = []
    reply = SimpleNamespace(
        status="completed",
        output_text=json.dumps(result, ensure_ascii=False),
        usage=None,
        id="synthetic",
    )
    fake = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **arguments: calls.append(arguments) or reply)
    )
    return fake, calls


def _exact_date(text: str, date: str) -> dict[str, Any]:
    """Represent a normalized Temporal response without a real model call."""
    return {
        "temporal_text": text,
        "temporal": {
            "kind": "EXACT_DATE",
            "exact_date": date,
            "exact_datetime": None,
            "range_start": None,
            "range_end_exclusive": None,
        },
    }


def test_full_source_scoped_fact_flow_to_luna_is_read_only_and_preflighted() -> None:
    """Three events get the right lexical dates, but only Core chooses actions."""
    case = next(item for item in CASES if item["id"] == "F13")
    router_fake, router_calls = _sdk_fake(_from_design(case))
    temporal_fake, temporal_calls = _sdk_fake(
        {
            "mentions": [
                _exact_date("Ayer", "2026-10-08"),
                _exact_date("Mañana", "2026-10-10"),
                _exact_date("Hoy", "2026-10-09"),
            ]
        }
    )
    core_fake, core_calls = _sdk_fake(
        {
            "result": {
                "outcome": "ESCALATE",
                "actions": None,
                "limitations": None,
                "clarification_code": None,
            }
        }
    )

    # Two independent source interpreters. Router has no Note/identity/write role.
    proposal = OpenAIFactCandidateRouter(router_fake).propose(case["source"])
    assert len(proposal.candidates) == 3
    temporal = OpenAITemporalInterpreter(temporal_fake, CLOCK).interpret(case["source"])
    scope = bind_temporal_to_fact_candidates(proposal, temporal)
    assert [edge.resolution.exact_date for edge in scope if edge.role == "date"] == [
        "2026-10-08",
        "2026-10-10",
        "2026-10-09",
    ]
    assert all(edge.has_exact_source_shape for edge in scope if edge.role == "date")

    # The original request, all three candidates, and existing Temporal evidence
    # enter the real Luna Core planner. No Core action executor is constructed.
    core = to_core_candidate_context(proposal)
    domain = temporal.core_domain_interpretation()
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    result = OpenAILunaExperimentalPlanner(
        core_fake,
        schema,
        CLOCK,
        domain_interpretation=domain,
        candidate_context=core,
    ).plan(case["source"])
    assert isinstance(result, PlannerEscalation)
    assert len(router_calls) == len(temporal_calls) == len(core_calls) == 1
    assert all(call["store"] is False for call in (*router_calls, *temporal_calls, *core_calls))
    assert router_calls[0]["model"] == temporal_calls[0]["model"] == "gpt-6-luna"
    assert core_calls[0]["model"] == "gpt-5.6-luna"
    assert all(
        call["input"][1]["content"] == case["source"]
        for call in (*router_calls, *temporal_calls, *core_calls)
    )
    assert len(core_calls[0]["input"]) == 2
    system = str(core_calls[0]["input"][0]["content"])
    assert "candidate-3" in system
    assert "temporal_reference" in system
    assert "2026-10-10" in system
    assert '"role":"reference"' in system
    assert "canonical_id" not in system


def test_router_ambiguous_identity_remains_unverified_in_core_packet() -> None:
    """Do not resolve 'él' when previous sentence names two possible people."""
    case = next(item for item in CASES if item["id"] == "F27")
    router_fake, calls = _sdk_fake(_from_design(case))
    proposal = OpenAIFactCandidateRouter(router_fake).propose(case["source"])
    packet = to_core_candidate_context(proposal)
    assert len(calls) == 1
    assert packet.candidates[2].state == "ambiguous_identity"
    assert any(
        role.role == "reference" and role.span.text == "él" for role in packet.candidates[2].roles
    )
    assert not any("person:" in str(item.to_payload()) for item in packet.candidates)
    # No Core write path is wired to this experiment.
    assert not hasattr(packet, "execute")
