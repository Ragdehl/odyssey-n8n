"""Real isolated HTTP read of an immutable, actor-bound C4 sidecar."""

from __future__ import annotations

import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread
from uuid import uuid4

from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_runtime.conversation_gateway import OpenAIConversationGateway
from odyssey_runtime.server import _handler_for
from tests.runtime.test_c4_deferred_runtime import _wait_status
from tests.runtime.test_c4_safe_prewrite_recovery import RETRY_ADVICE, _bad_route
from tests.runtime.test_conversation_gateway import FakeClient
from tests.runtime.test_issue157_family_day_recollection import SOURCE, _family
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient


def test_deferred_http_rejects_unauthenticated_and_other_actor(tmp_path):
    _repo, actor, source_executor, runtime = _family(tmp_path)
    source_executor.client = RecordedClient([_bad_route()])
    runtime.conversation_graph_gateway = OpenAIConversationGateway(
        FakeClient([RETRY_ADVICE, {"verdict": "SUPPORTED", "reason": "GROUNDED"}])
    )
    runtime.conversation_graph_semantic_review_enabled = True
    runtime.conversation_graph_deferred_enabled = True
    reqid = "c4-deferred-http"
    original = runtime.execute_product(SOURCE, reqid, "main", actor)
    assert original["status"] == "needs_attention"
    assert _wait_status(runtime, reqid, actor)["status"] == "completed"

    http = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(runtime))
    thread = Thread(target=http.serve_forever, daemon=True)
    thread.start()

    def post(data):
        conn = HTTPConnection(*http.server_address, timeout=3)
        conn.request(
            "POST",
            "/conversation/diagnosis",
            json.dumps(data).encode(),
            {"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        result = response.status, json.loads(response.read())
        conn.close()
        return result

    try:
        base = {"operation": "diagnosis", "request_id": reqid}
        assert post(base)[0] == 400
        correct = post({**base, "authenticated_actor": {"stable_user_id": actor.stable_user_id}})
        assert correct[0] == 200
        assert correct[1]["status"] == "completed"
        assert correct[1]["diagnosis"]["verified_stage_only"] is True
        assert "explanation" not in correct[1]["diagnosis"]
        other = AuthenticatedActorContext(str(uuid4()))
        forbidden = post({**base, "authenticated_actor": {"stable_user_id": other.stable_user_id}})
        assert forbidden == (200, {"version": 1, "request_id": reqid, "status": "unavailable"})
        assert (
            post(
                {
                    **base,
                    "authenticated_actor": {"stable_user_id": actor.stable_user_id},
                    "source": SOURCE,
                }
            )[0]
            == 400
        )
        assert (
            post(
                {
                    **base,
                    "authenticated_actor": {"stable_user_id": actor.stable_user_id},
                    "external_principal": {"issuer": "x", "subject": "y"},
                }
            )[0]
            == 400
        )
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=5)
