"""Prewrite review and one-time correction: no Core/Tasks effects on rejection."""

from __future__ import annotations

from dataclasses import replace

import pytest

from odyssey_apps.fact_candidates import (
    FactCandidateProposal,
    validate_semantic_fact_candidate_proposal,
)
from odyssey_core.application import ApplicationStatus
from odyssey_core.source_boundary_review import (
    CoreSourceBoundaryInput,
    CoreSourceBoundaryReview,
    SourceBoundaryReviewError,
)
from odyssey_runtime.candidate_route_dispatch import (
    execute_candidate_routed_message,
    review_router_source_before_writes,
)
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault
from tests.runtime.test_generic_candidate_source_relations import proposal, unit

SOURCE = "The pump failed. The generator overheated."
SPLIT_RAW = proposal(
    SOURCE,
    [
        unit(SOURCE, "The pump failed", predicate="failed"),
        unit(SOURCE, "The generator overheated", predicate="overheated"),
    ],
    [("independent_assertion", 0), ("independent_assertion", 0)],
)
GROUP_RAW = proposal(
    SOURCE,
    [unit(SOURCE, "The pump failed. The generator overheated", predicate="failed")],
    [("independent_assertion", 0)],
)


def router_proposal(raw: dict) -> FactCandidateProposal:
    return validate_semantic_fact_candidate_proposal(SOURCE, raw)


def core_decision(context: CoreSourceBoundaryInput, decision: str, reason: str | None = None):
    return CoreSourceBoundaryReview(
        context.source_digest,
        context.partition_digest,
        decision,
        0 if decision == "accept" else 1,
        reason,
    )


class Reviewer:
    def __init__(self, *decisions):
        self.decisions = decisions
        self.calls = []
        self.model = "gpt-5.6"
        self.reasoning_effort = "low"
        self.last_usage = {"input_tokens": 11, "output_tokens": 3}
        self.last_error_category = None

    def review(self, context):
        self.calls.append(context)
        choice = self.decisions[len(self.calls) - 1]
        return core_decision(context, *choice)


class Router:
    def __init__(self, revised=GROUP_RAW):
        self.proposals = []
        self.revisions = []
        self.revised = revised

    def propose(self, source):
        self.proposals.append(source)
        return router_proposal(SPLIT_RAW)

    def revise(self, source, feedback):
        self.revisions.append((source, feedback))
        return router_proposal(self.revised)


def bundle():
    return compile_hybrid_candidate_bundle(router_proposal(SPLIT_RAW))


def test_one_cross_route_review_accepts_without_rerouting():
    router = Router()
    reviewer = Reviewer(("accept", None))
    result = review_router_source_before_writes(
        SOURCE,
        router_proposal(SPLIT_RAW),
        bundle(),
        router=router,
        bundle_compiler=compile_hybrid_candidate_bundle,
        boundary_reviewer=reviewer,
    )
    assert len(result.units) == 2
    assert len(reviewer.calls) == 1
    assert router.revisions == []


def test_reject_requests_one_correction_and_rechecks_without_more_model_calls():
    router = Router()
    reviewer = Reviewer(("revise", "SPLIT_LOSES_CONTEXT"))
    result = review_router_source_before_writes(
        SOURCE,
        router_proposal(SPLIT_RAW),
        bundle(),
        router=router,
        bundle_compiler=compile_hybrid_candidate_bundle,
        boundary_reviewer=reviewer,
    )
    assert len(result.units) == 1
    assert len(router.revisions) == 1
    assert router.revisions[0][0] == SOURCE
    assert router.revisions[0][1].reason == "SPLIT_LOSES_CONTEXT"
    assert len(reviewer.calls) == 1


