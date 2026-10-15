from __future__ import annotations

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_runtime.composition import ConversationRootResolver, RuntimeComposition
from odyssey_runtime.progress import ProductProgressStore


def runtime_with_progress(store: ProductProgressStore) -> RuntimeComposition:
    return RuntimeComposition(
        core_execute=lambda *_args, **_kwargs: None,  # not exercised here
        refresh_indexes=lambda: None,
        product_progress_store=store,
    )


def test_progress_store_is_latest_only_monotonic_and_actor_scoped() -> None:
    store = ProductProgressStore(max_records=2)
    first = store.begin("actor-a", "web-1")
    assert first.progress == 0

    store.update("actor-a", "web-1", "planner.started", 50)
    snapshot = store.update("actor-a", "web-1", "routing.ready", 18, ("2",))

    assert snapshot.progress == 50
    assert snapshot.stage == "routing.ready"
    assert snapshot.details == ("2",)
    assert snapshot.sequence == 3
    assert store.read("actor-b", "web-1") is None


def test_runtime_progress_projects_only_bounded_user_safe_details() -> None:
    store = ProductProgressStore()
    runtime = runtime_with_progress(store)
    actor_id = "123e4567-e89b-42d3-a456-426614174000"
    actor = AuthenticatedActorContext(actor_id)
    store.begin(actor_id, "web-1")

    runtime._record_progress_event(
        actor_id,
        "web-1",
        "planner.ready",
        {"references": ("Cloe", "Bruno", "Beatriz")},
    )
    response = runtime.product_progress("web-1", actor)

    assert response == {
        "version": 1,
        "request_id": "web-1",
        "stage": "planner.ready",
        "progress": 68,
        "details": ["Cloe", "Bruno", "Beatriz"],
        "sequence": 2,
        "complete": False,
        "stage_view": {
            "version": 1,
            "label": "He identificado las referencias importantes.",
            "icon": "planner",
        },
    }


def test_runtime_progress_reports_temporal_values_without_internal_reasoning() -> None:
    store = ProductProgressStore()
    runtime = runtime_with_progress(store)
    store.begin("odyssey-runtime", "web-time")

    runtime._record_progress_event(
        "odyssey-runtime",
        "web-time",
        "temporal.ready",
        {"values": ("mañana: 2026-10-08", "20h: 2026-10-08T20:00:00+02:00")},
    )

    response = runtime.product_progress("web-time")
    assert response["stage"] == "temporal.ready"
    assert response["version"] == 1
    assert response["progress"] == 42
    assert response["details"] == [
        "mañana: 2026-10-08",
        "20h: 2026-10-08T20:00:00+02:00",
    ]


def test_hybrid_product_path_publishes_dispatcher_lifecycle_to_product_progress(tmp_path) -> None:
    """The authenticated hybrid composition path feeds the same pollable progress channel."""
    store = ProductProgressStore()
    actor_id = "123e4567-e89b-42d3-a456-426614174000"

    def hybrid(_source, request_id, _actor, _conversation):
        from odyssey_runtime import composition

        composition._emit_progress("routing.started")
        composition._emit_progress("routing.ready", {"route_count": 2})
        composition._emit_progress("temporal.started")
        composition._emit_progress("temporal.ready", {"values": ("tomorrow: 2026-10-14",)})
        composition._emit_progress("planner.started")
        composition._emit_progress("planner.ready")
        return ApplicationResult(request_id, ApplicationStatus.NEEDS_ATTENTION, (), ())

    runtime = RuntimeComposition(
        core_execute=lambda *_args, **_kwargs: None,
        refresh_indexes=lambda: None,
        product_progress_store=store,
        hybrid_candidate_execute=hybrid,
        conversation_root_resolver=ConversationRootResolver(tmp_path / "state"),
    )
    runtime.execute_product(
        "Synthetic hybrid route.",
        "progress-hybrid",
        "main",
        AuthenticatedActorContext(actor_id),
    )
    response = runtime.product_progress("progress-hybrid", AuthenticatedActorContext(actor_id))
    assert response["stage"] == "finalizing"
    assert response["progress"] == 94
    assert response["details"] == []


