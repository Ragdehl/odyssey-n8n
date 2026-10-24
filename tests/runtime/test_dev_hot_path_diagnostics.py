"""Opt-in performance measurement cannot mutate results or disclose message contents."""

from __future__ import annotations

import hashlib
import json
import os
import stat

import pytest

from odyssey_core.application import ApplicationStatus
from odyssey_runtime.dev_hot_path_diagnostics import (
    _record_dev_hot_path_timing,
    timed_dev_hot_path,
)
from tests.runtime.test_conversation_entry_integration import _actor, _runtime
from tests.runtime.test_e6_direct_app_flow_diagnostics import _app_result
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient, _fixture


def _enable(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    root.mkdir()
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")
    monkeypatch.setenv("ODYSSEY_HOT_PATH_TIMING_ENABLED", "1")
    monkeypatch.setenv("ODYSSEY_RUNTIME_ROOT", str(root))
    return root / "hot-path-timing.jsonl"


def _read(path):
    return [json.loads(row) for row in path.read_text().splitlines()]


def test_hot_path_gate_is_off_without_two_dev_permissions(tmp_path, monkeypatch):
    target = _enable(tmp_path, monkeypatch)
    request = "sensitive-private-source"
    for deployment, flag in (("PROD", "1"), ("DEV", "0"), ("", "1")):
        monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", deployment)
        monkeypatch.setenv("ODYSSEY_HOT_PATH_TIMING_ENABLED", flag)
        with timed_dev_hot_path(request, "conversation.classify"):
            pass
        assert not target.exists()
    monkeypatch.setenv("ODYSSEY_DEPLOYMENT_ENV", "DEV")
    monkeypatch.setenv("ODYSSEY_HOT_PATH_TIMING_ENABLED", "1")
    _record_dev_hot_path_timing(request, "some-private-stage", 8, failed=False)
    _record_dev_hot_path_timing(request, "conversation.classify", float("nan"), failed=False)
    assert not target.exists()


def test_hot_path_logs_only_fixed_name_digest_duration_and_failure(tmp_path, monkeypatch):
    target = _enable(tmp_path, monkeypatch)
    request = "private-source-should-never-appear-in-logs"
    with timed_dev_hot_path(request, "conversation.classify"):
        pass
    with pytest.raises(RuntimeError, match="secret-text"):
        with timed_dev_hot_path(request, "tasks.delegate"):
            raise RuntimeError("secret-text")
    actual = _read(target)
    assert [e["stage"] for e in actual] == ["conversation.classify", "tasks.delegate"]
    assert [e["failed"] for e in actual] == [False, True]
    assert all(
        set(e) == {"request_digest", "stage", "failed", "duration_ms"}
        and e["request_digest"] == hashlib.sha256(request.encode()).hexdigest()[:16]
        and isinstance(e["duration_ms"], float)
        and e["duration_ms"] >= 0
        for e in actual
    )
    assert "private" not in target.read_text() and "secret" not in target.read_text()
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600


def test_symlink_target_never_followed_even_in_dev(tmp_path, monkeypatch):
    target = _enable(tmp_path, monkeypatch)
    private = tmp_path / "outside"
    private.write_text("KEEP")
    target.symlink_to(private)
    with timed_dev_hot_path("synthetic", "conversation.entry"):
        pass
    assert private.read_text() == "KEEP"


def test_real_conversation_router_and_chat_wiring_preserves_core_authority(tmp_path, monkeypatch):
    target = _enable(tmp_path, monkeypatch)
    source = "Synthetic one-task statement no personal details."
    runtime, writes, client = _runtime(tmp_path, [{"mode": "ROUTER", "context_scope": "NONE"}])
    result = runtime.execute_product(source, "diagnostic-router", "main", _actor())
    assert result["status"] == "completed"
    assert writes == [(source, "diagnostic-router")]
    assert len(client.responses.calls) == 1
    spans = _read(target)
    assert [x["stage"] for x in spans] == [
        "conversation.classify",
        "conversation.entry",
        "runtime.finish_product",
    ]
    assert all(x["failed"] is False for x in spans)
    assert source not in target.read_text()


def test_independent_tasks_delegate_keeps_same_result_and_timing(tmp_path, monkeypatch):
    target = _enable(tmp_path, monkeypatch)
    source = "Tarea sintética de una sola operación."
    called = []

    def delegate(message, request, actor):
        called.append((message, request, actor.stable_user_id))
        return _app_result("tasks", request, ApplicationStatus.NEEDS_ATTENTION)

    repo, actor, executor, _ = _fixture(tmp_path, task_delegate=delegate)
    executor.client = RecordedClient(
        [
            {
                "capabilities": ["tasks"],
                "interpretation": "joint",
                "reason": "single",
                "app_scopes": [],
            },
            {"only_task_semantics": True, "exactly_one_operation": True, "source_quote": source},
        ]
    )
    result = executor(source, "diagnostic-task", actor, "main")
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert len(called) == 1 and called[0][:2] == (source, "diagnostic-task")
    assert [e["stage"] for e in _read(target)] == [
        "p4.router",
        "p4.task_scope_primary",
        "tasks.delegate",
        "p4.source",
    ]
    assert source not in target.read_text()
    assert len(repo.list_markdown_paths()) == 1


def test_task_independent_scope_and_outer_source_are_measured_without_skipping_review(
    tmp_path, monkeypatch
):
    target = _enable(tmp_path, monkeypatch)
    source = "Una tarea sintética acotada."
    calls = []

    def delegate(message, request, actor):
        calls.append((message, request, actor.stable_user_id))
        return _app_result("tasks", request, ApplicationStatus.NEEDS_ATTENTION)

    _, actor, executor, _ = _fixture(tmp_path, task_delegate=delegate)
    executor.task_create_batch_enabled = True
    executor.client = RecordedClient(
        [
            {
                "capabilities": ["tasks"],
                "interpretation": "joint",
                "reason": "single",
                "app_scopes": [],
            },
            {"only_task_semantics": True, "exactly_one_operation": True, "source_quote": source},
            {"only_task_semantics": True, "exactly_one_operation": True, "source_quote": source},
        ]
    )
    result = executor(source, "two-scope-task", actor, "main")
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert len(calls) == 1
    assert executor.client.calls == [
        "odyssey_light_capability_route_v1",
        "odyssey_task_only_scope_v1",
        "odyssey_task_only_scope_v1",
    ]
    spans = _read(target)
    assert [e["stage"] for e in spans] == [
        "p4.router",
        "p4.task_scope_primary",
        "p4.task_scope_independent",
        "tasks.delegate",
        "p4.source",
    ]
    assert not any(e["failed"] for e in spans)
    assert source not in target.read_text()


def test_task_delegate_failure_is_traced_but_not_swallowed(tmp_path, monkeypatch):
    target = _enable(tmp_path, monkeypatch)
    source = "Un fallo sintético al delegar."

    def delegate(*_):
        raise RuntimeError("private-model-or-source-cannot-be-logged")

    _, actor, executor, _ = _fixture(tmp_path, task_delegate=delegate)
    executor.client = RecordedClient(
        [
            {
                "capabilities": ["tasks"],
                "interpretation": "joint",
                "reason": "single",
                "app_scopes": [],
            },
            {"only_task_semantics": True, "exactly_one_operation": True, "source_quote": source},
        ]
    )
    with pytest.raises(RuntimeError, match="private-model-or-source"):
        executor(source, "failed-task-delegate", actor, "main")
    spans = _read(target)
    assert [e["stage"] for e in spans] == [
        "p4.router",
        "p4.task_scope_primary",
        "tasks.delegate",
        "p4.source",
    ]
    assert [e["failed"] for e in spans] == [False, False, True, True]
    assert source not in target.read_text()
    assert "private-model-or-source" not in target.read_text()
