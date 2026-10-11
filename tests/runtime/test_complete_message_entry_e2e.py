"""One raw message -> Router -> independent Temporal -> Core -> Writer -> readback.

Generated source/fact graphs vary in size and correspondence; this is
contract/mechanical validation with provider-shaped fake SDK responses,
NOT proof of linguistic model correctness or authorization to activate chat.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
    review_candidate_coverage,
)
from odyssey_core.candidate_fact_readback import readback_core_facts
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner
from odyssey_core.storage import VaultRepository
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.complete_source_handoff import execute_complete_message_with_core
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_planning_vertical import _exact_date, _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA
from tests.runtime.test_general_source_fact_graph_e2e import _fixture


def _configuration(count: int, shape: str):
    """Specify independent N:M correspondences without app-side language rules."""
    indexes = tuple(range(count))
    if shape == "one_to_many":
        candidates = (indexes,)
        facts = tuple((i,) for i in indexes)
        edges = (indexes,)
    elif shape == "many_to_one":
        candidates = tuple((i,) for i in indexes)
        facts = (indexes,)
        edges = tuple((0,) for _ in indexes)
    elif shape == "mixed":
        candidates = ((0, 1), *((i,) for i in indexes[2:]))
        facts = ((0,), (1,), (2, 3), *((i,) for i in indexes[4:]))
        edges = ((0, 1), (2,), (2,), *((i - 1,) for i in indexes[4:]))
    else:
        raise AssertionError("Test configuration is invalid")
    return _fixture(count, source_candidate_groups=candidates, fact_groups=facts), edges


def _run_message(tmp_path: Path, count: int, shape: str, *, review_mode="valid"):
    """Use the complete inbound-message interface with every real local adapter."""
    (source, _values, raw_router, raw_core), edges = _configuration(count, shape)
    router_sdk, router_calls = _sdk_fake(raw_router)
    temporal_sdk, temporal_calls = _sdk_fake({"mentions": [_exact_date("Hoy", "2026-10-04")]})
    core_sdk, core_calls = _sdk_fake(raw_core)
    order = []
    for name, sdk in (
        ("router", router_sdk),
        ("temporal", temporal_sdk),
        ("core", core_sdk),
    ):
        original = sdk.responses.create

        def capture(_original=original, _name=name, **request):
            order.append(_name)
            return _original(**request)

        sdk.responses.create = capture

    plans = []
    domains = []

    def planner_factory(context, domain):
        domains.append(domain)
        return OpenAILunaExperimentalPlanner(
            core_sdk, SCHEMA, CLOCK, candidate_context=context, domain_interpretation=domain
        )

    def reviewer(original, context, plan):
        order.append("coverage")
        plans.append((original, context, plan))
        assert original == source
        current = edges
        if review_mode == "missing":
            current = edges[:-1]
        claims = tuple(
            CoreCandidateCoverageClaim(
                f"candidate-{i + 1}", "planned_fact", fact_ordinals=tuple(indices)
            )
            for i, indices in enumerate(current)
        )
        return build_candidate_coverage_manifest(original, context, plan, claims)

    vault = tmp_path / "vault"
    vault.mkdir()
    repo = VaultRepository(vault)
    result = execute_complete_message_with_core(
        source,
        router=OpenAIFactCandidateRouter(router_sdk, prompt_revision="v3"),
        temporal=OpenAITemporalInterpreter(temporal_sdk, CLOCK),
        core_planner_factory=planner_factory,
        candidate_coverage_factory=reviewer if review_mode != "absent" else None,
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="isolated-general-message-ingress",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: f"complete-message-{count}-{shape}",
    )
    assert [len(calls) for calls in (router_calls, temporal_calls)] == [1, 1]
    assert router_calls[0]["input"][1]["content"] == source
    assert temporal_calls[0]["input"][1]["content"] == source
    # Router never identified a date role in these varied original-source
    # graphs. Temporal nevertheless ran independently on the whole message.
    assert all(
        not any(role["role"] == "date" for role in unit["scoped_source"])
        for unit in raw_router["units"]
    )
    if review_mode != "absent":
        assert len(core_calls) == 1
        assert core_calls[0]["input"][1]["content"] == source
        assert core_calls[0]["model"] == "gpt-5.6-luna"
        assert domains and domains[0] is not None
        assert order == ["router", "temporal", "core", "coverage"]
    else:
        assert not core_calls
        assert order == ["router", "temporal"]
    return result, repo, plans, edges, source


@pytest.mark.parametrize(
    "shape,count",
    [
        ("one_to_many", 2),
        ("one_to_many", 3),
        ("one_to_many", 5),
        ("one_to_many", 8),
        ("one_to_many", 13),
        ("many_to_one", 2),
        ("many_to_one", 3),
        ("many_to_one", 5),
        ("many_to_one", 8),
        ("mixed", 5),
        ("mixed", 8),
    ],
)
def test_complete_raw_message_variable_graph_persists_and_reads_all_core_facts(
    tmp_path: Path, shape: str, count: int
):
    result, repo, plans, edges, source = _run_message(tmp_path, count, shape)
    assert result.status is ApplicationStatus.COMPLETED
    assert len(repo.list_markdown_paths()) == 1
    [(original, context, plan)] = plans
    assert original == source
    readback = readback_core_facts(source, context, plan, result, repo, SCHEMA)
    assert len(readback.persisted_facts) == len({n for group in edges for n in group})
    assert all(item.status == "verified_in_markdown" for item in readback.persisted_facts)
    manifest = build_candidate_coverage_manifest(
        source,
        context,
        plan,
        tuple(
            CoreCandidateCoverageClaim(
                f"candidate-{i + 1}", "planned_fact", fact_ordinals=tuple(facts)
            )
            for i, facts in enumerate(edges)
        ),
    )
    review = review_candidate_coverage(source, context, plan, manifest, readback)
    assert review.fully_accounted_for_structurally
    assert not review.candidate_semantics_verified
    assert not review.safe_to_report_all_candidates_complete


@pytest.mark.parametrize("shape,count", [("one_to_many", 3), ("many_to_one", 5), ("mixed", 8)])
def test_complete_raw_message_invalid_or_absent_coverage_never_writes(
    tmp_path: Path, shape: str, count: int
):
    mode = "absent" if shape == "one_to_many" else "missing"
    if mode == "absent":
        with pytest.raises(ValueError, match="coverage review required"):
            _run_message(tmp_path, count, shape, review_mode=mode)
        assert list((tmp_path / "vault").glob("**/*.md")) == []
    else:
        result, repo, _plans, _edges, _source = _run_message(
            tmp_path, count, shape, review_mode=mode
        )
        assert result.status is ApplicationStatus.NEEDS_ATTENTION
        assert result.clarification_code == "CANDIDATE_COVERAGE_REVIEW_REQUIRED"
        assert repo.list_markdown_paths() == []


@pytest.mark.parametrize("failed_boundary", ["router", "temporal", "planner"])
def test_complete_raw_message_provider_failure_stops_before_any_markdown(
    tmp_path: Path, failed_boundary: str
):
    """Contract failures cannot be rescued by later stages or partial writes."""
    from odyssey_apps.router import RouterError
    from odyssey_core.temporal_interpretation import TemporalInterpreterError

    (source, _values, router_result, core_result), _edges = _configuration(3, "one_to_many")
    temporal_result = {"mentions": [_exact_date("Hoy", "2026-10-04")]}
    if failed_boundary == "router":
        router_result["units"][0]["anchors"][0]["text"] = "absent-source-anchor"
    elif failed_boundary == "temporal":
        temporal_result = {"mentions": [_exact_date("absent-date-span", "2026-10-04")]}
    else:
        core_result = {
            "result": {
                "outcome": "INVALID",
                "actions": None,
                "limitations": None,
                "clarification_code": None,
            }
        }
    router_sdk, router_calls = _sdk_fake(router_result)
    temporal_sdk, temporal_calls = _sdk_fake(temporal_result)
    core_sdk, core_calls = _sdk_fake(core_result)
    vault = tmp_path / "vault"
    vault.mkdir()
    repo = VaultRepository(vault)

    def planner_factory(context, domain):
        return OpenAILunaExperimentalPlanner(
            core_sdk, SCHEMA, CLOCK, candidate_context=context, domain_interpretation=domain
        )

    def reviewer(*_):
        pytest.fail("Invalid planner output cannot reach source coverage")

    def run():
        return execute_complete_message_with_core(
            source,
            router=OpenAIFactCandidateRouter(router_sdk, prompt_revision="v3"),
            temporal=OpenAITemporalInterpreter(temporal_sdk, CLOCK),
            core_planner_factory=planner_factory,
            candidate_coverage_factory=reviewer,
            repository=repo,
            schema=SCHEMA,
            context_index=object(),
            semantic_index=object(),
            embedder=object(),
            contextual_reasoner=object(),
            actor="failure-closed-verification",
            now=NOW,
            context_limit=5,
            request_id_factory=lambda: "source-boundary-failure",
        )

    if failed_boundary == "router":
        with pytest.raises(RouterError):
            run()
        assert [len(router_calls), len(temporal_calls), len(core_calls)] == [1, 0, 0]
    elif failed_boundary == "temporal":
        with pytest.raises(TemporalInterpreterError):
            run()
        assert [len(router_calls), len(temporal_calls), len(core_calls)] == [1, 1, 0]
    else:
        result = run()
        assert result.status is ApplicationStatus.FAILED
        assert [len(router_calls), len(temporal_calls), len(core_calls)] == [1, 1, 1]
    assert repo.list_markdown_paths() == []
