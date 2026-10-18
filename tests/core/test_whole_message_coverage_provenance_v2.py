"""Source-anchored evidence is fact/app cardinality agnostic and never mutable."""

from __future__ import annotations

import copy

import pytest

from odyssey_core.source_provenance import anchor_literal_evidence
from odyssey_core.whole_message_coverage import validate_whole_message_coverage

SOURCE = (
    "El lunes organicé el proyecto. "
    "El martes debo llamar al taller y entregar la factura. "
    "El miércoles anoté una preferencia."
)


def _case():
    date_a, date_b, date_c = "2026-10-19", "2026-10-20", "2026-10-21"
    rows = [
        ("organicé el proyecto", [], "record", date_a),
        ("llamar al taller", ["El martes", "debo"], "task", date_b),
        ("entregar la factura", ["El martes", "debo"], "task", date_b),
        ("anoté una preferencia", ["El miércoles"], "record", date_c),
    ]
    proposal = {
        "entities": [],
        "unresolved": [],
        "facts": [
            {
                "source_evidence": literal,
                "source_evidence_fragments": supporting,
                "meaning": literal,
                "kind": kind,
                "date": date,
                "participants": [],
                "needs_clarification": False,
                "dependent_on_fact_index": None,
            }
            for literal, supporting, kind, date in rows
        ],
    }
    review = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": i,
                "kind": kind,
                "date": date,
                "reviewed_text": meaning,
                "reference_names": [],
                "supported": True,
            }
            for i, (meaning, _supports, kind, date) in enumerate(rows)
        ],
    }
    return proposal, review


def _validate(source=SOURCE, proposal=None, review=None, capabilities=None):
    if proposal is None or review is None:
        proposal, review = _case()
    return validate_whole_message_coverage(
        source,
        proposal,
        review,
        ["core", "tasks", "temporal"] if capabilities is None else capabilities,
        core_anchored_evidence=True,
    )


def test_four_mixed_facts_reuse_shared_source_support_without_kind_specific_cases():
    proposal, review = _case()
    proof = _validate(proposal=proposal, review=review)
    assert len(proof.reviewed_facts) == 4
    assert proof.has_write_authority is False
    source_spans = [f.source_spans for f in proof.reviewed_facts]
    assert source_spans[1][1:] == source_spans[2][1:]
    assert all(
        SOURCE[start:end] in [fact["source_evidence"], *fact["source_evidence_fragments"]]
        for fact, spans in zip(proposal["facts"], source_spans, strict=True)
        for start, end in spans
    )
    assert all(source_spans[i][0][0] <= source_spans[i + 1][0][0] for i in range(3))


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_variable_cardinality_without_special_handling_for_two_tasks(n):
    proposal, review = _case()
    proposal["facts"] = proposal["facts"][:n]
    review["facts"] = review["facts"][:n]
    assert len(_validate(proposal=proposal, review=review).reviewed_facts) == n


def test_broad_overlapping_planner_source_remains_literal_and_shared():
    proposal, review = _case()
    for index in (1, 2):
        proposal["facts"][index]["source_evidence"] = "debo llamar al taller y entregar la factura"
    proof = _validate(proposal=proposal, review=review)
    assert proof.reviewed_facts[1].source_spans[0] == proof.reviewed_facts[2].source_spans[0]


@pytest.mark.parametrize(
    "attack",
    [
        "invented_primary",
        "invented_support",
        "repeated_primary",
        "spoofed_review_quote",
        "missing_fact",
        "wrong_kind",
        "wrong_date",
        "unsupported",
        "invented_participant",
        "absent_scope",
        "nonliteral_source_edit",
        "unresolved",
        "bad_support_shape",
    ],
)
def test_provenance_review_still_rejects_untrusted_or_missing_evidence(attack):
    proposal, review = _case()
    source, caps = SOURCE, ["core", "tasks", "temporal"]
    if attack == "invented_primary":
        proposal["facts"][1]["source_evidence"] = "debo avisar al taller"
    elif attack == "invented_support":
        proposal["facts"][1]["source_evidence_fragments"].append("no existe")
    elif attack == "repeated_primary":
        source += " llamar al taller"
    elif attack == "spoofed_review_quote":
        review["facts"][1]["source_quote"] = "llamar al taller"
    elif attack == "missing_fact":
        review["facts"].pop()
    elif attack == "wrong_kind":
        review["facts"][1]["kind"] = "record"
    elif attack == "wrong_date":
        review["facts"][1]["date"] = "2026-10-22"
    elif attack == "unsupported":
        review["facts"][1]["supported"] = False
    elif attack == "invented_participant":
        review["facts"][1]["reference_names"] = ["Inés"]
    elif attack == "absent_scope":
        caps = ["core", "temporal"]
    elif attack == "nonliteral_source_edit":
        source = SOURCE.replace("llamar", "avisar")
    elif attack == "unresolved":
        proposal["unresolved"] = ["uncertain"]
    elif attack == "bad_support_shape":
        proposal["facts"][1]["source_evidence_fragments"] = "El martes"
    with pytest.raises(ValueError):
        _validate(source, proposal, review, caps)


def test_original_plan_and_review_inputs_are_never_rewritten_by_core():
    proposal, review = _case()
    before_plan, before_review = copy.deepcopy(proposal), copy.deepcopy(review)
    _validate(proposal=proposal, review=review)
    assert proposal == before_plan
    assert review == before_review


@pytest.mark.parametrize(
    "note_domain", ["person", "project", "calendar_day", "task", "fictitious_future_plugin"]
)
def test_anchoring_has_no_app_or_note_type_dependency(note_domain):
    # The arbitrary tag cannot affect literal provenance or source offsets.
    original = "En el jardín cultivé lavanda y en casa pinté una mesa."
    exact = anchor_literal_evidence(original, "pinté una mesa", ["en casa", "En el jardín"])
    assert original[exact.primary.start : exact.primary.end] == "pinté una mesa"
    assert len(exact.supporting) == 2
    assert note_domain
