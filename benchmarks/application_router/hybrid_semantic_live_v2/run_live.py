"""Budgeted real-provider replay over disposable canonical corpus Notes.

Never runs against DEV, PROD, or a personal vault. Run with explicit case IDs.
Stores immutable actual provider texts and physical Markdown observations.
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

OUT = Path(__file__).parent
MAX_NEW_USD = 0.22
MAX_TOTAL_USD = 1.0
PREVIOUS_USD = 0.471058
MAX_CALLS = 45
RATES = {"gpt-6-luna": (0.10, 0.50), "gpt-5.6-luna": (0.20, 1.20)}
MULTIPLIER = 1.10


class BudgetedResponses:
    def __init__(self, base):
        self.base = base
        self.records = []
        self.attempts = 0

    def cost(self):
        return MULTIPLIER * sum(
            (r["input_tokens"] * RATES[r["model"]][0] + r["output_tokens"] * RATES[r["model"]][1])
            / 1_000_000
            for r in self.records
        )

    def create(self, **kwargs):
        if (
            self.attempts >= MAX_CALLS
            or self.cost() >= MAX_NEW_USD
            or PREVIOUS_USD + self.cost() >= MAX_TOTAL_USD
        ):
            raise RuntimeError("authorized experimental API ceiling reached")
        model = kwargs.get("model")
        if model not in RATES:
            raise RuntimeError("unknown model; refusing")
        self.attempts += 1
        resp = self.base.create(**kwargs)
        usage = resp.usage
        self.records.append(
            {
                "model": model,
                "status": resp.status,
                "output_text": resp.output_text,
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            }
        )
        if self.cost() > MAX_NEW_USD or PREVIOUS_USD + self.cost() > MAX_TOTAL_USD:
            raise RuntimeError("post-call experimental budget ceiling reached")
        return resp


def main(ids):
    if os.getenv("ODYSSEY_APPROVE_HYBRID_EXPERIMENT") != "1":
        raise SystemExit("Set explicit live-gate approval")
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("No API credential")
    choices = {x["id"]: x["source"] for x in CASES}
    if not ids or len(set(ids)) != len(ids) or any(c not in choices for c in ids):
        raise SystemExit("Supply unique valid case IDs")
    if any((OUT / f"{case}.json").exists() for case in ids):
        raise SystemExit("Existing receipts would be overwritten")
    rec = BudgetedResponses(OpenAI(max_retries=0, timeout=80).responses)
    sdk = SimpleNamespace(responses=rec)
    completed = []
    for case in ids:
        source = choices[case]
        start = len(rec.records)
        status = "exception"
        error = None
        changed = {}
        routes = []
        with tempfile.TemporaryDirectory(prefix="odyssey-hybrid-live-") as tmp:
            repo, ctx, sem, emb = fresh_corpus_vault(Path(tmp))
            before = set(repo.list_markdown_paths())
            try:
                result = execute_candidate_routed_message(
                    source,
                    router=OpenAIFactCandidateRouter(sdk, prompt_revision="v4"),
                    temporal=OpenAITemporalInterpreter(
                        sdk, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
                    ),
                    core_planner_factory=lambda c, domain: OpenAILunaExperimentalPlanner(
                        sdk, SCHEMA, CLOCK, candidate_context=c, domain_interpretation=domain
                    ),
                    core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
                    repository=repo,
                    schema=SCHEMA,
                    context_index=ctx,
                    semantic_index=sem,
                    embedder=emb,
                    contextual_reasoner=object(),
                    actor="isolated-real-model-corpus",
                    now=NOW,
                    context_limit=5,
                    request_id_factory=lambda case_id=case: "review-v2-" + case_id,
                    bundle_compiler=compile_hybrid_candidate_bundle,
                )
                status = result.status.value
                routes = result.execution_flow.get("routes", [])
            except Exception as exc:
                error = f"{type(exc).__name__}: {str(exc)[:400]}"
            for path in sorted(set(repo.list_markdown_paths()) - before):
                changed[path] = repo.read_text(path)
        item = {
            "case": case,
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "status": status,
            "error": error,
            "routes": routes,
            "changed_notes": changed,
            "real_model_outputs": rec.records[start:],
            "estimated_new_usd": round(rec.cost(), 7),
            "estimated_cumulative_usd": round(PREVIOUS_USD + rec.cost(), 7),
        }
        path = OUT / f"{case}.json"
        path.write_text(json.dumps(item, indent=2, ensure_ascii=False, default=str) + "\n")
        completed.append(
            {
                "case": case,
                "status": status,
                "calls": len(rec.records) - start,
                "notes": list(changed),
                "error": error,
            }
        )
        print(json.dumps(completed[-1], ensure_ascii=False), flush=True)
    (OUT / "SUMMARY.json").write_text(
        json.dumps(
            {
                "cases": completed,
                "estimated_new_usd": round(rec.cost(), 7),
                "estimated_cumulative_usd": round(PREVIOUS_USD + rec.cost(), 7),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    print("Total estimated new USD", round(rec.cost(), 7), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
