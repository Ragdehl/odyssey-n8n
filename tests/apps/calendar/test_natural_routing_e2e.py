"""Vertical provider-free E2E coverage for Router → minimal Calendar → ordinary Core planning."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from odyssey_apps import ApplicationDescriptor, ApplicationRegistry
from odyssey_apps.calendar import (
    CALENDAR_DESCRIPTOR,
    CalendarLiteralCaptureService,
    CalendarRouteExecutor,
    OpenAICalendarPlanner,
)
from odyssey_apps.router import OpenAIApplicationRouter
from odyssey_core.application import (
    ActionResult,
    ActionStatus,
    ApplicationResult,
    ApplicationStatus,
)
from odyssey_core.domain_interpretation import DomainInterpretation
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.notes import parse_note
from odyssey_core.request_planning import RequestPlan, WriteAction
from odyssey_core.storage import VaultRepository
from odyssey_runtime.routing import execute_routed_request

ROOT = Path(__file__).resolve().parents[3]
CURRENT = {"date": "2026-10-02", "time": "17:00", "timezone": "Europe/Paris"}


class FakeResponses:
    """Return deterministic Structured Output and retain every provider-boundary payload."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls = 0
        self.last_kwargs: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> object:
        self.calls += 1
        self.last_kwargs = kwargs
        return SimpleNamespace(
            id=f"fake-{self.calls}",
            status="completed",
            usage=SimpleNamespace(input_tokens=100, output_tokens=50),
            output_text=json.dumps(self.payload),
        )


def load_schema() -> dict[str, Any]:
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def calendar_catalog():  # type: ignore[no-untyped-def]
    registry = ApplicationRegistry.from_descriptors(
        (
            CALENDAR_DESCRIPTOR,
            ApplicationDescriptor(
                "tasks", "task lifecycle, due dates, completion and obligations", ("temporal",)
            ),
        )
    )
    return registry.catalog(enabled_ids=("calendar",))


def calendar_payload(
    *,
    intent: str | None,
    temporal_kind: str,
    exact_date: str | None,
    temporal_text: str | None = None,
    capture_text: str | None = None,
    outcome: str = "PLAN",
    range_start: str | None = None,
    range_end_exclusive: str | None = None,
    failure_code: str | None = None,
) -> dict[str, Any]:
    return {
        "outcome": outcome,
        "intent": intent,
        "temporal_kind": temporal_kind,
        "exact_date": exact_date,
        "range_start": range_start,
        "range_end_exclusive": range_end_exclusive,
        "temporal_text": temporal_text,
        "capture_text": capture_text,
        "failure_code": failure_code,
    }


