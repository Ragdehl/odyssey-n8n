"""Model-facing Core attribution can only propose grounded, nonexecuting claims."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from odyssey_core.candidate_attribution import (
    CandidateAttributionError,
    OpenAICoreCandidateAttributor,
    candidate_attribution_json_schema,
    validate_candidate_attribution,
)
from odyssey_core.request_planning import RequestPlan, WriteAction
from tests.core.test_candidate_coverage import _three_day_plan
from tests.runtime.test_fact_candidate_provenance_readback import _two_items
from tests.runtime.test_fact_candidate_writes_e2e import _case
from tests.runtime.test_temporal_user_path_e2e import _day_plan


def _match(candidate_id: int, anchor: str, ordinal: int, fact: str) -> dict[str, Any]:
    """Build an explicit source/fact pair for offline injected model responses."""
    return {
        "candidate_id": f"candidate-{candidate_id}",
        "disposition": "proposed_fact",
        "fact_ordinal": ordinal,
        "pending_reason": None,
        "source_quote": anchor,
        "planned_fact_text": fact,
    }


def _pending(candidate_id: int, anchor: str, reason: str) -> dict[str, Any]:
    return {
        "candidate_id": f"candidate-{candidate_id}",
        "disposition": "pending",
        "fact_ordinal": None,
        "pending_reason": reason,
        "source_quote": anchor,
        "planned_fact_text": None,
    }


def _f11():
    case, context = _case("F11")
    plan = _two_items()
    return (
        case["source"],
        context,
        plan,
        {
            "candidates": [
                _match(1, "pan", 0, "Compré pan."),
                _match(2, "leche", 1, "Compré leche."),
            ]
        },
    )


def _f01():
    case, context = _case("F01")
    return (
        case["source"],
        context,
        _three_day_plan(),
        {
            "candidates": [
                _match(1, context.candidates[0].anchors[0].text, 0, "Fuimos al parque."),
                _match(2, "y después fuimos al cine", 1, "Después fuimos al cine."),
                _match(3, "y hoy vamos a ir a un concierto", 2, "Iremos a un concierto."),
            ]
        },
    )


def _f14():
    case, context = _case("F14")
    base = _day_plan("2026-10-03", "Hablé con Eric.", "2026-10-03")
    unit = base.actions[0].units[0]
    plan = RequestPlan(
        (
            WriteAction(
                (
                    replace(
                        unit,
                        facts=("Hablé con Eric.", "Hablé con Luis."),
                        fact_temporal_anchors=(unit.fact_temporal_anchors[0],) * 2,
                    ),
                )
            ),
        ),
        (),
    )
    return (
        case["source"],
        context,
        plan,
        {
            "candidates": [
                _match(1, "Eric", 0, "Hablé con Eric."),
                _match(2, "Luis", 1, "Hablé con Luis."),
                _pending(3, "Mañana iré al cine con él", "ambiguous_identity"),
            ]
        },
    )


@pytest.mark.parametrize(
    "factory", [_f11, _f01, _f14], ids=["one-purchase", "three-events", "ambiguous-pronoun"]
)
def test_three_frozen_cases_propose_grounded_but_non_authoritative_pairs(factory) -> None:
    source, context, plan, response = factory()
    proposal = validate_candidate_attribution(source, context, plan, response)
    assert proposal.has_grounded_literals
    assert not proposal.semantically_verified
    assert not proposal.may_authorize_writes
    assert proposal.matches_original_plan(source, plan)
    assert not proposal.matches_original_plan(source + " extra", plan)
    assert not hasattr(proposal, "execute")
    assert len(proposal.candidates) == len(context.candidates)
    assert [p.candidate_id for p in proposal.candidates] == [
        c.candidate_id for c in context.candidates
    ]


def test_model_proposer_uses_single_injected_call_and_never_executes_plan() -> None:
    source, context, plan, expected = _f11()
    captured: list[dict[str, Any]] = []
    reply = SimpleNamespace(status="completed", output_text=json.dumps(expected), usage=None)
    sdk = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: captured.append(kwargs) or reply)
    )
    proposer = OpenAICoreCandidateAttributor(sdk)
    result = proposer.propose(source, context, plan)
    assert len(result.candidates) == 2
    assert len(captured) == 1
    payload = captured[0]
    assert payload["model"] == "gpt-5.6-luna"
    assert payload["reasoning"]["effort"] == "low"
    assert payload["store"] is False
    assert payload["text"]["format"]["strict"] is True
    assert "candidate-1" in payload["input"][1]["content"]
    assert "Compré leche." in payload["input"][1]["content"]
    assert "do not" not in str(result.candidates)
    assert "write" not in candidate_attribution_json_schema()["properties"]


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (
            lambda p: p["candidates"][0].update(
                {"fact_ordinal": 1, "planned_fact_text": "Compré leche."}
            ),
            "lexical",
        ),
        (lambda p: p["candidates"][0].update({"source_quote": "leche"}), "quote"),
        (lambda p: p["candidates"][0].update({"source_quote": "pan inventado"}), "quote"),
        (lambda p: p["candidates"][0].update({"planned_fact_text": "No compré pan."}), "text"),
        (
            lambda p: p["candidates"][1].update(
                {"fact_ordinal": 0, "planned_fact_text": "Compré pan."}
            ),
            "ordinal",
        ),
        (lambda p: p["candidates"][0].update({"fact_ordinal": 99}), "ordinal"),
        (lambda p: p["candidates"][0].update({"fact_ordinal": True}), "ordinal"),
        (lambda p: p["candidates"][0].update({"disposition": "verified"}), "disposition"),
        (lambda p: p["candidates"][0].update({"canonical_id": "person:someone"}), "fields"),
        (lambda p: p["candidates"].pop(), "Every source"),
    ],
)
def test_mismatched_or_forged_pair_fails_closed_before_any_persistence(mutate, error: str) -> None:
    source, context, plan, good = _f11()
    forged = copy.deepcopy(good)
    mutate(forged)
    with pytest.raises(CandidateAttributionError, match=error):
        validate_candidate_attribution(source, context, plan, forged)


def test_ambiguous_reference_cannot_be_proposed_as_saved() -> None:
    source, context, plan, good = _f14()
    forged = copy.deepcopy(good)
    forged["candidates"][2] = _match(3, "Mañana iré al cine con él", 0, "Hablé con Eric.")
    with pytest.raises(CandidateAttributionError, match="Ambiguous identity"):
        validate_candidate_attribution(source, context, plan, forged)


def test_negation_and_conditional_source_cannot_be_approved_by_lexical_overlap() -> None:
    for case_id in ("F17", "F20"):
        case, context = _case(case_id)
        _source, _ctx, plan, payload = _f11()
        malicious = copy.deepcopy(payload)
        for i, candidate in enumerate(context.candidates):
            malicious["candidates"][i]["source_quote"] = candidate.anchors[0].text
        with pytest.raises(CandidateAttributionError, match="Sensitive source"):
            validate_candidate_attribution(case["source"], context, plan, malicious)


def test_bad_original_source_is_rejected_before_provider_call() -> None:
    source, context, plan, _expected = _f11()
    called: list[int] = []
    fake = SimpleNamespace(responses=SimpleNamespace(create=lambda **kw: called.append(1)))
    with pytest.raises(ValueError, match="full current source"):
        OpenAICoreCandidateAttributor(fake).propose(source + " an extra clause", context, plan)
    assert called == []


def test_incomplete_provider_and_invalid_output_fail_without_retry() -> None:
    source, context, plan, _expected = _f11()
    for response in (
        SimpleNamespace(status="incomplete", output_text=None),
        SimpleNamespace(status="completed", output_text="not-json"),
    ):
        calls: list[int] = []
        fake = SimpleNamespace(
            responses=SimpleNamespace(
                create=lambda response=response, calls=calls, **kw: calls.append(1) or response
            )
        )
        with pytest.raises(CandidateAttributionError):
            OpenAICoreCandidateAttributor(fake).propose(source, context, plan)
        assert calls == [1]


def test_unsupported_reference_unit_fails_before_provider_call() -> None:
    source, context, plan, _expected = _f11()
    unit = replace(plan.actions[0].units[0], force_create=True)
    modified = RequestPlan((WriteAction((unit,)),), ())
    sdk = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **kwargs: (_ for _ in ()).throw(AssertionError("called"))
        )
    )
    with pytest.raises(CandidateAttributionError, match="Complex Core fact"):
        OpenAICoreCandidateAttributor(sdk).propose(source, context, modified)


def test_lexical_overlap_cannot_certify_opposite_polarity() -> None:
    """A source/fact mismatch can share tokens; no automatic semantic approval."""
    source, context, plan, _ = _f11()
    unit = plan.actions[0].units[0]
    contradictory = replace(
        unit,
        facts=("No compré pan.", "Compré leche."),
    )
    opposite_plan = RequestPlan((WriteAction((contradictory,)),), ())
    proposed = {
        "candidates": [
            _match(1, "pan", 0, "No compré pan."),
            _match(2, "leche", 1, "Compré leche."),
        ]
    }
    checked = validate_candidate_attribution(source, context, opposite_plan, proposed)
    assert checked.has_grounded_literals  # Quote and fact are real literal text.
    assert not checked.semantically_verified  # The meaning is OPPOSITE.
    assert not checked.may_authorize_writes
    assert not hasattr(checked, "to_execution_manifest")


def test_pronoun_resolution_is_not_inferred_from_matching_event_vocabulary() -> None:
    """F13's 'él' can refer to Eric, but candidate text alone cannot certify it."""
    case, context = _case("F13")
    plans = [
        _day_plan("2026-10-08", "Hablé con Eric.", "2026-10-08"),
        _day_plan("2026-10-10", "Iré al cine con Eric.", "2026-10-10"),
        _day_plan("2026-10-09", "Compré pan.", "2026-10-09"),
    ]
    plan = RequestPlan((WriteAction(tuple(p.actions[0].units[0] for p in plans)),), ())
    raw = {
        "candidates": [
            _match(1, "Ayer hablé con Eric", 0, "Hablé con Eric."),
            _match(2, "Mañana iré al cine con él", 1, "Iré al cine con Eric."),
            _match(3, "Hoy compré pan", 2, "Compré pan."),
        ]
    }
    proposed = validate_candidate_attribution(case["source"], context, plan, raw)
    assert len(proposed.candidates) == 3
    assert not proposed.semantically_verified
    assert not proposed.may_authorize_writes  # Identity must go through Core selection.


def test_old_proposal_cannot_be_reused_after_core_plan_fact_change() -> None:
    """The proposal is bound to source/plan digests and has no execution API."""
    source, context, plan, raw = _f11()
    proposal = validate_candidate_attribution(source, context, plan, raw)
    unit = plan.actions[0].units[0]
    revised = RequestPlan(
        (WriteAction((replace(unit, facts=("Compré pan.", "Compré zumo.")),)),), ()
    )
    assert not proposal.matches_original_plan(source, revised)
    assert not proposal.may_authorize_writes
