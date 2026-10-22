#!/usr/bin/env python3
"""Source-only live E5 Router probe, no writes or personal data."""

from __future__ import annotations

import json
import os

from openai import OpenAI

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle

CASES = (
    ("create", "Foto del colegio el 22 de noviembre de 2026.", "events"),
    ("update", "Cambia Foto del colegio al 24 de noviembre de 2026.", "events"),
    ("cancel", "Cancela Foto del colegio.", "events"),
    ("historical", "Ayer vi a Irene por la calle.", "not-events"),
    ("task", "Mañana tengo que llamar a Julia.", "not-events"),
)


def main():
    if os.environ.get("ODYSSEY_E5_LIVE_APPROVED") != "1":
        raise SystemExit("Live route probe disabled")
    router = OpenAIFactCandidateRouter(
        OpenAI(max_retries=0, timeout=55), prompt_revision="v6", event_routing=True
    )
    results = []
    only = os.environ.get("ODYSSEY_E5_CASE", "")
    for key, source, expected in CASES:
        if only and key != only:
            continue
        try:
            proposal = router.propose(source)
            routes = compile_hybrid_candidate_bundle(
                proposal, enable_tasks=True, enable_events=True
            )
            kinds = [x.kind for x in proposal.candidates]
            capabilities = [x.capability_id for x in routes.plan.routes]
            ok = (
                all(r == "events" for r in capabilities)
                if expected == "events"
                else all(r != "events" for r in capabilities)
            )
            results.append({"case": key, "kinds": kinds, "routes": capabilities, "pass": ok})
        except Exception as exc:
            results.append({"case": key, "pass": False, "error_class": type(exc).__name__})
        print("E5_ROUTER_REAL_CASE=" + json.dumps(results[-1]), flush=True)
    print(
        "E5_ROUTER_REAL_SUMMARY="
        + json.dumps({"passed": sum(r["pass"] for r in results), "total": len(results)}),
        flush=True,
    )
    return 0 if all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
