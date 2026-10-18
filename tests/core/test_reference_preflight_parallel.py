"""Generic, fail-closed parallel read-only identity decisions (no parallel writers)."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from time import perf_counter, sleep

import pytest

from odyssey_core import reference_preflight as module
from odyssey_core.observability import SpanRecorder
from odyssey_core.storage import VaultRepository
from odyssey_core.write_target import WriteTargetDecision, WriteTargetOutcome
from tests.core.test_reference_preflight import action, unit


class ReadOnlyForkable:
    supports_parallel_target_decisions = True

    def fork_for_parallel_read(self, *_args):
        return self


def _call(repo, schema, *, parallel=False):
    allocator = iter(("alpha-id", "bravo-id", "charlie-id", "delta-id")).__next__
    return module.preflight_write_action(
        action(
            unit("Alpha", entity="Alpha"),
            unit("Bravo", entity="Bravo"),
            unit("Charlie", entity="Charlie"),
            unit("Delta", entity="Delta"),
        ),
        repository=repo,
        schema=schema,
        semantic_index=object(),
        embedder=ReadOnlyForkable(),
        contextual_reasoner=ReadOnlyForkable(),
        semantic_limit=8,
        id_allocator=allocator,
        span_recorder=SpanRecorder(perf_counter(), perf_counter),
        parallel_target_decisions=parallel,
    )


@pytest.fixture
def fx(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "config/note-schema.json").read_text()
    )
    return VaultRepository(vault), schema


def test_independent_target_decisions_are_parallel_but_id_allocation_is_still_ordered(
    fx, monkeypatch
):
    repo, schema = fx
    calls = []
    lock = Lock()

    def read_only_decision(unit_value, **_kwargs):
        with lock:
            calls.append((unit_value.target.query, perf_counter()))
        sleep(0.16)
        return WriteTargetDecision(WriteTargetOutcome.CREATE, target_type="person")

    monkeypatch.setattr(module, "decide_write_target", read_only_decision)
    t0 = perf_counter()
    parallel = _call(repo, schema, parallel=True)
    parallel_elapsed = perf_counter() - t0
    t1 = perf_counter()
    sequential = _call(repo, schema, parallel=False)
    sequential_elapsed = perf_counter() - t1
    assert parallel == sequential
    assert [row.stable_id for row in parallel] == ["alpha-id", "bravo-id", "charlie-id", "delta-id"]
    started = [now for _, now in calls[:4]]
    assert max(started) - min(started) < 0.11
    assert parallel_elapsed < sequential_elapsed * 0.55
    assert not repo.list_markdown_paths()


def test_external_source_change_during_parallel_resolution_rejects_all_units(fx, monkeypatch):
    repo, schema = fx
    touched = False

    def changed_during_decisions(unit_value, **_kwargs):
        nonlocal touched
        if unit_value.target.query == "Bravo" and not touched:
            touched = True
            (repo.root / "changed.md").write_text("external change", encoding="utf-8")
        return WriteTargetDecision(WriteTargetOutcome.CREATE, target_type="person")

    monkeypatch.setattr(module, "decide_write_target", changed_during_decisions)
    with pytest.raises(module.ReferencePreflightError, match="sources changed"):
        _call(repo, schema, parallel=True)


def test_unknown_nonforkable_reasoner_uses_legacy_sequential_safe_path(fx, monkeypatch):
    repo, schema = fx
    calls = []

    def read_only_decision(unit_value, **_kwargs):
        calls.append(unit_value.target.query)
        return WriteTargetDecision(WriteTargetOutcome.CREATE, target_type="person")

    monkeypatch.setattr(module, "decide_write_target", read_only_decision)
    ids = iter(("alpha-id", "bravo-id"))
    rows = module.preflight_write_action(
        action(unit("Alpha"), unit("Bravo")),
        repository=repo,
        schema=schema,
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        semantic_limit=4,
        id_allocator=ids.__next__,
        parallel_target_decisions=True,
    )
    assert calls == ["Alpha", "Bravo"]
    assert [row.stable_id for row in rows] == ["alpha-id", "bravo-id"]


def test_parallel_target_provider_exception_prevents_all_identity_allocations(fx, monkeypatch):
    repo, schema = fx
    count = 0

    def failing_decision(unit_value, **_kwargs):
        nonlocal count
        count += 1
        if unit_value.target.query == "Charlie":
            raise ValueError("untrusted model response")
        return WriteTargetDecision(WriteTargetOutcome.CREATE, target_type="person")

    monkeypatch.setattr(module, "decide_write_target", failing_decision)
    allocated = []

    def allocate():
        allocated.append("allocated")
        return "should-not-be-used"

    with pytest.raises(ValueError, match="untrusted model"):
        module.preflight_write_action(
            action(unit("Alpha"), unit("Bravo"), unit("Charlie")),
            repository=repo,
            schema=schema,
            semantic_index=object(),
            embedder=ReadOnlyForkable(),
            contextual_reasoner=ReadOnlyForkable(),
            semantic_limit=4,
            id_allocator=allocate,
            parallel_target_decisions=True,
        )
    assert count == 3
    assert allocated == []
    assert repo.list_markdown_paths() == []


def test_provider_forks_keep_model_contract_but_do_not_share_mutable_usage():
    from odyssey_core.contextual import OpenAIContextualReasoner

    base = OpenAIContextualReasoner(
        "gpt-6-luna",
        reasoning_effort="medium",
        timeout_seconds=42,
        examples=(),
        max_output_tokens=512,
    )
    a = base.fork_for_parallel_read()
    b = base.fork_for_parallel_read()
    assert a is not b and a is not base and b is not base
    assert (a.model, a.reasoning_effort, a.timeout_seconds, a.max_output_tokens) == (
        base.model,
        base.reasoning_effort,
        base.timeout_seconds,
        base.max_output_tokens,
    )
    a.last_usage = {"input_tokens": 1}
    assert b.last_usage is None and base.last_usage is None


def test_plain_reference_lookup_and_fact_target_resolve_together(fx, monkeypatch):
    """Real P4 CREATE shapes mix day/fact target with reference-only identities."""
    from dataclasses import replace

    repo, schema = fx
    calls = []
    lock = Lock()

    def fake_target(unit_value, **_kwargs):
        with lock:
            calls.append(
                (unit_value.target.query, unit_value.reference_lookup_only, perf_counter())
            )
        sleep(0.15)
        return WriteTargetDecision(WriteTargetOutcome.CREATE, target_type="person")

    monkeypatch.setattr(module, "decide_write_target", fake_target)
    monkeypatch.setattr(module, "_decide_reference_only_target", fake_target)
    source_action = action(
        unit("First"),
        replace(unit("Person 1"), reference_lookup_only=True),
        replace(unit("Person 2"), reference_lookup_only=True),
        unit("Last"),
    )

    def invoke(parallel):
        return module.preflight_write_action(
            source_action,
            repository=repo,
            schema=schema,
            semantic_index=object(),
            embedder=ReadOnlyForkable(),
            contextual_reasoner=ReadOnlyForkable(),
            semantic_limit=8,
            id_allocator=iter(("id-first", "id-person1", "id-person2", "id-last")).__next__,
            span_recorder=SpanRecorder(perf_counter(), perf_counter),
            parallel_target_decisions=parallel,
        )

    begin = perf_counter()
    concurrent = invoke(True)
    concurrent_elapsed = perf_counter() - begin
    begin = perf_counter()
    serial = invoke(False)
    serial_elapsed = perf_counter() - begin
    assert concurrent == serial
    assert len(calls) == 8
    assert sorted(was_lookup for _, was_lookup, _ in calls[:4]) == [False, False, True, True]
    assert max(start for _, _, start in calls[:4]) - min(start for _, _, start in calls[:4]) < 0.10
    assert concurrent_elapsed < serial_elapsed * 0.65
    assert not repo.list_markdown_paths()
