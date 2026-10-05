"""Task role relationships resolve through Core and remain ordinary navigable links."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TASK_SCHEMA_EXTENSION,
    TaskCorePlanner,
    TaskInterpretation,
    TaskLifecycleGuard,
    TaskOperation,
    TaskRelationshipMention,
    TaskRelationshipRole,
)
from odyssey_core import create_entity
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.context import ContextIndex
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.request_planning import (
    KnowledgeUnit,
    PropertyChange,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.schema_types import planning_schema_for_capability
from odyssey_core.semantic import SemanticEntityIndex
from odyssey_core.storage import VaultRepository

ROOT = Path(__file__).resolve().parents[3]
BASE = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
SCHEMA = compose_application_schema(BASE, (TASK_SCHEMA_EXTENSION,))
PLANNING_SCHEMA = planning_schema_for_capability(SCHEMA, "tasks")


class Embedder:
    model_name = "tests/task-relations"
    model_version = "1"

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [[1.0, float(index + 1)] for index, _ in enumerate(texts)]

    def embed_queries(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [[1.0, 1.0] for _ in texts]


class FirstReasoner:
    def resolve(self, request):  # type: ignore[no-untyped-def]
        candidate = request.candidates[0]
        return ({"outcome": "RESOLVED", "id": candidate.id, "ambiguous_ids": []}, {})


def test_assignee_and_parent_resolve_to_canonical_links_and_parent_backlink(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "people").mkdir()
    repository = VaultRepository(vault)
    create_entity(
        repository,
        SCHEMA,
        path="people/beatriz.md",
        entity_id="beatriz",
        metadata={"name": "Beatriz", "type": "person"},
        content="",
        actor="fixture",
        now="2026-10-05T07:00:00+02:00",
    )
    create_entity(
        repository,
        SCHEMA,
        path="preparar dossier - parent.md",
        entity_id="task-parent",
        metadata={"name": "Preparar dossier", "type": "task", "status": "pending"},
        content="- Preparar dossier.\n",
        actor="fixture",
        now="2026-10-05T07:00:00+02:00",
    )
    base_plan = RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria(
                            "Reunir documentos", "reunir documentos", "task", (), None
                        ),
                        "record",
                        (PropertyChange("status", "set", "pending"),),
                        (),
                        ("Reunir documentos.",),
                        (),
                        "one",
                        fact_temporal_anchors=((),),
                    ),
                )
            ),
        ),
        (),
    )
    interpretation = TaskInterpretation(
        "Beatriz tiene que reunir documentos para preparar dossier",
        TaskOperation.CREATE,
        relationship_mentions=(
            TaskRelationshipMention("Beatriz", TaskRelationshipRole.ASSIGNEE),
            TaskRelationshipMention("preparar dossier", TaskRelationshipRole.PARENT_TASK),
        ),
    )
    planner = TaskCorePlanner(SimpleNamespace(plan=lambda *_: base_plan), interpretation)
    embedder = Embedder()
    context = ContextIndex(tmp_path / "context.sqlite3")
    semantic = SemanticEntityIndex(tmp_path / "semantic-tasks.sqlite3")
    context.rebuild(repository, SCHEMA, embedder)
    semantic.rebuild(repository, PLANNING_SCHEMA, embedder)
    result = execute_request(
        interpretation.source_text,
        planner=planner,
        repository=repository,
        schema=PLANNING_SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=FirstReasoner(),
        actor="tasks-e2e",
        now="2026-10-05T07:10:00+02:00",
        context_limit=10,
        request_id_factory=lambda: "task-relations",
        preflight_id_allocator=lambda: "task-child",
        write_preflight_guard=TaskLifecycleGuard(TaskOperation.CREATE),
    )
    assert result.status is ApplicationStatus.COMPLETED
    child_path = next(path for path in repository.list_markdown_paths() if "task-child" in path)
    child = repository.read_text(child_path)
    assert "- Reunir documentos." in child
    assert "Responsable: [[people/beatriz|Beatriz]]." in child
    assert "Tarea superior: [[preparar dossier - parent|Preparar dossier]]." in child

    context.rebuild(repository, SCHEMA, embedder)
    notes = NotesQueryService(repository, SCHEMA, context)
    backlinks = notes.backlinks("task-parent")
    assert [(item.source.id, item.occurrences) for item in backlinks.items] == [("task-child", 1)]


def test_missing_parent_task_clarifies_without_creating_hidden_parent(tmp_path: Path) -> None:
    """A parent-task reference must not bypass Tasks lifecycle authority by creating itself."""
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    base_plan = RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria("Reservar hotel", "reservar hotel", "task", (), None),
                        "record",
                        (PropertyChange("status", "set", "pending"),),
                        (),
                        ("Reservar hotel.",),
                        (),
                        "one",
                        fact_temporal_anchors=((),),
                    ),
                )
            ),
        ),
        (),
    )
    interpretation = TaskInterpretation(
        "Tengo que reservar hotel como subtarea de preparar el viaje",
        TaskOperation.CREATE,
        relationship_mentions=(
            TaskRelationshipMention("preparar el viaje", TaskRelationshipRole.PARENT_TASK),
        ),
    )
    planner = TaskCorePlanner(SimpleNamespace(plan=lambda *_: base_plan), interpretation)
    embedder = Embedder()
    context = ContextIndex(tmp_path / "context.sqlite3")
    semantic = SemanticEntityIndex(tmp_path / "semantic-tasks.sqlite3")
    context.rebuild(repository, SCHEMA, embedder)
    semantic.rebuild(repository, PLANNING_SCHEMA, embedder)

    result = execute_request(
        interpretation.source_text,
        planner=planner,
        repository=repository,
        schema=PLANNING_SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=FirstReasoner(),
        actor="tasks-e2e",
        now="2026-10-05T07:10:00+02:00",
        context_limit=10,
        request_id_factory=lambda: "task-missing-parent",
        preflight_id_allocator=iter(("task-child", "must-not-create-parent")).__next__,
        write_preflight_guard=TaskLifecycleGuard(TaskOperation.CREATE),
    )

    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.affected_stable_note_ids == ()
    assert repository.list_markdown_paths() == []
    primary, parent = result.action_results[0].unit_results
    assert primary.reason == "DEPENDENCY_FAILED"
    assert parent.reason == "unresolved_existing_reference"
