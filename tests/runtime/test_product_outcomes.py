"""Product-facing outcome regression tests with no provider or network calls."""

from __future__ import annotations

from odyssey_core.application import (
    ActionResult,
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
    UnitResult,
    UnitStatus,
)
from odyssey_core.context import ContextPackage
from odyssey_core.semantic_sets import (
    GroundedSemanticSet,
    LiteralSetMember,
    SemanticSetCompleteness,
    SemanticSetOutcome,
    SemanticSetResolution,
    SetEvidenceProvenance,
)
from odyssey_runtime.serialization import application_result_to_response


def _result(action: ActionResult, status: ApplicationStatus) -> dict:
    """Project one action through the public boundary without a runtime server."""
    return application_result_to_response(ApplicationResult("request", status, (action,), ()))


def test_multiple_grounded_collection_members_are_answer_not_ambiguity() -> None:
    """Cardinality alone must never trigger clarification for a collection."""
    members = tuple(
        LiteralSetMember(
            f"member-{index}",
            SetEvidenceProvenance("source", "fact", "hash", index, index + 1, "literal"),
        )
        for index in range(8)
    )
    grounded = GroundedSemanticSet(
        None, None, members, SemanticSetCompleteness.COMPLETE_WITHIN_SCANNED_SCOPE, 1, 1, 80
    )
    response = _result(
        ActionResult(
            0,
            "retrieve",
            ActionStatus.COMPLETED,
            semantic_set=SemanticSetResolution(SemanticSetOutcome.ANSWERABLE, grounded),
        ),
        ApplicationStatus.COMPLETED,
    )

    assert response["product_outcome"] == "ANSWER"
    assert [member["value"] for member in response["actions"][0]["collection"]["members"]] == [
        f"member-{index}" for index in range(8)
    ]


def test_scope_ambiguity_clarifies_but_missing_evidence_cannot_answer() -> None:
    """Only a resolvable decision is a clarification, not all non-answers."""
    ambiguous = _result(
        ActionResult(
            0,
            "retrieve",
            ActionStatus.DEFERRED,
            semantic_set=SemanticSetResolution(SemanticSetOutcome.AMBIGUOUS_SET_SCOPE),
        ),
        ApplicationStatus.NEEDS_ATTENTION,
    )
    absent = _result(
        ActionResult(
            0,
            "retrieve",
            ActionStatus.DEFERRED,
            semantic_set=SemanticSetResolution(SemanticSetOutcome.NO_RELEVANT_EVIDENCE),
        ),
        ApplicationStatus.NEEDS_ATTENTION,
    )

    assert (ambiguous["product_outcome"], ambiguous["product_reason"]) == (
        "CLARIFY",
        "AMBIGUOUS_SET_SCOPE",
    )
    assert (absent["product_outcome"], absent["product_reason"]) == (
        "CANNOT_ANSWER",
        "NO_RELEVANT_EVIDENCE",
    )


def test_ambiguous_write_target_clarifies_with_only_candidate_ids() -> None:
    """Core may offer a bounded identity decision without fabricating a write target."""
    response = _result(
        ActionResult(
            0,
            "write",
            ActionStatus.DEFERRED,
            unit_results=(
                UnitResult(
                    0,
                    UnitStatus.DEFERRED,
                    reason="ambiguous_existing_target",
                    candidates=("note-one", "note-two"),
                ),
            ),
        ),
        ApplicationStatus.NEEDS_ATTENTION,
    )
    assert response["product_outcome"] == "CLARIFY"
    assert response["product_reason"] == "AMBIGUOUS_REFERENCE"
    assert response["actions"][0]["units"][0]["candidates"] == ["note-one", "note-two"]


def test_note_set_uses_matching_note_snapshot_not_singular_retrieval_cardinality() -> None:
    """Seven matching Notes are a valid set even if the ordinary answer context is empty."""
    result = ApplicationResult(
        "request",
        ApplicationStatus.COMPLETED,
        (
            ActionResult(
                0, "retrieve", ActionStatus.COMPLETED, retrieval=ContextPackage("notes", ())
            ),
        ),
        (),
        presentation_intent="note_set",
        note_result_snapshot={
            "version": 1,
            "query": "notes",
            "filters": [],
            "note_ids": [f"note-{index}" for index in range(7)],
            "total": 7,
            "truncated": False,
        },
    )
    response = application_result_to_response(result)

    assert response["product_outcome"] == "ANSWER"
    assert response["note_result_snapshot"]["note_ids"] == [f"note-{index}" for index in range(7)]
