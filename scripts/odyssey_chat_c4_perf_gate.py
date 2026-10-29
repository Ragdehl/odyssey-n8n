#!/usr/bin/env python3
"""Synthetic, bounded Raspberry Pi C4 latency/resource probe (no billable provider).

Invoke with ``python -m scripts.odyssey_chat_c4_perf_gate`` from repo root.
It exercises the actual actor-scoped guarded runtime/durable replay, but stubs
Core failures and applies an artificial provider delay. Never claim live E2E.
"""

from __future__ import annotations

import json
import statistics
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from math import ceil
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_core.observability import OperationalEvidence, OperationalOutcome, OperationalStage
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime.conversation_gateway import (
    ContextScope,
    ConversationDecision,
    ConversationMode,
    ErrorAdvice,
    GuidanceKind,
    OpenAIConversationGateway,
    RecoveryHint,
)


def snapshot() -> dict:
    data = {"monotonic": time.monotonic(), "cpu_seconds": time.process_time()}
    try:
        fields = dict(
            (row.partition(":")[0], row.partition(":")[2].strip().split()[0])
            for row in Path("/proc/self/status").read_text().splitlines()
            if row.startswith(("VmRSS:", "VmSwap:"))
        )
        data["process_rss_kib"] = int(fields.get("VmRSS", 0))
        data["process_swap_kib"] = int(fields.get("VmSwap", 0))
        mem = dict(
            (row.partition(":")[0], row.partition(":")[2].strip().split()[0])
            for row in Path("/proc/meminfo").read_text().splitlines()
            if row.startswith(("MemAvailable:", "SwapFree:"))
        )
        data["mem_available_kib"] = int(mem.get("MemAvailable", 0))
        data["swap_free_kib"] = int(mem.get("SwapFree", 0))
    except (OSError, ValueError):
        pass
    try:
        data["temperature_c"] = (
            int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
        )
    except (OSError, ValueError):
        data["temperature_c"] = None
    try:
        speeds = [
            int(p.read_text().strip()) for p in Path("/sys/class/hwmon").glob("hwmon*/fan*_input")
        ]
        data["fan_rpm"] = speeds or None
    except (OSError, ValueError):
        data["fan_rpm"] = None
    return data


class DelayedFakeGateway(OpenAIConversationGateway):
    """Fixed schema-compatible output: delay simulates only provider round trip."""

    def __init__(self, delay: float) -> None:
        self.delay = delay
        self.calls = 0
        self.lock = threading.Lock()

    def classify(self, original_message, state):
        # This probe explicitly exercises the Router/CORE failure path; C3
        # classification is stable and synthetic, not billable.
        return ConversationDecision(ConversationMode.ROUTER, ContextScope.NONE)

    def explain_error(self, receipt):
        with self.lock:
            self.calls += 1
        time.sleep(self.delay)
        return ErrorAdvice(GuidanceKind.RETRY_LATER, RecoveryHint.REVIEW_RETRY)


class GraphDelayedFakeGateway(OpenAIConversationGateway):
    """Run C4's ACTUAL strict schema and validator over a delayed fake provider."""

    def __init__(self, delay: float) -> None:
        self.calls = 0
        self.delay = delay
        self.lock = threading.Lock()
        self.client = SimpleNamespace(responses=self)
        self.model = "DELAYED_FAKE_NOT_REAL_PROVIDER"
        self.reasoning_effort = "synthetic"

    def create(self, **kwargs):
        name = kwargs["text"]["format"]["name"]
        assert name in {
            "odyssey_execution_graph_diagnosis",
            "odyssey_execution_diagnosis_semantic_review",
        }
        assert kwargs["store"] is False
        with self.lock:
            self.calls += 1
        time.sleep(self.delay)
        if name == "odyssey_execution_diagnosis_semantic_review":
            return SimpleNamespace(
                status="completed",
                output_text=json.dumps({"verdict": "SUPPORTED", "reason": "GROUNDED"}),
            )
        return SimpleNamespace(
            status="completed",
            output_text=json.dumps(
                {
                    "evidence_stage": "application.source_processing",
                    "route_index": None,
                    "explanation": "La etapa observada falló en la revisión de la ruta original.",
                    "next_step": "CHECK_SYSTEM",
                    "user_question": "",
                }
            ),
        )


