"""Provider-free user-path regressions for Router -> Temporal -> Core -> Calendar."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace

from odyssey_apps import ApplicationCatalog, Route, RouteOutcome, RoutePlan
from odyssey_apps.calendar import CalendarQueryService
from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.context import ContextIndex
from odyssey_core.note_queries import NotesQueryService
from odyssey_core.request_planning import KnowledgeUnit, RequestPlan, SelectionCriteria, WriteAction
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
        return _core_with_plan(repository, text, locator, plan)

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
    )

    assert result.status is ApplicationStatus.COMPLETED
    assert result.affected_stable_note_ids == ("date:2026-10-03", "date:2026-10-04")
    calendar = _calendar(repository, tmp_path)
    assert "Vi a Ana." in _visible_day(calendar, "2026-10-03")
    assert "Vi a Luis." in _visible_day(calendar, "2026-10-04")


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
