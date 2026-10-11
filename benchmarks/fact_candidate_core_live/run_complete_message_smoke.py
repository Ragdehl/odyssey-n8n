"""Live, isolated entire-message Router/Temporal/Core/Writer smoke gate.

Provider access is OFF unless explicitly armed by the existing authorized
transient systemd user unit. No live vaults, n8n routes, or DEV/PROD. Original
Core model and Writer execute; this is not a miniature planning implementation.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from odyssey_apps.fact_candidate_core import to_core_candidate_context
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

ROOT = Path(__file__).resolve().parents[2]
MAX_SPEND_USD = 0.07
# Observed prior approved experiments including one 2026-10-11 complete-source
# GPT-5.6 call (baseline 0.0438566 + observed 0.0026154).
PREVIOUS_ESTIMATED_SPEND_USD = 0.0564021
FLAG = "ODYSSEY_CORE_FACT_LIVE_APPROVED"
RECEIPT = Path(
    "/home/ragdehl/projects/odyssey-experimental-receipts/full-source-smoke-attempt3.json"
)
DEFAULT_SOURCE = "Hoy compré cuaderno, lápiz y carpeta."


class CappedResponses:
    """Pre-authorize each provider call using the pinned conservative prices."""

    def __init__(self, *, client, models: dict, cap_usd: float = MAX_SPEND_USD) -> None:
        if (
            not isinstance(cap_usd, (int, float))
            or isinstance(cap_usd, bool)
            or not math.isfinite(cap_usd)
            or not 0 < cap_usd <= 1
        ):
            raise ValueError("A positive finite authorized cap up to one USD is required")
        self._client = client
        self._models = models
        self.cap_usd = float(cap_usd)
        self.spent = PREVIOUS_ESTIMATED_SPEND_USD
        self.calls: list[dict] = []
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **request):
        """Never let one model request exceed remaining authorized spend."""
        model = request["model"]
        rates = self._models[model]
        if request.get("store") is not False or not isinstance(
            request.get("max_output_tokens"), int
        ):
            raise ValueError("Model request must have explicit safety and token limits")
        # The input byte count exceeds ordinary token count for these ASCII
        # schema and Spanish synthetic-message requests. No cached discount.
        input_upper = len(
            json.dumps(request["input"], ensure_ascii=False, default=str).encode("utf-8")
        ) + len(json.dumps(request.get("text", {}), default=str).encode("utf-8"))
        output_upper = request["max_output_tokens"]
        reserve = (
            input_upper * rates["input_per_million"] + output_upper * rates["output_per_million"]
        ) / 1_000_000
        if self.spent + reserve > self.cap_usd:
            raise ValueError(
                f"Provider cap reached before {model}: spent={self.spent:.6f} "
                f"reservation={reserve:.6f} cap={self.cap_usd:.2f}"
            )
        # Charge full conservative reservation on transport uncertainty;
        # successful completed usage allows releasing unused budget.
        self.spent += reserve
        response = self._client.responses.create(**request)
        usage = getattr(response, "usage", None)
        in_tokens = getattr(usage, "input_tokens", None)
        out_tokens = getattr(usage, "output_tokens", None)
        if isinstance(in_tokens, int) and isinstance(out_tokens, int):
            observed = (
                in_tokens * rates["input_per_million"] + out_tokens * rates["output_per_million"]
            ) / 1_000_000
            self.spent += observed - reserve
        else:
            observed = reserve
        self.calls.append(
            {
                "model": model,
                "input_tokens": in_tokens,
                "output_tokens": out_tokens,
                "estimated_usd": round(observed, 8),
                "status": getattr(response, "status", None),
            }
        )
        return response


def current_capture_time() -> datetime:
    """Return the same second-precision offset-aware clock required by Core facts."""
    return datetime.now(ZoneInfo("Europe/Paris")).replace(microsecond=0)


def dry_run() -> dict:
    """No provider calls or filesystem mutation before explicit live approval."""
    return {
        "mode": "offline",
        "full_original_message": DEFAULT_SOURCE,
        "stages": ["router", "temporal", "core", "core_coverage", "writer", "readback"],
        "new_provider_calls": 0,
        "allowed_estimated_remaining_usd": round(MAX_SPEND_USD - PREVIOUS_ESTIMATED_SPEND_USD, 8),
        "active": False,
    }


def execute_live() -> dict:
    """Execute the already existing modules on a disposable canonical vault."""
    if os.getenv(FLAG) != "1":
        raise ValueError("Live provider requests require the previously approved gate flag")
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("The approved transient systemd EnvironmentFile is required")
    # One-shot proof: never bill a second run under the same inherited cap.
    RECEIPT.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(RECEIPT), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump({"status": "armed_once", "provider_cost_unknown": True}, stream)
    from openai import OpenAI

    models = json.loads(
        (ROOT / "config/runtime-pricing-snapshot.json").read_text(encoding="utf-8")
    )["models"]
    client = CappedResponses(client=OpenAI(max_retries=0, timeout=90), models=models)
    today = current_capture_time()
    clock = {
        "date": today.date().isoformat(),
        "time": today.strftime("%H:%M"),
        "timezone": "Europe/Paris",
    }
    schema = json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))
    router = OpenAIFactCandidateRouter(client, prompt_revision="v3")
    temporal = OpenAITemporalInterpreter(client, clock)
    attributor = OpenAICoreCandidateAttributor(client)
    captured: dict = {}

    class RecordingRouter:
        """Capture exactly the Router output already consumed by Core."""

        def propose(self, source):
            proposal = router.propose(source)
            captured["proposal"] = proposal
            return proposal

    def planner_factory(context, domain):
        normal = OpenAILunaExperimentalPlanner(
            client,
            schema,
            clock,
            candidate_context=context,
            domain_interpretation=domain,
        )

        class CapturingPlanner:
            """Observe the ordinary Core plan without changing its authority."""

            def plan(self, source):
                result = normal.plan(source)
                if isinstance(result, RequestPlan):
                    captured["plan"] = result
                return result

            def __getattr__(self, name):
                return getattr(normal, name)

        return CapturingPlanner()

    with tempfile.TemporaryDirectory(prefix="odyssey-full-message-live-") as folder:
        vault = Path(folder) / "vault"
        vault.mkdir()
        repo = VaultRepository(vault)
        embedder = FastEmbedTextEmbedder(
            cache_dir=Path("/data/odyssey/runtime/phase11a-benchmark/embedding-cache"),
            local_files_only=True,
        )
        context_index = ContextIndex(Path(folder) / "context.sqlite3")
        semantic_index = SemanticEntityIndex(Path(folder) / "semantic.sqlite3")
        context_index.rebuild(repo, schema, embedder)
        semantic_index.rebuild(repo, schema, embedder)
        try:
            result = execute_complete_message_with_core(
                DEFAULT_SOURCE,
                router=RecordingRouter(),
                temporal=temporal,
                core_planner_factory=planner_factory,
                core_candidate_attributor=attributor,
                repository=repo,
                schema=schema,
                context_index=context_index,
                semantic_index=semantic_index,
                embedder=embedder,
                contextual_reasoner=object(),
                actor="disposable-entire-message-live",
                now=today.isoformat(),
                context_limit=5,
                request_id_factory=lambda: "full-message-live-verified",
            )
        except Exception as error:
            return {
                "mode": "live",
                "status": "failed_before_application_result",
                "error_category": type(error).__name__,
                "error": str(error)[:240],
                "model_calls": client.calls,
                "estimated_cumulative_usd": round(client.spent, 8),
                "written_markdown_files": len(repo.list_markdown_paths()),
            }
        output = {
            "mode": "live",
            "application_status": result.status.value,
            "clarification_code": result.clarification_code,
            "planning_error": result.planning_error,
            "model_calls": client.calls,
            "estimated_cumulative_usd": round(client.spent, 8),
            "written_markdown_files": len(repo.list_markdown_paths()),
            "readback_verified": False,
            "actions": [
                {
                    "status": action.status.value,
                    "reason": action.reason,
                    "units": [
                        {"status": unit.status.value, "reason": unit.reason}
                        for unit in action.unit_results
                    ],
                }
                for action in result.action_results
            ],
            "operational_stages": [
                {
                    "name": stage.name,
                    "outcome": stage.outcome.value,
                    "error_category": stage.error_category,
                }
                for stage in result.operational.stages
            ],
            "core_plan_summary": repr(captured.get("plan"))[:1800],
        }
        if isinstance(captured.get("plan"), RequestPlan):
            # Recover the exact proposed source context already held by Router
            # without issuing a second provider call or re-planning.
            # Router source proposal is read from the decorator below, if captured.
            proposal = captured.get("proposal")
            if proposal is not None:
                evidence = readback_core_facts(
                    DEFAULT_SOURCE,
                    to_core_candidate_context(proposal),
                    captured["plan"],
                    result,
                    repo,
                    schema,
                )
                output["core_facts_readback"] = [fact.status for fact in evidence.persisted_facts]
                output["readback_verified"] = (
                    bool(evidence.persisted_facts)
                    and all(f.status == "verified_in_markdown" for f in evidence.persisted_facts)
                    and result.status == ApplicationStatus.COMPLETED
                )
        return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    response = execute_live() if args.live else dry_run()
    if args.live:
        RECEIPT.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