def test_repeated_bad_split_is_never_accepted_or_retried_indefinitely():
    router = Router(revised=SPLIT_RAW)
    reviewer = Reviewer(("revise", "SPLIT_LOSES_CONTEXT"), ("revise", "SPLIT_LOSES_CONTEXT"))
    with pytest.raises(SourceBoundaryReviewError, match="REVISION_REQUIRED"):
        review_router_source_before_writes(
            SOURCE,
            router_proposal(SPLIT_RAW),
            bundle(),
            router=router,
            bundle_compiler=compile_hybrid_candidate_bundle,
            boundary_reviewer=reviewer,
        )
    assert len(router.revisions) == 1
    assert len(reviewer.calls) == 2


def test_missing_reviewer_blocks_multiple_routes_before_any_exec():
    with pytest.raises(SourceBoundaryReviewError, match="UNAVAILABLE"):
        review_router_source_before_writes(
            SOURCE,
            router_proposal(SPLIT_RAW),
            bundle(),
            router=Router(),
            bundle_compiler=compile_hybrid_candidate_bundle,
            boundary_reviewer=None,
        )


def test_unresolved_boundary_blocks_before_any_route_execution():
    router = Router()
    reviewer = Reviewer(("needs_attention", "INDEPENDENCE_NOT_PROVEN"))
    with pytest.raises(SourceBoundaryReviewError, match="NEEDS_CLARIFICATION"):
        review_router_source_before_writes(
            SOURCE,
            router_proposal(SPLIT_RAW),
            bundle(),
            router=router,
            bundle_compiler=compile_hybrid_candidate_bundle,
            boundary_reviewer=reviewer,
        )
    assert not router.revisions


def test_stale_review_cannot_authorize_routed_execution():
    class StaleReviewer:
        def review(self, context):
            return replace(
                core_decision(context, "accept"),
                source_digest="f" * 64,
            )

    with pytest.raises(SourceBoundaryReviewError, match="stale"):
        review_router_source_before_writes(
            SOURCE,
            router_proposal(SPLIT_RAW),
            bundle(),
            router=Router(),
            bundle_compiler=compile_hybrid_candidate_bundle,
            boundary_reviewer=StaleReviewer(),
        )


def test_existing_v1_does_not_require_extra_model_call():
    old = FactCandidateProposal(SOURCE, router_proposal(SPLIT_RAW).candidates)
    compiled = compile_hybrid_candidate_bundle(old)
    assert (
        review_router_source_before_writes(
            SOURCE,
            old,
            compiled,
            router=Router(),
            bundle_compiler=compile_hybrid_candidate_bundle,
            boundary_reviewer=None,
        )
        is compiled
    )


@pytest.mark.parametrize("provide_reviewer", [False, True])
def test_dispatcher_blocks_unreviewed_or_disputed_routes_with_zero_mutations(
    tmp_path, provide_reviewer
):
    repository, context_index, semantic_index, embedder = fresh_corpus_vault(tmp_path)
    before = {path: repository.read_text(path) for path in repository.list_markdown_paths()}
    core_planner_calls = []
    router = Router()
    reviewer = Reviewer(("needs_attention", "SPLIT_LOSES_CONTEXT")) if provide_reviewer else None

    def unreachable_planner(*_args):
        core_planner_calls.append(True)
        raise AssertionError("Core planner was called before split review")

    result = execute_candidate_routed_message(
        SOURCE,
        router=router,
        temporal=None,
        core_planner_factory=unreachable_planner,
        candidate_coverage_factory=lambda *_args: None,
        repository=repository,
        schema=SCHEMA,
        context_index=context_index,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="synthetic-boundary-review",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "bounded-boundary-prewrite",
        bundle_compiler=compile_hybrid_candidate_bundle,
        source_boundary_reviewer=reviewer,
    )
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.clarification_code == "CORE_SOURCE_BOUNDARY_REVIEW_REQUIRED"
    assert not core_planner_calls
    assert {path: repository.read_text(path) for path in repository.list_markdown_paths()} == before
    assert not [path for path in repository.list_markdown_paths() if path not in before]
    if provide_reviewer:
        stage = result.operational.stages[0]
        assert stage.name == "candidate.source_boundary_review"
        assert stage.model == "gpt-5.6"
        assert stage.usage == {"input_tokens": 11, "output_tokens": 3}
        assert stage.error_category is None


