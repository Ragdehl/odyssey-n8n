"""P2 proposed whole-source proof does not grant unreviewed canonical write authority.

Frozen genuine-model snapshots ensure this test runs without API calls. It
exercises the new EXPERIMENTAL boundary only; production acceptance still
requires a separately reviewed general Core candidate/fact coverage contract.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from benchmarks.application_router.light_router_poc_20261016.p2_integrated_bridge import (
    evidence_check,
)

ROOT = Path(__file__).resolve().parents[2]
POC = ROOT / "benchmarks/application_router/light_router_poc_20261016"


def _case(name: str):
    cases = json.loads((POC / "observations.json").read_text())["cases"]
    row = next(x for x in cases if x["case"] == name)
    review_runs = json.loads((POC / "p2_integration_receipts.json").read_text())["results"]
    receipt = next(x for x in review_runs if x["case"] == name)
    assert receipt["review"] is not None
    plan = dict(row["shared_plan"])
    plan["_allowed_capabilities"] = row["router"]["capabilities"]
    return row["original_source"], plan, deepcopy(receipt["review"])


def test_real_reviewed_maya_still_has_every_grounded_link() -> None:
    source, proposal, review = _case("maya_simple")
    assert evidence_check(source, proposal, review)


def test_real_reviewed_maite_requires_two_distinct_ops_with_one_canonical_identity() -> None:
    source, proposal, review = _case("maite_cross_app")
    assert evidence_check(source, proposal, review)
    assert [fact["kind"] for fact in review["facts"]] == ["record", "task"]
    assert [fact["date"] for fact in review["facts"]] == ["2026-10-16", "2026-10-17"]
    assert all("Maite" in fact["reference_names"] for fact in review["facts"])


@pytest.mark.parametrize(
    "corruption",
    (
        "drop_fact",
        "fabricate_quote",
        "wrong_date",
        "invent_participant",
        "drop_reference",
        "fake_ordinal",
        "raw_link",
        "wrong_kind",
        "unreviewed_ambiguous",
        "reject",
    ),
)
def test_corrupted_source_review_cannot_authorize_mutation(corruption: str) -> None:
    source, proposal, review = _case("maite_cross_app")
    if corruption == "drop_fact":
        review["facts"].pop()
    elif corruption == "fabricate_quote":
        review["facts"][1]["source_quote"] = "mañana tengo que llamarlo"
    elif corruption == "wrong_date":
        review["facts"][1]["date"] = "2026-10-18"
    elif corruption == "invent_participant":
        review["facts"][1]["reference_names"] = ["Cloe"]
    elif corruption == "drop_reference":
        review["facts"][1]["reference_names"] = []
    elif corruption == "fake_ordinal":
        review["facts"][1]["ordinal"] = 6
    elif corruption == "raw_link":
        review["facts"][1]["reviewed_text"] = "Llamar a [[Maite]]."
    elif corruption == "wrong_kind":
        review["facts"][1]["kind"] = "record"
    elif corruption == "unreviewed_ambiguous":
        proposal["facts"][1]["needs_clarification"] = True
    elif corruption == "reject":
        review["approved"] = False
    with pytest.raises(ValueError):
        evidence_check(source, proposal, review)


def test_ambiguous_proposal_must_not_write_even_with_fabricated_verdict() -> None:
    source, proposal, review = _case("maya_simple")
    proposal["unresolved"] = ["identity unresolved"]
    with pytest.raises(ValueError):
        evidence_check(source, proposal, review)


def test_wrong_routing_scope_cannot_create_task() -> None:
    source, proposal, review = _case("maite_cross_app")
    proposal["_allowed_capabilities"] = ["core", "temporal"]
    with pytest.raises(ValueError, match="Task without routing scope"):
        evidence_check(source, proposal, review)


def test_genuine_sandbox_receipts_are_not_misrepresented_as_user_path_e2e() -> None:
    report = json.loads((POC / "p2_integration_receipts.json").read_text())
    assert report["isolated_vault"] is True
    assert report["synthetic_embeddings"] is True
    assert "Experimental" in report["WARNING"]
    assert report["real_ai"] is True
    assert not (POC / "dev_deployed_marker.txt").exists()
