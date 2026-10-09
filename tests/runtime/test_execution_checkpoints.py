"""Provider-free contract coverage for optional durable execution checkpoints."""

from __future__ import annotations

from pathlib import Path

import pytest

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.git_history import GitHistoryResult
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_runtime import composition
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime.execution_checkpoints import (
    CheckpointOutcome,
    ExecutionCheckpointError,
    LocalExecutionCheckpointStore,
)

ACTOR_A = AuthenticatedActorContext("11111111-1111-4111-8111-111111111111")
ACTOR_B = AuthenticatedActorContext("22222222-2222-4222-8222-222222222222")
NOW = "2026-10-09T12:00:00+02:00"


def test_checkpoint_store_is_latest_only_atomic_bounded_and_recoverable(tmp_path: Path) -> None:
    """A recreated root-bound store sees only validated latest evidence after replacement."""
    store = LocalExecutionCheckpointStore(tmp_path / "checkpoints", max_records=1)

    first = store.record("request-1", "starting", CheckpointOutcome.MILESTONE_OBSERVED, NOW)
    second = store.record("request-1", "planner.ready", CheckpointOutcome.MILESTONE_OBSERVED, NOW)

    assert first["sequence"] == 1
    assert second["sequence"] == 2
    assert (
        LocalExecutionCheckpointStore(tmp_path / "checkpoints", max_records=1).load("request-1")
        == second
    )
    with pytest.raises(ExecutionCheckpointError, match="capacity"):
        store.record("request-2", "starting", CheckpointOutcome.MILESTONE_OBSERVED, NOW)


@pytest.mark.parametrize(
    ("request_id", "stage", "outcome", "observed_at"),
    [
        ("bad id", "starting", CheckpointOutcome.MILESTONE_OBSERVED, NOW),
        ("request-1", "unapproved.stage", CheckpointOutcome.MILESTONE_OBSERVED, NOW),
        ("request-1", "starting", "completed", NOW),  # type: ignore[arg-type]
        ("request-1", "starting", CheckpointOutcome.MILESTONE_OBSERVED, "not-a-time"),
    ],
)
def test_checkpoint_store_rejects_invalid_records(
    tmp_path: Path, request_id: str, stage: str, outcome: CheckpointOutcome, observed_at: str
) -> None:
    """No free-form stages, outcomes, identities, or timestamps enter durable diagnostics."""
    with pytest.raises(ExecutionCheckpointError):
        LocalExecutionCheckpointStore(tmp_path).record(request_id, stage, outcome, observed_at)


def test_checkpoint_store_fails_closed_for_corruption(tmp_path: Path) -> None:
    """A malformed persisted record cannot be treated as execution evidence."""
    store = LocalExecutionCheckpointStore(tmp_path)
    store.record("request-1", "starting", CheckpointOutcome.MILESTONE_OBSERVED, NOW)
    next((tmp_path).iterdir()).write_text("{", encoding="utf-8")

    with pytest.raises(ExecutionCheckpointError):
        store.load("request-1")


def _mutation_result(request_id: str) -> ApplicationResult:
    """Return synthetic Core mutation evidence without a model or personal data."""
    return ApplicationResult(
        request_id=request_id,
        status=ApplicationStatus.COMPLETED,
        action_results=(),
        affected_stable_note_ids=("synthetic-note",),
        history=GitHistoryResult.disabled(),
    )


def test_opt_in_checkpoint_tracks_existing_progress_and_delivery_replay_per_actor(
    tmp_path: Path,
) -> None:
    """Runtime progress feeds an isolated durable checkpoint without changing replay authority."""
    resolver = ConversationRootResolver(tmp_path / "state")
    calls: list[str] = []

    def execute(_request, request_id, *_args, **_kwargs):
        calls.append(request_id)
        composition._emit_progress("routing.started")
        composition._emit_progress("planner.ready", {"references": ("never persisted",)})
        return _mutation_result(request_id)

    runtime = RuntimeComposition(
        core_execute=execute,
        refresh_indexes=lambda: None,
        conversation_root_resolver=resolver,
        execution_checkpoint_store_factory=LocalExecutionCheckpointStore,
    )
    response = runtime.execute_product("synthetic request", "delivery-1", "main", ACTOR_A)
    replay = runtime.execute_product("synthetic request", "delivery-1", "main", ACTOR_A)

    root_a = resolver.resolve(ACTOR_A.stable_user_id) / "execution-checkpoints"
    checkpoint = LocalExecutionCheckpointStore(root_a).load("delivery-1")
    assert response["request_id"] == "delivery-1"
    assert replay["delivery_replayed"] is True
    assert calls == ["delivery-1"]
    assert checkpoint is not None
    assert checkpoint["stage"] == "delivery.result_persisted"
    assert checkpoint["outcome"] == "result_persisted"
    assert "never persisted" not in str(checkpoint)
    assert (
        LocalExecutionCheckpointStore(
            resolver.resolve(ACTOR_B.stable_user_id) / "execution-checkpoints"
        ).load("delivery-1")
        is None
    )


def test_checkpoint_failure_never_interrupts_write_and_execution_failure_is_unknown(
    tmp_path: Path,
) -> None:
    """Diagnostics are best effort while a failed execution never claims completion."""
    resolver = ConversationRootResolver(tmp_path / "state")

    class BrokenStore(LocalExecutionCheckpointStore):
        def record(self, *args, **kwargs):
            raise OSError("diagnostic disk unavailable")

    successful = RuntimeComposition(
        core_execute=lambda _request, request_id, *_args: _mutation_result(request_id),
        refresh_indexes=lambda: None,
        conversation_root_resolver=resolver,
        execution_checkpoint_store_factory=BrokenStore,
    )
    assert (
        successful.execute_product("synthetic", "delivery-ok", "main", ACTOR_A)["request_id"]
        == "delivery-ok"
    )

    failing = RuntimeComposition(
        core_execute=lambda *_args: (_ for _ in ()).throw(RuntimeError("synthetic interruption")),
        refresh_indexes=lambda: None,
        conversation_root_resolver=resolver,
        execution_checkpoint_store_factory=LocalExecutionCheckpointStore,
    )
    with pytest.raises(RuntimeError, match="interruption"):
        failing.execute_product("synthetic", "delivery-failed", "main", ACTOR_A)

    checkpoint = LocalExecutionCheckpointStore(
        resolver.resolve(ACTOR_A.stable_user_id) / "execution-checkpoints"
    ).load("delivery-failed")
    assert checkpoint is not None
    assert checkpoint["stage"] == "failed_or_unknown"
    assert checkpoint["outcome"] == "failed_or_unknown"
