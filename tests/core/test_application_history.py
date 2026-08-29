"""Focused request-boundary coverage for Phase 17C history integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

import odyssey_core.application as application
from odyssey_core import (
    ApplicationStatus,
    DelegateAction,
    GitHistoryResult,
    HistoryStatus,
    RequestPlan,
    RetrieveAction,
    SelectionCriteria,
)
from odyssey_core.git_history import GitHistorySnapshot


@dataclass
class FakePlanner:
    """Return one fixed plan or planning failure without contacting a provider."""

    value: RequestPlan | Exception

    def plan(self, request: str) -> RequestPlan:
        """Return the configured plan or raise its configured exception."""
        del request
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


class FakeHistoryRecorder:
    """Provide controllable request-level history behavior for application tests."""

    def __init__(self, *, begin_error: Exception | None = None, record_error: Exception | None = None):
        self.begin_error = begin_error
        self.record_error = record_error
        self.begin_calls = 0
        self.record_calls = 0

    def begin(self, request_id: str) -> GitHistorySnapshot:
        """Return an empty snapshot unless a begin failure was configured."""
        del request_id
        self.begin_calls += 1
        if self.begin_error is not None:
            raise self.begin_error
        return GitHistorySnapshot(frozenset())

    def record(self, **kwargs: Any) -> GitHistoryResult:
        """Return no-change history unless a record failure was configured."""
        del kwargs
        self.record_calls += 1
        if self.record_error is not None:
            raise self.record_error
        return GitHistoryResult(HistoryStatus.NO_CHANGES)


class FakePendingRecorder:
    """Persist one synthetic pending record while observing history evidence."""

    def __init__(self) -> None:
        self.history_status: HistoryStatus | None = None

    def record(self, **kwargs: Any) -> str:
        """Capture the application history status and return a fixed record ID."""
        result = kwargs["result"]
        self.history_status = result.history.status
        return "request-history"


def execute(
    plan_or_error: RequestPlan | Exception,
    *,
    history_recorder: FakeHistoryRecorder | None,
    pending_recorder: FakePendingRecorder | None = None,
):
    """Run one application request with inert non-history dependencies."""
    return application.execute_request(
        "request",
        planner=FakePlanner(plan_or_error),
        repository=object(),
        schema={},
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="test",
        now="2026-08-29T10:00:00+02:00",
        context_limit=5,
        request_id_factory=lambda: "request-history",
        history_recorder=history_recorder,
        pending_recorder=pending_recorder,
    )


def retrieval_plan() -> RequestPlan:
    """Build one provider-free retrieval plan for request-boundary tests."""
    return RequestPlan((RetrieveAction(SelectionCriteria(None, "Marta", None, (), None)),), ())


def test_planning_failure_does_not_touch_configured_history() -> None:
    """History remains not-attempted when no valid RequestPlan exists."""
    recorder = FakeHistoryRecorder()

    result = execute(RuntimeError("planner unavailable"), history_recorder=recorder)

    assert result.status is ApplicationStatus.FAILED
    assert result.history.status is HistoryStatus.NOT_ATTEMPTED
    assert recorder.begin_calls == 0
    assert recorder.record_calls == 0


def test_history_begin_failure_is_bounded_and_request_execution_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A snapshot failure is operational evidence rather than application authority."""
    retrieved = object()
    monkeypatch.setattr(application, "get_context", lambda *args, **kwargs: retrieved)
    recorder = FakeHistoryRecorder(begin_error=RuntimeError("git unavailable"))

    result = execute(retrieval_plan(), history_recorder=recorder)

    assert result.status is ApplicationStatus.COMPLETED
    assert result.action_results[0].retrieval is retrieved
    assert result.history.status is HistoryStatus.FAILED
    assert recorder.begin_calls == 1
    assert recorder.record_calls == 0


def test_history_record_failure_is_bounded_after_request_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A finalize failure is reported without changing the completed application result."""
    retrieved = object()
    monkeypatch.setattr(application, "get_context", lambda *args, **kwargs: retrieved)
    recorder = FakeHistoryRecorder(record_error=RuntimeError("commit unavailable"))

    result = execute(retrieval_plan(), history_recorder=recorder)

    assert result.status is ApplicationStatus.COMPLETED
    assert result.action_results[0].retrieval is retrieved
    assert result.history.status is HistoryStatus.FAILED
    assert recorder.begin_calls == 1
    assert recorder.record_calls == 1


def test_history_disabled_remains_explicit_and_backward_compatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitting the optional recorder preserves normal execution with DISABLED evidence."""
    monkeypatch.setattr(application, "get_context", lambda *args, **kwargs: object())

    result = execute(retrieval_plan(), history_recorder=None)

    assert result.status is ApplicationStatus.COMPLETED
    assert result.history.status is HistoryStatus.DISABLED


def test_pending_work_persists_independently_from_history() -> None:
    """Phase 17B pending evidence preserves the already-computed Phase 17C result."""
    history = FakeHistoryRecorder()
    pending = FakePendingRecorder()
    plan = RequestPlan((DelegateAction("translate this", None),), ())

    result = execute(plan, history_recorder=history, pending_recorder=pending)

    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.history.status is HistoryStatus.NO_CHANGES
    assert result.pending_work.persisted is True
    assert result.pending_work.record_id == "request-history"
    assert pending.history_status is HistoryStatus.NO_CHANGES
