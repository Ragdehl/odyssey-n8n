"""Provider-free provenance of why Core rejected frozen real-model plans."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from benchmarks.fact_candidate_core_live.run_remaining_scoped_corpus import ORDER
from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core import candidate_coverage
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider

ROOT = Path(__file__).resolve().parents[2]
SAVED = ROOT / "benchmarks/application_router/scoped_routing_v1"


def main() -> None:
    original = candidate_coverage.validate_candidate_coverage_manifest
    case_name = [""]
    issues: dict[str, list[str]] = {}

    def inspect_coverage(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except Exception as error:
            issues.setdefault(case_name[0], []).append(
                f"{type(error).__name__}: {str(error)[:140]}"
            )
            raise

    candidate_coverage.validate_candidate_coverage_manifest = inspect_coverage
    cases = {item["id"]: item["source"] for item in CASES}
    try:
        for case_id in ORDER:
            case_name[0] = case_id
            frozen = json.loads((SAVED / f"{case_id}.json").read_text(encoding="utf-8"))
            sdk = FrozenProvider(frozen["responses"])
            with tempfile.TemporaryDirectory() as folder:
                repo, context, semantic, embedder = fresh_corpus_vault(Path(folder))
                try:
                    result = execute_candidate_routed_message(
                        cases[case_id],
                        router=OpenAIFactCandidateRouter(sdk, prompt_revision="v3"),
                        temporal=OpenAITemporalInterpreter(sdk, CLOCK),
                        core_planner_factory=lambda hints, domain, client=sdk: (
                            OpenAILunaExperimentalPlanner(
                                client,
                                SCHEMA,
                                CLOCK,
                                candidate_context=hints,
                                domain_interpretation=domain,
                            )
                        ),
                        core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
                        repository=repo,
                        schema=SCHEMA,
                        context_index=context,
                        semantic_index=semantic,
                        embedder=embedder,
                        contextual_reasoner=object(),
                        actor="synthetic-coverage-diagnostics",
                        now=NOW,
                        context_limit=5,
                        request_id_factory=lambda identifier=case_id: f"diagnostic-{identifier}",
                    )
                    status = result.status.value
                except Exception as error:
                    status = type(error).__name__ + ": " + str(error)[:80]
            print(
                json.dumps(
                    {
                        "case": case_id,
                        "status": status,
                        "coverage_rejections": issues.get(case_id, []),
                    },
                    ensure_ascii=False,
                )
            )
    finally:
        candidate_coverage.validate_candidate_coverage_manifest = original


if __name__ == "__main__":
    main()
