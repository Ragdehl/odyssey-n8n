"""P4 DEV front door must delegate only Events-only intent to E5.

Frozen provider responses exercise the actual product route selection, outer
delivery replay and immutable Core/E3 ownership. Existing P4 Core/Tasks stay frozen.
"""

from __future__ import annotations

from odyssey_core.application import ApplicationResult, ApplicationStatus
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient, _fixture


def route(*capabilities):
    return {
        "capabilities": list(capabilities),
        "interpretation": "joint",
        "reason": "single",
        "app_scopes": [],
        "self_relation_span": None,
    }


def test_p4_events_only_executes_one_authenticated_e5_delegate_and_replays(tmp_path):
    _repo, actor, service, runtime = _fixture(tmp_path)
    calls = []

    def event_delegate(source, locator, identity):
        calls.append((source, locator, identity))
        return ApplicationResult(
            locator,
            ApplicationStatus.COMPLETED,
            (),
            (),
            execution_flow={"events": {"operation": "query", "match_count": 0}},
        )

    service.event_delegate = event_delegate
    service.client = RecordedClient([route("events")])
    source = "Foto de clase el 22 de noviembre de 2026."
    result = runtime.execute_product(source, "e5-p4-frozen-a", "main", actor)
    assert result["status"] == "completed", result
    assert len(calls) == 1 and calls[0][0] == source and calls[0][2] == actor
    assert service.client.calls == ["odyssey_light_capability_route_events_v1"]
    assert result["execution_flow"]["routes"][0]["capability"] == "events"
    replay = runtime.execute_product(source, "e5-p4-frozen-a", "main", actor)
    assert replay["delivery_replayed"] is True and len(calls) == 1


def test_p4_events_with_lower_level_temporal_dependency_remains_one_app_route(tmp_path):
    _repo, actor, service, runtime = _fixture(tmp_path)
    received = []

    def delegate(source, locator, identity):
        received.append((source, identity))
        return ApplicationResult(locator, ApplicationStatus.COMPLETED, (), ())

    service.event_delegate = delegate
    service.client = RecordedClient([route("events", "temporal")])
    result = runtime.execute_product(
        "Cambia el concierto al jueves.", "e5-event-with-temporal", "main", actor
    )
    assert result["status"] == "completed"
    assert len(received) == 1 and received[0][1] == actor


def test_p4_events_with_temporal_and_one_valid_event_scope(tmp_path):
    _repo, actor, service, runtime = _fixture(tmp_path)
    calls = []

    def delegate(source, locator, identity):
        calls.append((source, locator, identity))
        return ApplicationResult(locator, ApplicationStatus.COMPLETED, (), ())

    service.event_delegate = delegate
    proposed = route("events", "temporal")
    proposed["app_scopes"] = [
        {
            "capability": "events",
            "description": "one reschedule",
            "depends_on_another_scope": False,
        }
    ]
    service.client = RecordedClient([proposed])
    result = runtime.execute_product(
        "Cambia el concierto al jueves.", "e5-event-with-scope", "main", actor
    )
    assert result["status"] == "completed"
    assert len(calls) == 1 and calls[0][2] == actor


def test_p4_mixed_events_and_tasks_abstains_before_any_e3_write(tmp_path):
    _repo, actor, service, runtime = _fixture(tmp_path)
    calls = []
    service.event_delegate = lambda *_: calls.append(True)
    service.client = RecordedClient([route("events", "tasks")])
    result = runtime.execute_product(
        "Excursión mañana y preparar mochila.", "e5-mixed", "main", actor
    )
    assert result["status"] == "needs_attention"
    assert not calls


def test_p4_without_events_flag_keeps_legacy_router_contract(tmp_path):
    _repo, actor, service, runtime = _fixture(tmp_path)
    service.client = RecordedClient([route("events")])
    result = runtime.execute_product("Concierto mañana.", "e5-disabled", "main", actor)
    assert result["status"] == "needs_attention"
    assert service.client.calls == ["odyssey_light_capability_route_v1"]
