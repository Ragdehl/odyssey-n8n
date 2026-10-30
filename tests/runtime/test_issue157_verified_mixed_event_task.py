"""Mixed future Event/Task may use verified SELF relationship without bypassing E3."""

from __future__ import annotations

from dataclasses import replace

from odyssey_core import create_entity
from odyssey_core.atomic_facts import render_atomic_facts
from odyssey_core.notes import parse_note, serialize_note
from tests.runtime import test_e5_p4_independent_event_task as mixed
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient

FUTURE = "Concierto independiente E5 con mi pareja el 24 de noviembre de 2026."


def _setup(tmp_path, monkeypatch, *, verified=True):
    monkeypatch.setattr(mixed, "EVENT", FUTURE)
    monkeypatch.setattr(mixed, "SOURCE", FUTURE + " " + mixed.TASK)
    repo, actor, executor, runtime, calls, stages = mixed._fixture(tmp_path)
    if verified:
        create_entity(
            repo,
            executor.schema,
            path="Vera.md",
            entity_id="person-Vera",
            metadata={"name": "Vera", "type": "person"},
            content="",
            actor="synthetic",
            now="2026-10-16T08:00:00+02:00",
        )
        self_note = parse_note(repo.read_text("self.md"))
        fact = render_atomic_facts(
            ("Mi pareja es [[Vera]].",), "test-relationship", (0,), "2026-10-16"
        )
        repo.replace_text("self.md", serialize_note(replace(self_note, content=fact)))
    router = mixed._router()
    router["self_relation_span"] = "mi pareja"
    router["self_relation_spans"] = ["mi pareja"]
    rows = [router, *mixed._client_rows()[1:]]
    executor.client = RecordedClient(rows)
    return repo, actor, executor, runtime, calls, stages


def test_verified_partner_on_future_event_preserves_independent_task_and_replay(
    tmp_path, monkeypatch
):
    repo, actor, executor, runtime, calls, stages = _setup(tmp_path, monkeypatch)
    original = mixed.SOURCE
    result = runtime.execute_product(original, "issue157-event-task-partner", "main", actor)
    assert result["status"] == "completed", result
    assert len(mixed._event_notes(repo)) == 1
    assert len(calls) == 1
    assert stages == ["task_prepared", "event_prepared", "event_written", "task_written"]
    assert [x["capability"] for x in result["execution_flow"]["routes"]] == ["events", "tasks"]
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    assert runtime.execute_product(original, "issue157-event-task-partner", "main", actor)[
        "delivery_replayed"
    ]
    assert before == {p: repo.read_text(p) for p in repo.list_markdown_paths()}


def test_missing_verified_partner_cannot_launch_either_operation(tmp_path, monkeypatch):
    repo, actor, executor, runtime, calls, stages = _setup(tmp_path, monkeypatch, verified=False)
    original = mixed.SOURCE
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    result = runtime.execute_product(original, "issue157-event-task-unverified", "main", actor)
    assert result["status"] == "needs_attention"
    assert not calls and not stages
    assert not mixed._event_notes(repo)
    assert before == {p: repo.read_text(p) for p in repo.list_markdown_paths()}


def test_stale_partner_after_partition_is_rejected_prewrite(tmp_path, monkeypatch):
    repo, actor, executor, runtime, calls, stages = _setup(tmp_path, monkeypatch)
    original_prepare = executor.independent_event_prepare

    def mutate_self_before_event_preflight(source, instant):
        current = parse_note(repo.read_text("self.md"))
        repo.replace_text("self.md", serialize_note(replace(current, content="")))
        return original_prepare(source, instant)

    executor.independent_event_prepare = mutate_self_before_event_preflight
    source = mixed.SOURCE
    result = runtime.execute_product(source, "issue157-event-task-stale-self", "main", actor)
    assert result["status"] == "needs_attention"
    assert "event_written" not in stages and "task_written" not in stages
    assert not calls and not mixed._event_notes(repo)
