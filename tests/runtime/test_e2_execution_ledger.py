"""Read-only E2 execution ledger joins actual checkpoints and Core receipts."""

from __future__ import annotations

from dataclasses import replace

import pytest

from odyssey_core.application import (
    ActionResult,
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
    UnitResult,
    UnitStatus,
)
from odyssey_core.observability import OperationalEvidence, OperationalOutcome, OperationalStage
from odyssey_runtime.execution_checkpoints import CheckpointOutcome, LocalExecutionCheckpointStore
from odyssey_runtime.execution_ledger import project_execution_ledger
from tests.runtime.test_execution_checkpoints import NOW


def partial_result():
    return ApplicationResult(
        "test-ledger",
        ApplicationStatus.PARTIAL,
        (
            ActionResult(
                0,
                "write",
                ActionStatus.COMPLETED,
                unit_results=(UnitResult(0, UnitStatus.SUCCEEDED, "UPDATED", "date:2026-10-15"),),
            ),
            ActionResult(
                1,
                "write",
                ActionStatus.FAILED,
                unit_results=(
                    UnitResult(0, UnitStatus.FAILED, "UPDATED", None, reason="STALE_NOTE"),
                ),
            ),
        ),
        ("date:2026-10-15",),
        operational=OperationalEvidence(
            51,
            (
                OperationalStage("temporal.interpretation", OperationalOutcome.COMPLETED, 20),
                OperationalStage(
                    "planner", OperationalOutcome.FAILED, 31, error_category="ProviderError"
                ),
            ),
        ),
        execution_flow={
            "version": 1,
            "input": "Private request never copied",
            "parallel_preparation": False,
            "routes": [
                {"capability": "temporal", "text": "secret route A", "status": "completed"},
                {
                    "capability": "tasks",
                    "text": "secret route B",
                    "status": "failed",
                    "depends_on": 0,
                },
            ],
        },
    )


def test_partial_write_ledger_preserves_only_confirmed_receipt_and_stage_error(tmp_path):
    checkpoint = LocalExecutionCheckpointStore(tmp_path / "ledger")
    checkpoint.record("test-ledger", "starting", CheckpointOutcome.MILESTONE_OBSERVED, NOW)
    checkpoint.record(
        "test-ledger", "core.notes.started", CheckpointOutcome.MILESTONE_OBSERVED, NOW
    )
    checkpoint.record("test-ledger", "core.notes.ready", CheckpointOutcome.MILESTONE_OBSERVED, NOW)
    report = project_execution_ledger(partial_result(), checkpoint.load("test-ledger"))
    assert report["version"] == 1
    assert report["status"] == "partial"
    assert [x["sequence"] for x in report["events"]] == [1, 2, 3]
    assert report["events"][2]["stage"] == "core.notes.ready"
    assert report["event_sequence"] == 3
    assert report["stages"][1]["error_category"] == "ProviderError"
    assert report["stages"][1]["route_index"] is None  # route attribution not guessed
    assert report["routes"] == [
        {"route_index": 0, "capability": "temporal", "status": "completed", "depends_on": None},
        {"route_index": 1, "capability": "tasks", "status": "failed", "depends_on": 0},
    ]
    assert report["write_receipts"] == [
        {
            "action_index": 0,
            "unit_index": 0,
            "stable_note_id": "date:2026-10-15",
            "operation": "UPDATED",
            "status": "succeeded",
        }
    ]
    assert report["affected_stable_note_ids"] == ["date:2026-10-15"]
    assert "secret" not in str(report)
    assert "Private request" not in str(report)


def test_read_model_never_invents_success_or_loses_affected_ids_on_failure():
    result = replace(partial_result(), action_results=(), status=ApplicationStatus.FAILED)
    projection = project_execution_ledger(result)
    assert projection["write_receipts"] == []
    assert projection["affected_stable_note_ids"] == ["date:2026-10-15"]
    assert projection["event_sequence"] is None
    assert projection["events"] == []


def test_checkpoint_identity_cross_actor_or_delivery_mismatch_is_rejected(tmp_path):
    checkpoint = LocalExecutionCheckpointStore(tmp_path / "ledger")
    checkpoint.record("other-delivery", "starting", CheckpointOutcome.MILESTONE_OBSERVED, NOW)
    with pytest.raises(ValueError, match="different request IDs"):
        project_execution_ledger(partial_result(), checkpoint.load("other-delivery"))


def test_actual_runtime_attaches_actor_root_verified_checkpoint_to_returned_result(tmp_path):
    from odyssey_core.identity_boundary import AuthenticatedActorContext
    from odyssey_core.local_conversations import ConversationRootResolver
    from odyssey_runtime import composition
    from odyssey_runtime.composition import RuntimeComposition

    actor = AuthenticatedActorContext("11111111-1111-4111-8111-111111111111")

    def executor(_message, request_id, *_args, **_kwargs):
        composition._emit_progress("core.notes.started")
        composition._emit_progress("core.notes.ready")
        return replace(partial_result(), request_id=request_id)

    runtime = RuntimeComposition(
        core_execute=executor,
        refresh_indexes=lambda: None,
        conversation_root_resolver=ConversationRootResolver(tmp_path / "state"),
        execution_checkpoint_store_factory=LocalExecutionCheckpointStore,
    )
    result = runtime.execute_product("Private fact source", "live-ledger", "main", actor)
    assert result["request_id"] == "live-ledger"
    ledger = result["execution_ledger"]
    assert ledger["request_id"] == "live-ledger"
    stages = [event["stage"] for event in ledger["events"]]
    assert stages.index("core.notes.started") < stages.index("core.notes.ready")
    assert stages[-1] == "finalizing"
    assert ledger["write_receipts"][0]["stable_note_id"] == "date:2026-10-15"
    replay = runtime.execute_product("Private fact source", "live-ledger", "main", actor)
    assert replay["delivery_replayed"] is True
    assert replay["execution_ledger"] == ledger


def test_succeeded_but_nonmaterial_known_fact_does_not_fabricate_write_receipt():
    result = partial_result()
    first = result.action_results[0]
    unit = first.unit_results[0]
    altered = replace(
        result,
        action_results=(
            replace(first, unit_results=(replace(unit, materially_affected=False),)),
            result.action_results[1],
        ),
    )
    assert project_execution_ledger(altered)["write_receipts"] == []
    assert project_execution_ledger(altered)["affected_stable_note_ids"] == ["date:2026-10-15"]


def test_future_app_checkpoint_uses_same_safe_names_without_new_allowlist(tmp_path):
    store = LocalExecutionCheckpointStore(tmp_path / "new-app")
    store.record(
        "future-1", "events.classify_occurrence.started", CheckpointOutcome.MILESTONE_OBSERVED, NOW
    )
    store.record(
        "future-1", "events.classify_occurrence.ready", CheckpointOutcome.MILESTONE_OBSERVED, NOW
    )
    assert [entry["stage"] for entry in store.load("future-1")["events"]] == [
        "events.classify_occurrence.started",
        "events.classify_occurrence.ready",
    ]
    from odyssey_runtime.execution_checkpoints import ExecutionCheckpointError

    with pytest.raises(ExecutionCheckpointError):
        store.record(
            "future-1", "private user name.started", CheckpointOutcome.MILESTONE_OBSERVED, NOW
        )
