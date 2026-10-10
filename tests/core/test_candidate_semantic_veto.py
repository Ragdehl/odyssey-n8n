"""Negative-evidence-only Core guard: never equate literal overlap with truth."""

from __future__ import annotations

from dataclasses import replace

import pytest

from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_core.candidate_semantic_veto import (
    CandidateSemanticVeto,
    candidate_distinctive_overlap,
    normalized_words,
    veto_unsafe_literal_match,
)
from odyssey_core.request_planning import RequestPlan, WriteAction
from tests.runtime.test_fact_candidate_provenance_readback import _two_items
from tests.runtime.test_fact_candidate_writes_e2e import _case


def _claims(*pairs):
    return tuple(
        CoreCandidateCoverageClaim(f"candidate-{candidate_id}", "planned_fact", fact_ordinal)
        for candidate_id, fact_ordinal in pairs
    )


def test_good_bread_and_milk_are_not_approved_merely_because_veto_passes() -> None:
    source, context = _case("F11")
    assert candidate_distinctive_overlap(context, 0, "Compré pan.")
    assert candidate_distinctive_overlap(context, 1, "Compré leche.")
    assert veto_unsafe_literal_match(source["source"], context, 0, "Compré pan.") is None
    assert veto_unsafe_literal_match(source["source"], context, 1, "Compré leche.") is None
    # The lack of an exception is NEVER a semantic entailment / write authority.


def test_manual_fact_mapping_fails_if_items_swapped() -> None:
    case, context = _case("F11")
    with pytest.raises(CandidateSemanticVeto, match="distinctive original source"):
        build_candidate_coverage_manifest(
            case["source"], context, _two_items(), _claims((1, 1), (2, 0))
        )


def test_manual_fact_mapping_fails_if_new_negation_is_invented() -> None:
    case, context = _case("F11")
    plan = _two_items()
    unit = replace(plan.actions[0].units[0], facts=("No compré pan.", "Compré leche."))
    inverted = RequestPlan((WriteAction((unit,)),), ())
    with pytest.raises(CandidateSemanticVeto, match="unsupported negation"):
        build_candidate_coverage_manifest(
            case["source"], context, inverted, _claims((1, 0), (2, 1))
        )


@pytest.mark.parametrize(
    "negated",
    [
        "No compré pan.",
        "Nunca compré pan.",
        "Jamás compré pan.",
        "I did not buy pan.",
        "Je n'ai jamais acheté pan.",
    ],
)
def test_invented_denial_is_rejected_across_common_languages(negated: str) -> None:
    source, context = _case("F11")
    with pytest.raises(CandidateSemanticVeto, match="unsupported negation"):
        veto_unsafe_literal_match(source["source"], context, 0, negated)


def test_existing_negation_elsewhere_is_not_claimed_as_semantic_resolution() -> None:
    """Guard intentionally cannot determine denial scope from an entire multi-clause source."""
    case, context = _case("F11")
    # This synthetic request is not the original source context, so only a
    # lexical veto is exercised here. It MUST NOT be used as semantic proof.
    source = "No vi a Ana. Hoy compré pan y leche."
    assert veto_unsafe_literal_match(source, context, 0, "No compré pan.") is None


def test_core_must_verify_pronoun_identity_before_candidate_fact_write() -> None:
    """F13 'él' cannot be silently materialized as an explicit Eric by lexical overlap."""
    case, context = _case("F13")
    with pytest.raises(CandidateSemanticVeto, match="Core identity evidence"):
        veto_unsafe_literal_match(case["source"], context, 1, "Mañana iré al cine con Eric.")


def test_generic_nonhuman_subjects_are_not_rejected_solely_due_to_type() -> None:
    """No hard-coded person-only assumptions in the source overlap guard."""
    case, context = _case("F23")
    assert (
        veto_unsafe_literal_match(case["source"], context, 0, "Odyssey tiene un fallo en Router.")
        is None
    )


def test_accent_normalization_does_not_change_original_evidence() -> None:
    assert "jamas" in normalized_words("Jamás")
    assert "eric" in normalized_words("Éric")
    assert "leche" in normalized_words("LECHE")
