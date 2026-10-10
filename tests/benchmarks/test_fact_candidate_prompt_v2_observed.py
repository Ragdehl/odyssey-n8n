"""Observed GPT-6 prompt-v2 findings, replayed offline from synthetic saved JSON.

These tests preserve actual provider output while keeping Core's source
preflight strict. They do not accept an arbitrary future model result.
"""

from __future__ import annotations

import json
from pathlib import Path

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
    / "benchmarks/fact_candidate_v2_live/results/20261010T191859Z.json"
)


def _observed():
    saved = json.loads(RESULT.read_text(encoding="utf-8"))
    assert saved["prompt_revision"] == "v2"
    assert all(r["result"] == "source_valid" for r in saved["results"])
    return saved["raw_router_json"]


def _context(case_id: str):
    case = next(c for c in CASES if c["id"] == case_id)
    return case["source"], to_core_candidate_context(
        validate_fact_candidate_proposal(case["source"], _observed()[case_id])
    )


def test_v2_corrected_two_independently_managed_residences() -> None:
    result = _observed()["F09"]
    assert [u["kind"] for u in result["units"]] == ["property", "property"]
    assert [u["anchors"][0]["text"] for u in result["units"]] == ["Marta", "Luis"]


def test_v2_kept_one_mutual_meeting_but_regressed_kind() -> None:
    result = _observed()["F10"]
    assert len(result["units"]) == 1
    assert result["units"][0]["kind"] == "occurrence"  # Approved kind is relationship.


def test_v2_f14_real_router_roles_are_verified_by_core_without_writes() -> None:
    source, context = _context("F14")
    assert [c.kind for c in context.candidates] == ["occurrence", "occurrence"]
    assert any(r.role == "reference" and r.span.text == "él" for r in context.candidates[1].roles)
    assert [r.span.text for r in context.candidates[0].roles if r.role == "date"] == ["Ayer"]
    _case, _baseline_context, _scope, planner, _calls = f14_pipeline()
    plan = planner.plan(source)
    claims = (
        CoreCandidateCoverageClaim("candidate-1", "planned_fact", 0),
        CoreCandidateCoverageClaim("candidate-2", "pending", pending_reason="ambiguous_identity"),
    )
    manifest = build_candidate_coverage_manifest(source, context, plan, claims)
    assert len(manifest.claims) == 2


def test_v2_f27_real_router_roles_are_verified_by_core_without_writes() -> None:
    source, context = _context("F27")
    assert [c.kind for c in context.candidates] == ["occurrence"] * 3
    assert [c.state for c in context.candidates] == ["candidate", "candidate", "ambiguous_identity"]
    assert any(r.role == "reference" and r.span.text == "él" for r in context.candidates[2].roles)
    _case, _baseline_context, plan = f27_pipeline()
    manifest = build_candidate_coverage_manifest(source, context, plan, f27_claims())
    assert len(manifest.claims) == 3
