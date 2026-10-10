"""Existing GPT-5.6 Core planner is invoked once per independent source fact.

All model outputs here are provider-shaped fakes; original GPT-6 Router
source candidates are real saved responses. NO paid calls or canonical writes.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_core.candidate_scoped_handoff import CandidateScopeSafetyError
from odyssey_core.candidate_scoped_planning import plan_independent_core_units
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.request_planning import RequestPlan
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from tests.benchmarks.test_fact_candidate_prompt_v3_observed import _case
from tests.runtime.test_fact_candidate_planning_vertical import _exact_date, _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import (
    CLOCK,
    SCHEMA,
    _raw_semantic_plan,
)


def _raw_single_contact(name: str, *, ordered: bool) -> dict:
    """Reuse the same frozen provider-shaped Core semantic-write template."""
    if name not in {"Eric", "Luis"}:
        raise ValueError("Only synthetic fixture people")
    payload = deepcopy(_raw_semantic_plan())
    operation = payload["result"]["actions"][0]["operations"][0]
    group = operation["facts"][0]["parts"]
    chosen = group[1] if name == "Eric" else group[3]
    operation["facts"][0]["parts"] = [
        {"kind": "literal", "text": "Después hablé con " if ordered else "Hablé con "},
        chosen,
        {"kind": "literal", "text": "."},
    ]
    return payload


def _setup(case_id: str):
    context = to_core_candidate_context(_case(case_id))
    fake_temporal, calls = _sdk_fake(
        {
            "mentions": [
                _exact_date("Ayer", "2026-10-03"),
                _exact_date("Mañana", "2026-10-05"),
            ]
        }
    )
    temporal = OpenAITemporalInterpreter(fake_temporal, CLOCK).interpret(context.source)
    assert len(calls) == 1
    return context, temporal.core_domain_interpretation()


@pytest.mark.parametrize(
    "case_id,expected_requests",
    [
        ("F14", ["Ayer hablé con Eric y Luis."]),
        ("F27", ["Ayer hablé con Eric.", "Ayer hablé después con Luis."]),
    ],
)
def test_existing_core_planner_is_called_once_per_selected_fact(
    case_id: str, expected_requests: list[str]
) -> None:
    context, temporal = _setup(case_id)
    actual: list[tuple[str, str, object, dict]] = []

    def factory(unit, domain):
        people = [span.text for role, span in unit.roles if role == "participants"]
        payload = (
            _raw_semantic_plan()
            if len(people) == 2
            else _raw_single_contact(people[0], ordered="después" in unit.scoped_request())
        )
        fake, requests = _sdk_fake(payload)
        planner = OpenAILunaExperimentalPlanner(fake, SCHEMA, CLOCK, domain_interpretation=domain)
        actual.append((unit.candidate_id, unit.scoped_request(), domain, requests))
        return planner

    result = plan_independent_core_units(context.source, context, temporal, factory)
    assert not result.fully_reviewed_for_write
    assert result.pending_candidate_ids == (f"candidate-{len(expected_requests) + 1}",)
    assert [p.scoped_request for p in result.planned] == expected_requests
    assert [p.candidate_id for p in result.planned] == [
        f"candidate-{index + 1}" for index in range(len(expected_requests))
    ]
    assert all(isinstance(p.plan, RequestPlan) for p in result.planned)
    assert len(actual) == len(expected_requests)
    for candidate_id, request, domain, provider_calls in actual:
        assert len(provider_calls) == 1
        sent = provider_calls[0]
        assert sent["input"][1]["content"] == request
        assert sent["model"] == "gpt-5.6-luna"
        assert sent["store"] is False
        assert domain.source_text == request
        assert len(domain.temporal_references()) == 1
        assert domain.temporal_references()[0].value == "2026-10-03"
        assert "Mañana" not in request and "cine" not in request
        assert candidate_id.startswith("candidate-")


@pytest.mark.parametrize("case_id", ["F14", "F27"])
def test_escalate_in_any_individual_core_call_aborts_entire_result(case_id):
    context, temporal = _setup(case_id)
    calls = []

    def factory(unit, domain):
        calls.append(unit.candidate_id)
        fake, _ = _sdk_fake(
            {
                "result": {
                    "outcome": "ESCALATE",
                    "actions": None,
                    "limitations": None,
                    "clarification_code": None,
                }
            }
        )
        return OpenAILunaExperimentalPlanner(fake, SCHEMA, CLOCK, domain_interpretation=domain)

    with pytest.raises(CandidateScopeSafetyError, match="did not produce"):
        plan_independent_core_units(context.source, context, temporal, factory)
    assert calls == ["candidate-1"]


@pytest.mark.parametrize("case_id", ["F14", "F27"])
def test_wrong_temporal_context_blocks_all_core_calls(case_id):
    context, temporal = _setup(case_id)
    altered = replace(temporal, source_text="Ayer conocí a otra persona. Mañana tengo visita.")

    def cannot_call(*_):
        raise AssertionError("No planner may be invoked")

    with pytest.raises(CandidateScopeSafetyError, match="full original"):
        plan_independent_core_units(context.source, context, altered, cannot_call)


def test_wrong_one_person_plan_is_rejected_even_if_luna_compiles_it():
    context, temporal = _setup("F27")
    calls = []

    def factory(unit, domain):
        # Correct first unit but wrong second participant "Eric" instead of Luis.
        wrong = _raw_single_contact("Eric", ordered=unit.candidate_id == "candidate-2")
        fake, _ = _sdk_fake(wrong)
        calls.append(unit.candidate_id)
        return OpenAILunaExperimentalPlanner(fake, SCHEMA, CLOCK, domain_interpretation=domain)

    with pytest.raises(CandidateScopeSafetyError, match="selected source participants"):
        plan_independent_core_units(context.source, context, temporal, factory)
    assert calls == ["candidate-1", "candidate-2"]
