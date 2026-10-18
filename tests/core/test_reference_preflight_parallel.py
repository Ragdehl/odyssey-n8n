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
