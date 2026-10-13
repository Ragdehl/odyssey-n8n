"""Bounded live Core validation of the genuine v5 Router, only on disposable Notes."""

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
V5 = OUT.parent / "hybrid_router_v5_20261013"
BASE_USD = 0.61172125
MAX_NEW_USD = 0.06
MAX_TOTAL_USD = 1.0
RATES = {"gpt-6-luna": (0.10, 0.50), "gpt-5.6-luna": (0.20, 1.20)}
SURCHARGE = 1.10
MAX_CALLS = 30


def cost(rows):
    return SURCHARGE * sum(
        (r["input_tokens"] * RATES[r["model"]][0] + r["output_tokens"] * RATES[r["model"]][1])
        / 1_000_000
        for r in rows
    )


class LiveAfterFrozenRouter:
    def __init__(self, responses, router_record, budget):
        self.responses_source = responses
        self.router_record = router_record
        self.budget = budget
        self.calls = 0
        self.records = []

    def create(self, **kwargs):
        model = kwargs.get("model")
        self.calls += 1
        if self.calls == 1:
            if model != "gpt-6-luna" or self.router_record["status"] != "completed":
                raise RuntimeError("Frozen Router mismatch")
            return SimpleNamespace(
                status=self.router_record["status"],
                output_text=self.router_record["output_text"],
                usage=None,
            )
        if (
            model not in RATES
            or cost(self.budget) >= MAX_NEW_USD
            or BASE_USD + cost(self.budget) >= MAX_TOTAL_USD
            or len(self.budget) >= MAX_CALLS
        ):
            raise RuntimeError("Unapproved or exceeded model budget")
        response = self.responses_source.create(**kwargs)
        usage = response.usage
        record = {
            "model": model,
            "status": response.status,
            "output_text": response.output_text,
            "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        }
        self.records.append(record)
        self.budget.append(record)
        if cost(self.budget) >= MAX_NEW_USD or BASE_USD + cost(self.budget) >= MAX_TOTAL_USD:
            raise RuntimeError("Model budget exceeded after call")
        return response


def main(case_ids):
    if os.getenv("ODYSSEY_APPROVE_HYBRID_EXPERIMENT") != "1" or not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("No API authorization")
    if not 1 <= len(case_ids) <= 5 or len(set(case_ids)) != len(case_ids):
        raise SystemExit("Only 1..5 unique cases")
    known = {row["id"]: row["source"] for row in CASES}
    if any(case not in known for case in case_ids):
        raise SystemExit("Unknown corpus source")
    if any((OUT / f"{case}.json").exists() for case in case_ids):
        raise SystemExit("Cannot overwrite genuine results")
    api = OpenAI(max_retries=0, timeout=85).responses
    budget = []
    overview = []
    for case in case_ids:
        source = known[case]
        router_receipt = json.loads((V5 / f"{case}.json").read_text())
        if (
            router_receipt["status"] != "completed"
            or len(router_receipt["real_model_outputs"]) != 1
            or router_receipt["source_sha256"] != hashlib.sha256(source.encode()).hexdigest()
        ):
            raise RuntimeError("Missing genuine frozen v5 Router response")
        client = LiveAfterFrozenRouter(api, router_receipt["real_model_outputs"][0], budget)
        sdk = SimpleNamespace(responses=client)
        status = "exception"
        error = None
        flow = []
        changed = {}
        with tempfile.TemporaryDirectory(prefix="odyssey-v5-live-") as tmp:
            repo, ctx, semantic, emb = fresh_corpus_vault(Path(tmp))
            before = {path: repo.read_text(path) for path in repo.list_markdown_paths()}
            try:
                result = execute_candidate_routed_message(
                    source,
                    router=OpenAIFactCandidateRouter(sdk, prompt_revision="v5"),
                    temporal=OpenAITemporalInterpreter(
                        sdk, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
                    ),
                    core_planner_factory=lambda c, domain, captured=sdk: (
                        OpenAILunaExperimentalPlanner(
                            captured,
                            SCHEMA,
                            CLOCK,
                            candidate_context=c,
                            domain_interpretation=domain,
                        )
                    ),
                    core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
                    repository=repo,
                    schema=SCHEMA,
                    context_index=ctx,
                    semantic_index=semantic,
                    embedder=emb,
                    contextual_reasoner=object(),
                    actor="isolated-v5-real-test",
                    now=NOW,
                    context_limit=5,
                    request_id_factory=lambda case_id=case: "verified-live-v5-" + case_id,
                    bundle_compiler=compile_hybrid_candidate_bundle,
                )
                status = result.status.value
                flow = result.execution_flow.get("routes", []) if result.execution_flow else []
            except Exception as exc:
                error = f"{type(exc).__name__}: {str(exc)[:350]}"
            for path in repo.list_markdown_paths():
                markdown = repo.read_text(path)
                if before.get(path) != markdown:
                    changed[path] = markdown
        receipt = {
            "case": case,
            "source_sha256": router_receipt["source_sha256"],
            "status": status,
            "error": error,
            "real_model_outputs": [router_receipt["real_model_outputs"][0], *client.records],
            "fresh_model_calls": len(client.records),
            "routes": flow,
            "changed_notes": changed,
            "estimated_new_usd": round(cost(budget), 8),
            "estimated_cumulative_usd": round(BASE_USD + cost(budget), 8),
        }
        (OUT / f"{case}.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, default=str) + "\n"
        )
        result_row = {
            "case": case,
            "status": status,
            "calls": client.calls,
            "notes": list(changed),
            "error": error,
        }
        overview.append(result_row)
        print(json.dumps(result_row, ensure_ascii=False), flush=True)
    summary = {
        "cases": overview,
        "estimated_new_usd": round(cost(budget), 8),
        "estimated_cumulative_usd": round(BASE_USD + cost(budget), 8),
    }
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print("Estimated new spend", summary["estimated_new_usd"], flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
