"""Tests for blind contextual requests and fail-closed Core validation."""

from __future__ import annotations

import json

import pytest

from odyssey_core.contextual import (
    ContextualCandidate,
    ContextualResolutionDecision,
    ContextualResolutionError,
    ContextualResolutionExample,
    ContextualResolutionRequest,
    build_openai_payload,
    validate_contextual_decision,
)


def request() -> ContextualResolutionRequest:
    """Return one synthetic contextual request with two plausible people."""
    return ContextualResolutionRequest(
        reference="the other Beatriz",
        context="Dinner with Xavi and his partner",
        entity_type="person",
        candidates=(
            ContextualCandidate("beatriz-alonso", "The user's spouse."),
            ContextualCandidate("beatriz-costa", "Xavi's partner."),
        ),
    )


def test_openai_payload_is_blind_and_uses_required_api_controls() -> None:
    """Exclude labels and case identity while enforcing privacy and output controls."""
    payload = build_openai_payload(request(), "gpt-5.6-luna")
    serialized = json.dumps(payload)

    assert payload["store"] is False
    assert payload["reasoning"] == {"effort": "medium"}
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["strict"] is True
    assert "expected" not in serialized.casefold()
    assert "case_id" not in serialized.casefold()
    assert "correct" not in serialized.casefold()
    assert "label_disputed" not in serialized.casefold()


def test_expected_labels_cannot_enter_payload_through_request_contract() -> None:
    """Keep benchmark truth outside the request type accepted by the provider builder."""
    assert set(ContextualResolutionRequest.__dataclass_fields__) == {
        "reference",
        "context",
        "entity_type",
        "candidates",
    }


def test_frozen_examples_are_compact_turns_and_evaluation_stays_blind() -> None:
    """Include labelled calibration turns without leaking evaluation identity or truth."""
    example = ContextualResolutionExample(
        request=request(),
        decision=ContextualResolutionDecision("RESOLVED", "beatriz-costa"),
    )
    evaluation = ContextualResolutionRequest(
        reference="EVALUATION-REFERENCE",
        context="EVALUATION-CONTEXT",
        entity_type="person",
        candidates=(ContextualCandidate("evaluation-candidate", "EVALUATION-EVIDENCE"),),
    )

    payload = build_openai_payload(evaluation, "gpt-5.6-luna", examples=(example,))
    turns = payload["input"]

    assert [turn["role"] for turn in turns] == ["system", "user", "assistant", "user"]
    assert json.loads(turns[2]["content"]) == {
        "outcome": "RESOLVED",
        "id": "beatriz-costa",
    }
    assert sum("EVALUATION-REFERENCE" in turn["content"] for turn in turns) == 1
    assert sum("EVALUATION-CONTEXT" in turn["content"] for turn in turns) == 1
    assert "case_id" not in json.dumps(payload).casefold()


@pytest.mark.parametrize(
    ("output", "message"),
    [
        ({"outcome": "MAYBE", "id": None}, "invalid outcome"),
        ({"outcome": "RESOLVED", "id": None}, "non-null"),
        ({"outcome": "AMBIGUOUS", "id": "a"}, "null ID"),
        ({"outcome": "UNRESOLVED", "id": "a"}, "null ID"),
        ({"outcome": "RESOLVED", "id": "outside"}, "outside"),
        ({"outcome": "RESOLVED", "id": "a", "extra": True}, "schema"),
        (["RESOLVED", "a"], "schema"),
    ],
)
def test_invalid_model_output_fails_closed(output: object, message: str) -> None:
    """Reject malformed, inconsistent, and out-of-candidate model decisions."""
    with pytest.raises(ContextualResolutionError, match=message):
        validate_contextual_decision(output, {"a", "b"})


@pytest.mark.parametrize(
    ("output", "outcome", "identity"),
    [
        ({"outcome": "RESOLVED", "id": "a"}, "RESOLVED", "a"),
        ({"outcome": "AMBIGUOUS", "id": None}, "AMBIGUOUS", None),
        ({"outcome": "UNRESOLVED", "id": None}, "UNRESOLVED", None),
    ],
)
def test_valid_model_output_is_accepted(output: object, outcome: str, identity: str | None) -> None:
    """Accept each valid outcome only with its required ID semantics."""
    decision = validate_contextual_decision(output, {"a", "b"})

    assert decision.outcome == outcome
    assert decision.id == identity
