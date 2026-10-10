"""Frozen semantic sentinels from the third four-case GPT-6 Router gate.

Compare meaningful assertion units, never demand identical valid source quotes.
Provider variance requires a fresh explicit live gate; CI replays these receipts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from tests.apps.test_fact_candidates import CASES

RESULT = (
    Path(__file__).resolve().parents[2]
    / "benchmarks/fact_candidate_v2_live/results/20261010T193754Z.json"
)


def _case(case_id: str):
    saved = json.loads(RESULT.read_text(encoding="utf-8"))
    assert saved["prompt_revision"] == "v3"
    assert len(saved["results"]) == 4
    assert all(
        r["status"] == "completed" and r["result"] == "source_valid" for r in saved["results"]
    )
    case = next(c for c in CASES if c["id"] == case_id)
    return validate_fact_candidate_proposal(case["source"], saved["raw_router_json"][case_id])


def test_f09_two_independent_properties_remain_independently_grounded() -> None:
    units = _case("F09").candidates
    assert [unit.kind for unit in units] == ["property", "property"]
    assert [unit.anchors[0].text for unit in units] == ["Marta", "Luis"]
    assert all(
        any(role.role == "location" and role.anchor.text == "Lyon" for role in unit.scopes)
        for unit in units
    )


def test_f10_mutual_encounter_is_exactly_one_relationship() -> None:
    units = _case("F10").candidates
    assert len(units) == 1 and units[0].kind == "relationship"
    assert [r.anchor.text for r in units[0].scopes if r.role == "participants"] == ["Marta", "Luis"]


@pytest.mark.parametrize("case_id,past_count", [("F14", 1), ("F27", 2)])
def test_real_semantic_event_count_and_pending_reference(case_id: str, past_count: int) -> None:
    units = _case(case_id).candidates
    assert len(units) == past_count + 1
    assert [unit.kind for unit in units] == ["occurrence"] * (past_count + 1)
    assert [unit.state for unit in units] == [*(["candidate"] * past_count), "ambiguous_identity"]
    assert [r.anchor.text for r in units[-1].scopes if r.role == "reference"] == ["él"]
    assert [r.anchor.text for r in units[-1].scopes if r.role == "date"] == ["Mañana"]
    assert [r.anchor.text for r in units[0].scopes if r.role == "date"] == ["Ayer"]
    participants = [
        role.anchor.text
        for unit in units[:past_count]
        for role in unit.scopes
        if role.role == "participants"
    ]
    assert participants == ["Eric", "Luis"]
    if case_id == "F27":
        assert any(
            role.role == "order" and role.anchor.text == "después" for role in units[1].scopes
        )


def test_f10_core_can_verify_mutual_relationship_source_roles_before_any_write() -> None:
    """Two separate name spans before a reciprocal predicate are legitimate evidence.

    A synthetic Core plan is used ONLY for isolated provenance checking. The
    dated destination inherited from F14 is not suitable for F10 persistence.
    """
    from dataclasses import replace

    from odyssey_apps.fact_candidate_core import to_core_candidate_context
    from odyssey_core.candidate_multi_participant import validate_two_named_participant_fact
    from odyssey_core.request_planning import (
        KnowledgeReference,
        RequestPlan,
        SelectionCriteria,
        WriteAction,
    )
    from tests.runtime.test_fact_multi_participant_event import _core_linked_event

    case = next(c for c in CASES if c["id"] == "F10")
    candidate = to_core_candidate_context(_case("F10")).candidates[0]
    _day, old_eric, old_luis = _core_linked_event().actions[0].units
    day = replace(
        _day,
        facts=("{{ref:0}} y {{ref:1}} se conocieron en Lyon.",),
        references=(
            KnowledgeReference(1, "person", "Marta"),
            KnowledgeReference(2, "person", "Luis"),
        ),
    )
    marta = replace(old_eric, target=SelectionCriteria("Marta", "Marta", "person", (), None))
    luis = replace(old_luis, target=SelectionCriteria("Luis", "Luis", "person", (), None))
    plan = RequestPlan((WriteAction((day, marta, luis)),), ())
    validate_two_named_participant_fact(case["source"], candidate, plan, 0, 0)

    import pytest

    altered_kind = replace(candidate, kind="occurrence")
    with pytest.raises(ValueError, match="not uniquely anchored"):
        validate_two_named_participant_fact(case["source"], altered_kind, plan, 0, 0)
    missing_predicate = replace(
        candidate, roles=tuple(r for r in candidate.roles if r.role != "predicate")
    )
    with pytest.raises(ValueError, match="not uniquely anchored"):
        validate_two_named_participant_fact(case["source"], missing_predicate, plan, 0, 0)
    wrong_helper = RequestPlan((WriteAction((day, luis, marta)),), ())
    with pytest.raises(ValueError, match="helper"):
        validate_two_named_participant_fact(case["source"], candidate, wrong_helper, 0, 0)