def core_semantic_result() -> dict[str, Any]:
    """Represent Core choosing a valid person participant independently of Calendar."""

    def identity(name: str) -> dict[str, Any]:
        return {
            "description": name,
            "binding": "described",
            "direct_name": name,
            "note_type": "person",
            "filters": [],
            "candidate_scope": None,
        }

    return {
        "result": {
            "outcome": "PLAN",
            "actions": [
                {
                    "kind": "write",
                    "operations": [
                        {
                            "target": identity("Marta Test"),
                            "apply_to": "one",
                            "intent": "record",
                            "facts": [
                                {
                                    "parts": [
                                        {"kind": "literal", "text": "Empieza "},
                                        {
                                            "kind": "temporal_reference",
                                            "text": "mañana",
                                            "date": "2026-10-03",
                                        },
                                        {"kind": "literal", "text": " a vivir con "},
                                        {
                                            "kind": "identity",
                                            "text": "Daniel Test",
                                            "identity": identity("Daniel Test"),
                                        },
                                        {"kind": "literal", "text": "."},
                                    ]
                                }
                            ],
                            "properties": [],
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
    }


def core_semantic_end_result() -> dict[str, Any]:
    """Represent Core retaining a valid person participant when a relation ends."""

    def identity(name: str) -> dict[str, Any]:
        return {
            "description": name,
            "binding": "described",
            "direct_name": name,
            "note_type": "person",
            "filters": [],
            "candidate_scope": None,
        }

    return {
        "result": {
            "outcome": "PLAN",
            "actions": [
                {
                    "kind": "write",
                    "operations": [
                        {
                            "target": identity("Lucía Test"),
                            "apply_to": "one",
                            "intent": "record",
                            "facts": [
                                {
                                    "parts": [
                                        {"kind": "literal", "text": "Deja "},
                                        {
                                            "kind": "temporal_reference",
                                            "text": "mañana",
                                            "date": "2026-10-03",
                                        },
                                        {"kind": "literal", "text": " de vivir con "},
                                        {
                                            "kind": "identity",
                                            "text": "Daniel Test",
                                            "identity": identity("Daniel Test"),
                                        },
                                        {"kind": "literal", "text": "."},
                                    ]
                                }
                            ],
                            "properties": [],
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
    }


def core_semantic_company_literal_result() -> dict[str, Any]:
    """Keep a company literal because company/organization is absent from note-schema."""

    def person(name: str) -> dict[str, Any]:
        return {
            "description": name,
            "binding": "described",
            "direct_name": name,
            "note_type": "person",
            "filters": [],
            "candidate_scope": None,
        }

    return {
        "result": {
            "outcome": "PLAN",
            "actions": [
                {
                    "kind": "write",
                    "operations": [
                        {
                            "target": person("Marta Test"),
                            "apply_to": "one",
                            "intent": "record",
                            "facts": [
                                {
                                    "parts": [
                                        {"kind": "literal", "text": "Empieza "},
                                        {
                                            "kind": "temporal_reference",
                                            "text": "mañana",
                                            "date": "2026-10-03",
                                        },
                                        {
                                            "kind": "literal",
                                            "text": " a trabajar en Airbus Test.",
                                        },
                                    ]
                                }
                            ],
                            "properties": [],
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
    }


def test_router_calendar_day_occurrence_persists_exact_source_e2e(tmp_path: Path) -> None:
    source = "Mañana viene el fontanero"
    schema = load_schema()
    vault = tmp_path / "vault"
    vault.mkdir()
    catalog = calendar_catalog()
    router_transport = FakeResponses(
        {"outcome": "ROUTE", "routes": [{"capability_id": "calendar", "source_text": source}]}
    )
    calendar_transport = FakeResponses(
        calendar_payload(
            intent="DAY_LITERAL_CAPTURE",
            temporal_kind="EXACT_DATE",
            exact_date="2026-10-03",
            temporal_text="Mañana",
            capture_text=source,
        )
    )
    router = OpenAIApplicationRouter(SimpleNamespace(responses=router_transport), catalog)
    planner = OpenAICalendarPlanner(SimpleNamespace(responses=calendar_transport), CURRENT)
    captures = CalendarLiteralCaptureService(VaultRepository(vault), schema, None)

    def capture(
        date: str, literal: str, request_id: str, _actor: object | None
    ) -> ApplicationResult:
        result = captures.capture(
            date=date,
            literal=literal,
            request_id=request_id,
            actor={"human": "user-e2e", "app": "calendar"},
            now="2026-10-02T17:00:00+02:00",
        )
        return ApplicationResult(
            request_id,
            ApplicationStatus.COMPLETED,
            (ActionResult(0, "calendar", ActionStatus.COMPLETED),),
            (result.note_id,),
            history=result.history,
        )

    executor = CalendarRouteExecutor(
        planner,
        capture_day_literal=capture,
        execute_core=lambda *_args: pytest.fail(
            "Day-owned occurrence must not invoke Core planning"
        ),
    )
    result = execute_routed_request(
        user_request=source,
        outer_request_id="outer-day",
        router=router,
        catalog=catalog,
        core_execute=lambda *_args, **_kwargs: pytest.fail("Router Core route must not run"),
        application_executors={"calendar": executor},
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert result.affected_stable_note_ids == ("date:2026-10-03",)
    note = parse_note((vault / "calendar/days/2026-10-03.md").read_text(encoding="utf-8"))
    assert "03-10-2026 viene el fontanero" in note.content
    assert "Mañana viene el fontanero" not in note.content


@pytest.mark.parametrize(
    ("source", "exact_date", "temporal_text", "capture_text", "expected"),
    [
        (
            "Escribe en mi diario que he tenido un día muy tranquilo.",
            "2026-10-02",
            None,
            "he tenido un día muy tranquilo.",
            "he tenido un día muy tranquilo.",
        ),
        (
            "Escribe en mi diario que ayer tuve un buen día.",
            "2026-10-01",
            "ayer",
            "ayer tuve un buen día.",
            "01-10-2026 tuve un buen día.",
        ),
    ],
)
def test_router_calendar_diary_capture_writes_day_not_journal_entry_e2e(
    tmp_path: Path,
    source: str,
    exact_date: str,
    temporal_text: str | None,
    capture_text: str,
    expected: str,
) -> None:
    schema = load_schema()
    vault = tmp_path / "vault"
    vault.mkdir()
    catalog = calendar_catalog()
    router_transport = FakeResponses(
        {"outcome": "ROUTE", "routes": [{"capability_id": "calendar", "source_text": source}]}
    )
    calendar_transport = FakeResponses(
        calendar_payload(
            intent="DAY_LITERAL_CAPTURE",
            temporal_kind="EXACT_DATE",
            exact_date=exact_date,
            temporal_text=temporal_text,
            capture_text=capture_text,
        )
    )
    router = OpenAIApplicationRouter(SimpleNamespace(responses=router_transport), catalog)
    planner = OpenAICalendarPlanner(SimpleNamespace(responses=calendar_transport), CURRENT)
    repository = VaultRepository(vault)
    captures = CalendarLiteralCaptureService(repository, schema, None)

    def capture(
        date: str, literal: str, request_id: str, _actor: object | None
    ) -> ApplicationResult:
        result = captures.capture(
            date=date,
            literal=literal,
            request_id=request_id,
            actor={"human": "user-e2e", "app": "calendar"},
            now="2026-10-02T17:00:00+02:00",
        )
        return ApplicationResult(
            request_id,
            ApplicationStatus.COMPLETED,
            (ActionResult(0, "calendar", ActionStatus.COMPLETED),),
            (result.note_id,),
            history=result.history,
        )

    executor = CalendarRouteExecutor(
        planner,
        capture_day_literal=capture,
        execute_core=lambda *_args: pytest.fail("Diary capture must remain Day-owned"),
    )
    result = execute_routed_request(
        user_request=source,
        outer_request_id="outer-diary",
        router=router,
        catalog=catalog,
        core_execute=lambda *_args, **_kwargs: pytest.fail("Router Core route must not run"),
        application_executors={"calendar": executor},
    )

    assert result.status is ApplicationStatus.COMPLETED
    assert result.affected_stable_note_ids == (f"date:{exact_date}",)
    paths = repository.list_markdown_paths()
    assert f"calendar/days/{exact_date}.md" in paths
    assert all(path.startswith("calendar/days/") for path in paths)
    for path in paths:
        assert parse_note(repository.read_text(path)).metadata["type"] == "calendar_day"
    note = parse_note((vault / f"calendar/days/{exact_date}.md").read_text(encoding="utf-8"))
    assert note.metadata["type"] == "calendar_day"
    assert expected in note.content
    assert "Escribe en mi diario" not in note.content


def test_router_calendar_durable_statement_returns_to_ordinary_core_planner_e2e() -> None:
    """Calendar resolves only time; Core independently plans two schema-valid people."""
    source = "Marta Test empieza mañana a vivir con Daniel Test."
    schema = load_schema()
    catalog = calendar_catalog()
    router_transport = FakeResponses(
        {"outcome": "ROUTE", "routes": [{"capability_id": "calendar", "source_text": source}]}
    )
    calendar_transport = FakeResponses(
        calendar_payload(
            intent="DELEGATE_TO_CORE",
            temporal_kind="EXACT_DATE",
            exact_date="2026-10-03",
            temporal_text="mañana",
        )
    )
    core_transport = FakeResponses(core_semantic_result())
    router = OpenAIApplicationRouter(SimpleNamespace(responses=router_transport), catalog)
    calendar = OpenAICalendarPlanner(SimpleNamespace(responses=calendar_transport), CURRENT)
    seen: list[DomainInterpretation] = []

    def execute_core(
        routed_source: str,
        request_id: str,
        _actor: object | None,
        context: object,
        interpretation: DomainInterpretation,
    ) -> ApplicationResult:
        assert routed_source == source
        assert not context
        seen.append(interpretation)
        planner = OpenAILunaExperimentalPlanner(
            SimpleNamespace(responses=core_transport),
            schema,
            CURRENT,
            teaching_examples=None,
            domain_interpretation=interpretation,
        )
        plan = planner.plan(routed_source)
        assert isinstance(plan, RequestPlan)
        action = plan.actions[0]
        assert isinstance(action, WriteAction)
        unit = action.units[0]
        # These semantic choices came from Core's output, not Calendar's schema.
        assert unit.target.entity == "Marta Test"
        assert unit.references[0].mention == "Daniel Test"
        assert unit.references[0].target_index == 1
        assert unit.references[0].selection is None
        assert action.units[1].target.entity == "Daniel Test"
        assert action.units[1].reference_lookup_only is True
        assert "[[calendar/days/2026-10-03|03-10-2026]]" in unit.facts[0]
        return ApplicationResult(
            request_id,
            ApplicationStatus.COMPLETED,
            (ActionResult(0, "write", ActionStatus.COMPLETED),),
            (),
        )

    executor = CalendarRouteExecutor(
        calendar,
        capture_day_literal=lambda *_args: pytest.fail("durable knowledge is not Day-owned"),
        execute_core=execute_core,
    )
    result = execute_routed_request(
        user_request=source,
        outer_request_id="outer-durable",
        router=router,
        catalog=catalog,
        core_execute=lambda *_args, **_kwargs: pytest.fail(
            "route remains Calendar-owned until handoff"
        ),
        application_executors={"calendar": executor},
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert len(seen) == 1
    calendar_schema = calendar_transport.last_kwargs["text"]["format"]["schema"]  # type: ignore[index]
    serialized = json.dumps(calendar_schema)
    assert (
        "Marta" not in serialized
        and "candidate_scope" not in serialized
        and "facts" not in serialized
    )
    core_schema = core_transport.last_kwargs["text"]["format"]["schema"]  # type: ignore[index]
    assert "semantic_temporal_reference_part" in core_schema["$defs"]


def test_router_calendar_ending_relation_keeps_participant_identity_e2e() -> None:
    """Keep participant decomposition in Core when temporal evidence qualifies an ending relation."""
    source = "Lucía Test deja mañana de vivir con Daniel Test."
    schema = load_schema()
    catalog = calendar_catalog()
    router_transport = FakeResponses(
        {"outcome": "ROUTE", "routes": [{"capability_id": "calendar", "source_text": source}]}
    )
    calendar_transport = FakeResponses(
        calendar_payload(
            intent="DELEGATE_TO_CORE",
            temporal_kind="EXACT_DATE",
            exact_date="2026-10-03",
            temporal_text="mañana",
        )
    )
    core_transport = FakeResponses(core_semantic_end_result())
    router = OpenAIApplicationRouter(SimpleNamespace(responses=router_transport), catalog)
    calendar = OpenAICalendarPlanner(SimpleNamespace(responses=calendar_transport), CURRENT)

    def execute_core(
        routed_source: str,
        request_id: str,
        _actor: object | None,
        _context: object,
        interpretation: DomainInterpretation,
    ) -> ApplicationResult:
        planner = OpenAILunaExperimentalPlanner(
            SimpleNamespace(responses=core_transport),
            schema,
            CURRENT,
            teaching_examples=None,
            domain_interpretation=interpretation,
        )
        plan = planner.plan(routed_source)
        assert isinstance(plan, RequestPlan)
        action = plan.actions[0]
        assert isinstance(action, WriteAction)
        assert action.units[0].target.entity == "Lucía Test"
        assert action.units[0].references[0].mention == "Daniel Test"
        assert action.units[1].target.entity == "Daniel Test"
        assert "[[calendar/days/2026-10-03|03-10-2026]]" in action.units[0].facts[0]
        return ApplicationResult(
            request_id,
            ApplicationStatus.COMPLETED,
            (ActionResult(0, "write", ActionStatus.COMPLETED),),
            (),
        )

    executor = CalendarRouteExecutor(
        calendar,
        capture_day_literal=lambda *_args: pytest.fail("ending durable knowledge is not Day-owned"),
        execute_core=execute_core,
    )
    result = execute_routed_request(
        user_request=source,
        outer_request_id="outer-durable-end",
        router=router,
        catalog=catalog,
        core_execute=lambda *_args, **_kwargs: pytest.fail("route stays app-owned until handoff"),
        application_executors={"calendar": executor},
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert router_transport.calls == 1
    assert calendar_transport.calls == 1
    assert core_transport.calls == 1


def test_router_calendar_non_schema_company_stays_literal_e2e() -> None:
    """Do not promote a company to an Odyssey identity when note-schema has no company type."""
    source = "Marta Test empieza mañana a trabajar en Airbus Test."
    schema = load_schema()
    assert "company" not in {item["id"] for item in schema["types"]}
    assert "organization" not in {item["id"] for item in schema["types"]}
    catalog = calendar_catalog()
    router_transport = FakeResponses(
        {"outcome": "ROUTE", "routes": [{"capability_id": "calendar", "source_text": source}]}
    )
    calendar_transport = FakeResponses(
        calendar_payload(
            intent="DELEGATE_TO_CORE",
            temporal_kind="EXACT_DATE",
            exact_date="2026-10-03",
            temporal_text="mañana",
        )
    )
    core_transport = FakeResponses(core_semantic_company_literal_result())
    router = OpenAIApplicationRouter(SimpleNamespace(responses=router_transport), catalog)
    calendar = OpenAICalendarPlanner(SimpleNamespace(responses=calendar_transport), CURRENT)

    def execute_core(
        routed_source: str,
        request_id: str,
        _actor: object | None,
        _context: object,
        interpretation: DomainInterpretation,
    ) -> ApplicationResult:
        planner = OpenAILunaExperimentalPlanner(
            SimpleNamespace(responses=core_transport),
            schema,
            CURRENT,
            teaching_examples=None,
            domain_interpretation=interpretation,
        )
        plan = planner.plan(routed_source)
        assert isinstance(plan, RequestPlan)
        action = plan.actions[0]
        assert isinstance(action, WriteAction)
        assert len(action.units) == 1
        unit = action.units[0]
        assert unit.target.entity == "Marta Test"
        assert unit.references == ()
        assert "Airbus Test" in unit.facts[0]
        assert "[[calendar/days/2026-10-03|03-10-2026]]" in unit.facts[0]
        return ApplicationResult(
            request_id,
            ApplicationStatus.COMPLETED,
            (ActionResult(0, "write", ActionStatus.COMPLETED),),
            (),
        )

    executor = CalendarRouteExecutor(
        calendar,
        capture_day_literal=lambda *_args: pytest.fail("durable knowledge is not Day-owned"),
        execute_core=execute_core,
    )
    result = execute_routed_request(
        user_request=source,
        outer_request_id="outer-company-literal",
        router=router,
        catalog=catalog,
        core_execute=lambda *_args, **_kwargs: pytest.fail("route stays app-owned until handoff"),
        application_executors={"calendar": executor},
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert router_transport.calls == calendar_transport.calls == core_transport.calls == 1


def test_router_calendar_unresolved_time_stays_non_executable_e2e() -> None:
    source = "A finales de mes viene el fontanero"
    catalog = calendar_catalog()
    router_transport = FakeResponses(
        {"outcome": "ROUTE", "routes": [{"capability_id": "calendar", "source_text": source}]}
    )
    calendar_transport = FakeResponses(
        calendar_payload(
            outcome="FAIL_CLOSED",
            intent="DAY_LITERAL_CAPTURE",
            temporal_kind="UNSPECIFIED",
            exact_date=None,
            temporal_text="finales de mes",
            failure_code="TEMPORAL_UNRESOLVED",
        )
    )
    router = OpenAIApplicationRouter(SimpleNamespace(responses=router_transport), catalog)
    calendar = OpenAICalendarPlanner(SimpleNamespace(responses=calendar_transport), CURRENT)
    executor = CalendarRouteExecutor(
        calendar,
        capture_day_literal=lambda *_args: pytest.fail("unresolved time must not capture"),
        execute_core=lambda *_args: pytest.fail("unresolved time must not reach Core"),
    )
    result = execute_routed_request(
        user_request=source,
        outer_request_id="outer-unresolved",
        router=router,
        catalog=catalog,
        core_execute=lambda *_args, **_kwargs: pytest.fail("Core route must not run"),
        application_executors={"calendar": executor},
    )
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.clarification_code == "TEMPORAL_UNRESOLVED"


def test_router_needs_disabled_tasks_capability_never_invokes_calendar() -> None:
    catalog = calendar_catalog()
    transport = FakeResponses({"outcome": "NEEDS_CAPABILITY", "routes": []})
    router = OpenAIApplicationRouter(SimpleNamespace(responses=transport), catalog)
    result = execute_routed_request(
        user_request="Tengo que llamar al banco el viernes",
        outer_request_id="outer-task",
        router=router,
        catalog=catalog,
        core_execute=lambda *_args, **_kwargs: pytest.fail("Core must not run"),
        application_executors={
            "calendar": lambda *_args, **_kwargs: pytest.fail("Calendar must not run")
        },
    )
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.planning_error == "ROUTER_NEEDS_CAPABILITY"


def test_calendar_provider_cannot_smuggle_old_core_write_shape_e2e() -> None:
    """A stale/malicious old mini-Core payload fails before capture or Core handoff."""
    source = "Escribe en mi diario que hoy fui al trabajo"
    catalog = calendar_catalog()
    router_transport = FakeResponses(
        {"outcome": "ROUTE", "routes": [{"capability_id": "calendar", "source_text": source}]}
    )
    old_payload = calendar_payload(
        intent="DELEGATE_TO_CORE",
        temporal_kind="EXACT_DATE",
        exact_date="2026-10-02",
        temporal_text="hoy",
    )
    old_payload["semantic_write"] = {"operations": []}
    calendar_transport = FakeResponses(old_payload)
    router = OpenAIApplicationRouter(SimpleNamespace(responses=router_transport), catalog)
    calendar = OpenAICalendarPlanner(SimpleNamespace(responses=calendar_transport), CURRENT)
    executor = CalendarRouteExecutor(
        calendar,
        capture_day_literal=lambda *_args: pytest.fail("invalid payload must not capture"),
        execute_core=lambda *_args: pytest.fail("invalid payload must not reach Core"),
    )
    result = execute_routed_request(
        user_request=source,
        outer_request_id="outer-smuggle",
        router=router,
        catalog=catalog,
        core_execute=lambda *_args, **_kwargs: pytest.fail("Core must not run"),
        application_executors={"calendar": executor},
    )
    assert result.status is ApplicationStatus.FAILED
    assert result.planning_error == "CALENDAR_PLANNER_INVALID"
