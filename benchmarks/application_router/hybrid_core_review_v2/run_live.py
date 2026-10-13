"""Real independent Core reviewer over fully authentic frozen Router/Temporal/Planner.

This tests a changed Core graph/readback contract without repaying for
unmodified front-end provider results. Disposable synthetic vault only.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from openai import OpenAI

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault

HERE = Path(__file__).parent
INPUTS = HERE.parent / "hybrid_router_v5_end_to_end_v3"
PREVIOUS_USD = 0.62315817
NEW_LIMIT_USD = 0.02
TOTAL_LIMIT_USD = 1.0
RATES = {"gpt-6-luna": (0.10, 0.50), "gpt-5.6-luna": (0.20, 1.20)}
MULTIPLIER = 1.10


class HybridResponses:
    def __init__(self, actual, frozen, cost_ledger):
        self.actual = actual
        self.frozen = frozen
        self.calls = 0
        self.new_records = []
        self.cost_ledger = cost_ledger

    def create(self, **request):
        model = request.get("model")
        if self.calls < len(self.frozen):
            record = self.frozen[self.calls]
            if record["model"] != model or record["status"] != "completed":
                raise RuntimeError("Frozen provider model/provenance mismatch")
            self.calls += 1
            return SimpleNamespace(
                status=record["status"], output_text=record["output_text"], usage=None, id=None
            )
        if (
            model != "gpt-5.6-luna"
            or self.calls != len(self.frozen)
            or cost(self.cost_ledger) >= NEW_LIMIT_USD
            or PREVIOUS_USD + cost(self.cost_ledger) >= TOTAL_LIMIT_USD
        ):
            raise RuntimeError("Unapproved additional reviewer call")
        self.calls += 1
        response = self.actual.create(**request)
        usage = response.usage
        record = {
            "model": model,
            "status": response.status,
            "output_text": response.output_text,
            "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        }
        self.new_records.append(record)
        self.cost_ledger.append(record)
        if (
            cost(self.cost_ledger) > NEW_LIMIT_USD
            or PREVIOUS_USD + cost(self.cost_ledger) > TOTAL_LIMIT_USD
        ):
            raise RuntimeError("Reviewer post-call budget exceeded")
        return response


def cost(rows):
    return MULTIPLIER * sum(
        (x["input_tokens"] * RATES[x["model"]][0] + x["output_tokens"] * RATES[x["model"]][1])
        / 1_000_000
        for x in rows
    )


def main(case_ids):
    if os.getenv("ODYSSEY_APPROVE_HYBRID_EXPERIMENT") != "1" or not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Explicit authorization and API credential required")
    choices = {x["id"]: x["source"] for x in CASES}
    if not case_ids or len(case_ids) > 2 or len(set(case_ids)) != len(case_ids):
        raise SystemExit("Run one or two unique case IDs")
    if any(c != "F26" for c in case_ids):
        raise SystemExit("Only previously frozen compatible sources permitted")
    if any((HERE / f"{c}.json").exists() for c in case_ids):
        raise SystemExit("Immutable results already exist")
    sdk = OpenAI(max_retries=0, timeout=80.0)
    costs = []
    summary = []
    for case in case_ids:
        source = choices[case]
        source_receipt = json.loads((INPUTS / f"{case}.json").read_text())
        frozen = source_receipt["real_model_outputs"][:6]
        if hashlib.sha256(source.encode()).hexdigest() != source_receipt["source_sha256"]:
            raise SystemExit("Stale source replay")
        client = HybridResponses(sdk.responses, frozen, costs)
        bridge = SimpleNamespace(responses=client)
        status = "exception"
        error = None
        routes = []
        changed = {}
        with tempfile.TemporaryDirectory(prefix="odyssey-reviewed-") as tmp:
            repo, ctx, sem, emb = fresh_corpus_vault(Path(tmp))
            before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
            try:
                result = execute_candidate_routed_message(
                    source,
                    router=OpenAIFactCandidateRouter(bridge, prompt_revision="v5"),
                    temporal=OpenAITemporalInterpreter(
                        bridge, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
                    ),
                    core_planner_factory=lambda c, domain, bound=bridge: (
                        OpenAILunaExperimentalPlanner(
                            bound, SCHEMA, CLOCK, candidate_context=c, domain_interpretation=domain
                        )
                    ),
                    core_candidate_attributor=OpenAICoreCandidateAttributor(bridge),
                    repository=repo,
                    schema=SCHEMA,
                    context_index=ctx,
                    semantic_index=sem,
                    embedder=emb,
                    contextual_reasoner=object(),
                    actor="synthetic-reviewer-only-corpus",
                    now=NOW,
                    context_limit=5,
                    request_id_factory=lambda case_id=case: "fresh-reviewer-" + case_id,
                    bundle_compiler=compile_hybrid_candidate_bundle,
                )
                status = result.status.value
                routes = result.execution_flow.get("routes", [])
            except Exception as exc:
                error = f"{type(exc).__name__}: {str(exc)[:380]}"
            for path in repo.list_markdown_paths():
                actual = repo.read_text(path)
                if before.get(path) != actual:
                    changed[path] = actual
        receipt = {
            "case": case,
            "source_sha256": source_receipt["source_sha256"],
            "status": status,
            "error": error,
            "real_model_outputs": [*frozen, *client.new_records],
            "fresh_reviewer_calls": len(client.new_records),
            "routes": routes,
            "changed_notes": changed,
            "estimated_total_usd": round(PREVIOUS_USD + cost(costs), 8),
        }
        (HERE / f"{case}.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, default=str) + "\n"
        )
        summary.append(
            {
                "case": case,
                "status": status,
                "reviewer_calls": len(client.new_records),
                "note_paths": list(changed),
                "error": error,
            }
        )
        print(json.dumps(summary[-1], ensure_ascii=False), flush=True)
    (HERE / "SUMMARY.json").write_text(
        json.dumps(
            {
                "results": summary,
                "new_estimated_usd": round(cost(costs), 8),
                "estimated_cumulative_usd": round(PREVIOUS_USD + cost(costs), 8),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    print("New estimated USD", round(cost(costs), 8), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
