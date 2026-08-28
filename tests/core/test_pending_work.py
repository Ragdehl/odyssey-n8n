"""Deterministic Phase 17B pending-work repository and application coverage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import odyssey_core.application as application
import odyssey_core.pending_work as pending_work
from odyssey_core import (
    ActionResult,
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
    BulkUpdateFailure,
    BulkUpdateResult,
    BulkUpdateSuccess,
    DelegateAction,
    DependencyEvidence,
    KnowledgeReference,
    KnowledgeUnit,
    PendingWorkError,
    PendingWorkRepository,
    RequestPlan,
    RetrieveAction,
    SelectionCriteria,
    UnitResult,
    UnitStatus,
    WriteAction,
)
from odyssey_core.persistence import EntityPersistenceResult, PersistenceOperation


def selection(name: str | None = "Laura") -> SelectionCriteria:
    """Build a compact validated-shaped selection for pending-work evidence."""
    return SelectionCriteria(name, name or "people", "person", (), None)


def write_action() -> WriteAction:
    """Build a two-unit action whose source retains multiple local reference indexes."""
    return WriteAction(
        (
            KnowledgeUnit(
                selection(),
                "record",
                (),
                (),
                ("Laura knows Marta and works at Airbus.",),
                (
                    KnowledgeReference(1, "friend", "Marta"),
                    KnowledgeReference(2, "employer", "Airbus"),
                ),
            ),
            KnowledgeUnit(selection("Marta"), "record", (), (), (), ()),
            KnowledgeUnit(selection("Airbus"), "record", (), (), (), ()),
        )
    )


def incomplete_result(action: WriteAction) -> ApplicationResult:
    """Build partial execution evidence including a success and all dependency evidence."""
    return ApplicationResult(
        "request-17b",
        ApplicationStatus.PARTIAL,
        (
            ActionResult(
                0,
                action.kind,
                ActionStatus.DEFERRED,
                unit_results=(
                    UnitResult(
                        0,
                        UnitStatus.DEFERRED,
                        reason="REFERENCE_DEPENDENCY_UNRESOLVED",
                        dependencies=(
                            DependencyEvidence(0, 1, "ambiguous Marta", ("marta-1", "marta-2")),
                            DependencyEvidence(0, 2, "ambiguous Airbus", ("airbus-1",)),
                        ),
                    ),
                    UnitResult(1, UnitStatus.DEFERRED, reason="ambiguous Marta"),
                    UnitResult(2, UnitStatus.SUCCEEDED, stable_note_id="airbus-1"),
                ),
            ),
        ),
        ("airbus-1",),
    )


def test_record_round_trip_preserves_whole_action_and_all_dependencies(tmp_path: Path) -> None:
    """Persist exact request intent and every dependency without a model or membership rerun."""
    action = write_action()
    repository = PendingWorkRepository(tmp_path)
    assert (
        repository.record(
            user_request="Remember Laura's employer.",
            plan=RequestPlan((action,), ("requires clarification",)),
            result=incomplete_result(action),
            created_at="2026-08-28T12:00:00Z",
        )
        == "request-17b"
    )

    record = repository.read("request-17b")
    assert repository.list_ids() == ("request-17b",)
    assert record["user_request"] == "Remember Laura's employer."
    assert record["planner_limitations"] == ["requires clarification"]
    assert record["affected_stable_note_ids"] == ["airbus-1"]
    saved = record["incomplete_actions"][0]
    assert len(saved["planned_action"]["units"]) == 3
    assert saved["execution_result"]["unit_results"][0]["dependencies"] == [
        {
            "source_unit_index": 0,
            "target_unit_index": 1,
            "reason": "ambiguous Marta",
            "candidate_stable_ids": ["marta-1", "marta-2"],
        },
        {
            "source_unit_index": 0,
            "target_unit_index": 2,
            "reason": "ambiguous Airbus",
            "candidate_stable_ids": ["airbus-1"],
        },
    ]


def test_bulk_evidence_and_delegate_are_projected_without_execution(tmp_path: Path) -> None:
    """Keep frozen bulk outcomes and delegated intent as open pending evidence."""
    bulk = ActionResult(
        0,
        "write",
        ActionStatus.FAILED,
        bulk_result=BulkUpdateResult(
            "all_matching",
            ("a", "b"),
            (
                BulkUpdateSuccess(
                    "a",
                    EntityPersistenceResult(PersistenceOperation.UPDATED, "a", "A.md", 3),
                ),
            ),
            (BulkUpdateFailure("b", "OSError", "disk"),),
            "PARTIAL_SUCCESS",
        ),
    )
    delegate = DelegateAction("translate this", selection())
    result = ApplicationResult("request-bulk", ApplicationStatus.PARTIAL, (bulk,), ("a",))
    repository = PendingWorkRepository(tmp_path)
    repository.record(
        user_request="Update and translate",
        plan=RequestPlan(
            (WriteAction((KnowledgeUnit(selection(), "amend", (), (), (), (), "all_matching"),)),),
            (),
        ),
        result=result,
        created_at="now",
    )
    record = repository.read("request-bulk")
    assert record["incomplete_actions"][0]["execution_result"]["bulk_result"][
        "selected_note_ids"
    ] == ["a", "b"]
    bulk_evidence = record["incomplete_actions"][0]["execution_result"]["bulk_result"]
    assert bulk_evidence["succeeded"] == [
        {
            "stable_id": "a",
            "result": {"operation": "UPDATED", "id": "a", "path": "A.md", "revision": 3},
        }
    ]
    assert bulk_evidence["failed"] == [
        {"stable_id": "b", "error_type": "OSError", "reason": "disk"}
    ]
    assert bulk_evidence["status"] == "PARTIAL_SUCCESS"

    delegated_result = ApplicationResult(
        "request-delegate",
        ApplicationStatus.NEEDS_ATTENTION,
        (
            ActionResult(
                0,
                "delegate",
                ActionStatus.DEFERRED,
                delegated_request="translate this",
                delegated_selection=selection(),
                reason="DELEGATED_CAPABILITY",
            ),
        ),
        (),
    )
    repository.record(
        user_request="Translate",
        plan=RequestPlan((delegate,), ()),
        result=delegated_result,
        created_at="now",
    )
    assert (
        repository.read("request-delegate")["incomplete_actions"][0]["planned_action"]["request"]
        == "translate this"
    )


@pytest.mark.parametrize("request_id", ("", "../x", "/absolute", "a/b", "a\\b"))
def test_unsafe_ids_and_duplicate_creation_fail_closed(tmp_path: Path, request_id: str) -> None:
    """Reject unsafe paths and never replace an existing pending record."""
    repository = PendingWorkRepository(tmp_path)
    with pytest.raises(PendingWorkError):
        repository.read(request_id)

    action = write_action()
    args: dict[str, Any] = {
        "user_request": "x",
        "plan": RequestPlan((action,), ()),
        "result": incomplete_result(action),
        "created_at": "now",
    }
    repository.record(**args)
    original = (tmp_path / "request-17b.json").read_text(encoding="utf-8")
    with pytest.raises(PendingWorkError, match="already exists"):
        repository.record(**args)
    assert (tmp_path / "request-17b.json").read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    "payload", ("{", '{"format":"wrong"}', '{"format":"odyssey_pending_work","format_version":2}')
)
def test_malformed_or_incompatible_json_is_rejected(tmp_path: Path, payload: str) -> None:
    """Fail closed on unreadable JSON and unsupported record marker/version."""
    path = tmp_path / "request-17b.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(PendingWorkError):
        PendingWorkRepository(tmp_path).read("request-17b")


def test_symlinked_record_is_rejected_without_following_it(tmp_path: Path) -> None:
    """Keep all pending reads and listings beneath the configured pending root."""
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    (tmp_path / "request-17b.json").symlink_to(outside)
    repository = PendingWorkRepository(tmp_path)
    with pytest.raises(PendingWorkError):
        repository.read("request-17b")
    with pytest.raises(PendingWorkError):
        repository.list_ids()


def test_failed_temporary_write_leaves_no_final_record_and_allows_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Remove failed staging output so a later clean create remains possible."""
    action = write_action()
    args: dict[str, Any] = {
        "user_request": "x",
        "plan": RequestPlan((action,), ()),
        "result": incomplete_result(action),
        "created_at": "now",
    }
    repository = PendingWorkRepository(tmp_path)

    def fail_write(*_args: Any, **_kwargs: Any) -> Path:
        """Simulate a disk failure during complete temporary-file construction."""
        raise OSError("disk full")

    monkeypatch.setattr(pending_work, "_write_temporary", fail_write)
    with pytest.raises(PendingWorkError):
        repository.record(**args)
    assert not (tmp_path / "request-17b.json").exists()

    monkeypatch.undo()
    assert repository.record(**args) == "request-17b"


