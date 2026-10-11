"""Regress the remaining real-model 27-case corpus through scoped routing.

Frozen responses are authentic provider outputs saved from the single approved
2026-10-11 capped batch. This replay calls no OpenAI service, writes ONLY
to a newly cloned synthetic thirteen-note vault, and verifies each actual
status, route result and physically marked Markdown note count.

Do not fabricate successful models' replies for failed cases; all negative
observations are kept as regression evidence, not converted to successes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import (
    ROOT,
    fresh_corpus_vault,
)
from tests.runtime.test_scoped_route_recorded_real_replay import FrozenProvider

SAVED = ROOT / "benchmarks/application_router/scoped_routing_v1"
REPLAY_IDS = tuple(
    path.stem for path in sorted(SAVED.glob("F*.json")) if path.stem not in {"F09", "F13"}
)


@pytest.mark.parametrize("case_id", REPLAY_IDS)
def test_remaining_live_model_captures_replay_without_new_provider_calls(
    case_id: str, tmp_path: Path
) -> None:
    case = next(item for item in CASES if item["id"] == case_id)
    capture = json.loads((SAVED / f"{case_id}.json").read_text(encoding="utf-8"))
    assert capture["version"] == 1
    assert capture["case_id"] == case_id
    assert (
        capture["original_source_sha256"]
        == hashlib.sha256(case["source"].encode("utf-8")).hexdigest()
    )
    assert capture["responses"]
    sdk = FrozenProvider(capture["responses"])
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)

    def scoped():
        return execute_candidate_routed_message(
            case["source"],
            router=OpenAIFactCandidateRouter(sdk, prompt_revision="v3"),
            temporal=OpenAITemporalInterpreter(sdk, CLOCK),
            core_planner_factory=lambda hints, domain: OpenAILunaExperimentalPlanner(
                sdk, SCHEMA, CLOCK, candidate_context=hints, domain_interpretation=domain
            ),
            core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
            repository=repo,
            schema=SCHEMA,
            context_index=context,
            semantic_index=semantic,
            embedder=embedder,
            contextual_reasoner=object(),
            actor="frozen-synthetic-route-corpus",
            now=NOW,
            context_limit=5,
            request_id_factory=lambda: f"real-scoped-replay-{case_id}",
        )

    if capture.get("error_category"):
        with pytest.raises(Exception) as error:
            scoped()
        assert type(error.value).__name__ == capture["error_category"]
        actual = None
    else:
        actual = scoped()
        assert actual.status.value == capture["captured_application_status"], case_id
        assert [r["status"] for r in actual.execution_flow["routes"]] == [
            r["status"] for r in capture["route_summaries"]
        ]
    assert len(sdk.calls) == len(capture["responses"]), case_id
    assert sdk.calls[0]["input"][1]["content"] == case["source"]
    written = sum(
        "odyssey:fact request=route-" in repo.read_text(path) for path in repo.list_markdown_paths()
    )
    assert written == capture.get("written_notes", 0), case_id
    if actual is not None:
        # The original complete request must not be sent as the planning
        # source once Router provided more than one selected route.
        if len(actual.execution_flow["routes"]) > 1:
            assert any(
                request["input"][1]["content"] != case["source"] for request in sdk.calls[1:]
            )
