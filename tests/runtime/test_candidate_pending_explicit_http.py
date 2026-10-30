"""HTTP product-path continuation: exact pending locator, no implicit stale selection."""

from __future__ import annotations

import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread

from odyssey_core.candidate_pending_state import CandidatePendingRepository
from odyssey_runtime.routing import route_execution_id
from odyssey_runtime.server import _handler_for
from tests.runtime.test_hybrid_product_pending_v2 import ACTOR, OTHER_ACTOR, _runtime


def test_explicit_reply_uses_authenticated_http_boundary_after_other_turn(tmp_path):
    runtime, resolver, vault, calls, source, first_id = _runtime(tmp_path, routed=True)
    route_id = route_execution_id(first_id, 0)
    original_notes = {p: vault.read_text(p) for p in vault.list_markdown_paths()}
    http = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(runtime))
    thread = Thread(target=http.serve_forever, daemon=True)
    thread.start()

    def post(body):
        conn = HTTPConnection(*http.server_address, timeout=4)
        conn.request(
            "POST",
            "/execute",
            json.dumps(body).encode(),
            {
                "Content-Type": "application/json",
            },
        )
        response = conn.getresponse()
        payload = response.status, json.loads(response.read())
        conn.close()
        return payload

    def actor_body(actor):
        return {
            "authenticated_actor": {"stable_user_id": actor.stable_user_id},
            "conversation_id": "main",
        }

    try:
        status, first = post(
            {
                "request": source,
                "request_id": first_id,
                **actor_body(ACTOR),
            }
        )
        assert status == 200
        assert first["clarification"]["request_id"] == route_id
        runtime._conversation_store(ACTOR.stable_user_id).append_turn(
            request_id="not-original-assistant",
            role="assistant",
            text="Un turno posterior diferente.",
            created_at="2026-10-04T10:00:00+02:00",
        )
        payload = {
            "request": "Con Luis",
            "request_id": "http-explicit-luis",
            "reply_to_request_id": route_id,
        }
        foreign_code, foreign = post({**payload, **actor_body(OTHER_ACTOR)})
        assert foreign_code == 200
        assert foreign["product_control"] == "CANDIDATE_UNAVAILABLE"
        for malformed in ("../unsafe", "two words", "", 2, [], True):
            assert (
                post(
                    {
                        **payload,
                        "reply_to_request_id": malformed,
                        **actor_body(ACTOR),
                    }
                )[0]
                == 400
            )
        assert (
            post(
                {
                    **payload,
                    "conversation_id": None,
                    "authenticated_actor": actor_body(ACTOR)["authenticated_actor"],
                }
            )[0]
            == 400
        )
        assert (
            post({"request": "Con Luis", "reply_to_request_id": route_id, **actor_body(ACTOR)})[0]
            == 400
        )
        status, selected = post({**payload, **actor_body(ACTOR)})
        assert status == 200
        assert selected["product_control"] == "CANDIDATE_SELECTION_RECORDED"
        assert selected["product_reason"] == "CONTINUATION_REVIEW_REQUIRED"
        assert post({**payload, **actor_body(ACTOR)})[1]["delivery_replayed"] is True
        repository = CandidatePendingRepository(resolver.resolve(ACTOR.stable_user_id) / "pending")
        assert repository.read(route_id)["selected_note_id"] == "luis-id"
        assert {p: vault.read_text(p) for p in vault.list_markdown_paths()} == original_notes
        assert calls == [(source, first_id)]
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=5)
