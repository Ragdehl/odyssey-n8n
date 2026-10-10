"""Opt-in Router v1 -> Temporal -> Core Luna plan, with provider fakes only.

This proves the existing planner can inspect grounded candidate evidence, not
that a live model understands all fact units or that writes are ready to run.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_apps.fact_temporal import bind_temporal_to_fact_candidates
from odyssey_apps.router import RouterError
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


def test_duplicate_router_proposal_fails_at_model_adapter_boundary() -> None:
    """Malformed model evidence cannot be converted into Core candidate context."""
    case = next(item for item in CASES if item["id"] == "F14")
    raw = _from_design(case)
    raw["units"].append(dict(raw["units"][0]))
    router_fake, router_calls = _sdk_fake(raw)
    adapter = OpenAIFactCandidateRouter(router_fake)

    with pytest.raises(RouterError, match="grounded source evidence"):
        adapter.propose(case["source"])

    assert len(router_calls) == 1
    assert adapter.last_error_category == "InvalidSourceEvidence"


def test_repeated_temporal_source_aborts_before_core_planning() -> None:
    """Router/Temporal fake outputs cannot misattribute a repeated 'Mañana'."""
    source = "Mañana veré a Ana. Mañana veré a Luis."
    router_raw = {
        "version": 1,
        "units": [
            {
                "kind": "occurrence",
                "anchors": [{"text": f"veré a {name}", "occurrence": 0}],
                "scoped_source": [
                    {"role": "date", "anchor": {"text": "Mañana", "occurrence": index}},
                    {"role": "participants", "anchor": {"text": name, "occurrence": 0}},
                ],
                "inheritance": [],
                "state": "candidate",
            }
            for index, name in enumerate(("Ana", "Luis"))
        ],
    }
    router_fake, router_calls = _sdk_fake(router_raw)
    proposal = OpenAIFactCandidateRouter(router_fake).propose(source)
    temporal_fake, temporal_calls = _sdk_fake({"mentions": [_exact_date("Mañana", "2026-10-10")]})
    temporal = OpenAITemporalInterpreter(temporal_fake, CLOCK).interpret(source)

    # The ambiguity must be reported at the source-alignment boundary;
    # no Core planner or persistence object is needed or constructed.
    with pytest.raises(RouterError, match="occurrence is ambiguous"):
        bind_temporal_to_fact_candidates(proposal, temporal)
    assert len(router_calls) == len(temporal_calls) == 1
    assert router_calls[0]["store"] is False
    assert temporal_calls[0]["store"] is False


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
