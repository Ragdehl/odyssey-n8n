"""Proof and canonical writer shaping for explicit and elided SELF participation."""

import pytest

from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.whole_message_speaker_proof import (
    WholeMessageSpeakerError,
    attach_speaker_to_day_action,
    validate_dual_speaker_review,
)


def _check(source, evidence, roles, assertions):
    facts = [{"source_evidence": s} for s in evidence]
    a = {
        "facts": [
            {"ordinal": i + 1, "role": role, "assertion": assertion, "source_quote": quote}
            for i, (quote, role, assertion) in enumerate(
                zip(evidence, roles, assertions, strict=True)
            )
        ]
    }
    b = {
        "facts": [
            {"ordinal": i, "role": role, "assertion": assertion, "source_quote": quote}
            for i, (quote, role, assertion) in enumerate(
                zip(evidence, roles, assertions, strict=True)
            )
        ]
    }
    return validate_dual_speaker_review(source, facts, a, b), facts, a, b


@pytest.mark.parametrize(
    "source,role,assertion,expected",
    [
        ("Hoy he conocido a Guillem.", "self_participant", "asserted", True),
        ("Yo conocí a Guillem.", "self_participant", "asserted", True),
        ("María me presentó a Guillem.", "self_participant", "asserted", True),
        ("Hoy Guillem conoció a María.", "other", "asserted", False),
        ("Mis hijos fueron al parque.", "other", "asserted", False),
        ("Me encanta pasear por la montaña.", "self_participant", "asserted", True),
        ("Mañana llamaré a Guillem.", "self_participant", "planned", True),
        ("No conocí a Guillem.", "self_participant", "negated", False),
        ("Si conociera a Guillem, lo llamaría.", "self_participant", "conditional", False),
    ],
)
def test_speaker_review_differentiates_actor_and_event_reality(source, role, assertion, expected):
    proof, *_ = _check(source, [source], [role], [assertion])
    assert proof.requires_self_link(0) is expected


def test_three_children_events_are_all_other_even_with_shared_elided_subject():
    source = "Mis hijos fueron al parque, después comieron helado y luego vieron una película."
    evidence = [
        "Mis hijos fueron al parque",
        "después comieron helado",
        "luego vieron una película",
    ]
    proof, *_ = _check(source, evidence, ["other"] * 3, ["asserted"] * 3)
    assert len(proof.facts) == 3
    assert not any(proof.requires_self_link(i) for i in range(3))


def test_reviewer_disagreement_blocks_identity_promotion():
    source = "He conocido a Guillem."
    _proof, facts, a, b = _check(source, [source], ["self_participant"], ["asserted"])
    b["facts"][0]["role"] = "other"
    with pytest.raises(WholeMessageSpeakerError, match="disagree"):
        validate_dual_speaker_review(source, facts, a, b)


@pytest.mark.parametrize("bad_numbering", [[3], [True], ["1"], [0, 0]])
def test_invalid_ordinal_sequence_rejected(bad_numbering):
    source = "Hoy compré pan y mañana compraré leche."
    evidence = ["Hoy compré pan", "mañana compraré leche"]
    _proof, facts, a, b = _check(
        source, evidence, ["self_participant"] * 2, ["asserted", "planned"]
    )
    changed = list(bad_numbering)
    if len(changed) == 1:
        changed.append(2)
    for i, num in enumerate(changed):
        b["facts"][i]["ordinal"] = num
    with pytest.raises(WholeMessageSpeakerError):
        validate_dual_speaker_review(source, facts, a, b)


def test_untrusted_quote_or_invented_span_rejected():
    src = "Hoy he conocido a Guillem."
    _proof, facts, a, b = _check(src, [src], ["self_participant"], ["asserted"])
    b["facts"][0]["source_quote"] = "Ayer he conocido a Guillem."
    with pytest.raises(WholeMessageSpeakerError):
        validate_dual_speaker_review(src, facts, a, b)


def test_add_self_binding_to_exact_two_core_day_facts_not_third_person():
    action = WriteAction(
        (
            KnowledgeUnit(
                SelectionCriteria(None, "2026-10-16", "calendar_day", (), None),
                "record",
                (),
                (),
                ("Hoy hablé con {{ref:0}}.", "Después {{ref:1}} fue solo al cine."),
                (
                    KnowledgeReference(1, "person", "Guillem"),
                    KnowledgeReference(1, "person", "Guillem"),
                ),
            ),
            KnowledgeUnit(
                SelectionCriteria("Guillem", "Guillem", "person", (), None),
                "record",
                (),
                (),
                (),
                (),
                reference_lookup_only=True,
            ),
        )
    )
    augmented = attach_speaker_to_day_action(action, [True, False])
    assert len(augmented.units) == 3
    assert augmented.units[-1].target.self_target == "self"
    assert augmented.units[-1].reference_lookup_only
    assert "{{ref:2}}" in augmented.units[0].facts[0]
    assert augmented.units[0].facts[1] == action.units[0].facts[1]
    assert len(augmented.units[0].references) == 3
    assert action.units[0].facts[0] == "Hoy hablé con {{ref:0}}."


def test_self_is_not_added_without_direct_participation():
    action = WriteAction(
        (
            KnowledgeUnit(
                SelectionCriteria(None, "2026-10-16", "calendar_day", (), None),
                "record",
                (),
                (),
                ("Hoy Ana fue al cine.",),
                (),
            ),
        )
    )
    assert attach_speaker_to_day_action(action, [False]) is action
    with pytest.raises(WholeMessageSpeakerError):
        attach_speaker_to_day_action(action, [True, False])
