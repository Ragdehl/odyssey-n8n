"""Vertical provider-free E2E coverage for routed Calendar natural language."""

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
from odyssey_core.notes import parse_note
from odyssey_core.storage import VaultRepository
from odyssey_runtime.routing import execute_routed_request

ROOT = Path(__file__).resolve().parents[3]


class FakeResponses:
    """Return one deterministic Structured Output envelope and count provider-boundary calls."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls = 0

    def create(self, **_kwargs: Any) -> object:
        """Return the configured synthetic provider response without network access."""
        self.calls += 1
        return SimpleNamespace(status="completed", output_text=json.dumps(self.payload))


def load_schema() -> dict[str, Any]:
    """Load the canonical production schema for the isolated E2E vault."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def calendar_catalog():  # type: ignore[no-untyped-def]
    """Expose Calendar as executable while Router still sees one disabled sibling capability."""
    registry = ApplicationRegistry.from_descriptors(
        (
            CALENDAR_DESCRIPTOR,
            ApplicationDescriptor(
                "tasks", "task lifecycle, due dates, completion and obligations", ("temporal",)
            ),
        )
    )
    return registry.catalog(enabled_ids=("calendar",))


def test_router_to_calendar_to_runtime_to_core_persistence_e2e(tmp_path: Path) -> None:
    """Persist one routed natural-language occurrence through every local production boundary."""
    source = "Mañana viene el fontanero"
    schema = load_schema()
    vault = tmp_path / "vault"
    vault.mkdir()
    catalog = calendar_catalog()

    router_transport = FakeResponses(
        {
            "outcome": "ROUTE",
            "routes": [{"capability_id": "calendar", "source_text": source}],
        }
    )
    calendar_transport = FakeResponses(
        {
            "outcome": "PLAN",
            "intent": "DAY_LITERAL_CAPTURE",
            "temporal_kind": "EXACT_DATE",
            "exact_date": "2026-10-03",
            "range_start": None,
            "range_end_exclusive": None,
            "semantic_write": None,
            "failure_code": None,
        }
    )

    router = OpenAIApplicationRouter(SimpleNamespace(responses=router_transport), catalog)
    planner = OpenAICalendarPlanner(
        SimpleNamespace(responses=calendar_transport),
        schema,
        {"date": "2026-10-02", "time": "17:00", "timezone": "Europe/Paris"},
    )
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
        schema=schema,
        capture_day_literal=capture,
        execute_core_write=lambda *_args: pytest.fail(
            "literal Day capture must not use Core planner"
        ),
    )

    result = execute_routed_request(
        user_request=source,
        outer_request_id="outer-e2e",
        router=router,
        catalog=catalog,
        core_execute=lambda *_args, **_kwargs: pytest.fail(
            "Calendar route must bypass Core planner"
        ),
        application_executors={"calendar": executor},
    )

    assert result.status is ApplicationStatus.COMPLETED
    assert result.affected_stable_note_ids == ("date:2026-10-03",)
    assert router_transport.calls == 1 and calendar_transport.calls == 1
    note_path = vault / "calendar/days/2026-10-03.md"
    note = parse_note(note_path.read_text(encoding="utf-8"))
    assert source in note.content
    assert note.metadata["id"] == "date:2026-10-03"


def test_router_needs_capability_never_invokes_calendar_or_mutates_vault(tmp_path: Path) -> None:
    """Keep sibling-app knowledge in Router and stop before Calendar on unsupported ownership."""
    schema = load_schema()
    vault = tmp_path / "vault-out-of-scope"
    vault.mkdir()
    catalog = calendar_catalog()
    router_transport = FakeResponses({"outcome": "NEEDS_CAPABILITY", "routes": []})
    router = OpenAIApplicationRouter(SimpleNamespace(responses=router_transport), catalog)

    class NeverResponses:
        def create(self, **_kwargs: Any) -> object:
            pytest.fail("Calendar planner must not see a request owned by another capability")

    planner = OpenAICalendarPlanner(
        SimpleNamespace(responses=NeverResponses()),
        schema,
        {"date": "2026-10-02", "time": "17:00", "timezone": "Europe/Paris"},
    )
    executor = CalendarRouteExecutor(
        planner,
        schema=schema,
        capture_day_literal=lambda *_args: pytest.fail("Calendar capture must not run"),
        execute_core_write=lambda *_args: pytest.fail("Calendar Core write must not run"),
    )
    result = execute_routed_request(
        user_request="Tengo que llamar al banco el viernes",
        outer_request_id="outer-needs-capability",
        router=router,
        catalog=catalog,
        core_execute=lambda *_args, **_kwargs: pytest.fail("Core planner must not run"),
        application_executors={"calendar": executor},
    )
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.planning_error == "ROUTER_NEEDS_CAPABILITY"
    assert router_transport.calls == 1
    assert not (vault / "calendar").exists()


def test_misrouted_foreign_surface_cannot_reach_core_or_persistence_e2e(tmp_path: Path) -> None:
    """Reject foreign write authority even when a synthetic provider bypasses Calendar's schema."""
    source = "Escribe en mi diario que hoy fui al trabajo"
    schema = load_schema()
    vault = tmp_path / "vault-foreign-surface"
    vault.mkdir()
    catalog = calendar_catalog()
    router_transport = FakeResponses(
        {"outcome": "ROUTE", "routes": [{"capability_id": "calendar", "source_text": source}]}
    )
    calendar_transport = FakeResponses(
        {
            "outcome": "PLAN",
            "intent": "CORE_SEMANTIC_WRITE",
            "temporal_kind": "EXACT_DATE",
            "exact_date": "2026-10-02",
            "range_start": None,
            "range_end_exclusive": None,
            "semantic_write": {
                "kind": "write",
                "operations": [
                    {
                        "target": {
                            "description": "mi diario",
                            "binding": "described",
                            "direct_name": None,
                            "note_type": "journal_entry",
                            "filters": [],
                            "candidate_scope": None,
                        },
                        "apply_to": "one",
                        "intent": "record",
                        "facts": [
                            {
                                "parts": [
                                    {
                                        "kind": "temporal_reference",
                                        "text": "hoy",
                                        "date": "2026-10-02",
                                    },
                                    {"kind": "literal", "text": " Fui al trabajo"},
                                ]
                            }
                        ],
                        "properties": [],
                        "tag_changes": [],
                        "destination_type": "journal_entry",
                    }
                ],
            },
            "failure_code": None,
        }
    )
    router = OpenAIApplicationRouter(SimpleNamespace(responses=router_transport), catalog)
    planner = OpenAICalendarPlanner(
        SimpleNamespace(responses=calendar_transport),
        schema,
        {"date": "2026-10-02", "time": "17:00", "timezone": "Europe/Paris"},
    )
    executor = CalendarRouteExecutor(
        planner,
        schema=schema,
        capture_day_literal=lambda *_args: pytest.fail("foreign surface must not capture a Day"),
        execute_core_write=lambda *_args: pytest.fail("foreign surface must not reach Core write"),
    )
    result = execute_routed_request(
        user_request=source,
        outer_request_id="outer-foreign-surface",
        router=router,
        catalog=catalog,
        core_execute=lambda *_args, **_kwargs: pytest.fail(
            "misrouted Calendar source must not use Core planner"
        ),
        application_executors={"calendar": executor},
    )
    assert result.status is ApplicationStatus.FAILED
    assert result.planning_error == "CALENDAR_PLANNER_INVALID"
    assert router_transport.calls == 1 and calendar_transport.calls == 1
    assert not (vault / "calendar").exists()
