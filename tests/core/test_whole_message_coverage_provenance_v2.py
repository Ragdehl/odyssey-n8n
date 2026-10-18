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
                "source_evidence_context": None,
                "source_evidence_fragment_contexts": [None] * len(supporting),
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


def test_repeated_primary_occurrences_are_disambiguated_by_unique_literal_context():
    source = "Mañana llamo a Ana. Mañana llamo a Bea."
    first = anchor_literal_evidence(source, "Mañana", primary_context="Mañana llamo a Ana")
    second = anchor_literal_evidence(source, "Mañana", primary_context="Mañana llamo a Bea")
    assert first.primary != second.primary
    assert first.primary.start == 0
    assert second.primary.start == source.index("Mañana", 1)
    assert source[first.primary.start : first.primary.end] == "Mañana"
    assert source[second.primary.start : second.primary.end] == "Mañana"


def test_shared_repeated_context_can_support_different_notes_without_type_checks():
    source = "Hoy conocí a Marta. Hoy llamé a Marta."
    a = anchor_literal_evidence(
        source,
        "conocí a Marta",
        ["Hoy", "Marta"],
        supporting_contexts=["Hoy conocí", "conocí a Marta"],
    )
    b = anchor_literal_evidence(
        source,
        "llamé a Marta",
        ["Hoy", "Marta"],
        supporting_contexts=["Hoy llamé", "llamé a Marta"],
    )
    assert a.primary != b.primary
    assert a.supporting[0] != b.supporting[0]
    assert a.supporting[1] != b.supporting[1]


@pytest.mark.parametrize(
    ("primary", "context", "supports", "contexts"),
    [
        ("Mañana", None, [], []),
        ("Mañana", "Mañana", [], []),
        ("Mañana", "Mañana llamo a Ana. Mañana llamo a Bea", [], []),
        ("Mañana", "Mañana llamaré a Ana", [], []),
        ("Mañana", "Mañana llamo a Cora", [], []),
        ("Mañana", 12, [], []),
        ("Mañana", "Mañana llamo a Ana", ["llamo"], []),
        ("Mañana", "Mañana llamo a Ana", ["llamo"], ["inventado"]),
        ("Mañana", "Mañana llamo a Ana", ["llamo"], ["Mañana llamo a Beatriz"]),
    ],
)
def test_ambiguous_edited_or_misaligned_contexts_fail_closed(primary, context, supports, contexts):
    source = "Mañana llamo a Ana. Mañana llamo a Bea."
    with pytest.raises(ValueError):
        anchor_literal_evidence(
            source,
            primary,
            supports,
            primary_context=context,
            supporting_contexts=contexts,
        )


def test_typed_core_review_anchors_two_identical_original_fragments_on_distinct_facts():
    source = "Hoy leí. Hoy leí."
    proposal = {
        "entities": [],
        "unresolved": [],
        "facts": [
            {
                "source_evidence": "Hoy leí",
                "source_evidence_fragments": [],
                "source_evidence_context": scope,
                "source_evidence_fragment_contexts": [],
                "kind": "record",
                "date": "2026-10-18",
                "participants": [],
                "needs_clarification": False,
                "dependent_on_fact_index": None,
            }
            for scope in ("Hoy leí.", "Hoy leí.")
        ],
    }
    review = {
        "approved": True,
        "complete": True,
        "facts": [
            {
                "ordinal": i,
                "kind": "record",
                "date": "2026-10-18",
                "reviewed_text": "Hoy leí",
                "reference_names": [],
                "supported": True,
            }
            for i in range(2)
        ],
    }
    # An exact context that is repeated is NOT a unique occurrence proof.
    with pytest.raises(ValueError, match="ambiguous"):
        _validate(source, proposal, review)
    proposal["facts"][0]["source_evidence"] = "Hoy leí."
    proposal["facts"][0]["source_evidence_context"] = None
    with pytest.raises(ValueError, match="ambiguous"):
        _validate(source, proposal, review)


