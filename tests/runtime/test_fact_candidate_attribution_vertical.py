"""Actual Core disposable Markdown writes beside a separately proposed model mapping.

All model calls are injected fakes. The proposed mapping is deliberately not
converted into a write factory or semantic authority automatically.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from odyssey_core.application import ApplicationStatus, execute_request
from odyssey_core.candidate_attribution import (
    CandidateAttributionError,
    OpenAICoreCandidateAttributor,
)
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
    review_candidate_coverage,
)
from odyssey_core.candidate_fact_readback import readback_core_facts
from odyssey_core.request_planning import RequestPlan
from tests.core.test_candidate_attribution import _f01, _f11, _f14
from tests.runtime.test_fact_candidate_writes_e2e import _new_repo
from tests.runtime.test_temporal_user_path_e2e import SCHEMA


def _sdk(raw: dict[str, Any]):
    calls: list[dict[str, Any]] = []
    response = SimpleNamespace(status="completed", usage=None, output_text=json.dumps(raw))
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kw: calls.append(kw) or response)
    )
    return client, calls


def _execute(
    repo,
    source: str,
    plan: RequestPlan,
    context,
    reviewed_claims,
):
    """Execute only independently reviewed Core coverage in an empty vault."""

    def independently_reviewed(request, packet, given_plan):
        return build_candidate_coverage_manifest(request, packet, given_plan, reviewed_claims)

    result = execute_request(
        source,
        planner=SimpleNamespace(plan=lambda _: plan),
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="synthetic-attribution-vertical",
        now="2026-10-04T12:30:00+02:00",
        context_limit=5,
        request_id_factory=lambda: "attribution-vertical-fixture",
        candidate_context=context,
        candidate_coverage_factory=independently_reviewed,
    )
    return result, independently_reviewed(source, context, plan)


@pytest.mark.parametrize("fixture", [_f01, _f11], ids=["three-activities", "shared-purchase"])
def test_model_proposal_is_read_only_then_independently_reviewed_core_writes(
    tmp_path: Path, fixture
) -> None:
    """The model cannot execute; only existing Core writes independently vetted facts."""
    source, context, plan, raw = fixture()
    repo = _new_repo(tmp_path)
    fake, calls = _sdk(raw)
    proposal = OpenAICoreCandidateAttributor(fake).propose(source, context, plan)
    assert len(calls) == 1
    assert repo.list_markdown_paths() == []
    assert not proposal.may_authorize_writes
    assert not proposal.semantically_verified
    assert not hasattr(proposal, "to_execution_manifest")
    # Separate reviewed fixture, not derived from the model proposal.
    independently_reviewed = tuple(
        CoreCandidateCoverageClaim(f"candidate-{i}", "planned_fact", i - 1)
        for i in range(1, len(context.candidates) + 1)
    )
    result, manifest = _execute(repo, source, plan, context, independently_reviewed)
    assert result.status is ApplicationStatus.COMPLETED
    receipts = readback_core_facts(source, context, plan, result, repo, SCHEMA)
    review = review_candidate_coverage(source, context, plan, manifest, receipts)
    assert len(repo.list_markdown_paths()) == (2 if len(context.candidates) == 3 else 1)
    assert all(p.status == "physically_written_claim" for p in review.items)
    assert not review.candidate_semantics_verified
    assert not review.safe_to_report_all_candidates_complete


def test_ambiguous_identity_remains_pending_and_partial_even_after_safe_writes(
    tmp_path: Path,
) -> None:
    """One omitted ambiguous candidate is visible, not silently marked completed."""
    source, context, plan, raw = _f14()
    fake, calls = _sdk(raw)
    repo = _new_repo(tmp_path)
    proposal = OpenAICoreCandidateAttributor(fake).propose(source, context, plan)
    assert len(calls) == 1
    assert proposal.candidates[2].pending_reason == "ambiguous_identity"
    reviewed = (
        CoreCandidateCoverageClaim("candidate-1", "planned_fact", 0),
        CoreCandidateCoverageClaim("candidate-2", "planned_fact", 1),
        CoreCandidateCoverageClaim("candidate-3", "pending", pending_reason="ambiguous_identity"),
    )
    result, manifest = _execute(repo, source, plan, context, reviewed)
    assert result.status is ApplicationStatus.PARTIAL
    assert result.pending_work.required and not result.pending_work.persisted
    receipts = readback_core_facts(source, context, plan, result, repo, SCHEMA)
    final = review_candidate_coverage(source, context, plan, manifest, receipts)
    assert [x.status for x in final.items] == [
        "physically_written_claim",
        "physically_written_claim",
        "pending",
    ]
    assert final.pending_candidate_ids == ("candidate-3",)
    assert not final.candidate_semantics_verified
    assert not final.safe_to_report_all_candidates_complete


def test_provider_hallucinates_fact_identity_and_no_markdown_is_touched(tmp_path: Path) -> None:
    source, context, plan, raw = _f11()
    bad = copy.deepcopy(raw)
    bad["candidates"][0]["planned_fact_text"] = "No compré pan."
    fake, calls = _sdk(bad)
    repo = _new_repo(tmp_path)
    with pytest.raises(CandidateAttributionError, match="Core validation"):
        OpenAICoreCandidateAttributor(fake).propose(source, context, plan)
    assert len(calls) == 1
    assert repo.list_markdown_paths() == []


def test_wrong_semantic_claim_does_not_pretend_to_be_verified(tmp_path: Path) -> None:
    """This pilot can reject mismatched lexical evidence, but cannot certify truth."""
    source, context, plan, raw = _f11()
    altered = copy.deepcopy(raw)
    altered["candidates"][0]["fact_ordinal"] = 1
    altered["candidates"][0]["planned_fact_text"] = "Compré leche."
    fake, _calls = _sdk(altered)
    repo = _new_repo(tmp_path)
    with pytest.raises(CandidateAttributionError):
        OpenAICoreCandidateAttributor(fake).propose(source, context, plan)
    assert repo.list_markdown_paths() == []


def test_context_mismatch_never_reaches_model_or_writes(tmp_path: Path) -> None:
    source, context, plan, raw = _f11()
    fake, calls = _sdk(raw)
    repo = _new_repo(tmp_path)
    with pytest.raises(ValueError, match="full current source"):
        OpenAICoreCandidateAttributor(fake).propose(source + " mañana", context, plan)
    assert calls == []
    assert repo.list_markdown_paths() == []
