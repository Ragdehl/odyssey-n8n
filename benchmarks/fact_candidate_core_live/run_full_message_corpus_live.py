"""One complete corpus case against the real models and a cloned canonical test vault.

Offline by default, no personal Notes, no DEV/PROD, no silent retries.
Only the previously approved *cumulative* USD 0.07 cap has provider authority.
A larger 27-case gate needs its own explicit approval before any cap increase.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from benchmarks.fact_candidate_core_live.run_complete_message_smoke import (
    MAX_SPEND_USD,
    PREVIOUS_ESTIMATED_SPEND_USD,
    CappedResponses,
)
from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.candidate_fact_readback import readback_core_facts
from odyssey_core.context import ContextIndex
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.request_planning import RequestPlan
from odyssey_core.semantic import FastEmbedTextEmbedder, SemanticEntityIndex
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.complete_source_handoff import execute_complete_message_with_core
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import FIXTURE

ROOT = Path(__file__).resolve().parents[2]
RESULTS = Path("/home/ragdehl/projects/odyssey-experimental-receipts/full-message-corpus")
APPROVAL_FLAG = "ODYSSEY_CORE_FACT_LIVE_APPROVED"
# Refuse an incomplete four-model run BEFORE any provider call. Existing
# Core request envelopes can require USD 0.0146 of conservative reservation.
MIN_COMPLETE_CASE_HEADROOM_USD = 0.028


def case_ids() -> tuple[str, ...]:
    """Preserve the frozen 27-message human reviewed original-source corpus."""
    return tuple(row["id"] for row in CASES)


def previous_spend() -> float:
    """Charge all previous attempted corpus requests, including uncertain attempts."""
    total = PREVIOUS_ESTIMATED_SPEND_USD
    if not RESULTS.exists():
        return total
    files = list(RESULTS.glob("*.json"))
    if any(path.stem not in case_ids() for path in files):
        raise ValueError("Unrecognized corpus receipt: stop before provider access")
    for path in files:
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if receipt.get("case") != path.stem:
            raise ValueError("Mismatched corpus receipt")
        prior = receipt.get("reserved_or_estimated_usd")
        if not isinstance(prior, (float, int)) or prior < 0:
            raise ValueError("Incomplete corpus receipt has uncertain cost")
        total += prior
    if total > MAX_SPEND_USD:
        raise ValueError("Cumulative model budget exceeded")
    return total


def run(case_id: str, *, live: bool = False) -> dict:
    """Perform one full source-to-Core mutation on a disposable vault."""
    if case_id not in case_ids():
        raise ValueError("Corpus case is not in the frozen 27-message registry")
    total = previous_spend()
    row = next(item for item in CASES if item["id"] == case_id)
    if not live:
        return {
            "case": case_id,
            "mode": "offline",
            "source": row["source"],
            "model_calls": 0,
            "written_notes": 0,
            "already_consumed_estimated_usd": round(total, 8),
            "remaining_approved_usd": round(MAX_SPEND_USD - total, 8),
            "source_fixture": str(FIXTURE / "manifest.json"),
        }
    if MAX_SPEND_USD - total < MIN_COMPLETE_CASE_HEADROOM_USD:
        raise ValueError("Insufficient approved headroom for one complete case")
    if os.environ.get(APPROVAL_FLAG) != "1":
        raise ValueError("Real corpus gate requires the previously approved flag")
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("The approved systemd EnvironmentFile is required")
    RESULTS.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt_path = RESULTS / f"{case_id}.json"
    # The one-shot file is created BEFORE any model call and never reused.
    fd = os.open(str(receipt_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({"case": case_id, "status": "armed", "reserved_or_estimated_usd": None}, handle)

    import shutil
    import tempfile

    from openai import OpenAI

    rates = json.loads((ROOT / "config/runtime-pricing-snapshot.json").read_text())["models"]
    client = CappedResponses(client=OpenAI(max_retries=0, timeout=90), models=rates)
    client.spent = total
    result: dict = {
        "case": case_id,
        "mode": "live",
        "outcome": "attempted",
        "provider_calls": [],
        "written_notes": 0,
        "core_facts_verified": [],
    }
    try:
        with tempfile.TemporaryDirectory(prefix=f"odyssey-corpus-{case_id}-") as temp:
            vault = Path(temp) / "vault"
            shutil.copytree(FIXTURE / "vault", vault)
            repo = VaultRepository(vault)
            derived = Path(temp) / "derived"
            derived.mkdir()
            embedder = FastEmbedTextEmbedder(
                cache_dir=Path("/data/odyssey/runtime/phase11a-benchmark/embedding-cache"),
                local_files_only=True,
            )
            context_index = ContextIndex(derived / "context.sqlite3")
            semantic_index = SemanticEntityIndex(derived / "semantic.sqlite3")
            context_index.rebuild(repo, SCHEMA, embedder)
            semantic_index.rebuild(repo, SCHEMA, embedder)

            captured = {}
            actual_router = OpenAIFactCandidateRouter(client, prompt_revision="v3")

            class RecordingRouter:
                def propose(self, source):
                    proposal = actual_router.propose(source)
                    captured["router_proposal"] = proposal
                    return proposal

            def core_factory(context, domain):
                captured["context"] = context
                planner = OpenAILunaExperimentalPlanner(
                    client, SCHEMA, CLOCK, candidate_context=context, domain_interpretation=domain
                )

                class RecordingPlanner:
                    def plan(self, source):
                        compiled = planner.plan(source)
                        if isinstance(compiled, RequestPlan):
                            captured["plan"] = compiled
                        return compiled

                    def __getattr__(self, name):
                        return getattr(planner, name)

                return RecordingPlanner()

            try:
                outcome = execute_complete_message_with_core(
                    row["source"],
                    router=RecordingRouter(),
                    temporal=OpenAITemporalInterpreter(client, CLOCK),
                    core_planner_factory=core_factory,
                    core_candidate_attributor=OpenAICoreCandidateAttributor(client),
                    repository=repo,
                    schema=SCHEMA,
                    context_index=context_index,
                    semantic_index=semantic_index,
                    embedder=embedder,
                    contextual_reasoner=object(),  # No unmetered provider side calls.
                    actor="synthetic-corpus-actor",
                    now=NOW,
                    context_limit=5,
                    request_id_factory=lambda: f"corpus-{case_id}",
                )
                result["application_status"] = outcome.status.value
                result["planning_error"] = outcome.planning_error
                result["operational_stages"] = [
                    {
                        "name": stage.name,
                        "outcome": stage.outcome.value,
                        "error_category": stage.error_category,
                    }
                    for stage in outcome.operational.stages
                ]
                result["clarification_code"] = outcome.clarification_code
                result["actions"] = [
                    {"status": action.status.value, "reason": action.reason}
                    for action in outcome.action_results
                ]
                if "plan" in captured and "context" in captured:
                    evidence = readback_core_facts(
                        row["source"], captured["context"], captured["plan"], outcome, repo, SCHEMA
                    )
                    result["core_facts_verified"] = [
                        fact.status for fact in evidence.persisted_facts
                    ]
                result["outcome"] = (
                    "persisted_and_read_back"
                    if outcome.status is ApplicationStatus.COMPLETED
                    and result["core_facts_verified"]
                    and all(x == "verified_in_markdown" for x in result["core_facts_verified"])
                    else "pending_or_failed"
                )
            except Exception as error:
                result["outcome"] = "stopped_before_completion"
                result["error_type"] = type(error).__name__
                result["error"] = str(error)[:180]
            result["written_notes"] = sum(
                "odyssey:fact request=corpus-" in repo.read_text(path)
                for path in repo.list_markdown_paths()
            )
    except Exception as error:
        result["outcome"] = "harness_error"
        result["error_type"] = type(error).__name__
        result["error"] = str(error)[:180]

    result["provider_calls"] = client.calls
    result["reserved_or_estimated_usd"] = round(client.spent - total, 8)
    result["estimated_total_usd"] = round(client.spent, 8)
    receipt_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=case_ids(), required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.case, live=args.live), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
