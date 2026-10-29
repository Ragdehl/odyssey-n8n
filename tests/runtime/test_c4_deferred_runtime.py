"""Real source/Router/E3 receipt and delayed C4 on a disposable actor."""

from __future__ import annotations

from threading import Event
from time import monotonic, sleep

from odyssey_runtime.conversation_gateway import OpenAIConversationGateway
from tests.runtime.test_c4_safe_prewrite_recovery import RETRY_ADVICE, _bad_route
from tests.runtime.test_conversation_gateway import FakeClient
from tests.runtime.test_issue157_family_day_recollection import SOURCE, _family
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient


def _wait_status(runtime, request_id, actor, terminal="completed"):
    deadline = monotonic() + 4
    while monotonic() < deadline:
        status = runtime.deferred_diagnosis(request_id, actor)
        if status["status"] == terminal:
            return status
        sleep(0.02)
    raise AssertionError("deferred diagnosis did not reach " + terminal)


def test_c4_deferred_does_not_hold_e3_lock_or_replay_provider(tmp_path):
    repo, actor, source_executor, runtime = _family(tmp_path)
    source_executor.client = RecordedClient([_bad_route()])
    client = FakeClient([RETRY_ADVICE, {"verdict": "SUPPORTED", "reason": "GROUNDED"}])
    entered, release = Event(), Event()
    raw_create = client.responses.create

    def slow_provider(**kwargs):
        entered.set()
        assert release.wait(timeout=4)
        return raw_create(**kwargs)

    client.responses.create = slow_provider
    runtime.conversation_graph_gateway = OpenAIConversationGateway(client)
    runtime.conversation_graph_semantic_review_enabled = True
    runtime.conversation_graph_deferred_enabled = True
    before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
    request_id = "deferred-c4-no-writes"
    initial = runtime.execute_product(SOURCE, request_id, "main", actor)
    assert initial["status"] == "needs_attention"
    assert "error_diagnosis" not in initial
    assert entered.wait(timeout=2)
    assert runtime.deferred_diagnosis(request_id, actor)["status"] == "pending"
    # The provider is still blocked; the global writer lock must be free.
    assert runtime._execute_lock.acquire(blocking=False)
    runtime._execute_lock.release()
    replay = runtime.execute_product(SOURCE, request_id, "main", actor)
    assert replay["delivery_replayed"] is True
    assert len(source_executor.client.calls) == 1
    release.set()
    ready = _wait_status(runtime, request_id, actor)
    assert ready["diagnosis"]["verified_stage_only"] is True
    assert ready["diagnosis"]["stage_view"]["label"] == "Interpretación del mensaje"
    assert "explanation" not in ready["diagnosis"]
    assert {path: repo.read_text(path) for path in repo.list_markdown_paths()} == before
    assert runtime.deferred_diagnosis(request_id, actor) == ready
    assert len(client.responses.calls) == 2


def test_c4_deferred_model_refusal_keeps_original_reply_and_claim(tmp_path):
    repo, actor, source_executor, runtime = _family(tmp_path)
    source_executor.client = RecordedClient([_bad_route()])
    client = FakeClient([RETRY_ADVICE, {"verdict": "UNSUPPORTED", "reason": "OTHER"}])
    runtime.conversation_graph_gateway = OpenAIConversationGateway(client)
    runtime.conversation_graph_semantic_review_enabled = True
    runtime.conversation_graph_deferred_enabled = True
    request_id = "deferred-c4-denied"
    initial = runtime.execute_product(SOURCE, request_id, "main", actor)
    assert initial["status"] == "needs_attention"
    assert (
        _wait_status(runtime, request_id, actor, terminal="unavailable")["status"] == "unavailable"
    )
    assert len(client.responses.calls) == 2
    assert runtime.execute_product(SOURCE, request_id, "main", actor)["delivery_replayed"] is True
    assert len(client.responses.calls) == 2
