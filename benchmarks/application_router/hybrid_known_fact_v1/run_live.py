"""F09 independent genuine semantic equivalence x2; no real vault mutations."""

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
from odyssey_core.known_fact_equivalence import OpenAIKnownFactVerifier
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider

HERE = Path(__file__).parent
PREVIOUS = HERE.parent / "hybrid_existing_info_v1/F09.json"
PREVIOUS_USD = 0.66245633
MAX_NEW_USD = 0.02


class CappedProvider:
    def __init__(self, actual):
        self.actual = actual
        self.records = []

    @property
    def cost(self):
        return 1.10 * sum(
            (r["input_tokens"] * 0.20 + r["output_tokens"] * 1.20) / 1_000_000 for r in self.records
        )

    def create(self, **kwargs):
        if (
            len(self.records) >= 2
            or kwargs.get("model") != "gpt-5.6-luna"
            or self.cost >= MAX_NEW_USD
            or PREVIOUS_USD + self.cost >= 1
        ):
            raise RuntimeError("Known-fact reviewer budget exceeded")
        response = self.actual.create(**kwargs)
        usage = response.usage
        self.records.append(
            {
                "model": kwargs["model"],
                "status": response.status,
                "output_text": response.output_text,
                "input_tokens": int(getattr(usage, "input_tokens", 0)),
                "output_tokens": int(getattr(usage, "output_tokens", 0)),
            }
        )
        if self.cost > MAX_NEW_USD or PREVIOUS_USD + self.cost >= 1:
            raise RuntimeError("Post-call budget cap exceeded")
        return response


def main():
    if os.getenv("ODYSSEY_APPROVE_HYBRID_EXPERIMENT") != "1" or not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Explicit experimental API approval required")
    if (HERE / "F09.json").exists():
        raise SystemExit("Immutable genuine receipt already exists")
    source = next(x["source"] for x in CASES if x["id"] == "F09")
    previous = json.loads(PREVIOUS.read_text())
    if previous["source_sha256"] != hashlib.sha256(source.encode()).hexdigest():
        raise SystemExit("Source changed")
    old = FrozenProvider(previous["real_model_outputs"])
    paid = CappedProvider(OpenAI(max_retries=0, timeout=85).responses)
    verifier = OpenAIKnownFactVerifier(SimpleNamespace(responses=paid))
    with tempfile.TemporaryDirectory(prefix="odyssey-f09-independent-noop-") as tmp:
        repo, ctx, sem, emb = fresh_corpus_vault(Path(tmp))
        before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
        result = execute_candidate_routed_message(
            source,
            router=OpenAIFactCandidateRouter(old, prompt_revision="v5"),
            temporal=OpenAITemporalInterpreter(
                old, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
            ),
            core_planner_factory=lambda c, d: OpenAILunaExperimentalPlanner(
                old, SCHEMA, CLOCK, candidate_context=c, domain_interpretation=d
            ),
            core_candidate_attributor=OpenAICoreCandidateAttributor(old),
            known_fact_verifier=verifier,
            repository=repo,
            schema=SCHEMA,
            context_index=ctx,
            semantic_index=sem,
            embedder=emb,
            contextual_reasoner=object(),
            actor="isolated-independent-known-fact",
            now=NOW,
            context_limit=5,
            request_id_factory=lambda: "f09-two-independent-equivalence-reviews",
            bundle_compiler=compile_hybrid_candidate_bundle,
        )
        changed = {
            p: repo.read_text(p)
            for p in repo.list_markdown_paths()
            if before.get(p) != repo.read_text(p)
        }
        operations = []
        for route in result.execution_flow.get("routes", []):
            for step in route.get("steps", []):
                if step.get("name") == "action.write":
                    operations.append(step.get("output"))
        unchanged_marta = repo.read_text("Marta.md") == before["Marta.md"]
        written_luis = "- Vive en Lyon." in repo.read_text("Luis.md")
    receipt = {
        "case": "F09",
        "source_sha256": previous["source_sha256"],
        "model_provenance": previous["real_model_outputs"],
        "real_new_model_outputs": paid.records,
        "status": result.status.value,
        "routes": result.execution_flow.get("routes", []),
        "changed_notes": changed,
        "marta_unchanged": unchanged_marta,
        "luis_written": written_luis,
        "operations": operations,
        "estimated_new_usd": round(paid.cost, 8),
        "estimated_cumulative_usd": round(PREVIOUS_USD + paid.cost, 8),
    }
    (HERE / "F09.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, default=str) + "\n"
    )
    print("STATUS", receipt["status"], flush=True)
    print("WRITES", operations, flush=True)
    print("MARTA UNCHANGED", unchanged_marta, "LUIS WRITTEN", written_luis, flush=True)
    print("REVIEWER OUTPUTS", [(r["model"], r["output_text"]) for r in paid.records], flush=True)
    print("USD TOTAL", receipt["estimated_cumulative_usd"], flush=True)


if __name__ == "__main__":
    main()
