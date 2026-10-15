"""Authorized, capped genuine-provider E2 Router→Temporal→Core→Writer gate.

No ambient credentials, no DEV/PROD user vault and no destructive operations.
Use only the inspected transient systemd user unit with EnvironmentFile.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from benchmarks.fact_candidate_core_live.run_complete_message_smoke import CappedResponses
from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.source_boundary_review import OpenAICoreSourceBoundaryReviewer
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.composition import _persistence_actor
from odyssey_runtime.context_planner_ports import OpenAILunaContextPlannerFactory
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault

ROOT = Path(__file__).resolve().parents[2]
RECEIPT_DIR = Path("/home/ragdehl/projects/odyssey-experimental-receipts/e2-live-20261015")
MAX_NEW_USD = 1.0
APPROVAL_FLAG = "ODYSSEY_E2_LIVE_APPROVED"
CASES = (
    ("daypart_es", "Mañana por la tarde hablaré con Bea."),
    ("same_day_es", "Hoy por la tarde llamé a Bea y hoy por la noche vi a Marta."),
    ("third_party_es", "Ayer María vio a Marta."),
    ("daypart_fr", "Demain dans l'après-midi je parlerai avec Bea."),
    ("pronoun_es", "Ayer hablé con Eric. Mañana iré al cine con él. Hoy compré pan."),
)


ACCEPTANCE_CASES = (
    ("daypart_known_person", "Mañana por la tarde Bea hablará con Marta."),
    ("two_same_day", "hoy por la tarde Bea llamó a Marta y hoy por la noche Ana vio a Luis."),
    ("third_party", "Ayer Ana vio a Marta."),
    ("french_daypart", "Demain dans l'après-midi Bea parlera avec Marta."),
)


class PersistingBudget(CappedResponses):
    """Reserve before each SDK call and keep conservative unresolved attempts."""

    def __init__(self, *, client: object, models: dict[str, Any], receipt: Path):
        super().__init__(client=client, models=models, cap_usd=MAX_NEW_USD)
        self.spent = 0.0  # NEW approval; no unrelated historical campaign charged.
        self._receipt = receipt
        self._attempts: list[dict[str, Any]] = []
        self._sequence = 0
        self._model_fixtures: list[dict[str, Any]] = []

    def _save(self, status: str) -> None:
        # Every request snapshot is privately retained and bounded. No actual
        # prompt/model output is copied here; recorded facts remain in fixture.
        data = {
            "version": 1,
            "status": status,
            "cap_usd": MAX_NEW_USD,
            "charged_or_reserved_usd": round(self.spent, 8),
            "attempts": self._attempts,
            "completed_calls": self.calls,
            "model_fixtures": self._model_fixtures,
        }
        self._receipt.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self._receipt.chmod(0o600)

    def create(self, **request):
        self._sequence += 1
        number = self._sequence
        self._attempts.append({"ordinal": number, "model": request.get("model"), "status": "armed"})
        self._save("in_progress")
        try:
            output = super().create(**request)
        except Exception:
            self._attempts[-1]["status"] = "uncertain_or_blocked"
            self._save("stopped_uncertain")
            raise
        self._model_fixtures.append(
            {
                "ordinal": number,
                "model": request.get("model"),
                "response": getattr(output, "output_text", None),
            }
        )
        self._attempts[-1]["status"] = "completed"
        self._attempts[-1]["estimated_usd"] = self.calls[-1]["estimated_usd"]
        self._save("in_progress")
        return output


def run(
    *,
    diagnostic=False,
    acceptance=False,
    final_gate=False,
    verify_nonday=False,
    post_fix=False,
    same_day_verify=False,
) -> dict[str, Any]:
    if os.environ.get(APPROVAL_FLAG) != "1":
        raise ValueError("E2 live gate was not explicitly armed")
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("Fixed systemd credential environment is required")
    global RECEIPT_DIR
    if same_day_verify:
        RECEIPT_DIR = RECEIPT_DIR.with_name("e2-live-same-day-final-20261015")
    elif post_fix:
        RECEIPT_DIR = RECEIPT_DIR.with_name("e2-live-postfix-20261015")
    elif diagnostic:
        RECEIPT_DIR = RECEIPT_DIR.with_name("e2-live-diagnostic-20261015")
    elif acceptance:
        RECEIPT_DIR = RECEIPT_DIR.with_name("e2-live-acceptance-20261015")
    elif final_gate:
        RECEIPT_DIR = RECEIPT_DIR.with_name("e2-live-final-20261015")
    elif verify_nonday:
        RECEIPT_DIR = RECEIPT_DIR.with_name("e2-live-nonday-verification-20261015")
    if RECEIPT_DIR.exists():
        # Never reuse the same one-time campaign after interrupted billing.
        raise ValueError("The E2 live campaign already exists; refuse uncertain rerun")
    RECEIPT_DIR.mkdir(parents=True, mode=0o700)
    receipt = RECEIPT_DIR / "calls.json"
    receipt.touch(mode=0o600, exist_ok=False)

    from openai import OpenAI

    rates = json.loads((ROOT / "config/runtime-pricing-snapshot.json").read_text())["models"]
    client = PersistingBudget(
        client=OpenAI(max_retries=0, timeout=85), models=rates, receipt=receipt
    )
    if diagnostic or acceptance or final_gate or post_fix or same_day_verify:
        previous_name = (
            "e2-live-postfix-20261015"
            if same_day_verify
            else "e2-live-final-20261015"
            if post_fix
            else "e2-live-acceptance-20261015"
            if final_gate
            else "e2-live-diagnostic-20261015"
            if acceptance
            else "e2-live-20261015"
        )
        prior = json.loads((RECEIPT_DIR.with_name(previous_name) / "calls.json").read_text())
        if same_day_verify and (
            len(prior.get("completed_calls", [])) != len(prior.get("attempts", []))
            or any(x.get("status") != "completed" for x in prior.get("attempts", []))
            or len(json.loads((RECEIPT_DIR.with_name(previous_name) / "results.json").read_text()))
            != 4
        ):
            raise ValueError("Prior E2 live campaign has uncertain incomplete attempts")
        client.spent = prior["charged_or_reserved_usd"]
        if post_fix:
            # The separate non-Day verification followed the final campaign,
            # but used an independent reservation record; add only its actual
            # incremental spend to avoid ever reusing consumed authorization.
            extra_path = (
                RECEIPT_DIR.with_name("e2-live-nonday-verification-20261015") / "calls.json"
            )
            extra = json.loads(extra_path.read_text())
            if extra["status"] not in {"in_progress", "completed"}:
                raise ValueError("Cannot authorize new campaign with uncertain prior usage")
            client.spent += extra["charged_or_reserved_usd"]
    now = datetime.now(ZoneInfo("Europe/Paris")).replace(microsecond=0)
    clock = {
        "date": now.date().isoformat(),
        "time": now.strftime("%H:%M"),
        "timezone": "Europe/Paris",
    }
    summaries = []
    selected_cases = (
        ACCEPTANCE_CASES[1:2]
        if same_day_verify
        else ACCEPTANCE_CASES[:1]
        if verify_nonday
        else ACCEPTANCE_CASES
        if post_fix or final_gate
        else CASES[:4]
        if diagnostic
        else CASES
    )
    for case_id, source in selected_cases:
        # The next case may run only after the previous write/trace is saved.
        with tempfile.TemporaryDirectory(prefix="odyssey-e2-live-fixture-") as directory:
            vault, context_index, semantic_index, embedder = fresh_corpus_vault(Path(directory))
            before = {p: vault.read_text(p) for p in vault.list_markdown_paths()}
            stages = []
            from tests.core.test_reference_preflight import UnresolvedReasoner

            try:
                result = execute_candidate_routed_message(
                    source,
                    router=OpenAIFactCandidateRouter(client, prompt_revision="v6"),
                    temporal=OpenAITemporalInterpreter(
                        client,
                        clock,
                        max_output_tokens=1536,
                        scoped_date_time_context=True,
                    ),
                    core_planner_factory=OpenAILunaContextPlannerFactory(
                        client=client,
                        schema=SCHEMA,
                        clock=clock,
                    ),
                    core_candidate_attributor=OpenAICoreCandidateAttributor(client),
                    repository=vault,
                    schema=SCHEMA,
                    context_index=context_index,
                    semantic_index=semantic_index,
                    embedder=embedder,
                    contextual_reasoner=UnresolvedReasoner(),
                    actor=_persistence_actor("e2-live-fixture", None),
                    now=now.isoformat(),
                    context_limit=5,
                    request_id_factory=lambda case_id=case_id: f"e2-live-{case_id}",
                    bundle_compiler=compile_hybrid_candidate_bundle,
                    source_boundary_reviewer=OpenAICoreSourceBoundaryReviewer(client),
                    progress_callback=lambda stage, _data, stages=stages: stages.append(stage),
                )
                after = {p: vault.read_text(p) for p in vault.list_markdown_paths()}
                changed = [p for p in after if after.get(p) != before.get(p)]
                summary = {
                    "case": case_id,
                    "status": result.status.value,
                    "error": result.planning_error,
                    "clarification": result.clarification_code,
                    "changed_files": changed[:20],
                    "affected_ids": list(result.affected_stable_note_ids),
                    "stages": [
                        (s.name, s.outcome.value, s.error_category)
                        for s in result.operational.stages
                    ],
                    "milestones": stages[-30:],
                    "actions": [
                        {
                            "status": action.status.value,
                            "reason": action.reason,
                            "units": [
                                {"status": u.status.value, "reason": u.reason}
                                for u in action.unit_results
                            ],
                        }
                        for action in result.action_results
                    ],
                    "estimated_total_usd": round(client.spent, 8),
                    "daypart_saved": any(
                        "por la tarde" in after[p]
                        or "por la noche" in after[p]
                        or "dans l'après-midi" in after[p]
                        for p in changed
                    ),
                    "invented_clock": any(
                        "15:00" in after[p] or "21:00" in after[p] for p in changed
                    ),
                }
            except Exception as error:
                summary = {
                    "case": case_id,
                    "status": "harness_error",
                    "error": type(error).__name__,
                    "details": str(error)[:160],
                    "estimated_total_usd": round(client.spent, 8),
                }
            summaries.append(summary)
            (RECEIPT_DIR / "results.json").write_text(
                json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (RECEIPT_DIR / "results.json").chmod(0o600)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
            # Provider uncertainty is a one-time stop: no blind retries.
            if client._attempts and client._attempts[-1]["status"] == "uncertain_or_blocked":
                break
    if all(x.get("status") != "harness_error" for x in summaries) and not any(
        x.get("status") == "uncertain_or_blocked" for x in client._attempts
    ):
        client._save("finished")
    return {
        "cases": len(summaries),
        "estimated_usd": round(client.spent, 8),
        "receipt_root": str(RECEIPT_DIR),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--acceptance", action="store_true")
    parser.add_argument("--final-gate", action="store_true")
    parser.add_argument("--verify-nonday", action="store_true")
    parser.add_argument("--post-fix", action="store_true")
    parser.add_argument("--same-day-verify", action="store_true")
    args = parser.parse_args()
    if not args.live:
        print(
            json.dumps(
                {
                    "mode": "offline",
                    "cases": [x[0] for x in CASES],
                    "max_new_usd": MAX_NEW_USD,
                    "provider_calls": 0,
                }
            )
        )
        return
    print(
        json.dumps(
            run(
                diagnostic=args.diagnostic,
                acceptance=args.acceptance,
                final_gate=args.final_gate,
                verify_nonday=args.verify_nonday,
                post_fix=args.post_fix,
                same_day_verify=args.same_day_verify,
            )
        )
    )


if __name__ == "__main__":
    main()
