"""Tasks stay ordinary knowledge targets without surrendering app-owned lifecycle creation."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace

from odyssey_apps.schema_extensions import compose_application_schema
from odyssey_apps.tasks import (
    TASK_SCHEMA_EXTENSION,
    TaskLifecycleGuard,
    TaskOperation,
)
from odyssey_core import create_entity
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.context import ContextIndex
from odyssey_core.planner_capabilities import build_planner_capabilities, build_write_capabilities
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
from odyssey_core.write_target import WriteTargetOutcome, decide_write_target

ROOT = Path(__file__).resolve().parents[3]
BASE = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
SCHEMA = compose_application_schema(BASE, (TASK_SCHEMA_EXTENSION,))


class Embedder:
    model_name = "tests/tasks-core-interop"
    model_version = "1"

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [[1.0, 0.5] for _ in texts]

    def embed_queries(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return self.embed_documents(texts)


class Reasoner:
    def resolve(self, request):  # type: ignore[no-untyped-def]
        if not request.candidates:
            return ({"outcome": "NO_MATCH", "id": None, "ambiguous_ids": []}, {})
        candidate = request.candidates[0]
        return ({"outcome": "RESOLVED", "id": candidate.id, "ambiguous_ids": []}, {})


def _task_unit(name: str, *, facts: tuple[str, ...], intent: str = "amend") -> KnowledgeUnit:
    return KnowledgeUnit(
        SelectionCriteria(name, name, "task", (), None),
        intent,
        (),
        (),
        facts,
        (),
        "one",
        fact_temporal_anchors=tuple(() for _ in facts),
    )


def test_generic_contract_exposes_task_identity_but_not_lifecycle_properties() -> None:
    retrieval = build_planner_capabilities(SCHEMA)
    writes = build_write_capabilities(SCHEMA)
    assert "task" in retrieval["types"]
    assert "task" in writes["types"]
    assert writes["types"]["task"]["properties"] == {}
    for field in (
        "status",
        "target_date",
        "planned_start_at",
        "planned_end_at",
        "deadline_at",
        "completed_at",
    ):
        assert field not in retrieval["filters"]


def test_tasks_route_reclaims_its_lifecycle_filters_without_expanding_generic_core() -> None:
    retrieval = build_planner_capabilities(planning_schema_for_capability(SCHEMA, "tasks"))
    for field in (
        "status",
        "target_date",
        "planned_start_at",
        "planned_end_at",
        "deadline_at",
        "completed_at",
    ):
        assert retrieval["filters"][field]["applies_to"] == ["task"]


def test_core_can_add_ordinary_fact_to_existing_task(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    create_entity(
        repository,
        SCHEMA,
        path="llamar banco.md",
        entity_id="task-bank",
        metadata={
            "name": "Llamar al banco",
            "type": "task",
            "status": "pending",
            "target_date": "2026-10-09",
        },
        content="- Llamar al banco.\n",
        actor="fixture",
        now="2026-10-05T07:00:00+02:00",
    )
    embedder = Embedder()
    context = ContextIndex(tmp_path / "context.sqlite3")
    semantic = SemanticEntityIndex(tmp_path / "semantic.sqlite3")
    assert context.rebuild(repository, SCHEMA, embedder) == 1
    assert semantic.rebuild(repository, SCHEMA, embedder) == 1
    plan = RequestPlan(
        (
            WriteAction(
                (
                    _task_unit(
                        "Llamar al banco",
                        facts=("Preguntar por las comisiones.",),
                        intent="record",
                    ),
                )
            ),
        ),
        (),
    )
    result = execute_request(
        "Añade a la tarea llamar al banco que tengo que preguntar por las comisiones",
        planner=SimpleNamespace(plan=lambda *_: plan, is_local_replay=True),
        repository=repository,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=Reasoner(),
        actor="core-e2e",
        now="2026-10-05T07:15:00+02:00",
        context_limit=10,
        request_id_factory=lambda: "task-core-amend",
    )
    assert result.status is ApplicationStatus.COMPLETED
    raw = repository.read_text("llamar banco.md")
    assert "Preguntar por las comisiones." in raw
    assert 'status: "pending"' in raw
    assert 'target_date: "2026-10-09"' in raw


def test_generic_core_cannot_create_missing_managed_task(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    embedder = Embedder()
    semantic = SemanticEntityIndex(tmp_path / "semantic.sqlite3")
    semantic.rebuild(repository, SCHEMA, embedder)
    decision = decide_write_target(
        _task_unit("Enviar documentación", facts=("Enviar documentación.",), intent="record"),
        repository=repository,
        schema=SCHEMA,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=Reasoner(),
        semantic_limit=5,
    )
    assert decision.outcome is WriteTargetOutcome.NEEDS_CLARIFICATION
    assert decision.reason == "managed_type_requires_application_create"


def test_task_lifecycle_update_changes_status_and_markdown_checkbox_atomically(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    create_entity(
        repository,
        SCHEMA,
        path="llamar banco.md",
        entity_id="task-bank",
        metadata={"name": "Llamar al banco", "type": "task", "status": "pending"},
        content="- Llamar al banco.\n",
        actor="fixture",
        now="2026-10-05T07:00:00+02:00",
    )
    embedder = Embedder()
    context = ContextIndex(tmp_path / "context.sqlite3")
    semantic = SemanticEntityIndex(tmp_path / "semantic.sqlite3")
    context.rebuild(repository, SCHEMA, embedder)
    semantic.rebuild(repository, SCHEMA, embedder)
    plan = RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria("Llamar al banco", "Llamar al banco", "task", (), None),
                        "amend",
                        (
                            PropertyChange("status", "set", "completed"),
                            PropertyChange("completed_at", "set", "2026-10-05T07:20:00+02:00"),
                        ),
                        (),
                        (),
                        (),
                        "one",
                    ),
                )
            ),
        ),
        (),
    )
    result = execute_request(
        "Marca llamar al banco como hecho",
        planner=SimpleNamespace(plan=lambda *_: plan, is_local_replay=True),
        repository=repository,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=Reasoner(),
        actor="tasks-e2e",
        now="2026-10-05T07:20:00+02:00",
        context_limit=10,
        request_id_factory=lambda: "task-complete",
        write_preflight_guard=TaskLifecycleGuard(TaskOperation.COMPLETE),
    )
    assert result.status is ApplicationStatus.COMPLETED
    raw = repository.read_text("llamar banco.md")
    assert 'status: "completed"' in raw
    assert 'completed_at: "2026-10-05T07:20:00+02:00"' in raw
    assert "- Llamar al banco." in raw
    assert "revision: 2" in raw


def test_task_status_mutation_accepts_legacy_body_without_checkbox(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    create_entity(
        repository,
        SCHEMA,
        path="legacy.md",
        entity_id="task-legacy",
        metadata={"name": "Legacy", "type": "task", "status": "pending"},
        content="- Legacy.\n",
        actor="fixture",
        now="2026-10-05T07:00:00+02:00",
    )
    embedder = Embedder()
    context = ContextIndex(tmp_path / "context.sqlite3")
    semantic = SemanticEntityIndex(tmp_path / "semantic.sqlite3")
    context.rebuild(repository, SCHEMA, embedder)
    semantic.rebuild(repository, SCHEMA, embedder)
    plan = RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria("Legacy", "Legacy", "task", (), None),
                        "amend",
                        (PropertyChange("status", "set", "completed"),),
                        (),
                        (),
                        (),
                        "one",
                    ),
                )
            ),
        ),
        (),
    )
    result = execute_request(
        "Completa Legacy",
        planner=SimpleNamespace(plan=lambda *_: plan, is_local_replay=True),
        repository=repository,
        schema=SCHEMA,
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=Reasoner(),
        actor="tasks-e2e",
        now="2026-10-05T07:20:00+02:00",
        context_limit=10,
        request_id_factory=lambda: "task-legacy-complete",
        write_preflight_guard=TaskLifecycleGuard(TaskOperation.COMPLETE),
    )
    assert result.status is ApplicationStatus.COMPLETED
    raw = repository.read_text("legacy.md")
    assert 'status: "completed"' in raw
    assert "- Legacy." in raw
    assert "revision: 2" in raw


def test_existing_duplicate_task_titles_require_clarification(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    for task_id, path in (("task-one", "one.md"), ("task-two", "two.md")):
        create_entity(
            repository,
            SCHEMA,
            path=path,
            entity_id=task_id,
            metadata={"name": "Enviar documentación", "type": "task", "status": "pending"},
            content="- Enviar documentación.\n",
            actor="fixture",
            now="2026-10-05T07:00:00+02:00",
        )
    embedder = Embedder()
    semantic = SemanticEntityIndex(tmp_path / "semantic.sqlite3")
    semantic.rebuild(repository, SCHEMA, embedder)
    decision = decide_write_target(
        _task_unit("Enviar documentación", facts=()),
        repository=repository,
        schema=SCHEMA,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=Reasoner(),
        semantic_limit=5,
    )
    assert decision.outcome is WriteTargetOutcome.NEEDS_CLARIFICATION
    assert set(decision.candidate_note_ids) == {"task-one", "task-two"}
    assert decision.reason == "ambiguous_existing_target"
