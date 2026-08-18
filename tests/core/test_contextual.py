"""Tests for blind contextual requests and fail-closed Core validation."""

from __future__ import annotations

import json

import pytest

from odyssey_core.contextual import (
    SOL_FEW_SHOT_PROMPT_CACHE_KEY,
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
    assert turns[1]["content"][0]["type"] == "input_text"
    assert "prompt_cache_breakpoint" in turns[1]["content"][0]
    assert "EVALUATION-REFERENCE" in turns[-1]["content"]
    assert "EVALUATION-CONTEXT" in turns[-1]["content"]
    assert "case_id" not in json.dumps(payload).casefold()


def test_frozen_prefix_breakpoint_marks_final_calibration_user_turn() -> None:
    """Mark only the final calibration user block and preserve the full few-shot sequence."""
    examples = tuple(
        ContextualResolutionExample(
            request=request(),
            decision=ContextualResolutionDecision("RESOLVED", "beatriz-costa"),
        )
        for _ in range(10)
    )

    payload = build_openai_payload(request(), "gpt-5.6-sol", examples=examples)
    uncached = build_openai_payload(
        request(), "gpt-5.6-sol", examples=examples, prompt_cache_key=None
    )
    turns = payload["input"]
    breakpoints = [
        (index, block)
        for index, turn in enumerate(turns)
        for block in (turn["content"] if isinstance(turn["content"], list) else [])
        if "prompt_cache_breakpoint" in block
    ]

    assert payload["prompt_cache_key"] == SOL_FEW_SHOT_PROMPT_CACHE_KEY
    assert payload["prompt_cache_options"] == {"mode": "explicit"}
    assert len(breakpoints) == 1
    assert breakpoints[0][0] == len(turns) - 3
    assert turns[breakpoints[0][0]]["role"] == "user"
    assert turns[breakpoints[0][0] + 1]["role"] == "assistant"
    assert turns[breakpoints[0][0] + 1] == uncached["input"][breakpoints[0][0] + 1]
    assert turns[-1]["role"] == "user"
    assert isinstance(turns[-1]["content"], str)
    assert "prompt_cache_breakpoint" not in json.dumps(turns[-1])
    assert all(turn["role"] != "developer" for turn in turns)
    assert len(turns) == 22


def test_cache_configuration_does_not_change_semantic_prompt_or_contract() -> None:
    """Keep prompt meaning and output validation identical across cache configurations."""
    example = ContextualResolutionExample(
        request=request(), decision=ContextualResolutionDecision("RESOLVED", "beatriz-costa")
    )
    cached = build_openai_payload(request(), "gpt-5.6-sol", examples=(example,))
    changed_key = build_openai_payload(
        request(), "gpt-5.6-sol", examples=(example,), prompt_cache_key="another-stable-key"
    )
    uncached = build_openai_payload(
        request(), "gpt-5.6-sol", examples=(example,), prompt_cache_key=None
    )

    def semantic_payload(payload):
        """Remove only cache transport metadata from one test payload."""
        normalized = json.loads(json.dumps(payload))
        normalized.pop("prompt_cache_key", None)
        normalized.pop("prompt_cache_options", None)
        for turn in normalized["input"]:
            if isinstance(turn["content"], list):
                turn["content"] = turn["content"][0]["text"]
        return normalized

    assert semantic_payload(cached) == semantic_payload(changed_key) == semantic_payload(uncached)
    for payload in (cached, changed_key, uncached):
        assert payload["store"] is False
        assert payload["reasoning"] == {"effort": "medium"}
        assert payload["text"] == uncached["text"]


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
