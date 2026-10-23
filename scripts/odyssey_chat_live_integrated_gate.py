#!/usr/bin/env python3
"""Bounded real-Luna gate for integrated C1/C2/C3 with disposable actors.

One fresh non-production synthetic run. This does NOT use deployed n8n,
the real UI, or an actual Core/E3 writer. No personal vault is accessible.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import time
from pathlib import Path
from statistics import median
from uuid import uuid4

from odyssey_core.application import ApplicationResult, ApplicationStatus
from odyssey_core.identity_boundary import AuthenticatedActorContext
from odyssey_core.local_conversations import ConversationRootResolver
from odyssey_runtime.composition import RuntimeComposition
from odyssey_runtime.conversation_gateway import OpenAIConversationGateway

CASES = (
    ("social-es", "¡Hola! ¿Qué tal?", "CHAT", "completed"),
    ("help-es", "¿Cómo puedo crear subtareas en Odyssey?", "CHAT", "completed"),
    ("explicit-save", "Guarda que ayer conocí a Noa.", "ROUTER", "completed"),
    (
        "mixed-save-help",
        "He conocido a Leo. Guárdalo y dime cómo veo mis notas.",
        "ROUTER",
        "completed",
    ),
    ("recent-history", "¿De qué hablamos antes sobre el jardín?", "CHAT", "completed"),
    ("events-disabled", "¿Se pueden crear eventos en Odyssey?", "CHAT", "needs_attention"),
)
MAX_PROVIDER_CALLS = 20
MAX_BUDGETED_OUTPUT_TOKENS = 10000


def metrics() -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    try:
        fields = {}
        for row in Path("/proc/self/status").read_text().splitlines():
            if row.startswith(("VmRSS:", "VmSwap:")):
                name, size, _ = row.split()
                fields[name[:-1]] = int(size)
        result["rss_kib"] = fields.get("VmRSS")
        result["swap_kib"] = fields.get("VmSwap")
    except (OSError, ValueError):
        result["rss_kib"] = result["swap_kib"] = None
    try:
        result["thermal_c"] = round(
            int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000, 1
        )
    except (OSError, ValueError):
        result["thermal_c"] = None
    return result


def main() -> int:
    if os.environ.get("ODYSSEY_CHAT_LIVE_APPROVED") != "1":
        print("C3_INTEGRATED_LIVE_REFUSED: bounded billable approval missing")
        return 2
    if not os.environ.get("OPENAI_API_KEY"):
        print("C3_INTEGRATED_LIVE_REFUSED: protected provider unavailable")
        return 2
    if len(CASES) != 6 or MAX_PROVIDER_CALLS > 20:
        print("C3_INTEGRATED_LIVE_REFUSED: unbounded matrix")
        return 2

    gateway = OpenAIConversationGateway.from_environment()
    real_complete = gateway._complete
    counters = {"calls": 0, "output_tokens_cap": 0}

    def counted_complete(**kwargs):
        budget = kwargs.get("max_tokens")
        if type(budget) is not int or budget > 750 or budget <= 0:
            raise RuntimeError("Provider output budget exceeded")
        if counters["calls"] >= MAX_PROVIDER_CALLS or (
            counters["output_tokens_cap"] + budget > MAX_BUDGETED_OUTPUT_TOKENS
        ):
            raise RuntimeError("Aggregate C3 provider budget exceeded")
        counters["calls"] += 1
        counters["output_tokens_cap"] += budget
        return real_complete(**kwargs)

    gateway._complete = counted_complete
    results = []
    print(
        "C3_INTEGRATED_LIVE_START",
        json.dumps(
            {
                "model": gateway.model,
                "effort": gateway.reasoning_effort,
                "max_calls": MAX_PROVIDER_CALLS,
                "aggregate_max_output_tokens": MAX_BUDGETED_OUTPUT_TOKENS,
                "synthetic_only": True,
                "real_n8n": False,
                "real_browser": False,
            }
        ),
        flush=True,
    )
    started = time.monotonic()
    before = metrics()
    with tempfile.TemporaryDirectory(prefix="odyssey-c3-real-luna-", dir="/tmp") as root:
        core_calls = []

        def fake_core(source, request_id, *_args, **_kwargs):
            core_calls.append({"request_id": request_id, "message": source})
            return ApplicationResult(request_id, ApplicationStatus.COMPLETED, (), ())

        runtime = RuntimeComposition(
            core_execute=fake_core,
            refresh_indexes=lambda: None,
            conversation_root_resolver=ConversationRootResolver(Path(root) / "synthetic-state"),
            conversation_gateway=gateway,
            # Intentionally no Events executor: calendar viewing is available.
            conversation_deployed_capabilities=frozenset(
                {"tasks", "notes", "calendar", "clarifications"}
            ),
        )
        for index, (name, source, expected_route, expected_status) in enumerate(CASES):
            actor = AuthenticatedActorContext(str(uuid4()))
            if name == "recent-history":
                runtime.append_conversation_turn(
                    "main",
                    "garden-prior",
                    "user",
                    "Hablamos de plantar lavanda en el jardín.",
                    authenticated_actor=actor,
                )
            first = time.monotonic()
            cpu_start = time.process_time()
            call_start = counters["calls"]
            try:
                response = runtime.execute_product(source, "c3-live-" + str(index), "main", actor)
                actual_route = "CHAT" if "conversation_reply" in response else "ROUTER"
                actual_status = response["status"]
                if actual_route == "CHAT":
                    reply = {"request_id": response["request_id"], **response["conversation_reply"]}
                    runtime.persist_product_assistant_response(reply, actor)
                else:
                    reply = None
                result = {
                    "case": name,
                    "expected_route": expected_route,
                    "actual_route": actual_route,
                    "expected_status": expected_status,
                    "actual_status": actual_status,
                    "provider_calls": counters["calls"] - call_start,
                    "passed": actual_route == expected_route and actual_status == expected_status,
                    "turns": len(runtime.main_conversation(actor)["turns"]),
                    "reply_kind": reply["kind"] if reply else None,
                }
                if reply is not None:
                    result["reply_excerpt"] = reply["message"][:180]
                if name == "events-disabled" and reply is not None:
                    result["passed"] = result["passed"] and (
                        reply["kind"] == "cannot_answer" and "eventos" in reply["message"].lower()
                    )
            except Exception as exc:
                result = {
                    "case": name,
                    "passed": False,
                    "error_category": type(exc).__name__,
                    "provider_calls": counters["calls"] - call_start,
                }
            result["elapsed_ms"] = round((time.monotonic() - first) * 1000)
            result["cpu_ms"] = round((time.process_time() - cpu_start) * 1000)
            result["resource"] = metrics()
            results.append(result)
            print("C3_CASE", json.dumps(result, ensure_ascii=False), flush=True)
        # Synthetic Core returns no canonical note writes by construction.
        expected_core = [source for name, source, route, _ in CASES if route == "ROUTER"]
        core_verified = [x["message"] for x in core_calls] == expected_core
        markdown_count = len(tuple(Path(root).rglob("*.md")))

    ms = sorted(row["elapsed_ms"] for row in results)
    duration = round(time.monotonic() - started, 2)
    summary = {
        "passed": sum(row["passed"] for row in results),
        "total": len(results),
        "model_calls": counters["calls"],
        "output_tokens_upper_bound": counters["output_tokens_cap"],
        "route_p50_ms": round(median(ms)),
        "route_p95_nearest_rank_ms": ms[max(0, math.ceil(0.95 * len(ms)) - 1)],
        "elapsed_seconds": duration,
        "core_stub_sources_exact": core_verified,
        "markdown_files": markdown_count,
        "resource_before": before,
        "resource_after": metrics(),
        "real_provider": True,
        "real_n8n": False,
        "real_browser": False,
        "real_core_writer": False,
        "app_e2e_verified": False,
    }
    print("C3_INTEGRATED_LIVE_RESULT", json.dumps(summary, ensure_ascii=False), flush=True)
    return (
        0 if summary["passed"] == summary["total"] and core_verified and markdown_count == 0 else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
