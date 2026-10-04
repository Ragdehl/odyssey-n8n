"""Provider-free Tasks semantic-write -> Core -> canonical Markdown user path."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TASK_SCHEMA_EXTENSION,
    TaskInterpretation,
    TaskLifecycleGuard,
    TaskOperation,
    TaskTemporalMention,
    TaskTemporalRole,
    compose_task_domain_interpretation,
)
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.context import ContextIndex
from odyssey_core.experimental_luna_planning import validate_luna_experimental_result
from odyssey_core.notes import parse_note, validate_note
from odyssey_core.schema_types import planning_schema_for_capability
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal_interpretation import parse_temporal_interpretation

ROOT = Path(__file__).resolve().parents[3]
BASE_SCHEMA = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
SCHEMA = compose_application_schema(BASE_SCHEMA, (TASK_SCHEMA_EXTENSION,))


class ConstantEmbedder:
    model_name = "tests/tasks-user-e2e"
    model_version = "1"

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.5] for _ in texts]

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.5] for _ in texts]


def test_create_task_with_target_date_uses_core_materialization_end_to_end(tmp_path: Path) -> None:
    source = "Tengo que llamar al banco el viernes"
    task = TaskInterpretation(
        source,
        TaskOperation.CREATE,
        (TaskTemporalMention("el viernes", TaskTemporalRole.TARGET_DATE),),
    )
    temporal = parse_temporal_interpretation(
        {
            "mentions": [
                {
                    "temporal_text": "el viernes",
                    "temporal": {
                        "kind": "EXACT_DATE",
                        "exact_date": "2026-10-09",
                        "exact_datetime": None,
                        "range_start": None,
                        "range_end_exclusive": None,
                    },
                }
            ]
        },
        source,
        timezone="Europe/Paris",
    )
    domain = compose_task_domain_interpretation(task, temporal, now="2026-10-04T21:40:00+02:00")
    raw = {
        "outcome": "PLAN",
        "actions": [
            {
                "kind": "write",
                "operations": [
                    {
                        "target": {
                            "description": "llamar al banco",
                            "binding": "described",
                            "direct_name": "Llamar al banco",
                            "note_type": "task",
                            "filters": [],
                            "candidate_scope": None,
                        },
                        "apply_to": "one",
                        "intent": "record",
                        "facts": [{"parts": [{"kind": "literal", "text": "Llamar al banco."}]}],
                        "properties": [
                            {"field": "status", "op": "set", "value": "pending"},
                            {"field": "target_date", "op": "set", "value": "2026-10-09"},
                        ],
                        "tag_changes": [],
                        "destination_type": None,
                    }
                ],
            }
        ],
        "limitations": [],
        "clarification_code": None,
        "presentation_intent": "answer",
    }
    planning_schema = planning_schema_for_capability(SCHEMA, "tasks")
    plan = validate_luna_experimental_result(raw, planning_schema, domain)

    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    embedder = ConstantEmbedder()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    context = ContextIndex(runtime / "context.sqlite3")
    semantic = SemanticEntityIndex(runtime / "semantic.sqlite3")
    assert context.rebuild(repository, SCHEMA, embedder) == 0
    assert semantic.rebuild(repository, planning_schema, embedder) == 0

    result = execute_request(
        source,
        planner=SimpleNamespace(plan=lambda _request: plan, is_local_replay=True),
        repository=repository,
        schema=planning_schema,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="tasks-e2e",
        now="2026-10-04T21:40:00+02:00",
        context_limit=10,
        request_id_factory=lambda: "tasks-create-e2e",
        preflight_id_allocator=lambda: "task-bank",
        write_preflight_guard=TaskLifecycleGuard(TaskOperation.CREATE),
    )
    assert result.status is ApplicationStatus.COMPLETED
    paths = repository.list_markdown_paths()
    assert paths == [
        "Llamar al banco - task-bank.md",
        "calendar/days/2026-10-04.md",
    ]
    note = parse_note(repository.read_text("Llamar al banco - task-bank.md"))
    validate_note(note, SCHEMA)
    assert note.metadata["type"] == "task"
    assert note.metadata["status"] == "pending"
    assert note.metadata["target_date"] == "2026-10-09"
    assert "Llamar al banco." in note.content
    assert "2026-10-09" not in note.content

    complete_source = "He terminado llamar al banco"
    complete_task = TaskInterpretation(complete_source, TaskOperation.COMPLETE)
    complete_domain = compose_task_domain_interpretation(
        complete_task, None, now="2026-10-04T22:05:00+02:00"
    )
    complete_raw = {
        "outcome": "PLAN",
        "actions": [
            {
                "kind": "write",
                "operations": [
                    {
                        "target": {
                            "description": "llamar al banco",
                            "binding": "described",
                            "direct_name": "Llamar al banco",
                            "note_type": "task",
                            "filters": [],
                            "candidate_scope": None,
                        },
                        "apply_to": "one",
                        "intent": "amend",
                        "facts": [],
                        "properties": [
                            {"field": "status", "op": "set", "value": "completed"},
                            {
                                "field": "completed_at",
                                "op": "set",
                                "value": "2026-10-04T22:05:00+02:00",
                            },
                        ],
                        "tag_changes": [],
                        "destination_type": None,
                    }
                ],
            }
        ],
        "limitations": [],
        "clarification_code": None,
        "presentation_intent": "answer",
    }
    complete_plan = validate_luna_experimental_result(
        complete_raw, planning_schema, complete_domain
    )
    assert context.rebuild(repository, SCHEMA, embedder) >= 1
    assert semantic.rebuild(repository, planning_schema, embedder) >= 1

    complete_result = execute_request(
        complete_source,
        planner=SimpleNamespace(plan=lambda _request: complete_plan, is_local_replay=True),
        repository=repository,
        schema=planning_schema,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="tasks-e2e",
        now="2026-10-04T22:05:00+02:00",
        context_limit=10,
        request_id_factory=lambda: "tasks-complete-e2e",
        write_preflight_guard=TaskLifecycleGuard(TaskOperation.COMPLETE),
    )
    assert complete_result.status is ApplicationStatus.COMPLETED
    assert repository.list_markdown_paths() == paths
    completed = parse_note(repository.read_text("Llamar al banco - task-bank.md"))
    validate_note(completed, SCHEMA)
    assert completed.metadata["status"] == "completed"
    assert completed.metadata["completed_at"] == "2026-10-04T22:05:00+02:00"
    assert completed.metadata["target_date"] == "2026-10-09"
