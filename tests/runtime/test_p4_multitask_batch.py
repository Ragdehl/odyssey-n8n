"""Two independently reviewed dated Task creations share canonical Core Writer."""

from __future__ import annotations

import copy

from odyssey_core.notes import parse_note
from tests.runtime.test_whole_source_light_product_p4 import (
    RecordedClient,
    _fixture,
    _speaker,
)

SOURCE = "El 31 de octubre de 2026 tengo que llamar al electricista y revisar la factura."
ROUTE = {
    "capabilities": ["tasks", "temporal"],
    "interpretation": "joint",
    "reason": "single",
    "app_scopes": [],
}
SCOPE = {
    "only_task_semantics": True,
    "exactly_one_operation": False,
    "source_quote": SOURCE,
}
PLAN = {
    "entities": [],
    "facts": [
        {
            "meaning": "Llamar al electricista",
            "kind": "task",
            "subject": "yo",
            "date": "2026-10-31",
            "daypart": None,
            "participants": [],
            "source_evidence": "tengo que llamar al electricista",
            "dependent_on_fact_index": None,
            "needs_clarification": False,
        },
        {
            "meaning": "Revisar la factura",
            "kind": "task",
            "subject": "yo",
            "date": "2026-10-31",
            "daypart": None,
            "participants": [],
            "source_evidence": "revisar la factura",
            "dependent_on_fact_index": None,
            "needs_clarification": False,
        },
    ],
    "unresolved": [],
}
CREATE_AUDIT = {
    "only_new_task_creations": True,
    "no_work_session_or_lifecycle_transition": True,
    "source_quote": SOURCE,
}
REVIEW = {
    "approved": True,
    "complete": True,
    "reason": None,
    "facts": [
        {
            "ordinal": i,
            "source_quote": part["source_evidence"],
            "kind": "task",
            "reviewed_text": text,
            "date": "2026-10-31",
            "reference_names": [],
            "supported": True,
        }
        for i, (part, text) in enumerate(
            zip(PLAN["facts"], ["Llamar al electricista.", "Revisar la factura."], strict=True)
        )
    ],
}


def _rows(plan=PLAN, review=REVIEW, audit=CREATE_AUDIT):
    return [
        copy.deepcopy(ROUTE),
        copy.deepcopy(SCOPE),
        copy.deepcopy(plan),
        copy.deepcopy(audit),
        copy.deepcopy(review),
        _speaker(SOURCE, plan, assertion="planned", base=1),
        _speaker(SOURCE, plan, assertion="planned"),
    ]


def test_two_dated_tasks_use_existing_core_write_and_replay_boundary(tmp_path):
    repo, actor, service, runtime = _fixture(tmp_path)
    service.task_create_batch_enabled = True
    service.client = RecordedClient(_rows())
    result = runtime.execute_product(SOURCE, "two-task-canonical", "main", actor)
    assert result["status"] == "completed", result
    saved = [parse_note(repo.read_text(p)) for p in repo.list_markdown_paths()]
    task_notes = [n for n in saved if n.metadata["type"] == "task"]
    assert len(task_notes) == 2
    assert {n.metadata["name"] for n in task_notes} == {
        "Llamar al electricista",
        "Revisar la factura",
    }
    assert all(n.metadata["status"] == "pending" for n in task_notes)
    assert all(n.metadata["target_date"] == "2026-10-31" for n in task_notes)
    assert len(result["execution_flow"]["routes"][0]["writes"]) == 2
    original = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    second = runtime.execute_product(SOURCE, "two-task-canonical", "main", actor)
    assert second["delivery_replayed"] is True
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == original


def test_multi_tasks_without_batch_flag_abstain_without_legacy_task_delegate(tmp_path):
    repo, actor, service, runtime = _fixture(tmp_path)
    service.client = RecordedClient(_rows()[:2])
    result = runtime.execute_product(SOURCE, "two-task-off", "main", actor)
    assert result["status"] == "needs_attention"
    assert service.client.calls == [
        "odyssey_light_capability_route_v1",
        "odyssey_task_only_scope_v1",
    ]
    assert len(repo.list_markdown_paths()) == 1


def test_batch_cannot_relabel_two_obligations_as_one_task(tmp_path):
    repo, actor, service, runtime = _fixture(tmp_path)
    service.task_create_batch_enabled = True
    one_fact = copy.deepcopy(PLAN)
    one_fact["facts"] = one_fact["facts"][:1]
    service.client = RecordedClient(_rows(plan=one_fact)[:3])
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    result = runtime.execute_product(SOURCE, "two-task-incomplete", "main", actor)
    assert result["status"] == "needs_attention"
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before


def test_batch_cannot_downgrade_work_session_commands_to_task_create(tmp_path):
    repo, actor, service, runtime = _fixture(tmp_path)
    service.task_create_batch_enabled = True
    audit = {**CREATE_AUDIT, "only_new_task_creations": False}
    service.client = RecordedClient(_rows(audit=audit)[:4])
    before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
    result = runtime.execute_product(SOURCE, "two-task-lifecycle-veto", "main", actor)
    assert result["status"] == "needs_attention"
    assert {p: repo.read_text(p) for p in repo.list_markdown_paths()} == before
