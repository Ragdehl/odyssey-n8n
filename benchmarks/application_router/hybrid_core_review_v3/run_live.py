"""Review the final F01 fact text, with one freshly paid genuine reviewer.

All other previous GPT-6/GPT-5.6 outputs remain immutable real-model recordings.
No calls to a real vault; fresh 13-Note fixture only.
"""

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

ROOT = Path(__file__).parent
SRC_RECORD = ROOT.parent / "hybrid_router_v5_end_to_end_v5/F01.json"
BASE_SPEND_USD = 0.64280109
MAX_NEW_USD = 0.015


class Responses:
    def __init__(self, previous, live):
        self.previous = previous
        self.live = live
        self.calls = []
        self.new = None

    def create(self, **kwargs):
        i = len(self.calls)
        if i >= len(self.previous):
            raise RuntimeError("Unapproved extra provider call")
        if kwargs.get("model") != self.previous[i]["model"]:
            raise RuntimeError("Expected frozen provider/model sequence differs")
        self.calls.append(kwargs)
        if i != 3:
            old = self.previous[i]
            return SimpleNamespace(status=old["status"], output_text=old["output_text"])
        if self.new is not None:
            raise RuntimeError("Exactly one new reviewer permitted")
        response = self.live.create(**kwargs)
        usage = response.usage
        self.new = {
            "model": kwargs["model"],
            "status": response.status,
            "output_text": response.output_text,
            "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        }
        estimate = (
            1.1 * (self.new["input_tokens"] * 0.20 + self.new["output_tokens"] * 1.20) / 1_000_000
        )
        if estimate > MAX_NEW_USD or BASE_SPEND_USD + estimate >= 1.0:
            raise RuntimeError("Authorized budget exceeded after reviewer call")
        return response


def main():
    if os.getenv("ODYSSEY_APPROVE_HYBRID_EXPERIMENT") != "1" or not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("No explicit API authorization")
    if (ROOT / "F01.json").exists():
        raise RuntimeError("Immutable genuine model result already exists")
    source = next(row["source"] for row in CASES if row["id"] == "F01")
    previous_receipt = json.loads(SRC_RECORD.read_text())
    if hashlib.sha256(source.encode()).hexdigest() != previous_receipt["source_sha256"]:
        raise RuntimeError("Source replay has changed")
    client = Responses(
        previous_receipt["real_model_outputs"], OpenAI(max_retries=0, timeout=85).responses
    )
    sdk = SimpleNamespace(responses=client)
    with tempfile.TemporaryDirectory(prefix="odyssey-f01-generic-validator-") as tmp:
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
            actor="f01-generic-validation-review",
            now=NOW,
            context_limit=5,
            request_id_factory=lambda: "f01-new-independent-review",
            bundle_compiler=compile_hybrid_candidate_bundle,
        )
        changed = {
            p: repo.read_text(p)
            for p in repo.list_markdown_paths()
            if repo.read_text(p) != before.get(p)
        }
    if client.new is None:
        raise RuntimeError("No actual new reviewer ran")
    price = (
        1.1 * (client.new["input_tokens"] * 0.20 + client.new["output_tokens"] * 1.20) / 1_000_000
    )
    receipt = {
        "case": "F01",
        "source_sha256": previous_receipt["source_sha256"],
        "status": result.status.value,
        "routes": result.execution_flow.get("routes", []),
        "changed_notes": changed,
        "fresh_reviewer_calls": 1,
        "real_model_outputs": [
            client.new if i == 3 else record
            for i, record in enumerate(previous_receipt["real_model_outputs"])
        ],
        "estimated_new_usd": round(price, 8),
        "estimated_cumulative_usd": round(BASE_SPEND_USD + price, 8),
    }
    (ROOT / "F01.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False, default=str) + "\n"
    )
    print("status:", result.status.value)
    print("routes:", [(x["status"], x["text"]) for x in receipt["routes"]])
    print(
        "facts:",
        [(p, [x for x in s.splitlines() if x.startswith("- ")]) for p, s in changed.items()],
    )
    print("estimated total USD", receipt["estimated_cumulative_usd"])


if __name__ == "__main__":
    main()
