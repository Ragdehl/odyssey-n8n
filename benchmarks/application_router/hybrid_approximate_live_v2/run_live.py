"""F02: reuse exact genuine Router/Temporal responses, pay only new Core calls."""

from __future__ import annotations

import hashlib
import json
import os
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
OLD = OUT.parent / "hybrid_router_v5_end_to_end_v4/F02.json"
CUMULATIVE_BEFORE = 0.64353083
MAX_NEW_USD = 0.03


class FrozenThenRealResponses:
    def __init__(self, responses, frozen):
        self.responses = responses
        self.frozen = frozen
        self.calls = []
        self.new = []

    def new_cost(self):
        return 1.1 * sum(
            (r["input_tokens"] * 0.20 + r["output_tokens"] * 1.20) / 1_000_000 for r in self.new
        )

    def create(self, **kwargs):
        index = len(self.calls)
        self.calls.append(kwargs)
        if index < len(self.frozen):
            row = self.frozen[index]
            if row["status"] != "completed" or row["model"] != kwargs.get("model"):
                raise RuntimeError("Frozen source provider mismatch")
            return SimpleNamespace(status=row["status"], output_text=row["output_text"])
        if (
            kwargs.get("model") != "gpt-5.6-luna"
            or len(self.new) >= 2
            or self.new_cost() >= MAX_NEW_USD
            or CUMULATIVE_BEFORE + self.new_cost() >= 1
        ):
            raise RuntimeError("New provider call not authorized by budget")
        response = self.responses.create(**kwargs)
        usage = response.usage
        row = {
            "model": kwargs["model"],
            "status": response.status,
            "output_text": response.output_text,
            "input_tokens": int(usage.input_tokens),
            "output_tokens": int(usage.output_tokens),
        }
        self.new.append(row)
        if self.new_cost() >= MAX_NEW_USD:
            raise RuntimeError("Provider spend exceeds cap")
        return response


def main():
    if os.getenv("ODYSSEY_APPROVE_HYBRID_EXPERIMENT") != "1" or not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Experiment is not approved")
    if (OUT / "F02.json").exists():
        raise RuntimeError("Immutable receipt exists")
    source = next(x["source"] for x in CASES if x["id"] == "F02")
    prior = json.loads(OLD.read_text())
    if prior["source_sha256"] != hashlib.sha256(source.encode()).hexdigest():
        raise RuntimeError("Stale source")
    frozen = prior["real_model_outputs"][:2]
    client = FrozenThenRealResponses(OpenAI(max_retries=0, timeout=85).responses, frozen)
    sdk = SimpleNamespace(responses=client)
    with tempfile.TemporaryDirectory(prefix="odyssey-approx-time-") as tmp:
        repo, ctx, sem, emb = fresh_corpus_vault(Path(tmp))
        before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
        result = execute_candidate_routed_message(
            source,
            router=OpenAIFactCandidateRouter(sdk, prompt_revision="v5"),
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
            actor="isolated-approximate-check",
            now=NOW,
            context_limit=5,
            request_id_factory=lambda: "approx-clock-reviewed-f02",
            bundle_compiler=compile_hybrid_candidate_bundle,
        )
        changed = {
            p: repo.read_text(p)
            for p in repo.list_markdown_paths()
            if before.get(p) != repo.read_text(p)
        }
    receipt = {
        "case": "F02",
        "status": result.status.value,
        "source_sha256": prior["source_sha256"],
        "real_model_outputs": [*frozen, *client.new],
        "fresh_model_calls": len(client.new),
        "routes": result.execution_flow.get("routes", []),
        "changed_notes": changed,
        "estimated_new_usd": round(client.new_cost(), 8),
        "estimated_cumulative_usd": round(CUMULATIVE_BEFORE + client.new_cost(), 8),
    }
    (OUT / "F02.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, default=str) + "\n"
    )
    print("STATUS", receipt["status"])
    print("STAGES", [(r["status"], r["text"]) for r in receipt["routes"]])
    print(
        "NOTES",
        [
            (p, [line for line in s.splitlines() if line.startswith("- ")])
            for p, s in changed.items()
        ],
    )
    print("COST", receipt["estimated_cumulative_usd"])


if __name__ == "__main__":
    main()
