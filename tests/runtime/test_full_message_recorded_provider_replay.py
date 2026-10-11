"""Replay all 27 authentic 2026-10-11 model replies through the entire Core path.

Every test uses the unchanged original source, the same production-shaped
adapters and a fresh clone of the committed canonical synthetic Notes.
No OpenAI credentials, real Markdown root, network or mutable provider replay.
These are *historical observations*, not semantic correctness oracles.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_attribution import OpenAICoreCandidateAttributor
from odyssey_core.candidate_fact_readback import readback_core_facts
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.request_planning import RequestPlan
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.complete_source_handoff import execute_complete_message_with_core
from tests.apps.test_fact_candidates import CASES
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_full_message_corpus_regression import (
    ROOT,
    _vault_snapshot,
    fresh_corpus_vault,
)

SAVED = ROOT / "benchmarks/application_router/full_message_corpus_v1"


class RecordedProviderClient:
    """Return saved provider replies sequentially, without generating semantics."""

    def __init__(self, replies: list[dict]):
        self._replies = replies
        self.calls = []
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **request):
        if len(self.calls) >= len(self._replies):
            raise AssertionError("Unexpected extra provider request beyond authentic snapshot")
        expected = self._replies[len(self.calls)]
        assert request["model"] == expected["model"]
        assert request["store"] is False
        self.calls.append(request)
        return SimpleNamespace(
            status=expected["status"],
            output_text=expected["output_text"],
            id=None,
            usage=None,
        )


@pytest.mark.parametrize("case", CASES, ids=lambda item: item["id"])
def test_all_real_provider_replies_replay_on_unchanged_original_and_seeded_vault(
    case, tmp_path: Path
):
    """Regress every boundary while refusing an unverified or unsafe write."""
    path = SAVED / f"{case['id']}.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    assert receipt["version"] == 1
    assert receipt["case_id"] == case["id"]
    assert (
        receipt["original_source_sha256"]
        == hashlib.sha256(case["source"].encode("utf-8")).hexdigest()
    )
    assert 1 <= len(receipt["provider_replies"]) <= 4
    sdk = RecordedProviderClient(receipt["provider_replies"])
    repo, context_index, semantic_index, embedder = fresh_corpus_vault(tmp_path)
    before = _vault_snapshot(repo)
    captured = {}

    def planner_factory(context, domain):
        captured["context"] = context
        normal = OpenAILunaExperimentalPlanner(
            sdk, SCHEMA, CLOCK, candidate_context=context, domain_interpretation=domain
        )

        class RecordingPlanner:
            def plan(self, source):
                plan = normal.plan(source)
                if isinstance(plan, RequestPlan):
                    captured["plan"] = plan
                return plan

            def __getattr__(self, name):
                return getattr(normal, name)

        return RecordingPlanner()

    try:
        result = execute_complete_message_with_core(
            case["source"],
            router=OpenAIFactCandidateRouter(sdk, prompt_revision="v3"),
            temporal=OpenAITemporalInterpreter(sdk, CLOCK),
            core_planner_factory=planner_factory,
            core_candidate_attributor=OpenAICoreCandidateAttributor(sdk),
            repository=repo,
            schema=SCHEMA,
            context_index=context_index,
            semantic_index=semantic_index,
            embedder=embedder,
            contextual_reasoner=object(),
            actor="synthetic-corpus-actor",
            now=NOW,
            context_limit=5,
            request_id_factory=lambda: f"corpus-{case['id']}",
        )
    except (ValueError, TypeError) as error:
        assert receipt["captured_application_status"] is None
        assert type(error).__name__ == receipt["captured_error_type"]
        assert _vault_snapshot(repo) == before
    else:
        assert result.status.value == receipt["captured_application_status"]
        if result.status is ApplicationStatus.COMPLETED:
            assert "plan" in captured and "context" in captured
            evidence = readback_core_facts(
                case["source"], captured["context"], captured["plan"], result, repo, SCHEMA
            )
            assert evidence.persisted_facts
            assert all(fact.status == "verified_in_markdown" for fact in evidence.persisted_facts)
        else:
            assert _vault_snapshot(repo) == before
    assert len(sdk.calls) == len(receipt["provider_replies"])
    assert sdk.calls[0]["input"][1]["content"] == case["source"]
