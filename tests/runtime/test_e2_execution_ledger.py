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


def test_route_aggregate_attaches_actual_owner_to_each_stage_without_guessing():
    from odyssey_runtime.routing import _aggregate, _prepend_router_stage

    a = replace(
        partial_result(),
        request_id="route-1",
        operational=OperationalEvidence(
            stages=(OperationalStage("temporal.interpretation", OperationalOutcome.COMPLETED, 13),)
        ),
    )
    b = replace(
        partial_result(),
        request_id="route-2",
        operational=OperationalEvidence(
            stages=(OperationalStage("planner", OperationalOutcome.FAILED, 18),)
        ),
    )
    aggregate = _aggregate("one-delivery", (a, b))
    router = _prepend_router_stage(
        aggregate, OperationalStage("application.router", OperationalOutcome.COMPLETED, 11)
    )
    assert [st.route_index for st in router.operational.stages] == [None, 0, 1]
    summary = project_execution_ledger(router)
    assert [st["route_index"] for st in summary["stages"]] == [None, 0, 1]


def test_same_id_replay_does_not_add_false_start_or_reset_live_progress(tmp_path):
    from odyssey_core.identity_boundary import AuthenticatedActorContext
    from odyssey_core.local_conversations import ConversationRootResolver
    from odyssey_runtime.composition import RuntimeComposition
    from odyssey_runtime.progress import ProductProgressStore

    identity = AuthenticatedActorContext("11111111-1111-4111-8111-111111111111")
    resolver = ConversationRootResolver(tmp_path / "state")
    calls = []
    runtime = RuntimeComposition(
        core_execute=lambda _text, request_id, *_args, **_kwargs: (
            calls.append(request_id) or replace(partial_result(), request_id=request_id)
        ),
        refresh_indexes=lambda: None,
        conversation_root_resolver=resolver,
        execution_checkpoint_store_factory=LocalExecutionCheckpointStore,
        product_progress_store=ProductProgressStore(),
    )
    first = runtime.execute_product("sensitive fact", "replay-keep", "main", identity)
    first_progress = runtime.product_progress("replay-keep", identity)
    store = LocalExecutionCheckpointStore(
        resolver.resolve(identity.stable_user_id) / "execution-checkpoints"
    )
    old = store.load("replay-keep")
    assert old is not None
    assert [event["stage"] for event in old["events"]].count("starting") == 1
    second = runtime.execute_product("sensitive fact", "replay-keep", "main", identity)
    after = store.load("replay-keep")
    assert first["request_id"] == second["request_id"]
    assert second["delivery_replayed"] is True
    assert calls == ["replay-keep"]
    assert after is not None
    assert after == old  # A replay is not another lifecycle milestone.
    assert [event["stage"] for event in after["events"]].count("starting") == 1
    assert [event["stage"] for event in after["events"]].count("delivery.result_persisted") == 1
    assert after["events"][-1]["stage"] == "delivery.result_persisted"
    assert runtime.product_progress("replay-keep", identity) == first_progress


def test_optional_ledger_failure_does_not_lose_a_verified_delivery(tmp_path, monkeypatch):
    from odyssey_core.identity_boundary import AuthenticatedActorContext
    from odyssey_core.local_conversations import ConversationRootResolver
    from odyssey_runtime import execution_ledger
    from odyssey_runtime.composition import RuntimeComposition

    actor = AuthenticatedActorContext("11111111-1111-4111-8111-111111111111")
    calls = []

    def executor(_message, request_id, *_args, **_kwargs):
        calls.append(request_id)
        return replace(partial_result(), request_id=request_id)

    runtime = RuntimeComposition(
        core_execute=executor,
        refresh_indexes=lambda: None,
        conversation_root_resolver=ConversationRootResolver(tmp_path / "state"),
        execution_checkpoint_store_factory=LocalExecutionCheckpointStore,
    )

    def failed_projection(_result, _checkpoint):
        raise ValueError("unavailable optional diagnostic")

    monkeypatch.setattr(execution_ledger, "project_execution_ledger", failed_projection)
    first = runtime.execute_product("Day fixture", "delivery-optional", "main", actor)
    assert first["affected_stable_note_ids"] == ["date:2026-10-15"]
    assert "execution_ledger" not in first
    replay = runtime.execute_product("Day fixture", "delivery-optional", "main", actor)
    assert replay["delivery_replayed"] is True
    assert replay["affected_stable_note_ids"] == first["affected_stable_note_ids"]
    assert calls == ["delivery-optional"]


def test_no_write_hybrid_decision_checkpoint_reports_real_durable_result(tmp_path):
    from odyssey_core.identity_boundary import AuthenticatedActorContext
    from odyssey_core.local_conversations import ConversationRootResolver
    from odyssey_runtime.composition import RuntimeComposition

    actor = AuthenticatedActorContext("11111111-1111-4111-8111-111111111111")
    resolver = ConversationRootResolver(tmp_path / "state")
    calls = []

    def candidate_executor(source, request_id, *_args, **_kwargs):
        calls.append(source)
        return ApplicationResult(
            request_id,
            ApplicationStatus.NEEDS_ATTENTION,
            (),
            (),
            planning_error="SOURCE_DEPENDENCY_UNVERIFIED",
        )

    runtime = RuntimeComposition(
        core_execute=lambda *_args, **_kwargs: pytest.fail("Hybrid did not run"),
        hybrid_candidate_execute=candidate_executor,
        refresh_indexes=lambda: None,
        conversation_root_resolver=resolver,
        execution_checkpoint_store_factory=LocalExecutionCheckpointStore,
    )
    first = runtime.execute_product("source requires review", "hybrid-no-write", "main", actor)
    assert first["status"] == "needs_attention"
    assert first["affected_stable_note_ids"] == []
    checkpoint = LocalExecutionCheckpointStore(
        resolver.resolve(actor.stable_user_id) / "execution-checkpoints"
    ).load("hybrid-no-write")
    assert checkpoint is not None
    assert checkpoint["stage"] == "delivery.result_persisted"
    assert checkpoint["outcome"] == "result_persisted"
    assert (
        runtime.execute_product("source requires review", "hybrid-no-write", "main", actor)[
            "delivery_replayed"
        ]
        is True
    )
    assert calls == ["source requires review"]
