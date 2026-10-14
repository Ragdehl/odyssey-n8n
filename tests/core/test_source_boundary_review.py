"""Core's independent, bounded, source-bound review BEFORE any semantic write."""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from odyssey_core.source_boundary_review import (
    CoreSourceBoundaryInput,
    CoreSourceBoundaryUnit,
    OpenAICoreSourceBoundaryReviewer,
    SourceBoundaryReviewError,
    parse_core_source_boundary_review,
    source_boundary_review_json_schema,
)

SOURCE = "The pump failed. The generator overheated."


def input_context() -> CoreSourceBoundaryInput:
    boundary = SOURCE.index(" The generator")
    return CoreSourceBoundaryInput(
        SOURCE,
        (
            CoreSourceBoundaryUnit(
                0, boundary, "core", ("occurrence",), ("independent_assertion",)
            ),
            CoreSourceBoundaryUnit(
                boundary, len(SOURCE), "core", ("occurrence",), ("independent_assertion",)
            ),
        ),
    )


@pytest.mark.parametrize(
    ("decision", "index", "reason"),
    [
        ("accept", 0, None),
        ("revise", 1, "DEPENDENT_SOURCE_FRAGMENT"),
        ("needs_attention", 1, "INDEPENDENCE_NOT_PROVEN"),
    ],
)
def test_exact_valid_core_review_decision(decision, index, reason):
    context = input_context()
    result = parse_core_source_boundary_review(
        context, {"decision": decision, "boundary_index": index, "reason": reason}
    )
    assert result.source_digest == context.source_digest
    assert result.partition_digest == context.partition_digest
    assert result.decision == decision
    assert context.model_payload().count("source") >= 1


@pytest.mark.parametrize(
    "raw",
    [
        {"decision": "approve_writes", "boundary_index": 0, "reason": None},
        {"decision": "accept", "boundary_index": 1, "reason": None},
        {"decision": "accept", "boundary_index": 0, "reason": "SPLIT_LOSES_CONTEXT"},
        {"decision": "revise", "boundary_index": 0, "reason": "DEPENDENT_SOURCE_FRAGMENT"},
        {"decision": "revise", "boundary_index": 2, "reason": "DEPENDENT_SOURCE_FRAGMENT"},
        {"decision": "revise", "boundary_index": 1, "reason": "invented"},
        {"decision": "revise", "boundary_index": True, "reason": "SPLIT_LOSES_CONTEXT"},
        {"decision": "revise", "boundary_index": 1, "reason": "SPLIT_LOSES_CONTEXT", "write": True},
    ],
)
def test_invalid_or_authority_bearing_core_review_fails_closed(raw):
    with pytest.raises(SourceBoundaryReviewError):
        parse_core_source_boundary_review(input_context(), raw)


def test_core_reviewer_cannot_approve_stale_or_modified_partition():
    context = input_context()
    review = parse_core_source_boundary_review(
        context, {"decision": "accept", "boundary_index": 0, "reason": None}
    )
    with pytest.raises(SourceBoundaryReviewError, match="stale|partition"):
        review.validate(replace(context, source=context.source + " Goodbye."))
    with pytest.raises(SourceBoundaryReviewError, match="stale|partition"):
        review.validate(
            replace(
                context,
                routes=(
                    CoreSourceBoundaryUnit(
                        0,
                        context.routes[0].end,
                        "temporal",
                        ("occurrence",),
                        ("independent_assertion",),
                    ),
                    context.routes[1],
                ),
            )
        )


@pytest.mark.parametrize(
    "units",
    [
        (
            CoreSourceBoundaryUnit(0, 12, "core", ("occurrence",), ("independent_assertion",)),
            CoreSourceBoundaryUnit(
                13, len(SOURCE), "core", ("occurrence",), ("independent_assertion",)
            ),
        ),
        (
            CoreSourceBoundaryUnit(
                0, len(SOURCE) + 1, "core", ("occurrence",), ("independent_assertion",)
            ),
        ),
        (
            CoreSourceBoundaryUnit(
                0, len(SOURCE), "invalid space!", ("occurrence",), ("independent_assertion",)
            ),
        ),
    ],
)
def test_source_boundary_context_rejects_gaps_unsafe_caps_or_out_of_range(units):
    with pytest.raises(SourceBoundaryReviewError):
        CoreSourceBoundaryInput(SOURCE, units).validate()


def test_boundary_review_allows_new_app_capabilities_without_core_imports():
    context = input_context()
    changed = replace(
        context,
        routes=(
            replace(context.routes[0], capability="events"),
            replace(context.routes[1], capability="custom-tool.v2"),
        ),
    )
    changed.validate()
    review = parse_core_source_boundary_review(
        changed, {"decision": "accept", "boundary_index": 0, "reason": None}
    )
    assert (
        review.partition_digest
        != parse_core_source_boundary_review(
            context, {"decision": "accept", "boundary_index": 0, "reason": None}
        ).partition_digest
    )


def test_model_reviewer_uses_gpt56_low_store_false_and_enum_reply():
    context = input_context()
    calls = []

    class FakeClient:
        class Responses:
            def create(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(
                    status="completed",
                    output_text=json.dumps(
                        {"decision": "revise", "boundary_index": 1, "reason": "SPLIT_LOSES_CONTEXT"}
                    ),
                    usage={"input_tokens": 120, "output_tokens": 23},
                )

        responses = Responses()

    reviewer = OpenAICoreSourceBoundaryReviewer(FakeClient())
    reply = reviewer.review(context)
    assert reply.decision == "revise"
    assert reply.reason == "SPLIT_LOSES_CONTEXT"
    assert reviewer.model == "gpt-5.6-luna"
    assert reviewer.reasoning_effort == "low"
    assert len(calls) == 1
    assert calls[0]["store"] is False
    assert calls[0]["max_output_tokens"] <= 400
    assert calls[0]["reasoning"]["effort"] == "low"
    assert calls[0]["text"]["format"]["schema"] == source_boundary_review_json_schema()
    assert calls[0]["input"][1]["content"].count("The pump failed.") == 2


def test_review_result_never_contains_free_text_explanations():
    context = input_context()
    raw = {"decision": "revise", "boundary_index": 1, "reason": "SPLIT_LOSES_CONTEXT"}
    review = parse_core_source_boundary_review(context, raw)
    assert not hasattr(review, "model_reasoning")
    assert not hasattr(review, "new_plan")
    assert review.boundary_index == 1
