"""Deterministic Phase 17A application-composition coverage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

import odyssey_core.application as application
from odyssey_core import (
    ApplicationStatus,
    BulkUpdateResult,
    DelegateAction,
    KnowledgeReference,
    KnowledgeUnit,
    RequestPlan,
    RetrieveAction,
    SelectionCriteria,
    UnitStatus,
    WriteAction,
    WriteTargetOutcome,
)
from odyssey_core.persistence import EntityPersistenceResult, PersistenceOperation
from odyssey_core.reference_binding import PendingReference, ReferenceRenderingResult
from odyssey_core.reference_preflight import UnitTargetPreflight


@dataclass
class FakePlanner:
    """Return one frozen plan without contacting a model provider."""

    value: RequestPlan | Exception
    calls: int = 0

    def plan(self, request: str) -> RequestPlan:
        """Return the configured plan or raise its configured planning failure."""
        self.calls += 1
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def unit(name: str, *, references: tuple[KnowledgeReference, ...] = ()) -> KnowledgeUnit:
    """Build a small validated-shaped record unit for application tests."""
    return KnowledgeUnit(
        SelectionCriteria(name, name, "person", (), None), "record", (), (), (), references
    )


def run(plan: RequestPlan, monkeypatch: pytest.MonkeyPatch, **kwargs: Any):
    """Run an application request with inert injected Core dependencies."""
    return application.execute_request(
        "request",
        planner=FakePlanner(plan),
        repository=object(),
        schema={},
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="test",
        now="2026-08-28T12:00:00Z",
        context_limit=5,
        request_id_factory=lambda: "request-17a",
        **kwargs,
    )


def test_retrieve_uses_existing_context_and_propagates_one_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Execute an ordinary read through get_context without invoking any model transport."""
    retrieved = object()
    calls: list[dict[str, Any]] = []

    def fake_context(*args: Any, **kwargs: Any) -> object:
        calls.append(kwargs)
        return retrieved

    monkeypatch.setattr(application, "get_context", fake_context)
    plan = RequestPlan((RetrieveAction(SelectionCriteria(None, "Marta", None, (), None)),), ())

    result = run(plan, monkeypatch)

    assert result.request_id == "request-17a"
    assert result.status is ApplicationStatus.COMPLETED
    assert result.action_results[0].retrieval is retrieved
    assert calls == [{"query": "Marta", "limit": 5, "type": None, "filters": ()}]


