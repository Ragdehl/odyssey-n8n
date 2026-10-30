"""Disposable Pi-only C4 timing and resource probe; no GPT/network/private vault."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from odyssey_runtime.conversation_gateway import OpenAIConversationGateway
from tests.runtime.test_c4_safe_prewrite_recovery import RETRY_ADVICE, _bad_route
from tests.runtime.test_conversation_gateway import FakeClient
from tests.runtime.test_issue157_family_day_recollection import SOURCE, _family
from tests.runtime.test_whole_source_light_product_p4 import RecordedClient

N = 8


def resources():
    fields = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(("VmRSS:", "VmSwap:", "Threads:")):
            k, v = line.split(":", 1)
            fields[k] = v.strip()
    mem = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith(("MemAvailable:", "SwapFree:")):
            k, v = line.split(":", 1)
            mem[k] = v.strip()
    try:
        thermal = round(int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000, 2)
    except (FileNotFoundError, ValueError):
        thermal = None
    return {
        **fields,
        **mem,
        "temperature_c": thermal,
        "cpu_process_s": round(time.process_time(), 3),
    }


def percentile(samples, q):
    vals = sorted(samples)
    pos = (len(vals) - 1) * q
    lower = int(pos)
    upper = min(len(vals) - 1, lower + 1)
    return round(vals[lower] + (vals[upper] - vals[lower]) * (pos - lower), 1)


def batch(parent, mode):
    parent.mkdir(parents=True, exist_ok=True)
    repo, actor, executor, runtime = _family(parent)
    executor.client = RecordedClient([_bad_route()] * (N + 3))
    client = FakeClient(
        [
            response
            for _ in range(N + 3)
            for response in (RETRY_ADVICE, {"verdict": "SUPPORTED", "reason": "GROUNDED"})
        ]
    )
    original_create = client.responses.create

    def slow_provider(**kwargs):
        time.sleep(0.18)
        return original_create(**kwargs)

    client.responses.create = slow_provider
    runtime.conversation_graph_gateway = OpenAIConversationGateway(client)
    runtime.conversation_graph_semantic_review_enabled = True
    runtime.conversation_graph_deferred_enabled = mode == "deferred"
    before = {str(path): repo.read_text(path) for path in repo.list_markdown_paths()}
    times = []
    diagnosis_ms = []
    peak_threads = 0
    start_resources = resources()
    for i in range(N):
        rid = f"c4-perf-{mode}-{i}"
        t0 = time.perf_counter()
        output = runtime.execute_product(SOURCE, rid, "main", actor)
        times.append((time.perf_counter() - t0) * 1000)
        assert output["status"] == "needs_attention"
        if mode == "deferred":
            deadline = time.perf_counter() + 4
            while time.perf_counter() < deadline:
                result = runtime.deferred_diagnosis(rid, actor)
                peak_threads = max(peak_threads, int(resources()["Threads"]))
                if result["status"] != "pending":
                    break
                time.sleep(0.015)
            assert result["status"] == "completed", result
            diagnosis_ms.append(round((time.perf_counter() - t0) * 1000, 1))
    after = {str(path): repo.read_text(path) for path in repo.list_markdown_paths()}
    assert before == after
    return {
        "mode": mode,
        "samples": len(times),
        "response_p50_ms": percentile(times, 0.5),
        "response_p95_ms": percentile(times, 0.95),
        "diag_p50_ms": percentile(diagnosis_ms, 0.5) if diagnosis_ms else None,
        "diag_p95_ms": percentile(diagnosis_ms, 0.95) if diagnosis_ms else None,
        "provider_fake_delay_ms_each": 180,
        "calls_fake_provider": len(client.responses.calls),
        "peak_threads": peak_threads,
        "start": start_resources,
        "end": resources(),
        "synthetic_vault_unchanged": True,
    }


with tempfile.TemporaryDirectory(prefix="odyssey-c4-pi-perf-") as root:
    root = Path(root)
    print(
        json.dumps(
            {
                "environment": "Pi runtime, synthetic FakeClient, no API calls",
                "sync": batch(root / "sync", "sync"),
                "deferred": batch(root / "deferred", "deferred"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
