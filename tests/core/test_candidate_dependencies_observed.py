"""Frozen REAL Router v3 dependency diagnostics; never grant write authority."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from benchmarks.fact_candidate_v2_live import run_remaining
from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from odyssey_core.candidate_context import CoreCandidateInheritance
from odyssey_core.candidate_dependencies import (
    CandidateDependencyError,
    trace_core_candidate_dependencies,
)
from tests.apps.test_fact_candidates import CASES


def _observed(case_id: str):
    """Recover the real saved GPT-6 output without a provider request."""
    case = next(item for item in CASES if item["id"] == case_id)
    p = next(run_remaining.RESULTS.glob(f"*--{case_id}.json"))
    raw = json.loads(json.loads(p.read_text(encoding="utf-8"))["raw_model_response"])
    return case["source"], to_core_candidate_context(
        validate_fact_candidate_proposal(case["source"], raw)
    )


def test_shared_original_hour_remains_temporal_job_not_fake_inherited_time():
    source, context = _observed("F08")
    a, b = trace_core_candidate_dependencies(source, context)
    assert [x.span.text for x in a.for_role("time")] == ["a las 10"]
    assert [x.span.text for x in b.for_role("time")] == ["a la misma hora"]
    assert [x.span.text for x in b.for_role("predicate")] == ["irá"]
    assert b.for_role("predicate")[0].inherited
    assert not b.for_role("time")[0].inherited
    assert b.for_role("time")[0].source_candidate_id == "candidate-2"


def test_other_defect_carries_only_explicit_predecessor_roles():
    source, context = _observed("F23")
    first, second = trace_core_candidate_dependencies(source, context)
    assert [x.span.text for x in first.for_role("object")] == ["un fallo"]
    assert [x.span.text for x in second.for_role("object")] == ["otro"]
    assert [(x.role, x.span.text, x.inherited) for x in second.roles] == [
        ("object", "otro", False),
        ("location", "Temporal", False),
        ("subject", "El proyecto Odyssey", True),
        ("predicate", "tiene", True),
    ]
    assert not second.unresolved_references
    # It has not inferred that 'otro' means 'otro fallo': Core must do so.


@pytest.mark.parametrize("case_id,pronoun", [("F13", "él"), ("F26", "lo")])
def test_unresolved_anaphora_is_not_a_name_or_canonical_reference(case_id, pronoun):
    source, context = _observed(case_id)
    units = trace_core_candidate_dependencies(source, context)
    assert [span.text for span in units[1].unresolved_references] == [pronoun]
    assert not units[1].for_role("subject")
    assert not units[1].for_role("reference")[0].inherited
    assert context.source == source


def test_explicit_source_role_overrides_stale_inherited_same_role():
    source, context = _observed("F08")
    second = context.candidates[1]
    changed = replace(
        second,
        inherits=(*second.inherits, replace(second.inherits[0], role="time")),
    )
    projected = trace_core_candidate_dependencies(
        source, replace(context, candidates=(context.candidates[0], changed))
    )
    assert [e.span.text for e in projected[1].for_role("time")] == ["a la misma hora"]


def test_missing_predecessor_role_aborts_without_guessing():
    source, context = _observed("F26")
    second = replace(
        context.candidates[1],
        inherits=(*context.candidates[1].inherits, CoreCandidateInheritance("location", 1)),
    )
    with pytest.raises(CandidateDependencyError, match="no evidence"):
        trace_core_candidate_dependencies(
            source, replace(context, candidates=(context.candidates[0], second))
        )


def test_shared_plural_people_are_not_collapsed_to_one():
    source, context = _observed("F01")
    units = trace_core_candidate_dependencies(source, context)
    assert [r.span.text for r in units[1].for_role("participants")] == ["mi mujer", "mis hijos"]


def test_inheritance_does_not_jump_to_a_unrelated_new_date():
    source, context = _observed("F02")
    units = trace_core_candidate_dependencies(source, context)
    assert not units[1].for_role("date_scope")
    assert [r.span.text for r in units[2].for_role("date")] == ["el domingo"]
    assert [r.span.text for r in units[2].for_role("participants")] == [
        "mis hijos",
        "mi mujer",
        "yo",
    ]