def test_router_revision_receives_only_typed_bounded_core_feedback():
    import json
    from types import SimpleNamespace

    from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter

    recorded_calls = []

    class FakeClient:
        class Responses:
            def create(self, **kwargs):
                recorded_calls.append(kwargs)
                return SimpleNamespace(
                    status="completed",
                    usage=None,
                    output_text=json.dumps(GROUP_RAW),
                )

        responses = Responses()

    review = core_decision(
        _build_source_context_for_test(),
        "revise",
        "DEPENDENT_SOURCE_FRAGMENT",
    )
    router = OpenAIFactCandidateRouter(FakeClient(), prompt_revision="v6")
    result = router.revise(SOURCE, review)
    assert result.contract_version == 2
    assert len(result.candidates) == 1
    assert len(recorded_calls) == 1
    assert recorded_calls[0]["store"] is False
    assert recorded_calls[0]["input"][1]["content"] == SOURCE
    prompt = recorded_calls[0]["input"][0]["content"]
    assert "DEPENDENT_SOURCE_FRAGMENT" in prompt
    assert review.boundary_index == 1
    assert review.source_digest not in prompt
    assert "canonical_name" not in prompt

    legacy = OpenAIFactCandidateRouter(FakeClient(), prompt_revision="v5")
    with pytest.raises(Exception, match="opt-in"):
        legacy.revise(SOURCE, review)
    with pytest.raises(Exception, match="feedback"):
        router.revise(SOURCE + " amended", review)


def _build_source_context_for_test():
    from odyssey_runtime.candidate_route_dispatch import _build_core_source_boundary_input

    return _build_core_source_boundary_input(SOURCE, router_proposal(SPLIT_RAW), bundle())


def test_router_cannot_change_user_source_after_core_requests_revision():
    router = Router(revised=SPLIT_RAW)

    def forge_revision(source, feedback):
        router.revisions.append((source, feedback))
        return replace(router_proposal(SPLIT_RAW), source="forged different input")

    router.revise = forge_revision
    with pytest.raises(SourceBoundaryReviewError, match="REVISION_INVALID"):
        review_router_source_before_writes(
            SOURCE,
            router_proposal(SPLIT_RAW),
            bundle(),
            router=router,
            bundle_compiler=compile_hybrid_candidate_bundle,
            boundary_reviewer=Reviewer(("revise", "SPLIT_LOSES_CONTEXT")),
        )
    assert len(router.revisions) == 1


def test_reviewer_exception_prevents_core_and_writer_without_second_router_call(tmp_path):
    repository, context_index, semantic_index, embedder = fresh_corpus_vault(tmp_path)
    old_paths = repository.list_markdown_paths()
    old_hashes = {path: repository.read_text(path) for path in old_paths}

    class BrokenReviewer:
        def review(self, _context):
            raise SourceBoundaryReviewError("PROVIDER_RATE_LIMIT")

    router = Router()
    result = execute_candidate_routed_message(
        SOURCE,
        router=router,
        temporal=None,
        core_planner_factory=lambda *_: pytest.fail("Core called despite failed review"),
        candidate_coverage_factory=lambda *_: pytest.fail(
            "Core coverage called despite failed review"
        ),
        repository=repository,
        schema=SCHEMA,
        context_index=context_index,
        semantic_index=semantic_index,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="synthetic-boundary-review",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "review-provider-failure",
        bundle_compiler=compile_hybrid_candidate_bundle,
        source_boundary_reviewer=BrokenReviewer(),
    )
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.affected_stable_note_ids == ()
    assert router.revisions == []
    assert repository.list_markdown_paths() == old_paths
    assert {path: repository.read_text(path) for path in old_paths} == old_hashes
