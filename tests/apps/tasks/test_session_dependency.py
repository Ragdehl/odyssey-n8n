"""Session anaphora is reviewed before writes and never selects a Note ID."""

from copy import deepcopy

import pytest

from odyssey_apps.tasks import (
    SessionDependencyError,
    TaskInterpretation,
    TaskOperation,
    verify_session_dependency,
)

SOURCE_A = "Inicia una sesión de trabajo en Atlas. "
SOURCE_B = "Después termina la sesión en Atlas."
SOURCE = SOURCE_A + SOURCE_B


def _args():
    first = TaskInterpretation(
        SOURCE_A.strip(), TaskOperation.START_WORK_SESSION, task_reference="Atlas"
    )
    second = TaskInterpretation(
        SOURCE_B.strip(), TaskOperation.STOP_WORK_SESSION, task_reference="Atlas"
    )
    review = {
        "full_source_quote": SOURCE,
        "producer_quote": SOURCE_A,
        "consumer_quote": SOURCE_B,
        "source_mention": "una sesión de trabajo",
        "dependent_mention": "la sesión",
        "producer_operation": "START_WORK_SESSION",
        "consumer_operation": "STOP_WORK_SESSION",
        "one_session": True,
        "same_session": True,
        "operation_supported": True,
    }
    return {
        "full_source": SOURCE,
        "producer_source": SOURCE_A,
        "consumer_source": SOURCE_B,
        "source_mention": "una sesión de trabajo",
        "dependent_mention": "la sesión",
        "producer_index": 0,
        "consumer_index": 1,
        "producer": first,
        "consumer": second,
        "reviews": [deepcopy(review), deepcopy(review)],
    }


def test_session_dependency_requires_two_exact_semantic_attestations():
    args = _args()
    evidence = verify_session_dependency(**args)
    assert (evidence.producer_index, evidence.consumer_index) == (0, 1)
    assert evidence.consumer_operation is TaskOperation.STOP_WORK_SESSION
    assert not hasattr(evidence, "session_id")


@pytest.mark.parametrize(
    "change",
    [
        "unreviewed",
        "one_reviewer",
        "ambiguous",
        "different_session",
        "wrong_operation",
        "wrong_source",
        "wrong_mention",
        "duplicate_mention",
        "forward_reference",
        "boolean_index",
        "extra_id",
        "producer_not_start",
    ],
)
def test_invalid_or_ambiguous_task_session_relation_does_not_claim_proof(change):
    args = _args()
    if change == "unreviewed":
        args["reviews"] = []
    elif change == "one_reviewer":
        args["reviews"] = args["reviews"][:1]
    elif change == "ambiguous":
        args["reviews"][1]["one_session"] = False
    elif change == "different_session":
        args["reviews"][0]["same_session"] = False
    elif change == "wrong_operation":
        args["reviews"][1]["consumer_operation"] = "EDIT_WORK_SESSION"
    elif change == "wrong_source":
        args["reviews"][0]["producer_quote"] = "other"
    elif change == "wrong_mention":
        args["dependent_mention"] = "otra sesión"
    elif change == "duplicate_mention":
        args["consumer_source"] += " También la sesión."
    elif change == "forward_reference":
        args["producer_index"] = 2
    elif change == "boolean_index":
        args["consumer_index"] = True
    elif change == "extra_id":
        args["reviews"][0]["canonical_note_id"] = "injected"
    elif change == "producer_not_start":
        args["producer"] = TaskInterpretation(
            SOURCE_A.strip(), TaskOperation.STOP_WORK_SESSION, task_reference="Atlas"
        )
    with pytest.raises(SessionDependencyError):
        verify_session_dependency(**args)