def test_unicode_character_offsets_are_from_exact_unmodified_source():
    original = "Mañana hablaré con Chloé. Mañana escribiré a Inés."
    one = anchor_literal_evidence(original, "Mañana", primary_context="Mañana hablaré con Chloé")
    two = anchor_literal_evidence(original, "Mañana", primary_context="Mañana escribiré a Inés")
    assert original[one.primary.start : one.primary.end] == "Mañana"
    assert original[two.primary.start : two.primary.end] == "Mañana"
    assert two.primary.start == original.index("Mañana", one.primary.end)


@pytest.mark.parametrize(
    "parts",
    [
        ("Hoy compré pan. ", "Mañana hago deporte."),
        ("Hoy compré ", "pan. Mañana ", "hago deporte."),
        ("Hoy compré pan. Mañana hago deporte.",),
    ],
)
def test_one_shared_core_source_partition_for_arbitrary_group_counts(parts):
    from odyssey_core.source_provenance import anchor_original_partition

    original = "Hoy compré pan. Mañana hago deporte."
    anchors = anchor_original_partition(original, parts)
    assert len(anchors) == len(parts)
    assert tuple(original[a.start : a.end] for a in anchors) == parts
    assert anchors[0].start == 0 and anchors[-1].end == len(original)


@pytest.mark.parametrize(
    "parts",
    [
        ("Hoy compré pan. ", "Mañana hago deport."),
        ("Hoy compré pan.", "Mañana hago deporte."),
        ("Hoy compré pan. ", " Mañana hago deporte."),
        ("Hoy compré pan. Mañana hago deporte.", ""),
        ("Mañana hago deporte.", "Hoy compré pan. "),
    ],
)
def test_shared_partition_refuses_gaps_duplication_reorder_or_empty_spans(parts):
    from odyssey_core.source_provenance import anchor_original_partition

    with pytest.raises(ValueError):
        anchor_original_partition("Hoy compré pan. Mañana hago deporte.", parts)


def test_whole_core_review_with_repeated_primary_and_distinct_verified_contexts():
    source = "Hoy fui al parque. Hoy fui al cine."
    proposal, review = _case()
    proposal["facts"] = proposal["facts"][:2]
    review["facts"] = review["facts"][:2]
    for fact, judgment, context in zip(
        proposal["facts"], review["facts"], ("Hoy fui al parque", "Hoy fui al cine"), strict=True
    ):
        fact.update(
            kind="record",
            date="2026-10-18",
            source_evidence="Hoy fui",
            source_evidence_context=context,
            source_evidence_fragments=["Hoy"],
            source_evidence_fragment_contexts=[context],
        )
        judgment.update(kind="record", date="2026-10-18", reviewed_text=context)
    proof = _validate(source, proposal, review)
    assert len(proof.reviewed_facts) == 2
    assert proof.reviewed_facts[0].source_spans[0] != proof.reviewed_facts[1].source_spans[0]
    assert proof.reviewed_facts[0].source_spans[1] != proof.reviewed_facts[1].source_spans[1]


@pytest.mark.parametrize(
    ("original", "literal", "context"),
    [
        ("aaa", "aa", None),
        ("banana", "ana", None),
        ("aaaa", "aaa", None),
        ("äää", "ää", None),
        ("abaXaba", "aba", "abaXaba"),
        ("aaaaX", "aa", "aaaaX"),
        ("ababab", "ab", "abab"),
    ],
)
def test_provenance_rejects_all_overlapping_source_occurrences(original, literal, context):
    with pytest.raises(ValueError, match="ambiguous"):
        anchor_literal_evidence(original, literal, primary_context=context)


def test_overlapping_text_outside_unique_context_does_not_invalidate_inner_quote():
    original = "aaaXaa"
    anchored = anchor_literal_evidence(original, "aa", primary_context="Xaa")
    assert anchored.primary.start == original.index("Xaa") + 1
    assert original[anchored.primary.start : anchored.primary.end] == "aa"


def test_genuine_single_literal_still_anchors_without_context_after_overlap_fix():
    original = "Mañana veré a Chloé y por la tarde llamaré a Lucía."
    anchor = anchor_literal_evidence(original, "llamaré a Lucía")
    assert original[anchor.primary.start : anchor.primary.end] == "llamaré a Lucía"
