"""Short Pi three-request concurrency probe with a synthetic provider."""

import json
import tempfile
import time
from pathlib import Path
from threading import Lock, get_ident
from types import SimpleNamespace

from odyssey_runtime.conversation_gateway import OpenAIConversationGateway
from tests.runtime.test_c4_safe_prewrite_recovery import RETRY_ADVICE, _bad_route
from tests.runtime.test_conversation_gateway import FakeClient
from tests.runtime.test_issue157_family_day_recollection import SOURCE, _family
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient

with tempfile.TemporaryDirectory(prefix="odyssey-c4-concurrent-") as root:
    repo, actor, executor, runtime = _family(Path(root))
    executor.client = RecordedClient([_bad_route()] * 4)
    client = FakeClient(
        [
            answer
            for _ in range(4)
            for answer in (RETRY_ADVICE, {"verdict": "SUPPORTED", "reason": "GROUNDED"})
        ]
    )
    lock = Lock()
    inflight = 0
    peak = 0
    calls_per_thread = {}

    def slow(**kwargs):
        global inflight, peak
        with lock:
            tid = get_ident()
            calls_per_thread[tid] = calls_per_thread.get(tid, 0) + 1
            sequence = calls_per_thread[tid]
            client.responses.calls.append(kwargs)
            inflight += 1
            peak = max(peak, inflight)
        time.sleep(0.18)
        try:
            answer = (
                RETRY_ADVICE if sequence == 1 else {"verdict": "SUPPORTED", "reason": "GROUNDED"}
            )
            return SimpleNamespace(status="completed", output_text=json.dumps(answer))
        finally:
            with lock:
                inflight -= 1

    client.responses.create = slow
    runtime.conversation_graph_gateway = OpenAIConversationGateway(client)
    runtime.conversation_graph_semantic_review_enabled = True
    runtime.conversation_graph_deferred_enabled = True
    before = {str(p): repo.read_text(p) for p in repo.list_markdown_paths()}
    ids = [f"c4-concurrent-{i}" for i in range(3)]
    spans = []
    for rid in ids:
        started = time.perf_counter()
        response = runtime.execute_product(SOURCE, rid, "main", actor)
        spans.append(round((time.perf_counter() - started) * 1000, 2))
        assert response["status"] == "needs_attention"
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        states = [runtime.deferred_diagnosis(rid, actor)["status"] for rid in ids]
        if states.count("pending") == 0:
            break
        time.sleep(0.018)
    assert before == {str(p): repo.read_text(p) for p in repo.list_markdown_paths()}
    assert peak <= 2
    print(
        json.dumps(
            {
                "mode": "synthetic Pi concurrency",
                "requests": 3,
                "provider_call_delay_ms": 180,
                "initial_response_ms": spans,
                "peak_concurrent_provider_calls": peak,
                "sidecar_states": states,
                "fake_provider_calls": len(client.responses.calls),
                "no_knowledge_changes": True,
            },
            indent=2,
        )
    )
