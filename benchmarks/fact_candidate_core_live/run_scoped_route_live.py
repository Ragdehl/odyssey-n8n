"""One-shot, budgeted real-provider evidence for approved route-local dispatch.

No production workflows, personal Notes or retries; each case uses a fresh
clone of the thirteen committed synthetic canonical Notes. Prior capped test
spend of USD 0.1096283 and every historical receipt are ALWAYS debited.
The user increased the accumulated maximum from USD 0.25 to USD 0.50 on
2026-10-12; a separate 050 approval flag is mandatory for live calls.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

from benchmarks.fact_candidate_core_live.run_complete_message_smoke import CappedResponses
from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.context import ContextIndex
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.semantic import FastEmbedTextEmbedder, SemanticEntityIndex
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import FIXTURE

ROOT = Path(__file__).resolve().parents[2]
RECEIPTS = Path("/home/ragdehl/projects/odyssey-experimental-receipts/unit-routing-cap025")
MAX_USD = 0.50
BASELINE_USD = 0.1096283
FLAG = "ODYSSEY_ROUTE_SCOPED_050_APPROVED"


def previous_spend() -> float:
    """Debits completed one-shot receipts, never guesses uncertain API costs."""
    total = BASELINE_USD
    for path in RECEIPTS.glob("*.json") if RECEIPTS.exists() else ():
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if (
            receipt.get("receipt_id", receipt.get("case")) != path.stem
            or receipt.get("status") != "finished"
        ):
            raise ValueError("Uncertain prior route-local provider charge")
        spent = receipt.get("new_estimated_usd")
        if type(spent) not in (float, int) or spent < 0:
            raise ValueError("Missing provider estimate in receipt")
        total += spent
    if total >= MAX_USD:
        raise ValueError("Approved model budget exhausted")
    return total


def run_one(case_id: str, *, live: bool = False, attempt: int = 1) -> dict:
    """Make one full scoped model attempt with provider-free mode by default."""
    if attempt not in (1, 2, 3, 4, 5, 6, 7, 8, 9):
        raise ValueError("Only explicitly bounded attempts 1 through 9 are allowed")
    if case_id not in {item["id"] for item in CASES}:
        raise ValueError("Only the frozen 27-case regression corpus may reach the provider")
    row = next(c for c in CASES if c["id"] == case_id)
    total = previous_spend()
    if not live:
        return {"case": case_id, "mode": "offline", "spent_usd": total, "calls": 0}
    if os.environ.get(FLAG) != "1" or not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("A separately armed transient provider unit is required")
    # The model wrapper rechecks a conservative reserve BEFORE *each* call.
    # Stop the next case if only a tiny amount remains, rather than producing
    # a misleading success after one unfinished billable provider operation.
    if MAX_USD - total < 0.004:
        raise ValueError("Insufficient approved budget to start another case")
    RECEIPTS.mkdir(mode=0o700, parents=True, exist_ok=True)
    receipt_id = case_id if attempt == 1 else f"{case_id}-v{attempt}"
    path = RECEIPTS / f"{receipt_id}.json"
    with os.fdopen(os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as f:
        json.dump({"case": case_id, "receipt_id": receipt_id, "status": "armed_unknown_cost"}, f)

    from openai import OpenAI

    prices = json.loads(
        (ROOT / "config/runtime-pricing-snapshot.json").read_text(encoding="utf-8")
    )["models"]
    client = CappedResponses(
        client=OpenAI(max_retries=0, timeout=90),
        models=prices,
        cap_usd=MAX_USD,
    )
    client.spent = total
    provider_outputs = []

    class RecordingProvider:
        def __init__(self):
            self.responses = SimpleNamespace(create=self.create)

        def create(self, **request):
            response = client.responses.create(**request)
            provider_outputs.append(
                {
                    "model": request["model"],
                    "status": response.status,
                    "output_text": getattr(response, "output_text", None),
                }
            )
            path.write_text(
                json.dumps(
                    {
                        "case": case_id,
                        "status": "in_progress",
                        "provider_calls": client.calls,
                        "provider_outputs": provider_outputs,
                        "spent_usd_observed": round(client.spent - total, 8),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return response

    provider = RecordingProvider()
    outcome = {
        "case": case_id,
        "receipt_id": receipt_id,
        "status": "finished",
        "mode": "live",
    }
    try:
        with tempfile.TemporaryDirectory(prefix="odyssey-unit-routing-") as folder:
            vault = Path(folder) / "vault"
            shutil.copytree(FIXTURE / "vault", vault)
            repo = VaultRepository(vault)
            embedder = FastEmbedTextEmbedder(
                cache_dir=Path("/data/odyssey/runtime/phase11a-benchmark/embedding-cache"),
                local_files_only=True,
            )
            context = ContextIndex(Path(folder) / "context.sqlite3")
            semantic = SemanticEntityIndex(Path(folder) / "semantic.sqlite3")
            context.rebuild(repo, SCHEMA, embedder)
            semantic.rebuild(repo, SCHEMA, embedder)
            result = execute_candidate_routed_message(
                row["source"],
                router=OpenAIFactCandidateRouter(provider, prompt_revision="v4"),
                temporal=OpenAITemporalInterpreter(
                    provider, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
                ),
                core_planner_factory=lambda candidate_context, domain: (
                    OpenAILunaExperimentalPlanner(
                        provider,
                        SCHEMA,
                        CLOCK,
                        candidate_context=candidate_context,
                        domain_interpretation=domain,
                    )
                ),
                core_candidate_attributor=OpenAICoreCandidateAttributor(provider),
                repository=repo,
                schema=SCHEMA,
                context_index=context,
                semantic_index=semantic,
                embedder=embedder,
                contextual_reasoner=object(),
                actor="synthetic-unit-provider-test",
                now=NOW,
                context_limit=5,
                request_id_factory=lambda: f"unit-live-{case_id}",
            )
            outcome["application_status"] = result.status.value
            outcome["route_summaries"] = [
                {
                    "status": r["status"],
                    "depends_on": r.get("depends_on"),
                    "reason": r.get("reason"),
                }
                for r in result.execution_flow.get("routes", [])
            ]
            outcome["route_sources"] = [
                r.get("source")
                for r in result.execution_flow.get("routes", [])
                if isinstance(r, dict) and "source" in r
            ]
            outcome["written_notes"] = sum(
                "odyssey:fact request=route-" in repo.read_text(p)
                for p in repo.list_markdown_paths()
            )
    except Exception as error:
        outcome["error_category"] = type(error).__name__
        outcome["error_message"] = str(error)[:200]
    outcome["provider_calls"] = client.calls
    outcome["provider_outputs"] = provider_outputs
    outcome["new_estimated_usd"] = round(client.spent - total, 8)
    outcome["estimated_cumulative_usd"] = round(client.spent, 8)
    path.write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
    return {key: value for key, value in outcome.items() if key != "provider_outputs"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=[x["id"] for x in CASES], required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--attempt", type=int, choices=[1, 2, 3, 4, 5, 6, 7, 8, 9], default=1)
    arguments = parser.parse_args()
    print(
        json.dumps(
            run_one(arguments.case, live=arguments.live, attempt=arguments.attempt),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
