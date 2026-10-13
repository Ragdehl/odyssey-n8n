"""No API: replay frozen genuine model outputs and record stage evidence.

For cases where the old capture runs out of model replies under changed code,
mark the run INCOMPLETE_REPLAY rather than inventing a new provider result.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile

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
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider

ROOT = pathlib.Path(__file__).parent
SOURCES = {x["id"]: x["source"] for x in CASES}
PREVIOUS = {
    "F01": "hybrid_live_matrix_20261012",
    "F02": "hybrid_live_matrix_20261012",
    "F09": "hybrid_live_matrix_20261012",
    "F14": "hybrid_source_review_v1",
    "F18": "hybrid_live_matrix_20261012",
    "F25": "hybrid_live_matrix_20261012",
    "F26": "hybrid_semantic_live_v5",
    "F27": "hybrid_live_matrix_20261012",
}


def run(case):
    folder = PREVIOUS[case]
    rec = json.loads((ROOT.parent / folder / f"{case}.json").read_text())
    sdk = FrozenProvider(rec["real_model_outputs"])
    source = SOURCES[case]
    actual = None
    error = None
    with tempfile.TemporaryDirectory(prefix="odyssey-corpus-audit-") as root:
        repo, ctx, sem, emb = fresh_corpus_vault(pathlib.Path(root))
        before = {p: repo.read_text(p) for p in repo.list_markdown_paths()}
        try:
            actual = execute_candidate_routed_message(
                source,
                router=OpenAIFactCandidateRouter(sdk, prompt_revision="v4"),
                temporal=OpenAITemporalInterpreter(
                    sdk, CLOCK, max_output_tokens=1536, scoped_date_time_context=True
                ),
                core_planner_factory=lambda c, d: OpenAILunaExperimentalPlanner(
                    sdk, SCHEMA, CLOCK, candidate_context=c, domain_interpretation=d
                ),
                core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
                repository=repo,
                schema=SCHEMA,
                context_index=ctx,
                semantic_index=sem,
                embedder=emb,
                contextual_reasoner=object(),
                actor="diagnostic-disposable-vault",
                now=NOW,
                context_limit=5,
                request_id_factory=lambda: "frozen-diagnostic-" + case,
                bundle_compiler=compile_hybrid_candidate_bundle,
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:450]}"
        changed = {
            p: [line for line in repo.read_text(p).splitlines() if line.startswith("- ")]
            for p in repo.list_markdown_paths()
            if before.get(p) != repo.read_text(p)
        }
        result = {
            "case": case,
            "source": source,
            "frozen_capture": folder,
            "frozen_available": len(rec["real_model_outputs"]),
            "provider_requests_consumed": len(sdk.calls),
            "replay_status": (actual.status.value if actual else "INCOMPLETE_REPLAY"),
            "error": error,
            "routes": actual.execution_flow.get("routes", [])
            if actual and actual.execution_flow
            else [],
            "changed_notes": changed,
            "source_stage_outputs": [
                {"model": item["model"], "output_text": item["output_text"]}
                for item in rec["real_model_outputs"]
            ],
        }
        (ROOT / f"{case}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        return result


if __name__ == "__main__":
    for name in sys.argv[1:]:
        result = run(name)
        print(
            json.dumps(
                {
                    "case": name,
                    "status": result["replay_status"],
                    "error": result["error"],
                    "calls": str(result["provider_requests_consumed"])
                    + "/"
                    + str(result["frozen_available"]),
                    "routes": [
                        (x.get("capability"), x.get("status"), x.get("reason"))
                        for x in result["routes"]
                    ],
                    "notes": result["changed_notes"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