def test_create_dependency_runs_target_first_with_preflighted_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Order referenced CREATE targets first without resolving them again per occurrence."""
    target = unit("Airbus")
    source = unit("Laura", references=(KnowledgeReference(1, "employer", "Airbus"),))
    action = WriteAction((source, target))
    preflight = (
        UnitTargetPreflight(
            0, WriteTargetOutcome.CREATE, "laura-id", "Laura", "Laura - laura-id.md"
        ),
        UnitTargetPreflight(
            1, WriteTargetOutcome.CREATE, "airbus-id", "Airbus", "Airbus - airbus-id.md"
        ),
    )
    calls: list[int] = []
    preflight_calls: list[tuple[Any, ...]] = []

    def preflight_once(*args: Any, **kwargs: Any) -> tuple[UnitTargetPreflight, ...]:
        preflight_calls.append(args)
        return preflight

    render_calls: list[tuple[Any, ...]] = []

    def render_once(*args: Any) -> ReferenceRenderingResult:
        render_calls.append(args)
        assert args[1] is preflight
        return ReferenceRenderingResult((("Works at [[Airbus - airbus-id|Airbus]].",), ()), ())

    monkeypatch.setattr(application, "preflight_write_action", preflight_once)
    monkeypatch.setattr(
        application,
        "render_reference_facts",
        render_once,
    )
    rendered_by_index: dict[int, tuple[str, ...]] = {}

    def create(*args: Any, unit_index: int, **kwargs: Any) -> EntityPersistenceResult:
        calls.append(unit_index)
        rendered_by_index[unit_index] = kwargs["rendered_facts"]
        item = preflight[unit_index]
        return EntityPersistenceResult(
            PersistenceOperation.CREATED, item.stable_id or "", item.path or "", 1
        )

    monkeypatch.setattr(application, "materialize_create", create)
    result = run(RequestPlan((action,), ()), monkeypatch)

    assert calls == [1, 0]
    assert len(preflight_calls) == 1
    assert len(render_calls) == 1
    assert rendered_by_index[0] == ("Works at [[Airbus - airbus-id|Airbus]].",)
    assert result.affected_stable_note_ids == ("laura-id", "airbus-id")
    assert [item.status for item in result.action_results[0].unit_results] == [
        UnitStatus.SUCCEEDED,
        UnitStatus.SUCCEEDED,
    ]


def test_pending_reference_allows_safe_source_and_defers_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persist a safe source with a plain unresolved mention while deferring its target."""
    action = WriteAction(
        (unit("Laura", references=(KnowledgeReference(1, "friend", "Marta"),)), unit("Marta"))
    )
    preflight = (
        UnitTargetPreflight(0, WriteTargetOutcome.CREATE, "laura-id", "Laura", "Laura.md"),
        UnitTargetPreflight(
            1,
            WriteTargetOutcome.NEEDS_CLARIFICATION,
            candidate_note_ids=("m1", "m2"),
            reason="ambiguous",
        ),
    )
    monkeypatch.setattr(application, "preflight_write_action", lambda *args, **kwargs: preflight)
    monkeypatch.setattr(
        application,
        "render_reference_facts",
        lambda *args: ReferenceRenderingResult(
            (("Marta",), ()),
            (PendingReference(0, 0, 1, "friend", "Marta", "ambiguous", ("m1", "m2")),),
        ),
    )
    writes: list[int] = []

    def create(*args: Any, unit_index: int, **kwargs: Any) -> EntityPersistenceResult:
        writes.append(unit_index)
        item = preflight[unit_index]
        return EntityPersistenceResult(
            PersistenceOperation.CREATED, item.stable_id or "", item.path or "", 1
        )

    monkeypatch.setattr(application, "materialize_create", create)

    result = run(RequestPlan((action,), ()), monkeypatch)

    source, target = result.action_results[0].unit_results
    assert source.status is UnitStatus.SUCCEEDED
    assert source.stable_note_id == "laura-id"
    assert target.status is UnitStatus.DEFERRED
    assert target.candidates == ("m1", "m2")
    assert writes == [0]