def test_execute_request_reports_missing_or_successful_pending_recorder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Attach explicit durability evidence after a valid plan without rerunning it."""
    action = write_action()
    plan = RequestPlan((action,), ())
    monkeypatch.setattr(
        application,
        "_execute_write",
        lambda *_args, **_kwargs: incomplete_result(action).action_results[0],
    )
    args = dict(
        planner=type("Planner", (), {"plan": lambda self, request: plan})(),
        repository=object(),
        schema={},
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="test",
        now="2026-08-28T12:00:00Z",
        context_limit=1,
        request_id_factory=lambda: "request-17b",
    )
    missing = application.execute_request("raw", **args)
    assert missing.pending_work.required and not missing.pending_work.persisted
    persisted = application.execute_request(
        "raw", pending_recorder=PendingWorkRepository(tmp_path), **args
    )
    assert persisted.pending_work.persisted and persisted.pending_work.record_id == "request-17b"
    assert (tmp_path / "request-17b.json").exists()


def test_runtime_error_from_recorder_is_returned_as_durability_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch ordinary custom-recorder exceptions while preserving execution evidence."""
    action = write_action()
    evidence = incomplete_result(action).action_results[0]
    plan = RequestPlan((action,), ())
    monkeypatch.setattr(application, "_execute_write", lambda *_args, **_kwargs: evidence)

    class RuntimeFailingRecorder:
        """Simulate an adapter-specific ordinary failure."""

        def record(self, **kwargs: Any) -> str:
            """Raise the backend failure that must not escape the application boundary."""
            raise RuntimeError("pending backend unavailable")

    result = application.execute_request(
        "raw",
        planner=type("Planner", (), {"plan": lambda self, request: plan})(),
        repository=object(),
        schema={},
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="test",
        now="now",
        context_limit=1,
        request_id_factory=lambda: "request-17b",
        pending_recorder=RuntimeFailingRecorder(),
    )
    assert result.status is ApplicationStatus.PARTIAL
    assert result.action_results == (evidence,)
    assert result.affected_stable_note_ids == ("airbus-1",)
    assert result.pending_work == application.PendingWorkStatus(
        required=True, persisted=False, error="pending backend unavailable"
    )


