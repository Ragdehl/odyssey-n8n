"""Frozen synthetic GPT-6 outputs: actual semantic regressions, offline forever.

Evidence was obtained 2026-10-10 under the separately reviewed four-call
Router-only gate. These tests replay saved responses without provider access.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_fact_candidate_semantic_luna_vertical import _pipeline as f14_pipeline
from tests.runtime.test_fact_candidate_sequential_vertical import (
    _claims as f27_claims,
)
from tests.runtime.test_fact_candidate_sequential_vertical import (
    _pipeline as f27_pipeline,
)

RESULT = (
    Path(__file__).resolve().parents[2]
    / "benchmarks/fact_candidate_v2_live/results/20261010T185618Z.json"
)


def _observed():
    saved = json.loads(RESULT.read_text(encoding="utf-8"))
    assert saved["mode"] == "LIVE_SYNTHETIC_ROUTER"
    assert len(saved["results"]) == 4
    assert all(row["result"] == "source_valid" for row in saved["results"])
    return saved["raw_router_json"]


def _context(case_id: str):
    case = next(c for c in CASES if c["id"] == case_id)
    result = validate_fact_candidate_proposal(case["source"], _observed()[case_id])
    return case["source"], to_core_candidate_context(result)


def test_observed_f09_conflated_two_independent_residences() -> None:
    output = _observed()["F09"]
    assert len(output["units"]) == 1
    assert output["units"][0]["kind"] == "relationship"


def test_observed_f10_preserved_one_mutual_relationship() -> None:
    output = _observed()["F10"]
    assert [row["kind"] for row in output["units"]] == ["relationship"]


def test_observed_f14_was_source_valid_but_failed_core_reference_preflight() -> None:
    source, context = _context("F14")
    assert [(u.kind, u.state) for u in context.candidates] == [
        ("occurrence", "candidate"),
        ("plan", "ambiguous_identity"),
    ]
    _case, _baseline, _scope, planner, _calls = f14_pipeline()
    correct_plan = planner.plan(source)
    claims = (
        CoreCandidateCoverageClaim("candidate-1", "planned_fact", 0),
        CoreCandidateCoverageClaim("candidate-2", "pending", pending_reason="ambiguous_identity"),
    )
    with pytest.raises(ValueError, match="participant lacks its own Core reference"):
        build_candidate_coverage_manifest(source, context, correct_plan, claims)


def test_observed_f27_was_source_valid_but_failed_ambiguous_pronoun_preflight() -> None:
    source, context = _context("F27")
    assert [(u.kind, u.state) for u in context.candidates] == [
        ("occurrence", "candidate"),
        ("occurrence", "candidate"),
        ("plan", "ambiguous_identity"),
    ]
    _case, _baseline, correct_plan = f27_pipeline()
    with pytest.raises(ValueError, match="Future reference ambiguity"):
        build_candidate_coverage_manifest(source, context, correct_plan, f27_claims())