def test_failed_create_defers_dependent_but_runs_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve target failure while independent and dependency-safe writes continue."""
    target, source, independent = (
        unit("Airbus"),
        unit("Laura", references=(KnowledgeReference(0, "employer", "Airbus"),)),
        unit("Bea"),
    )
    action = WriteAction((target, source, independent))
    preflight = tuple(
        UnitTargetPreflight(index, WriteTargetOutcome.CREATE, f"{name}-id", name, f"{name}.md")
        for index, name in enumerate(("Airbus", "Laura", "Bea"))
    )
    monkeypatch.setattr(application, "preflight_write_action", lambda *args, **kwargs: preflight)
    monkeypatch.setattr(
        application,
        "render_reference_facts",
        lambda *args: ReferenceRenderingResult(((), (), ()), ()),
    )

    def create(*args: Any, unit_index: int, **kwargs: Any) -> EntityPersistenceResult:
        if unit_index == 0:
            raise RuntimeError("disk failure")
        item = preflight[unit_index]
        return EntityPersistenceResult(
            PersistenceOperation.CREATED, item.stable_id or "", item.path or "", 1
        )

    monkeypatch.setattr(application, "materialize_create", create)
    result = run(RequestPlan((action,), ()), monkeypatch)

    target_result, source_result, independent_result = result.action_results[0].unit_results
    assert target_result.status is UnitStatus.FAILED
    assert source_result.status is UnitStatus.DEFERRED
    assert source_result.dependencies
    assert independent_result.status is UnitStatus.SUCCEEDED
    assert result.status is ApplicationStatus.PARTIAL


def test_execute_request_create_does_not_forward_fact_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CREATE receives request ordinals but never the UPDATE-only fact selector."""
    action = WriteAction((unit("Marta"),))
    preflight = (
        UnitTargetPreflight(0, WriteTargetOutcome.CREATE, "marta-id", "Marta", "Marta.md"),
    )
    monkeypatch.setattr(application, "preflight_write_action", lambda *args, **kwargs: preflight)
    monkeypatch.setattr(
        application, "render_reference_facts", lambda *args: ReferenceRenderingResult(((),), ())
    )
    calls: list[dict[str, Any]] = []

    def create(*args: Any, **kwargs: Any) -> EntityPersistenceResult:
        calls.append(kwargs)
        item = preflight[0]
        return EntityPersistenceResult(
            PersistenceOperation.CREATED, item.stable_id or "", item.path or "", 1
        )

    monkeypatch.setattr(application, "materialize_create", create)
    selector = object()
    result = run(RequestPlan((action,), ()), monkeypatch, fact_selector=selector)

    assert result.status is ApplicationStatus.COMPLETED
    assert calls[0]["request_id"] == "request-17a"
    assert calls[0]["fact_ordinals"] == ()
    assert "fact_selector" not in calls[0]


def test_execute_request_update_forwards_fact_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    """An injected selector reaches UPDATE materialization through request execution."""
    target_unit = KnowledgeUnit(
        SelectionCriteria("Marta", "Marta", "person", (), None),
        "remove",
        (),
        (),
        ("lo del piano",),
        (),
    )
    action = WriteAction((target_unit,))
    preflight = (
        UnitTargetPreflight(0, WriteTargetOutcome.UPDATE, "marta-id", "Marta", "Marta.md"),
    )
    monkeypatch.setattr(application, "preflight_write_action", lambda *args, **kwargs: preflight)
    monkeypatch.setattr(
        application, "render_reference_facts", lambda *args: ReferenceRenderingResult(((),), ())
    )
    calls: list[dict[str, Any]] = []

    def update(*args: Any, **kwargs: Any) -> EntityPersistenceResult:
        calls.append(kwargs)
        return EntityPersistenceResult(PersistenceOperation.UPDATED, "marta-id", "Marta.md", 2)

    monkeypatch.setattr(application, "materialize_update", update)
    selector = object()
    result = run(RequestPlan((action,), ()), monkeypatch, fact_selector=selector)

    assert result.status is ApplicationStatus.COMPLETED
    assert calls[0]["fact_selector"] is selector


