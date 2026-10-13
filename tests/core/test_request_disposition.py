"""Contract tests for Core-owned execution disposition."""

from odyssey_core.request_planning import (
    DelegateAction,
    RequestDisposition,
    RequestPlan,
    RetrieveAction,
    SelectionCriteria,
    WriteAction,
    request_disposition,
)


def _selection() -> SelectionCriteria:
    """Build the smallest valid selection used only for action ownership tests."""
    return SelectionCriteria(None, "work", None, (), None)


def test_only_retrieval_actions_are_proven_read_only() -> None:
    """Candidate emptiness never participates in the read-only proof."""
    plan = RequestPlan((RetrieveAction(_selection()),), ())

    assert request_disposition(plan) is RequestDisposition.READ_ONLY


def test_writes_delegates_and_mixed_actions_cannot_be_read_executed() -> None:
    """Any non-retrieval action retains its existing guarded execution boundary."""
    write = RequestPlan((WriteAction(()),), ())
    delegate = RequestPlan((DelegateAction("compare", _selection()),), ())
    mixed = RequestPlan((RetrieveAction(_selection()), WriteAction(())), ())

    assert request_disposition(write) is RequestDisposition.WRITE_OR_DELEGATE
    assert request_disposition(delegate) is RequestDisposition.WRITE_OR_DELEGATE
    assert request_disposition(mixed) is RequestDisposition.MIXED
