"""Provider-free user-path regressions for Router -> Temporal -> Core -> Calendar."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

from odyssey_apps import ApplicationCatalog, Route, RouteOutcome, RoutePlan
from odyssey_apps.calendar import CalendarQueryService
from odyssey_core.application import (
    ApplicationStatus,
    DependentReferenceGuard,
    execute_request,
)
from odyssey_core.context import ContextIndex
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.notes import Note, serialize_note
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal import TemporalAnchor
from odyssey_runtime.routing import execute_routed_request

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
NOW = "2026-10-04T17:35:00+02:00"


class FixedRouter:
    """Replay one already-validated routing decision without a provider call."""

    def __init__(self, routes: tuple[Route, ...]) -> None:
        self._plan = RoutePlan(RouteOutcome.ROUTE, routes)

    def route(self, request: str, conversation_context=()) -> RoutePlan:
        del request, conversation_context
        return self._plan


class ConstantEmbedder:
    """Build disposable derived indexes without a model dependency."""

    model_name = "tests/temporal-user-path"
    model_version = "1"

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.5] for _ in texts]

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.5] for _ in texts]


def _day_plan(date: str, fact: str, temporal: str) -> RequestPlan:
    anchor = TemporalAnchor.from_value(temporal)
    unit = KnowledgeUnit(
        SelectionCriteria(None, date, "calendar_day", (), None),
        "record",
        (),
        (),
        (fact,),
        (),
        fact_temporal_anchors=((anchor,),),
    )
    return RequestPlan((WriteAction((unit,)),), ())


def _linked_day_plan(
    date: str,
    fact: str,
    mention: str,
    temporal: str,
    *,
    target_name: str | None = None,
    create_person: bool = False,
) -> RequestPlan:
    """Build a real Calendar Day fact plus Core-owned person reference lookup helper."""
    anchor = TemporalAnchor.from_value(temporal)
    day = KnowledgeUnit(
        SelectionCriteria(None, date, "calendar_day", (), None),
        "record",
        (),
        (),
        (fact,),
        (KnowledgeReference(1, "person", mention),),
        fact_temporal_anchors=((anchor,),),
    )
    person = KnowledgeUnit(
        SelectionCriteria(target_name or mention, target_name or mention, "person", (), None),
        "record",
        (),
        (),
        (),
        (),
        reference_lookup_only=not create_person,
    )
    return RequestPlan((WriteAction((day, person)),), ())


def _core_with_plan(
    repository: VaultRepository,
    source: str,
    locator: str,
    plan: RequestPlan,
):
    return execute_request(
        source,
        planner=SimpleNamespace(plan=lambda request: plan),
        repository=repository,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="user-path-e2e",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: locator,
    )


def _calendar(repository: VaultRepository, tmp_path: Path) -> CalendarQueryService:
    index = ContextIndex(tmp_path / "runtime" / "context.sqlite3")
    index.rebuild(repository, SCHEMA, ConstantEmbedder())
    notes = NotesQueryService(repository, SCHEMA, index)
    return CalendarQueryService(repository, SCHEMA, notes)


def _visible_day(calendar: CalendarQueryService, date: str) -> list[str]:
    return [
        "".join(segment.text for segment in block.segments) for block in calendar.day(date).content
    ]


def _write_existing_eric(vault: Path) -> None:
    """Seed one schema-valid canonical person for the existing-identity handoff sentinel."""
    note = Note(
        {
            "id": "eric-id",
            "name": "Eric",
            "type": "person",
            "aliases": [],
            "created_at": NOW,
            "updated_at": NOW,
            "created_by": {"human": None, "app": "test"},
            "updated_by": {"human": None, "app": "test"},
            "revision": 1,
            "schema_version": 3,
        },
        "",
    )
    (vault / "Eric.md").write_text(serialize_note(note), encoding="utf-8")


def test_independent_temporal_routes_materialize_separate_days_end_to_end(tmp_path: Path) -> None:
    """Keep independently routed date facts separate through real Core persistence."""
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    source = "Ayer vi a Ana y hoy vi a Luis."
    router = FixedRouter(
        (
            Route("temporal", "Ayer vi a Ana"),
            Route("temporal", "y hoy vi a Luis."),
        )
    )

    def temporal(text, locator, actor, conversation_context):
        del actor, conversation_context
        if text.strip() == "Ayer vi a Ana":
            plan = _day_plan("2026-10-03", "Vi a Ana.", "2026-10-03")
        elif text.strip() == "y hoy vi a Luis.":
            plan = _day_plan("2026-10-04", "Vi a Luis.", "2026-10-04")
        else:  # pragma: no cover - closed frozen route set
            raise AssertionError(text)
        result = _core_with_plan(repository, text, locator, plan)
        if text == "Ayer hablé con Eric.":
            assert result.canonical_reference_evidence
        return result

    prepared = Barrier(2, timeout=3)

    def prepare_temporal(text, prior):
        """Prepare only immutable planning evidence before any vault write begins."""
        assert prior == ()
        prepared.wait()
        return temporal

    result = execute_routed_request(
        user_request=source,
        outer_request_id="temporal-user-split",
        router=router,
        catalog=ApplicationCatalog.empty(),
        core_execute=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("split temporal routes must not bypass Temporal")
        ),
        application_executors={},
        temporal_execute=temporal,
        route_preparers={"temporal": prepare_temporal},
    )

    assert result.status is ApplicationStatus.COMPLETED
    assert result.affected_stable_note_ids == ("date:2026-10-03", "date:2026-10-04")
    assert result.execution_flow is not None
    assert result.execution_flow["input"] == source
    assert result.execution_flow["parallel_preparation"] is True
    first_route, second_route = result.execution_flow["routes"]
    assert first_route["text"] == "Ayer vi a Ana"
    assert second_route["text"] == "y hoy vi a Luis."
    assert first_route["plan"][0]["target"] == "2026-10-03"
    assert second_route["plan"][0]["target"] == "2026-10-04"
    assert first_route["writes"][0]["status"] == "succeeded"
    assert second_route["writes"][0]["status"] == "succeeded"
    # Each validated routed input/plan/output remains available for a future
    # per-message request graph without re-reading or modifying the vault.
    assert len(first_route["steps"]) == first_route["stage_count"]
    assert len(second_route["steps"]) == second_route["stage_count"]
    assert first_route["steps"][0]["name"] == "planner"
    assert first_route["steps"][0]["input"] == "Ayer vi a Ana"
    assert "record · calendar_day → 2026-10-03" in first_route["steps"][0]["output"]
    assert second_route["steps"][0]["input"] == "y hoy vi a Luis."
    assert "2026-10-04" in second_route["steps"][0]["output"]
    assert any(
        "succeeded: " in step["output"] and "2026-10-03" in step["output"]
        for step in first_route["steps"]
        if step["name"] == "action.write"
    )
    calendar = _calendar(repository, tmp_path)
    assert "Vi a Ana." in _visible_day(calendar, "2026-10-03")
    assert "Vi a Luis." in _visible_day(calendar, "2026-10-04")


def test_dependent_eric_route_hands_one_current_core_identity_to_the_normal_writer(
    tmp_path: Path,
) -> None:
    """Persist an exact pronoun link only through predecessor carrier and Core guard."""
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_existing_eric(vault)
    repository = VaultRepository(vault)
    source = "Ayer hablé con Eric. Mañana iré al cine con él. Hoy compré pan."
    router = FixedRouter(
        (
            Route("temporal", "Ayer hablé con Eric."),
            Route("temporal", "Mañana iré al cine con él.", depends_on=0, dependent_mention="él"),
            Route("temporal", "Hoy compré pan."),
        )
    )
    calls: list[str] = []

    def temporal(text, locator, actor, conversation_context, *, dependent_handoff=None):
        del actor, conversation_context
        calls.append(text)
        if text == "Ayer hablé con Eric.":
            plan = _linked_day_plan("2026-10-03", "Hablé con {{ref:0}}.", "Eric", "2026-10-03")
        elif text == "Mañana iré al cine con él.":
            assert dependent_handoff is not None
            assert dependent_handoff.mention == "él"
            assert dependent_handoff.evidence.canonical_name == "Eric"
            plan = _linked_day_plan(
                "2026-10-05", "Iré al cine con {{ref:0}}.", "él", "2026-10-05", target_name="Eric"
            )
            return execute_request(
                text,
                planner=SimpleNamespace(plan=lambda request: plan),
                repository=repository,
                schema=SCHEMA,
                context_index=object(),
                semantic_index=object(),
                embedder=object(),
                contextual_reasoner=object(),
                actor="user-path-e2e",
                now=NOW,
                context_limit=5,
                request_id_factory=lambda: locator,
                write_preflight_guard=DependentReferenceGuard(
                    dependent_handoff.mention, dependent_handoff.evidence
                ),
            )
        elif text == "Hoy compré pan.":
            plan = _day_plan("2026-10-04", "Compré pan.", "2026-10-04")
        else:  # pragma: no cover - closed frozen route set
            raise AssertionError(text)
        result = _core_with_plan(repository, text, locator, plan)
        return result

    result = execute_routed_request(
        user_request=source,
        outer_request_id="erik-dependency-e2e",
        router=router,
        catalog=ApplicationCatalog.empty(),
        core_execute=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("split temporal routes must not bypass Temporal")
        ),
        application_executors={},
        temporal_execute=temporal,
    )

    assert calls == ["Ayer hablé con Eric.", "Mañana iré al cine con él.", "Hoy compré pan."]
    assert result.status is ApplicationStatus.COMPLETED
    dependent = result.execution_flow["routes"][1]
    assert dependent["status"] == "completed"
    assert "Hablé con Eric." in _visible_day(_calendar(repository, tmp_path), "2026-10-03")
    assert "Iré al cine con Eric." in _visible_day(_calendar(repository, tmp_path), "2026-10-05")
    stored = "\n".join(path.read_text(encoding="utf-8") for path in vault.rglob("*.md"))
    assert stored.count("[[Eric|Eric]]") == 2


def test_parallel_planned_facts_same_calendar_day_apply_in_order(tmp_path: Path) -> None:
    """Two concurrent planner decisions must never write the same canonical note concurrently."""
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    text = "Hoy he desayunado y hoy he paseado."
    spans = ("Hoy he desayunado", "y hoy he paseado.")
    router = FixedRouter(tuple(Route("temporal", span) for span in spans))
    planner_barrier = Barrier(2, timeout=3)
    planned: list[str] = []
    committed: list[str] = []

    def prepare(source: str, prior: Sequence[object]):
        """Emulate normal validated Core model planning, never persistence."""
        assert not prior
        planner_barrier.wait()
        planned.append(source)
        plan = _day_plan(
            "2026-10-04",
            "He desayunado." if "desayunado" in source else "He paseado.",
            "2026-10-04",
        )

        def serial_core(route: str, locator: str, actor: object, context: Sequence[object]):
            assert route == source and not context
            committed.append(source)
            return _core_with_plan(repository, route, locator, plan)

        return serial_core

    result = execute_routed_request(
        user_request=text,
        outer_request_id="same-day-parallel-plans",
        router=router,
        catalog=ApplicationCatalog.empty(),
        core_execute=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("all routes must use serial preplanned Core")
        ),
        application_executors={},
        route_preparers={"temporal": prepare},
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert sorted(planned) == sorted(spans)
    assert committed == list(spans)
    assert result.affected_stable_note_ids == ("date:2026-10-04",)
    lines = _visible_day(_calendar(repository, tmp_path), "2026-10-04")
    assert "He desayunado." in lines
    assert "He paseado." in lines


def test_exact_datetime_user_path_renders_canonical_clock_in_calendar(tmp_path: Path) -> None:
    """Show one exact clock consistently after routed Temporal/Core persistence."""
    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    source = "Mañana a las 15:35 viene el fontanero."
    router = FixedRouter((Route("temporal", source),))
    plan = _day_plan(
        "2026-10-05",
        "15:35 — Viene el fontanero.",
        "2026-10-05T15:35:00+02:00",
    )

    def temporal(text, locator, actor, conversation_context):
        del actor, conversation_context
        return _core_with_plan(repository, text, locator, plan)

    result = execute_routed_request(
        user_request=source,
        outer_request_id="temporal-user-clock",
        router=router,
        catalog=ApplicationCatalog.empty(),
        core_execute=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("dated request must not bypass Temporal")
        ),
        application_executors={},
        temporal_execute=temporal,
    )

    assert result.status is ApplicationStatus.COMPLETED
    assert result.affected_stable_note_ids == ("date:2026-10-05",)
    calendar = _calendar(repository, tmp_path)
    assert _visible_day(calendar, "2026-10-05") == [
        "Added 04-10-2026",
        "15:35 — Viene el fontanero.",
    ]
    markdown = repository.read_text("calendar/days/2026-10-05.md")
    assert "recorded_at=2026-10-04T17:35:00+02:00" in markdown
    assert "temporal=2026-10-05T15:35:00+02:00" in markdown


def test_split_october_dates_mixed_years_abort_before_any_day_write(tmp_path: Path) -> None:
    """Real Delta/Epsilon/Zeta/Eta failure must not save a sibling in the wrong year."""
    from odyssey_runtime.routing import PreparedExecution

    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    spans = (
        "El 19 de octubre hice la prueba gráfica Delta.",
        " El 20 de octubre hice la prueba gráfica Épsilon.",
        " El 21 de octubre hice la prueba gráfica Zeta.",
        " El 22 de octubre hice la prueba gráfica Eta.",
    )
    source = "".join(spans)
    normalized = ("2026-10-19", "2025-10-20", "2026-10-21", "2026-10-22")
    router = FixedRouter(tuple(Route("temporal", item) for item in spans))
    prepared_count = []
    committed = []

    def prepare(text, context):
        assert not context
        date = normalized[spans.index(text)]
        prepared_count.append(date)

        def write(route, locator, actor, prior):
            del actor, prior
            committed.append(date)
            return _core_with_plan(repository, route, locator, _day_plan(date, "Test.", date))

        return PreparedExecution(write, temporal_dates=(date,), temporal_resolved=True)

    result = execute_routed_request(
        user_request=source,
        outer_request_id="october-mixed-year-e2e",
        router=router,
        catalog=ApplicationCatalog.empty(),
        core_execute=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("no Core bypass")
        ),
        application_executors={},
        route_preparers={"temporal": prepare},
    )
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.planning_error == "TEMPORAL_COHORT_YEAR_CONFLICT"
    assert sorted(prepared_count) == sorted(normalized)
    assert committed == []
    assert list(vault.rglob("*.md")) == []
    assert result.execution_flow is not None
    assert len(result.execution_flow["routes"]) == 4
    assert all(route["status"] == "needs_attention" for route in result.execution_flow["routes"])
    assert all(
        route["steps"][-1]["name"] == "temporal.coherence"
        for route in result.execution_flow["routes"]
    )


def test_split_temporal_unknown_aborts_whole_batch_before_write(tmp_path: Path) -> None:
    """Alpha UNSPECIFIED must stop Beta/Gamma from leaving a partial calendar."""
    from odyssey_runtime.routing import PreparedExecution

    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    spans = (
        "El lunes 12 de octubre hice la prueba técnica Alfa.",
        " El martes 13 de octubre hice la prueba técnica Beta.",
        " El miércoles 14 de octubre hice la prueba técnica Gamma.",
    )
    normalized = (None, "2026-10-13", "2026-10-14")
    committed = []

    def prepare(text, context):
        del context
        date = normalized[spans.index(text)]

        def execute(route, locator, actor, prior):
            del actor, prior
            committed.append(route)
            assert date is not None
            return _core_with_plan(repository, route, locator, _day_plan(date, "Test.", date))

        return PreparedExecution(
            execute, temporal_dates=(date,) if date else (), temporal_resolved=date is not None
        )

    result = execute_routed_request(
        user_request="".join(spans),
        outer_request_id="october-unspecified-e2e",
        router=FixedRouter(tuple(Route("temporal", item) for item in spans)),
        catalog=ApplicationCatalog.empty(),
        core_execute=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no bypass")),
        application_executors={},
        route_preparers={"temporal": prepare},
    )
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.planning_error == "TEMPORAL_COHORT_UNRESOLVED"
    assert committed == []
    assert list(vault.rglob("*.md")) == []


def test_year_qualified_split_routes_can_commit_both_calendar_years(tmp_path: Path) -> None:
    """A deliberately stated year change is not confused with mixed model guesses."""
    from odyssey_runtime.routing import PreparedExecution

    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    spans = ("El 31 de diciembre de 2025 vi a Ana.", " El 1 de enero de 2026 vi a Luis.")
    dates = ("2025-12-31", "2026-01-01")

    def prepare(text, context):
        del context
        date = dates[spans.index(text)]

        def execute(route, locator, actor, prior):
            del actor, prior
            return _core_with_plan(repository, route, locator, _day_plan(date, "Test.", date))

        return PreparedExecution(execute, temporal_dates=(date,), temporal_resolved=True)

    result = execute_routed_request(
        user_request="".join(spans),
        outer_request_id="explicit-year-boundary-e2e",
        router=FixedRouter(tuple(Route("temporal", item) for item in spans)),
        catalog=ApplicationCatalog.empty(),
        core_execute=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no bypass")),
        application_executors={},
        route_preparers={"temporal": prepare},
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert result.affected_stable_note_ids == ("date:2025-12-31", "date:2026-01-01")
    assert (vault / "calendar/days/2025-12-31.md").exists()
    assert (vault / "calendar/days/2026-01-01.md").exists()


def test_failed_sibling_preparation_blocks_validated_temporal_write(tmp_path: Path) -> None:
    """Provider preparation failure must not allow a sibling Core write before detection."""
    from odyssey_runtime.routing import PreparedExecution

    vault = tmp_path / "vault"
    vault.mkdir()
    repository = VaultRepository(vault)
    spans = ("El 19 de octubre haré A.", " El 20 de octubre haré B.")
    executed = []

    def prepare(text, prior):
        assert not prior
        if text == spans[1]:
            raise RuntimeError("Synthetic Temporal preparation failed")
        date = "2026-10-19"

        def execute(route, locator, actor, context):
            del actor, context
            executed.append(route)
            return _core_with_plan(repository, route, locator, _day_plan(date, "Test.", date))

        return PreparedExecution(execute, temporal_dates=(date,), temporal_resolved=True)

    result = execute_routed_request(
        user_request="".join(spans),
        outer_request_id="temporal-prep-error-e2e",
        router=FixedRouter(tuple(Route("temporal", item) for item in spans)),
        catalog=ApplicationCatalog.empty(),
        core_execute=lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no bypass")),
        application_executors={},
        route_preparers={"temporal": prepare},
    )
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.planning_error == "TEMPORAL_COHORT_UNRESOLVED"
    assert executed == []
    assert list(vault.rglob("*.md")) == []