def test_progress_http_projection_is_readable_while_product_request_is_in_flight() -> None:
    import json
    import threading
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer

    from odyssey_runtime.server import _handler_for

    store = ProductProgressStore()
    runtime = runtime_with_progress(store)
    store.begin("odyssey-runtime", "web-http")
    store.update("odyssey-runtime", "web-http", "routing.started", 8)

    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(runtime))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
        connection.request(
            "POST",
            "/conversation/progress",
            body=json.dumps({"operation": "progress", "request_id": "web-http"}),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
    finally:
        server.shutdown()
        server.server_close()

    assert response.status == 200
    assert payload["version"] == 1
    assert payload["stage_view"] == {
        "version": 1,
        "label": "Entendiendo tu mensaje…",
        "icon": "router",
    }
    assert payload["request_id"] == "web-http"
    assert payload["stage"] == "routing.started"
    assert payload["progress"] == 8


def test_future_app_progress_is_observed_with_no_invented_percent_and_has_typed_view() -> None:
    store = ProductProgressStore()
    runtime = runtime_with_progress(store)
    store.begin("123e4567-e89b-42d3-a456-426614174000", "future-app")
    runtime._record_progress_event(
        "123e4567-e89b-42d3-a456-426614174000", "future-app", "planner.started", {}
    )
    first = store.read("123e4567-e89b-42d3-a456-426614174000", "future-app")
    assert first.progress == 50

    runtime._record_progress_event(
        "123e4567-e89b-42d3-a456-426614174000",
        "future-app",
        "events.classify_occurrence.started",
        {},
    )
    in_flight = store.read("123e4567-e89b-42d3-a456-426614174000", "future-app")
    assert in_flight.progress == 50
    assert in_flight.stage == "events.classify_occurrence.started"
    assert in_flight.stage_view.to_response() == {
        "version": 1,
        "label": "events · classify occurrence · en curso",
        "icon": "result",
    }
    assert in_flight.sequence == first.sequence + 1

    runtime._record_progress_event(
        "123e4567-e89b-42d3-a456-426614174000", "future-app", "events.classify_occurrence.ready", {}
    )
    ready = runtime.product_progress(
        "future-app", AuthenticatedActorContext("123e4567-e89b-42d3-a456-426614174000")
    )
    assert ready["progress"] == 50
    assert ready["stage_view"]["label"] == "events · classify occurrence · preparado"
    assert ready["sequence"] == in_flight.sequence + 1

    runtime._record_progress_event(
        "123e4567-e89b-42d3-a456-426614174000",
        "future-app",
        "events.classify_occurrence.execute user text",
        {},
    )
    assert (
        store.read("123e4567-e89b-42d3-a456-426614174000", "future-app").sequence
        == in_flight.sequence + 1
    )
    assert store.read("actor-b", "future-app") is None


def test_concurrent_stage_reporting_has_monotone_sequence_and_never_drops_a_valid_update() -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    store = ProductProgressStore()
    runtime = runtime_with_progress(store)
    store.begin("actor-a", "parallel")
    barrier = Barrier(2)

    def observe(stage):
        barrier.wait(timeout=3)
        runtime._record_progress_event("actor-a", "parallel", stage, {})

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(observe, name) for name in ("temporal.started", "core.notes.started")
        ]
        for future in futures:
            future.result(timeout=3)
    last = store.read("actor-a", "parallel")
    assert last.sequence == 3
    assert 0 <= last.progress <= 28
    assert last.stage in {"temporal.started", "core.notes.started"}
    assert last.stage_view is not None


def test_http_progress_exposes_shared_stage_view_for_future_app_without_leaking_source() -> None:
    from odyssey_core.stage_presentation import progress_stage_view

    assert progress_stage_view("events.classify_occurrence.started") is not None
    assert progress_stage_view("some private person's name.started") is None
    assert progress_stage_view("x" * 100 + ".started") is None


def test_progress_http_round_trip_of_new_app_keeps_actor_scope_and_versioned_view() -> None:
    import json
    import threading
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer

    from odyssey_runtime.server import _handler_for

    store = ProductProgressStore()
    runtime = runtime_with_progress(store)
    store.begin("odyssey-runtime", "web-future-http")
    store.update("odyssey-runtime", "web-future-http", "temporal.ready", 42)
    runtime._record_progress_event(
        "odyssey-runtime", "web-future-http", "events.classify_occurrence.started", {}
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(runtime))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
        client.request(
            "POST",
            "/conversation/progress",
            body=json.dumps({"operation": "progress", "request_id": "web-future-http"}),
            headers={"Content-Type": "application/json"},
        )
        response = client.getresponse()
        payload = json.loads(response.read())
        client.close()
    finally:
        server.shutdown()
        server.server_close()
    assert response.status == 200
    assert payload["version"] == 1
    assert payload["progress"] == 42
    assert payload["stage"] == "events.classify_occurrence.started"
    assert payload["stage_view"] == {
        "version": 1,
        "label": "events · classify occurrence · en curso",
        "icon": "result",
    }
    assert payload["sequence"] == 3
    assert payload["complete"] is False
