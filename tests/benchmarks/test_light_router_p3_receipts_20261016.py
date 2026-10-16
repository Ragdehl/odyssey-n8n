"""Replay acceptance facts captured from real P3 provider + canonical Writer runs.

These are recorded receipts, NOT fresh AI calls. Live calls are separate.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POC = ROOT / "benchmarks/application_router/light_router_poc_20261016"


def test_p3_new_core_contract_real_provider_receipts():
    x = json.loads((POC / "p3_core_contract_fresh_receipts.json").read_text())
    assert x["real_ai"] is True
    assert x["fresh_semantic_route_and_plan"] is True
    assert x["isolated_vault"] is True
    assert x["temporary_vaults_discarded"] is True
    cases = {r["case"]: r for r in x["results"]}
    assert len(cases) == 6
    assert {name for name, row in cases.items() if row["status"] == "completed"} == {
        "maya_simple",
        "guillermo_control",
        "maya_pronoun",
        "maite_cross_app",
        "two_dates",
    }
    ana = cases["ana_luis"]
    assert ana["status"] == "failed" and ana["note_changes"] == []
    assert len(cases["maya_pronoun"]["note_changes"]) == 3
    maite = cases["maite_cross_app"]
    writes = maite["writes"]
    assert writes[0]["units"][1]["id"] == writes[1]["units"][1]["id"]
    assert "backlinks:Maite:2" in maite["verified_readback"]["assertions"]


def test_five_additional_complex_cases_have_no_unsafe_partial_writes():
    x = json.loads((POC / "p3_extended_receipts.json").read_text())
    assert x["fresh_semantic_route_and_plan"] is True
    assert x["isolated_vault"] is True and x["temporary_vaults_discarded"] is True
    cases = {r["case"]: r for r in x["results"]}
    assert set(cases) == {
        "children_subject",
        "maite_variant",
        "independent_apps",
        "gender_disambiguated",
        "ambiguous_two_males",
    }
    assert all(r["status"] == "failed" and not r["note_changes"] for r in cases.values())
    assert "UNPROVEN_PARTIAL" in cases["maite_variant"]["reason"]


def test_three_undated_children_facts_read_back_from_self_with_both_backlinks():
    r = json.loads((POC / "p3_children_real_write.json").read_text())
    assert r["status"] == "completed" and r["writer_status"] == "completed"
    assert r["cloned_dev"] is True
    assert r["temp_vault_deleted"] is True
    assert r["fresh_independent_reviewer"] is True
    assert r["facts_written"] == 3 and r["new_person_notes"] == 0
    assert set(r["backlinks"]) == {"Cloe", "Bruno"}
    assert all(occurrences >= 3 for occurrences in r["backlinks"].values())
    assert len(r["changed_notes"]) == 1
    assert "odyssey-dev-synthetic-person" in r["changed_notes"][0]
