"""Replay genuine E2 provider outputs locally, without API or personal vault."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.source_boundary_review import OpenAICoreSourceBoundaryReviewer
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.composition import _persistence_actor
from odyssey_runtime.context_planner_ports import OpenAILunaContextPlannerFactory
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.core.test_reference_preflight import UnresolvedReasoner
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault

DATA = Path(__file__).with_name("recorded_replies_v1.json")
NOW = "2026-10-15T20:00:00+02:00"
CLOCK = {"date": "2026-10-15", "time": "20:00", "timezone": "Europe/Paris"}


class RecordedResponses:
    def __init__(self, responses):
        self.responses = SimpleNamespace(create=self.create)
        self._responses = responses
        self.calls = []

    def create(self, **request):
        index = len(self.calls)
        if index >= len(self._responses):
            raise RuntimeError(f"UNRECORDED_PROVIDER_CALL model={request.get('model')}")
        item = self._responses[index]
        self.calls.append(request["model"])
        if item["model"] != request["model"]:
            raise RuntimeError(
                f"RECORDED_MODEL_ORDER_MISMATCH index={index} expected={item['model']} actual={request['model']}"
            )
        if request.get("store") is not False:
            raise RuntimeError("PROVIDER_RETENTION_CONTRACT_CHANGED")
        return SimpleNamespace(
            output_text=item["output_text"],
            status=item["status"],
            id=f"offline-{index}",
            usage=None,
        )


def replay_case(case):
    client = RecordedResponses(case["responses"])
    source = case["source"]
    with tempfile.TemporaryDirectory(prefix="odyssey-e2-recorded-") as tmp:
        repo, ci, si, embedder = fresh_corpus_vault(Path(tmp))
        before = {x: repo.read_text(x) for x in repo.list_markdown_paths()}
        result = execute_candidate_routed_message(
            source,
            router=OpenAIFactCandidateRouter(client, prompt_revision="v6"),
            temporal=OpenAITemporalInterpreter(
                client, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
            ),
            core_planner_factory=OpenAILunaContextPlannerFactory(
                client=client, schema=SCHEMA, clock=CLOCK
            ),
            core_candidate_attributor=OpenAICoreCandidateAttributor(client),
            repository=repo,
            schema=SCHEMA,
            context_index=ci,
            semantic_index=si,
            embedder=embedder,
            contextual_reasoner=UnresolvedReasoner(),
            actor=_persistence_actor("recorded-e2-fixture", None),
            now=NOW,
            context_limit=5,
            request_id_factory=lambda: "recorded-" + case["case"],
            bundle_compiler=compile_hybrid_candidate_bundle,
            source_boundary_reviewer=OpenAICoreSourceBoundaryReviewer(client),
        )
        paths = repo.list_markdown_paths()
        changed = {x: repo.read_text(x) for x in paths if repo.read_text(x) != before.get(x)}
        return {
            "case": case["case"],
            "status": result.status.value,
            "error": result.planning_error,
            "clarification": result.clarification_code,
            "provider_calls": len(client.calls),
            "recorded_calls": len(case["responses"]),
            "changed_paths": list(changed),
            "saved_qualifier": any(
                ("por la tarde" in body or "por la noche" in body or "dans l'après-midi" in body)
                for body in changed.values()
            ),
            "invented_clock": any(
                ("15:00" in body or "21:00" in body) for body in changed.values()
            ),
            "no_person_corruption": all(path.startswith("calendar/days/") for path in changed),
            "changed_excerpt": {k: v[-350:] for k, v in changed.items()},
        }


def main():
    data = json.loads(DATA.read_text())
    for case in data["cases"]:
        try:
            outcome = replay_case(case)
            print(json.dumps(outcome, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(
                json.dumps(
                    {"case": case["case"], "failed": type(exc).__name__, "reason": str(exc)[:250]}
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
