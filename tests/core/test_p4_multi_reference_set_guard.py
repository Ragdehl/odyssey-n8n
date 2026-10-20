"""N:M Core references must all survive to one E3-protected write action."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from odyssey_core.application import DependentReferenceSetGuard, WritePreflightGuardError
from odyssey_core.dependent_group_evidence import prove_canonical_group_handoff
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    SelectionCriteria,
    WriteAction,
)
from tests.core.test_p4_canonical_group_handoff import written_predecessors
from tests.runtime.test_p4_dependent_router_integrated import SCHEMA


def plan(*, include_second=True):
    references = (KnowledgeReference(1, "task", "ambas tareas"),)
    facts = ("Comparar {{ref:0}}.",)
    if include_second:
        references += (KnowledgeReference(2, "task", "ambas tareas"),)
        facts = ("Comparar {{ref:0}} y {{ref:1}}.",)
    primary = KnowledgeUnit(
        SelectionCriteria("Comparar tareas", "Comparar tareas", "task", (), None),
        "record",
        (),
        (),
        facts,
        references,
    )
    helpers = tuple(
        KnowledgeUnit(
            SelectionCriteria(name, name, "task", (), None),
            "record",
            (),
            (),
            (),
            (),
            reference_lookup_only=True,
        )
        for name in ("Preparar informe Atlas", "Revisar contratos")
    )
    return WriteAction((primary, *helpers))


def preflights(ids=("atlas-p4-dependent-task", "other-task")):
    return (
        SimpleNamespace(unit_index=0, stable_id="new-task", canonical_name="Comparar tareas"),
        SimpleNamespace(unit_index=1, stable_id=ids[0], canonical_name="Preparar informe Atlas"),
        SimpleNamespace(unit_index=2, stable_id=ids[1], canonical_name="Revisar contratos"),
    )


def test_multi_core_dependency_requires_all_two_materialized_receipts(tmp_path):
    repo, graph, first, second = written_predecessors.__wrapped__(tmp_path)
    handoff = prove_canonical_group_handoff(
        graph=graph,
        consumer_index=2,
        predecessors={0: first, 1: second},
        repository=repo,
        schema=SCHEMA,
    )

    guard = DependentReferenceSetGuard(tuple(edge.core_write_guard() for edge in handoff.edges))
    guard(plan(), preflights(), repo, SCHEMA)
    with pytest.raises(WritePreflightGuardError, match="REFERENCE_MARKER"):
        guard(plan(include_second=False), preflights(), repo, SCHEMA)
    with pytest.raises(WritePreflightGuardError, match="REFERENCE_MARKER"):
        guard(plan(), preflights(("atlas-p4-dependent-task", "wrong-task")), repo, SCHEMA)
    with pytest.raises(WritePreflightGuardError, match="SET_INVALID"):
        DependentReferenceSetGuard((guard.guards[0], guard.guards[0]))
    with pytest.raises(WritePreflightGuardError, match="SET_INVALID"):
        DependentReferenceSetGuard((guard.guards[0],))


def test_existing_core_writer_can_persist_two_verified_links_in_one_task(tmp_path):
    """Proof of mechanism: no new Writer/schema needed for the set of links."""
    from types import SimpleNamespace

    from odyssey_apps.tasks import TaskLifecycleGuard, TaskOperation
    from odyssey_core.application import ApplicationStatus, execute_request
    from odyssey_core.context import ContextIndex
    from odyssey_core.notes import parse_note
    from odyssey_core.request_planning import PropertyChange, RequestPlan
    from odyssey_core.schema_types import planning_schema_for_capability
    from odyssey_core.semantic import SemanticEntityIndex
    from tests.apps.tasks.test_core_interop import Embedder, Reasoner

    repo, graph, first, second = written_predecessors.__wrapped__(tmp_path)
    handoff = prove_canonical_group_handoff(
        graph=graph,
        consumer_index=2,
        predecessors={0: first, 1: second},
        repository=repo,
        schema=SCHEMA,
    )
    guard = DependentReferenceSetGuard(tuple(edge.core_write_guard() for edge in handoff.edges))
    embedder = Embedder()
    context = ContextIndex(tmp_path / "group-write-context.sqlite3")
    semantic = SemanticEntityIndex(tmp_path / "group-write-semantic.sqlite3")
    context.rebuild(repo, SCHEMA, embedder)
    semantic.rebuild(repo, SCHEMA, embedder)
    initial = plan()
    unit = initial.units[0]
    desired = replace(
        unit,
        properties=(PropertyChange("status", "set", "pending"),),
        force_create=True,
        fact_temporal_anchors=((),),
    )
    write = WriteAction((desired, *initial.units[1:]))
    task_guard = TaskLifecycleGuard(TaskOperation.CREATE)

    def combined(action, preflight, repository, schema):
        guard(action, preflight, repository, schema)
        task_guard(action, preflight, repository, schema)

    result = execute_request(
        "Ahora compara ambas tareas.",
        planner=SimpleNamespace(plan=lambda *_: RequestPlan((write,), ())),
        repository=repo,
        schema=planning_schema_for_capability(SCHEMA, "tasks"),
        context_index=context,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=Reasoner(),
        actor="synthetic-multireference",
        now="2026-10-20T18:00:00+02:00",
        context_limit=10,
        write_preflight_guard=combined,
        request_id_factory=lambda: "e4-multi-reference-writer-replay",
    )
    assert result.status is ApplicationStatus.COMPLETED, (result.status, result.planning_error)
    notes = [parse_note(repo.read_text(path)) for path in repo.list_markdown_paths()]
    matched = [n for n in notes if n.metadata.get("name") == "Comparar tareas"]
    assert len(matched) == 1
    assert "[[atlas|Preparar informe Atlas]]" in matched[0].content
    assert "[[other-task|Revisar contratos]]" in matched[0].content