def test_delegate_and_planning_failure_are_typed_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve delegation and fail planning before any execution primitive is reached."""
    delegated = run(RequestPlan((DelegateAction("translate this", None),), ()), monkeypatch)
    assert delegated.status is ApplicationStatus.NEEDS_ATTENTION
    assert delegated.action_results[0].delegated_request == "translate this"

    failed = application.execute_request(
        "request",
        planner=FakePlanner(RuntimeError("planner unavailable")),
        repository=object(),
        schema={},
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="test",
        now="2026-08-28T12:00:00Z",
        context_limit=5,
        request_id_factory=lambda: "request-17a",
    )
    assert failed.status is ApplicationStatus.FAILED
    assert failed.action_results == ()


@pytest.mark.parametrize(
    ("knowledge", "operation", "materializer"),
    [
        (
            KnowledgeUnit(
                SelectionCriteria("Marta", "Marta", "person", (), None), "amend", (), (), (), ()
            ),
            PersistenceOperation.UPDATED,
            "materialize_update",
        ),
        (
            KnowledgeUnit(
                SelectionCriteria("Marta", "Marta", "person", (), None), "delete", (), (), (), ()
            ),
            PersistenceOperation.DELETED,
            "materialize_delete",
        ),
        (
            KnowledgeUnit(
                SelectionCriteria("Marta", "Marta", "person", (), None),
                "amend",
                (),
                (),
                (),
                (),
                destination_type="project",
            ),
            PersistenceOperation.MIGRATED,
            "materialize_type_migration",
        ),
    ],
)
def test_existing_single_unit_routes_to_the_matching_materializer(
    monkeypatch: pytest.MonkeyPatch,
    knowledge: KnowledgeUnit,
    operation: PersistenceOperation,
    materializer: str,
) -> None:
    """Reuse the established update, delete, and migration boundaries without re-resolution."""
    preflight = (
        UnitTargetPreflight(0, WriteTargetOutcome.UPDATE, "marta-id", "Marta", "Marta.md"),
    )
    calls: list[str] = []
    monkeypatch.setattr(application, "preflight_write_action", lambda *args, **kwargs: preflight)
    monkeypatch.setattr(
        application, "render_reference_facts", lambda *args: ReferenceRenderingResult(((),), ())
    )

    def persist(*args: Any, **kwargs: Any) -> EntityPersistenceResult:
        calls.append(materializer)
        return EntityPersistenceResult(operation, "marta-id", "Marta.md", 2)

    monkeypatch.setattr(application, materializer, persist)
    result = run(RequestPlan((WriteAction((knowledge,)),), ()), monkeypatch)

    assert calls == [materializer]
    assert result.affected_stable_note_ids == ("marta-id",)


def test_bulk_and_cyclic_create_are_explicit_and_provider_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delegate bulk evidence and fail closed for CREATE cycles without any mutation."""
    bulk = KnowledgeUnit(
        SelectionCriteria(None, "people", "person", (), None),
        "amend",
        (),
        (),
        (),
        (),
        "all_matching",
    )
    bulk_result = BulkUpdateResult("all_matching", ("m1",), (), (), "EMPTY_SET")
    monkeypatch.setattr(application, "execute_bulk_update", lambda *args, **kwargs: bulk_result)
    result = run(RequestPlan((WriteAction((bulk,)),), ()), monkeypatch)
    assert result.action_results[0].bulk_result is bulk_result

    first = unit("A", references=(KnowledgeReference(1, "peer", "B"),))
    second = unit("B", references=(KnowledgeReference(0, "peer", "A"),))
    preflight = (
        UnitTargetPreflight(0, WriteTargetOutcome.CREATE, "a-id", "A", "A.md"),
        UnitTargetPreflight(1, WriteTargetOutcome.CREATE, "b-id", "B", "B.md"),
    )
    monkeypatch.setattr(application, "preflight_write_action", lambda *args, **kwargs: preflight)
    monkeypatch.setattr(
        application, "render_reference_facts", lambda *args: ReferenceRenderingResult(((), ()), ())
    )
    monkeypatch.setattr(
        application,
        "materialize_create",
        lambda *args, **kwargs: pytest.fail("cycle must not write"),
    )
    cyclic = run(RequestPlan((WriteAction((first, second)),), ()), monkeypatch)
    assert {item.reason for item in cyclic.action_results[0].unit_results} == {
        "CYCLIC_CREATE_DEPENDENCY"
    }


