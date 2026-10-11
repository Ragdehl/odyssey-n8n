"""Genuine saved model replies through route-scoped Core and canonical test Notes.

Zero provider calls. F13's original live run was PARTIAL because the
predecessor-confirmed Core identity hadn't superseded Router's earlier
provisional ambiguous_identity source state. The repaired run must use the
SAME frozen replies and persist all three facts, without guessing a name.
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

RECEIPTS = ROOT / "benchmarks/application_router/scoped_routing_v1"


class FrozenProvider:
    def __init__(self, records):
        self.records = records
        self.calls = []
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **request):
        assert len(self.calls) < len(self.records), "Unexpected new model call"
        record = self.records[len(self.calls)]
        assert request["model"] == record["model"]
        assert request["store"] is False
        self.calls.append(request)
        return SimpleNamespace(
            status=record["status"],
            output_text=record["output_text"],
            usage=None,
            id=None,
        )


@pytest.mark.parametrize("case_id", ["F09", "F13"])
def test_frozen_genuine_scoped_provider_plans_write_in_clean_canonical_vault(
    case_id: str, tmp_path: Path
):
    case = next(c for c in CASES if c["id"] == case_id)
    saved = json.loads((RECEIPTS / f"{case_id}.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(case["source"].encode()).hexdigest() == saved["original_source_sha256"]
    sdk = FrozenProvider(saved["responses"])
    repo, context, semantic, embedder = fresh_corpus_vault(tmp_path)

    result = execute_candidate_routed_message(
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
        actor="only-synthetic-scoped-provider-replay",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: f"real-scoped-replay-{case_id}",
    )
    assert len(sdk.calls) == len(saved["responses"])
    assert sdk.calls[0]["input"][1]["content"] == case["source"]
    assert (
        all(request["input"][1]["content"] != case["source"] for request in sdk.calls[1:])
        if case_id == "F13"
        else True
    )
    assert result.status is ApplicationStatus.COMPLETED, [
        (r["status"], r.get("reason")) for r in result.execution_flow["routes"]
    ]
    texts = "\n".join(repo.read_text(path) for path in repo.list_markdown_paths())
    if case_id == "F09":
        assert "Vive en Lyon." in repo.read_text("Marta.md")
        assert "Vive en Lyon." in repo.read_text("Luis.md")
        assert len(sdk.calls) == 3  # Router, Core, independent Core review; no Temporal.
    else:
        assert len(result.execution_flow["routes"]) == 3
        assert "Hablé con [[Eric|Eric]]." in texts
        assert "Iré al cine con [[Eric|Eric]]." in texts
        assert "Hoy compré pan." in texts
        assert len(sdk.calls) == 10


def test_router_ambiguity_is_not_overridden_without_fresh_core_markdown(tmp_path: Path):
    """A forged canonical predecessor cannot promote Router's ambiguous pronoun."""
    from odyssey_apps.fact_candidates import validate_fact_candidate_proposal
    from odyssey_core.application import CanonicalReferenceEvidence, DependentReferenceGuard
    from odyssey_runtime.candidate_route_dispatch import (
        compile_candidate_route_bundle,
        resolve_scoped_reference_with_core_proof,
    )

    record = json.loads((RECEIPTS / "F13.json").read_text(encoding="utf-8"))
    source = next(c["source"] for c in CASES if c["id"] == "F13")
    proposal = validate_fact_candidate_proposal(
        source, json.loads(record["responses"][0]["output_text"])
    )
    dependent = compile_candidate_route_bundle(proposal).units[1].context
    assert dependent.candidates[0].state == "ambiguous_identity"

    repo, *_ = fresh_corpus_vault(tmp_path)
    invalid = DependentReferenceGuard(
        "él",
        CanonicalReferenceEvidence(
            0,
            0,
            0,
            "Eric",
            "fixture-person-eric",
            "person",
            "Eric",
            "nonexistent-predecessor-source-note",
            "fake-source-guard",
            "fake-canonical-guard",
        ),
    )
    with pytest.raises(ValueError, match="no longer valid"):
        resolve_scoped_reference_with_core_proof(dependent, invalid, repo, SCHEMA)
    assert dependent.candidates[0].state == "ambiguous_identity"
    assert all(
        "odyssey:fact request=" not in repo.read_text(path) for path in repo.list_markdown_paths()
    )
