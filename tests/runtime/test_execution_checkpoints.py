"""Provider-free contract coverage for optional durable execution checkpoints."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
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


def _clock(value: datetime):
    """Return a deterministic trusted clock for retention boundary tests."""
    return lambda: value


def test_checkpoint_store_is_latest_only_atomic_bounded_and_recoverable(tmp_path: Path) -> None:
    """A recreated root-bound store retains latest evidence and evicts at bounded capacity."""
    store = LocalExecutionCheckpointStore(tmp_path / "checkpoints", max_records=1)

    first = store.record("request-1", "starting", CheckpointOutcome.MILESTONE_OBSERVED, NOW)
    second = store.record("request-1", "planner.ready", CheckpointOutcome.MILESTONE_OBSERVED, NOW)

    assert first["sequence"] == 1
    assert second["sequence"] == 2
    assert [entry["stage"] for entry in second["events"]] == ["starting", "planner.ready"]
    assert second["truncated"] is False
    assert (
        LocalExecutionCheckpointStore(tmp_path / "checkpoints", max_records=1).load("request-1")
        == second
    )
    store.record("request-2", "starting", CheckpointOutcome.MILESTONE_OBSERVED, NOW)
    assert store.load("request-1") is None
    assert store.load("request-2") is not None


def test_checkpoint_retention_keeps_exact_30_day_boundary_and_expires_after_it(
    tmp_path: Path,
) -> None:
    """Retention compares aware timestamps in UTC and retains the exact 30-day boundary."""
    now = datetime(2026, 11, 8, 10, tzinfo=UTC)
    store = LocalExecutionCheckpointStore(tmp_path, now=_clock(now))
    exact = (now - timedelta(days=30)).astimezone().isoformat()
    expired = (now - timedelta(days=30, microseconds=1)).astimezone().isoformat()

    store.record("exact-boundary", "starting", CheckpointOutcome.MILESTONE_OBSERVED, exact)
    store.record("expired-boundary", "starting", CheckpointOutcome.MILESTONE_OBSERVED, expired)

    assert store.load("exact-boundary") is not None
    assert store.load("expired-boundary") is None


def test_checkpoint_capacity_prefers_old_terminal_before_unknown_or_incomplete(
    tmp_path: Path,
) -> None:
    """Capacity pressure evicts oldest returned histories before newer unknown diagnostics."""
    now = datetime(2026, 11, 8, 10, tzinfo=UTC)
    store = LocalExecutionCheckpointStore(tmp_path, max_records=2, now=_clock(now))
    old = (now - timedelta(days=2)).isoformat()
    recent = (now - timedelta(days=1)).isoformat()
    store.record("terminal", "processing.returned", CheckpointOutcome.PROCESSING_RETURNED, old)
    store.record("unknown", "failed_or_unknown", CheckpointOutcome.FAILED_OR_UNKNOWN, recent)

    store.record("incoming", "starting", CheckpointOutcome.MILESTONE_OBSERVED, now.isoformat())

    assert store.load("terminal") is None
    assert store.load("unknown") is not None
    assert store.load("incoming") is not None


def test_checkpoint_retention_never_unlinks_symlink_malformed_or_unrecognized_files(
    tmp_path: Path,
) -> None:
    """Pruning only removes fully validated hash-named records inside its actor root."""
    root = tmp_path / "checkpoints"
    outside = tmp_path / "outside.json"
    outside.write_text("keep", encoding="utf-8")
    root.mkdir()
    (root / "not-a-checkpoint.json").write_text("keep", encoding="utf-8")
    malformed = root / ("0" * 64 + ".json")
    malformed.write_text("{", encoding="utf-8")
    symlink = root / ("1" * 64 + ".json")
    symlink.symlink_to(outside)
    now = datetime(2026, 11, 8, 10, tzinfo=UTC)
    store = LocalExecutionCheckpointStore(root, max_records=1, now=_clock(now))

    store.record(
        "old",
        "processing.returned",
        CheckpointOutcome.PROCESSING_RETURNED,
        (now - timedelta(days=31)).isoformat(),
    )
    store.record("new", "starting", CheckpointOutcome.MILESTONE_OBSERVED, now.isoformat())

    assert outside.read_text(encoding="utf-8") == "keep"
    assert malformed.read_text(encoding="utf-8") == "{"
    assert symlink.is_symlink()
    assert (root / "not-a-checkpoint.json").read_text(encoding="utf-8") == "keep"
    assert store.load("old") is None
    assert store.load("new") is not None


def test_checkpoint_concurrent_writers_preserve_valid_bounded_records(tmp_path: Path) -> None:
    """A root-local lock prevents concurrent writers from exceeding the retention cap."""
    root = tmp_path / "checkpoints"
    now = datetime(2026, 11, 8, 10, tzinfo=UTC)

    def record(request_id: str) -> None:
        LocalExecutionCheckpointStore(root, max_records=2, now=_clock(now)).record(
            request_id, "starting", CheckpointOutcome.MILESTONE_OBSERVED, now.isoformat()
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(record, ("request-1", "request-2", "request-3", "request-4")))

    records = list(root.glob("*.json"))
    assert len(records) == 2
    for path in records:
        assert not path.is_symlink()
        request_id = json.loads(path.read_text(encoding="utf-8"))["request_id"]
        assert LocalExecutionCheckpointStore(root, now=_clock(now)).load(request_id) is not None


def test_checkpoint_stage_updates_do_not_rescan_retained_requests(tmp_path: Path) -> None:
    """Record-level retention runs per new request rather than per progress milestone."""
    now = datetime(2026, 11, 8, 10, tzinfo=UTC)

    class ScanCountingStore(LocalExecutionCheckpointStore):
        scan_count = 0

        def _validated_records(self):
            self.scan_count += 1
            yield from super()._validated_records()

    store = ScanCountingStore(tmp_path / "checkpoint", now=_clock(now))
    stamp = now.isoformat()
    store.record("trace", "starting", CheckpointOutcome.MILESTONE_OBSERVED, stamp)
    assert store.scan_count == 1
    for _ in range(12):
        store.record("trace", "planner.started", CheckpointOutcome.MILESTONE_OBSERVED, stamp)
    assert store.scan_count == 1
    store.record("next-request", "starting", CheckpointOutcome.MILESTONE_OBSERVED, stamp)
    assert store.scan_count == 2


def test_checkpoint_rejects_symlinked_retention_lock(tmp_path: Path) -> None:
    """A lock symlink cannot be followed into unrelated files."""
    root = tmp_path / "checkpoint"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("keep", encoding="utf-8")
    (root / ".retention.lock").symlink_to(outside)
    store = LocalExecutionCheckpointStore(root)
    with pytest.raises(ExecutionCheckpointError):
        store.record("trace", "starting", CheckpointOutcome.MILESTONE_OBSERVED, NOW)
    assert outside.read_text(encoding="utf-8") == "keep"


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


def test_runtime_composition_prunes_only_its_actor_checkpoint_history(tmp_path: Path) -> None:
    """Synthetic runtime deliveries exercise opt-in retention without a provider or real state."""
    resolver = ConversationRootResolver(tmp_path / "state")
    runtime = RuntimeComposition(
        core_execute=lambda _request, request_id, *_args: _mutation_result(request_id),
        refresh_indexes=lambda: None,
        conversation_root_resolver=resolver,
        execution_checkpoint_store_factory=lambda root: LocalExecutionCheckpointStore(
            root, max_records=1
        ),
    )

    runtime.execute_product("first", "delivery-1", "main", ACTOR_A)
    runtime.execute_product("second", "delivery-2", "main", ACTOR_A)

    root_a = resolver.resolve(ACTOR_A.stable_user_id) / "execution-checkpoints"
    root_b = resolver.resolve(ACTOR_B.stable_user_id) / "execution-checkpoints"
    assert LocalExecutionCheckpointStore(root_a).load("delivery-1") is None
    assert LocalExecutionCheckpointStore(root_a).load("delivery-2") is not None
    assert not root_b.exists()


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


def test_checkpoint_preserves_a_bounded_trace_and_marks_truncation(tmp_path: Path) -> None:
    """After a long trace, preserve the last 64 stages without hiding that earlier ones were lost."""
    store = LocalExecutionCheckpointStore(tmp_path / "checkpoint")
    for _ in range(69):
        store.record("trace-69", "planner.started", CheckpointOutcome.MILESTONE_OBSERVED, NOW)
    recovered = LocalExecutionCheckpointStore(tmp_path / "checkpoint").load("trace-69")
    assert recovered is not None
    assert recovered["sequence"] == 69
    assert recovered["truncated"] is True
    assert len(recovered["events"]) == 64
    assert [entry["sequence"] for entry in recovered["events"]] == list(range(6, 70))


def test_checkpoint_rejects_mismatched_record_identity_and_false_delivery_claim(
    tmp_path: Path,
) -> None:
    """A corrupt path binding or invented persisted status never becomes evidence."""
    import json

    store = LocalExecutionCheckpointStore(tmp_path / "checkpoint")
    store.record("trace-1", "starting", CheckpointOutcome.MILESTONE_OBSERVED, NOW)
    path = next((tmp_path / "checkpoint").iterdir())
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["request_id"] = "another-valid-id"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ExecutionCheckpointError):
        store.load("trace-1")
    with pytest.raises(ExecutionCheckpointError, match="disagree"):
        store.record(
            "trace-2", "delivery.result_persisted", CheckpointOutcome.MILESTONE_OBSERVED, NOW
        )
    assert store.load("trace-2") is None


def test_runtime_trace_contains_handoffs_but_never_claims_a_write_from_a_milestone(
    tmp_path: Path,
) -> None:
    """The sequence exposes observed stages without persisting any model reference text."""
    resolver = ConversationRootResolver(tmp_path / "state")

    def execute(_request, request_id, *_args, **_kwargs):
        composition._emit_progress("routing.started")
        composition._emit_progress("routing.ready", {"route_count": 3})
        composition._emit_progress("temporal.ready", {"values": ("tomorrow",)})
        return ApplicationResult(
            request_id=request_id,
            status=ApplicationStatus.NEEDS_ATTENTION,
            action_results=(),
            affected_stable_note_ids=(),
            history=GitHistoryResult.disabled(),
        )

    runtime = RuntimeComposition(
        core_execute=execute,
        refresh_indexes=lambda: None,
        conversation_root_resolver=resolver,
        execution_checkpoint_store_factory=LocalExecutionCheckpointStore,
    )
    response = runtime.execute_product("synthetic", "trace-ambiguous", "main", ACTOR_A)
    checkpoint = LocalExecutionCheckpointStore(
        resolver.resolve(ACTOR_A.stable_user_id) / "execution-checkpoints"
    ).load("trace-ambiguous")
    assert checkpoint is not None
    assert [event["stage"] for event in checkpoint["events"]] == [
        "starting",
        "routing.started",
        "routing.ready",
        "temporal.ready",
        "finalizing",
        "processing.returned",
    ]
    assert checkpoint["outcome"] == "processing_returned"
    assert "tomorrow" not in str(checkpoint)
    assert response["affected_stable_note_ids"] == []
