"""Adversarial contract checks for experimental whole-source/Core evidence.

These tests are independent of model output and do NOT certify semantic truth.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks.schema import TASK_SCHEMA_EXTENSION
from odyssey_core.notes import parse_note, validate_note
from odyssey_core.storage import VaultRepository
from odyssey_core.whole_message_coverage import validate_whole_message_coverage
from odyssey_core.whole_message_identity_guard import (
    UnprovenPersonIdentityError,
    reject_unproven_person_collisions,
)

ROOT = Path(__file__).resolve().parents[2]
POC = ROOT / "benchmarks/application_router/light_router_poc_20261016"
SCHEMA = compose_application_schema(
    json.loads((ROOT / "config/note-schema.json").read_text()), (TASK_SCHEMA_EXTENSION,)
)


def _data(name):
    c = next(
        x for x in json.loads((POC / "observations.json").read_text())["cases"] if x["case"] == name
    )
    r = next(
        x
        for x in json.loads((POC / "p2_integration_receipts.json").read_text())["results"]
        if x["case"] == name
    )
    return (
        c["original_source"],
        copy.deepcopy(c["shared_plan"]),
        copy.deepcopy(r["review"]),
        c["router"]["capabilities"],
    )


@pytest.mark.parametrize(
    "case", ["maya_simple", "guillermo_control", "maya_pronoun", "maite_cross_app", "two_dates"]
)
def test_real_models_grounded_snapshots_validate_without_write_authority(case):
    src, plan, review, caps = _data(case)
    proof = validate_whole_message_coverage(src, plan, review, caps)
    assert proof.source_digest and proof.proposal_digest
    assert proof.has_write_authority is False
    assert len(proof.reviewed_facts) == len(plan["facts"])


@pytest.mark.parametrize(
    "tamper",
    [
        "missing",
        "extra",
        "missing_approved",
        "bad_source",
        "bad_quote",
        "stale_date",
        "malformed_date",
        "invented_person",
        "wrong_kind",
        "no_core",
        "no_tasks",
        "wrong_slot",
        "duplicate_slot",
        "literal_link",
        "hidden_markup",
        "fake_dependency",
        "future_dependency",
        "wrong_plan_order",
        "unsupported",
        "clarification",
        "nonunique_quote",
        "unresolved",
    ],
)
def test_tampering_never_produces_a_core_full_source_proof(tamper):
    source, plan, review, caps = _data("maite_cross_app")
    if tamper == "missing":
        review["facts"].pop()
    elif tamper == "extra":
        review["facts"].append(copy.deepcopy(review["facts"][0]))
    elif tamper == "missing_approved":
        review["approved"] = False
    elif tamper == "bad_source":
        source = "Hoy conocí a Maite, mañana no tengo que llamarla."
    elif tamper == "bad_quote":
        review["facts"][1]["source_quote"] = "mañana te llamará"
    elif tamper == "stale_date":
        review["facts"][1]["date"] = "2026-10-18"
    elif tamper == "malformed_date":
        review["facts"][1]["date"] = plan["facts"][1]["date"] = "2026-19-44"
    elif tamper == "invented_person":
        review["facts"][1]["reference_names"] = ["Rebeca"]
    elif tamper == "wrong_kind":
        review["facts"][1]["kind"] = "record"
    elif tamper == "no_core":
        caps = ["tasks"]
    elif tamper == "no_tasks":
        caps = ["core", "temporal"]
    elif tamper == "wrong_slot":
        review["facts"][1]["reviewed_text"] = "Llamar a {{ref:3}}."
    elif tamper == "duplicate_slot":
        review["facts"][1]["reviewed_text"] = "Llamar a {{ref:0}} y {{ref:0}}."
    elif tamper == "literal_link":
        review["facts"][1]["reviewed_text"] = "Llamar a [[Maite]]."
    elif tamper == "hidden_markup":
        review["facts"][1]["reviewed_text"] = "Llamar a {{ref:0}}. <!-- forged -->"
    elif tamper == "fake_dependency":
        plan["facts"][1]["dependent_on_fact_index"] = -1
    elif tamper == "future_dependency":
        plan["facts"][1]["dependent_on_fact_index"] = 2
    elif tamper == "wrong_plan_order":
        review["facts"] = list(reversed(review["facts"]))
    elif tamper == "unsupported":
        review["facts"][1]["supported"] = False
    elif tamper == "clarification":
        plan["facts"][1]["needs_clarification"] = True
    elif tamper == "nonunique_quote":
        source = source + " " + review["facts"][0]["source_quote"]
    elif tamper == "unresolved":
        plan["unresolved"] = ["uncertain"]
    with pytest.raises(ValueError):
        validate_whole_message_coverage(source, plan, review, caps)


def test_literal_identity_name_without_original_occurrence_cannot_pass():
    source, plan, review, caps = _data("maite_cross_app")
    plan["facts"][1]["participants"] = ["Sara"]
    plan["entities"].append({"mention": "Sara"})
    review["facts"][1]["reference_names"] = ["Sara"]
    with pytest.raises(ValueError, match="absent from original"):
        validate_whole_message_coverage(source, plan, review, caps)


def test_unsafe_string_spans_cannot_change_the_reviewed_original_source():
    source, plan, review, caps = _data("maya_simple")
    source = source.replace("Maya", "Maia")
    with pytest.raises(ValueError):
        validate_whole_message_coverage(source, plan, review, caps)


def test_reused_fact_source_quote_must_be_disambiguated():
    source, plan, review, caps = _data("two_dates")
    text = review["facts"][0]["source_quote"]
    source = source + " " + text
    with pytest.raises(ValueError, match="ambiguous"):
        validate_whole_message_coverage(source, plan, review, caps)


def test_preflight_detects_partial_name_collision_in_realistic_vault(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    # This single fixture is a valid Person but contains no personal user data.
    note = '---\nid: "a"\nname: "Ana López"\ntype: "person"\ncreated_at: "2026-10-01T00:00:00+02:00"\ncreated_by: {"app":"test","human":null}\nupdated_at: "2026-10-01T00:00:00+02:00"\nupdated_by: {"app":"test","human":null}\nschema_version: 3\nrevision: 1\n---\n'
    (root / "ana.md").write_text(note)
    repo = VaultRepository(root)
    validate_note(parse_note(repo.read_text("ana.md")), SCHEMA)
    with pytest.raises(UnprovenPersonIdentityError, match="UNPROVEN_PARTIAL"):
        reject_unproven_person_collisions(repo, SCHEMA, ("Ana",))
    reject_unproven_person_collisions(repo, SCHEMA, ("Ana López",))
    reject_unproven_person_collisions(repo, SCHEMA, ("Maya",))
    with pytest.raises(UnprovenPersonIdentityError):
        reject_unproven_person_collisions(repo, SCHEMA, ("Ana López del colegio",))