def main() -> None:
    if sys.argv[1:] not in ([], ["--model-advisory"], ["--graph-diagnosis"], ["--semantic-review"]):
        raise SystemExit(
            "Usage: python -m scripts.odyssey_chat_c4_perf_gate [--model-advisory|--graph-diagnosis|--semantic-review]"
        )
    advisory = sys.argv[1:] == ["--model-advisory"]
    semantic_review = sys.argv[1:] == ["--semantic-review"]
    graph_mode = semantic_review or sys.argv[1:] == ["--graph-diagnosis"]
    delay = 0.18
    gateway = GraphDelayedFakeGateway(delay) if graph_mode else DelayedFakeGateway(delay)
    samples = []
    measurements = []
    stop = threading.Event()

    def sampler():
        while not stop.wait(0.08):
            samples.append(snapshot())

    start = snapshot()
    monitor = threading.Thread(target=sampler, daemon=True)
    monitor.start()
    with tempfile.TemporaryDirectory(prefix="odyssey-c4-perf-", dir="/tmp") as d:
        calls = []
        lock = threading.Lock()

        def hybrid(source, rid, actor, cid):
            with lock:
                calls.append(rid)
            if graph_mode:
                return ApplicationResult(
                    rid,
                    ApplicationStatus.NEEDS_ATTENTION,
                    (),
                    (),
                    clarification_code="FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED",
                    operational=OperationalEvidence(
                        2,
                        (
                            OperationalStage(
                                "application.source_processing",
                                OperationalOutcome.FAILED,
                                2,
                                error_category="FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED",
                            ),
                        ),
                    ),
                )
            return ApplicationResult(
                request_id=rid,
                status=ApplicationStatus.FAILED,
                action_results=(),
                affected_stable_note_ids=(),
                planning_error="OPERATIONAL_FAILURE",
            )

        runtime = RuntimeComposition(
            core_execute=lambda *_args, **_kw: (_ for _ in ()).throw(AssertionError("wrong path")),
            hybrid_candidate_execute=hybrid,
            full_source_mutation_guard=True,
            refresh_indexes=lambda: None,
            conversation_root_resolver=ConversationRootResolver(Path(d) / "state"),
            conversation_gateway=None if graph_mode else gateway,
            conversation_graph_gateway=gateway if graph_mode else None,
            conversation_graph_semantic_review_enabled=semantic_review,
            conversation_error_guidance_enabled=True,
            conversation_error_model_advisory_enabled=advisory,
        )

        def invoke(name):
            actor = AuthenticatedActorContext(str(uuid4()))
            rid = "c4-" + str(uuid4())
            before = time.monotonic()
            response = runtime.execute_product(name, rid, "main", actor)
            elapsed = (time.monotonic() - before) * 1000
            if graph_mode:
                assert (
                    response["error_diagnosis"]["evidence_stage"] == "application.source_processing"
                )
                assert response["error_diagnosis"]["next_step"] == "CHECK_SYSTEM"
                assert response["error_diagnosis"]["write_evidence"] == "UNKNOWN"
            else:
                assert response["error_guidance"]["write_evidence"] == "UNKNOWN"
                assert response["error_guidance"]["guidance_kind"] == "RETRY_LATER"
            again = runtime.execute_product(name, rid, "main", actor)
            assert again["delivery_replayed"] is True
            return {"id": rid, "latency_ms": round(elapsed, 1), "replay_verified": True}

        measurements.append({"scope": "cold", **invoke("synthetic-cold")})
        for index in range(3):
            measurements.append({"scope": "warm-serial", **invoke(f"synthetic-serial-{index}")})
        with ThreadPoolExecutor(max_workers=3) as pool:
            futs = [pool.submit(invoke, f"synthetic-parallel-{i}") for i in range(3)]
            measurements += [{"scope": "3-overlapping", **f.result()} for f in futs]
        assert len(calls) == len(measurements) == 7
        assert gateway.calls == (14 if semantic_review else 7 if advisory or graph_mode else 0)
    stop.set()
    monitor.join(1)
    last = snapshot()
    timings = [e["latency_ms"] for e in measurements]
    summary = {
        "kind": "C4_SYNTHETIC_PI_PROBE",
        "pass": True,
        "calls": len(measurements),
        "model": "DELAYED_FAKE_NOT_REAL_PROVIDER",
        "model_advisory_enabled": advisory,
        "graph_diagnosis_enabled": graph_mode,
        "semantic_review_enabled": semantic_review,
        "C4_advisory_calls": gateway.calls,
        "synthetic_provider_delay_ms": int(delay * 1000),
        "worker_concurrency": 3,
        "replay_core_extra_calls": 0,
        "p50_ms": round(statistics.median(timings), 1),
        "p95_nearest_rank_ms": sorted(timings)[ceil(len(timings) * 0.95) - 1],
        "cold_ms": measurements[0]["latency_ms"],
        "warm_serial_ms": [
            row["latency_ms"] for row in measurements if row["scope"] == "warm-serial"
        ],
        "parallel_ms": [
            row["latency_ms"] for row in measurements if row["scope"] == "3-overlapping"
        ],
        "before": start,
        "peak_observed": {
            "rss_kib": max((x.get("process_rss_kib", 0) for x in samples), default=0),
            "temperature_c": max(
                (x.get("temperature_c", 0) for x in samples if x.get("temperature_c") is not None),
                default=None,
            ),
            "swap_kib": max((x.get("process_swap_kib", 0) for x in samples), default=0),
            "min_mem_available_kib": min(
                (x.get("mem_available_kib", 0) for x in samples), default=0
            ),
        },
        "after": last,
        "notes_written": 0,
        "real_app": False,
        "real_provider": False,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