def test_cycle_descendant_gets_dependency_failure_and_independent_unit_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return complete results when a downstream unit depends on a CREATE cycle."""
    first = unit("A", references=(KnowledgeReference(1, "peer", "B"),))
    second = unit("B", references=(KnowledgeReference(0, "peer", "A"),))
    descendant = unit("C", references=(KnowledgeReference(0, "peer", "A"),))
    independent = unit("D")
    action = WriteAction((first, second, descendant, independent))
    preflight = tuple(
        UnitTargetPreflight(index, WriteTargetOutcome.CREATE, f"{name}-id", name, f"{name}.md")
        for index, name in enumerate(("A", "B", "C", "D"))
    )
    writes: list[int] = []
    monkeypatch.setattr(application, "preflight_write_action", lambda *args, **kwargs: preflight)
    monkeypatch.setattr(
        application,
        "render_reference_facts",
        lambda *args: ReferenceRenderingResult(((), (), (), ()), ()),
    )

    def create(*args: Any, unit_index: int, **kwargs: Any) -> EntityPersistenceResult:
        writes.append(unit_index)
        item = preflight[unit_index]
        return EntityPersistenceResult(
            PersistenceOperation.CREATED, item.stable_id or "", item.path or "", 1
        )

    monkeypatch.setattr(application, "materialize_create", create)
    result = run(RequestPlan((action,), ()), monkeypatch)

    units = result.action_results[0].unit_results
    assert len(units) == 4
    assert units[0].reason == units[1].reason == "CYCLIC_CREATE_DEPENDENCY"
    assert units[2].reason == "DEPENDENCY_FAILED"
    assert units[3].status is UnitStatus.SUCCEEDED
    assert writes == [3]


def test_multiple_pending_references_remain_typed_without_blocking_source_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve every unresolved reference while allowing the independently safe source to write."""
    source = unit(
        "Laura",
        references=(
            KnowledgeReference(1, "friend", "Marta"),
            KnowledgeReference(2, "employer", "Airbus"),
        ),
    )
    action = WriteAction((source, unit("Marta"), unit("Airbus")))
    preflight = (
        UnitTargetPreflight(0, WriteTargetOutcome.CREATE, "laura-id", "Laura", "Laura.md"),
        UnitTargetPreflight(
            1,
            WriteTargetOutcome.NEEDS_CLARIFICATION,
            candidate_note_ids=("marta-1", "marta-2"),
            reason="ambiguous Marta",
        ),
        UnitTargetPreflight(
            2,
            WriteTargetOutcome.NEEDS_CLARIFICATION,
            candidate_note_ids=("airbus-1",),
            reason="ambiguous Airbus",
        ),
    )
    monkeypatch.setattr(application, "preflight_write_action", lambda *args, **kwargs: preflight)
    pending = (
        PendingReference(0, 0, 1, "friend", "Marta", "ambiguous Marta", ("marta-1", "marta-2")),
        PendingReference(0, 1, 2, "employer", "Airbus", "ambiguous Airbus", ("airbus-1",)),
    )
    rendered: list[tuple[str, ...]] = []

    def render(*args: Any) -> ReferenceRenderingResult:
        """Capture plain rendered facts while returning all unresolved reference evidence."""
        rendering = ReferenceRenderingResult((("Marta and Airbus",), (), ()), pending)
        rendered.extend(rendering.rendered_facts)
        return rendering

    monkeypatch.setattr(
        application,
        "render_reference_facts",
        render,
    )
    writes: list[int] = []

    def create(*args: Any, unit_index: int, **kwargs: Any) -> EntityPersistenceResult:
        writes.append(unit_index)
        item = preflight[unit_index]
        return EntityPersistenceResult(
            PersistenceOperation.CREATED, item.stable_id or "", item.path or "", 1
        )

    monkeypatch.setattr(application, "materialize_create", create)

    result = run(RequestPlan((action,), ()), monkeypatch)

    source_result = result.action_results[0].unit_results[0]
    assert source_result.status is UnitStatus.SUCCEEDED
    assert source_result.stable_note_id == "laura-id"
    assert result.action_results[0].unit_results[1].status is UnitStatus.DEFERRED
    assert result.action_results[0].unit_results[2].status is UnitStatus.DEFERRED
    assert writes == [0]
    assert rendered[0] == ("Marta and Airbus",)
