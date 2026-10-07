from __future__ import annotations

from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_runtime.composition import RuntimeComposition
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
        "request_id": "web-1",
        "stage": "planner.ready",
        "progress": 68,
        "details": ["Cloe", "Bruno", "Beatriz"],
        "sequence": 2,
        "complete": False,
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
    assert response["progress"] == 42
    assert response["details"] == [
        "mañana: 2026-10-08",
        "20h: 2026-10-08T20:00:00+02:00",
    ]


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
    assert payload["request_id"] == "web-http"
    assert payload["stage"] == "routing.started"
    assert payload["progress"] == 8