def test_completed_and_preplan_failure_never_call_pending_recorder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Avoid records before a valid plan and after fully completed execution."""
    calls: list[dict[str, Any]] = []

    class Recorder:
        """Capture forbidden recorder calls."""

        def record(self, **kwargs: Any) -> str:
            """Record an invocation so the test can prove it was not required."""
            calls.append(kwargs)
            return "unexpected"

    monkeypatch.setattr(
        application,
        "_execute_retrieve",
        lambda *_args, **_kwargs: ActionResult(0, "retrieve", ActionStatus.COMPLETED),
    )
    # Use a real retrieve action to keep the public executor's type boundary intact.
    retrieve_plan = RequestPlan((RetrieveAction(selection()),), ())
    result = application.execute_request(
        "raw",
        planner=type("Planner", (), {"plan": lambda self, request: retrieve_plan})(),
        repository=object(),
        schema={},
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="test",
        now="now",
        context_limit=1,
        pending_recorder=Recorder(),
    )
    assert result.pending_work.required is False
    assert calls == []

    failed = application.execute_request(
        "raw",
        planner=type(
            "Planner",
            (),
            {"plan": lambda self, request: (_ for _ in ()).throw(RuntimeError("offline"))},
        )(),
        repository=object(),
        schema={},
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="test",
        now="now",
        context_limit=1,
        pending_recorder=Recorder(),
    )
    assert failed.planning_error == "offline"
    assert calls == []


def test_pending_recorder_failure_preserves_application_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Leave prior execution evidence intact when the post-write durability boundary fails."""
    action = write_action()
    evidence = incomplete_result(action).action_results[0]
    monkeypatch.setattr(application, "_execute_write", lambda *_args, **_kwargs: evidence)
    plan = RequestPlan((action,), ())

    class BrokenRecorder:
        """Simulate an expected contained persistence failure."""

        def record(self, **kwargs: Any) -> str:
            """Reject persistence without modifying execution evidence."""
            raise PendingWorkError("pending root is unavailable")

    result = application.execute_request(
        "raw",
        planner=type("Planner", (), {"plan": lambda self, request: plan})(),
        repository=object(),
        schema={},
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="test",
        now="now",
        context_limit=1,
        request_id_factory=lambda: "request-17b",
        pending_recorder=BrokenRecorder(),
    )
    assert result.status is ApplicationStatus.PARTIAL
    assert result.affected_stable_note_ids == ("airbus-1",)
    assert result.pending_work.required and not result.pending_work.persisted
