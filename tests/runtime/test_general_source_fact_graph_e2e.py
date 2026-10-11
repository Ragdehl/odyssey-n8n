"""General variable candidate↔fact correspondence through the existing Core gate.

Only tests choose the correspondence: Router offers original source roles,
Core offers its independently compiled N facts, and a separate Core review
must explicitly account for EVERY source candidate AND every planned fact.
No product code maps candidate IDs to fact ordinals from their order.
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
from odyssey_runtime.complete_source_handoff import (
    collect_complete_source_evidence,
    execute_complete_source_with_core,
)
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_planning_vertical import _exact_date, _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import CLOCK, SCHEMA


def _fixture(
    count: int,
    *,
    source_candidate_groups: tuple[tuple[int, ...], ...],
    fact_groups: tuple[tuple[int, ...], ...],
):
    """Generate explicit independent N↔M source/fact edges, not language cases.

    The fixture deliberately asks Core to split an ordinary list of purchased
    things, then allows multiple Router spans to support one compiled fact.
    Every word and claimed link remains visible for physical review.
    """
    values = [f"item{chr(97 + i)}" for i in range(count)]
    source = "Hoy compré " + ", ".join(values) + "."
    units = []
    for indices in source_candidate_groups:
        anchor = ", ".join(values[i] for i in indices)
        units.append(
            {
                "kind": "purchase_item",
                "anchors": [{"text": anchor, "occurrence": 0}],
                "scoped_source": [
                    {"role": "object", "anchor": {"text": anchor, "occurrence": 0}},
                ],
                "inheritance": [],
                "state": "candidate",
            }
        )
    # Any fact group can encompass several semantic source objects, and one
    # candidate can support several distinct Core atomic facts.
    facts = [
        {
            "parts": [
                {
                    "kind": "literal",
                    "text": "Compré " + " y ".join(values[i] for i in indices) + ".",
                }
            ]
        }
        for indices in fact_groups
    ]
    raw_router = {"version": 1, "units": units}
    raw_core = {
        "result": {
            "outcome": "PLAN",
            "actions": [
                {
                    "kind": "write",
                    "operations": [
                        {
                            "target": {
                                "description": "2026-10-04",
                                "binding": "described",
                                "direct_name": None,
                                "note_type": "calendar_day",
                                "filters": [],
                                "candidate_scope": None,
                            },
                            "apply_to": "one",
                            "intent": "record",
                            "facts": facts,
                            "properties": [],
                            "tag_changes": [],
                            "destination_type": None,
                        }
                    ],
                }
            ],
            "limitations": [],
            "clarification_code": None,
            "presentation_intent": "answer",
        }
    }
    return source, values, raw_router, raw_core


def _run(tmp_path: Path, configuration, pairs, *, request_id="graph-coverage"):
    source, values, router_raw, core_raw = configuration
    sdk_router, rcalls = _sdk_fake(router_raw)
    sdk_temporal, tcalls = _sdk_fake({"mentions": [_exact_date("Hoy", "2026-10-04")]})
    sdk_core, ccalls = _sdk_fake(core_raw)
    evidence = collect_complete_source_evidence(
        source,
        router=OpenAIFactCandidateRouter(sdk_router, prompt_revision="v3"),
        temporal=OpenAITemporalInterpreter(sdk_temporal, CLOCK),
    )

    def planner_factory(context, domain):
        return OpenAILunaExperimentalPlanner(
            sdk_core,
            SCHEMA,
            CLOCK,
            candidate_context=context,
            domain_interpretation=domain,
        )

    audits = []

    def independent_review(original, context, plan):
        audits.append(plan)
        assert original == source
        claims = tuple(
            CoreCandidateCoverageClaim(
                f"candidate-{i + 1}", "planned_fact", fact_ordinals=tuple(edges)
            )
            for i, edges in enumerate(pairs)
        )
        return build_candidate_coverage_manifest(original, context, plan, claims)

    vault = tmp_path / "vault"
    vault.mkdir()
    repo = VaultRepository(vault)
    result = execute_complete_source_with_core(
        evidence,
        core_planner_factory=planner_factory,
        candidate_coverage_factory=independent_review,
        repository=repo,
        schema=SCHEMA,
        context_index=object(),
        semantic_index=object(),
        embedder=object(),
        contextual_reasoner=object(),
        actor="synthetic-variable-graph",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: request_id,
    )
    assert [len(calls) for calls in (rcalls, tcalls, ccalls)] == [1, 1, 1]
    return result, repo, evidence, audits, independent_review


@pytest.mark.parametrize("count", [2, 3, 5, 8, 13])
def test_one_router_source_unit_may_support_n_distinct_physical_core_facts(
    count: int, tmp_path: Path
):
    item_indices = tuple(range(count))
    configuration = _fixture(
        count,
        source_candidate_groups=(item_indices,),
        fact_groups=tuple((i,) for i in item_indices),
    )
    result, repo, evidence, plans, review = _run(
        tmp_path, configuration, (item_indices,), request_id=f"split-{count}"
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert len(result.action_results) == 1
    assert len(repo.list_markdown_paths()) == 1
    [plan] = plans
    audit = readback_core_facts(configuration[0], evidence.context, plan, result, repo, SCHEMA)
    assert [fact.status for fact in audit.persisted_facts] == ["verified_in_markdown"] * count
    coverage = review_candidate_coverage(
        configuration[0],
        evidence.context,
        plan,
        review(configuration[0], evidence.context, plan),
        audit,
    )
    assert len(coverage.items) == 1
    assert coverage.items[0].fact_ordinals == item_indices
    assert coverage.items[0].status == "physically_written_claim"
    assert not coverage.candidate_semantics_verified
    assert not coverage.safe_to_report_all_candidates_complete


@pytest.mark.parametrize("count", [2, 3, 5, 8])
def test_n_router_source_units_may_support_one_physical_core_fact(count: int, tmp_path: Path):
    item_indices = tuple(range(count))
    configuration = _fixture(
        count,
        source_candidate_groups=tuple((i,) for i in item_indices),
        fact_groups=(item_indices,),
    )
    result, repo, evidence, plans, review = _run(
        tmp_path, configuration, tuple((0,) for _ in item_indices)
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert len(repo.list_markdown_paths()) == 1
    [plan] = plans
    audit = readback_core_facts(configuration[0], evidence.context, plan, result, repo, SCHEMA)
    coverage = review_candidate_coverage(
        configuration[0],
        evidence.context,
        plan,
        review(configuration[0], evidence.context, plan),
        audit,
    )
    assert len(audit.persisted_facts) == 1
    assert len(coverage.items) == count
    assert all(item.fact_ordinals == (0,) for item in coverage.items)
    assert all(item.status == "physically_written_claim" for item in coverage.items)
    assert not coverage.candidate_semantics_verified


@pytest.mark.parametrize("count", [3, 5, 8])
def test_variable_mixed_source_to_fact_cardinalities_without_count_assumptions(
    count: int, tmp_path: Path
):
    indices = tuple(range(count))
    # The first source candidate covers two independently recorded objects;
    # two others contribute jointly to one preserved physical fact; the rest
    # are independent. This is generated for all tested source sizes.
    groups = ((0, 1), *((i,) for i in indices[2:]))
    fact_groups = ((0,), (1,), (2, 3)) if count >= 4 else ((0,), (1,), (2,))
    if count >= 4:
        fact_groups += tuple((i,) for i in indices[4:])
        pairs = ((0, 1), (2,), (2,), *((i - 1,) for i in indices[4:]))
    else:
        pairs = ((0, 1), (2,))
    configuration = _fixture(count, source_candidate_groups=groups, fact_groups=fact_groups)
    result, repo, evidence, plans, _ = _run(tmp_path, configuration, pairs)
    assert result.status is ApplicationStatus.COMPLETED
    [plan] = plans
    audit = readback_core_facts(configuration[0], evidence.context, plan, result, repo, SCHEMA)
    assert len(audit.persisted_facts) == len(fact_groups)
    assert all(fact.status == "verified_in_markdown" for fact in audit.persisted_facts)


@pytest.mark.parametrize(
    "case",
    [
        "missing_claim",
        "wrong_source",
        "duplicate_edge",
        "invented_fact",
        "bool_fact",
        "empty_edges",
        "reused_unwarranted_fact",
    ],
)
def test_unproven_correspondence_is_rejected_before_any_real_write(tmp_path, case):
    configuration = _fixture(
        3,
        source_candidate_groups=((0,), (1,), (2,)),
        fact_groups=((0,), (1,), (2,)),
    )
    valid = [(0,), (1,), (2,)]
    if case == "missing_claim":
        valid = valid[:-1]
    elif case == "wrong_source":
        valid[0] = (1,)
    elif case == "duplicate_edge":
        valid[0] = (0, 0)
    elif case == "invented_fact":
        valid[1] = (99,)
    elif case == "bool_fact":
        valid[1] = (True,)
    elif case == "empty_edges":
        valid[1] = ()
    elif case == "reused_unwarranted_fact":
        valid[0] = (0, 1)
    result, repo, *_ = _run(tmp_path, configuration, valid)
    assert result.status is ApplicationStatus.NEEDS_ATTENTION
    assert result.clarification_code == "CANDIDATE_COVERAGE_REVIEW_REQUIRED"
    assert result.action_results == ()
    assert repo.list_markdown_paths() == []


def test_one_corrupt_fact_does_not_mark_whole_multi_fact_candidate_written(tmp_path):
    configuration = _fixture(
        3,
        source_candidate_groups=((0, 1, 2),),
        fact_groups=((0,), (1,), (2,)),
    )
    result, repo, evidence, plans, review = _run(tmp_path, configuration, ((0, 1, 2),))
    assert result.status is ApplicationStatus.COMPLETED
    [plan] = plans
    [path] = repo.list_markdown_paths()
    file = repo.root / path
    text = file.read_text()
    file.write_text(text.replace("ordinal=1 recorded_at=", "ordinal=99 recorded_at="))
    audit = readback_core_facts(configuration[0], evidence.context, plan, result, repo, SCHEMA)
    coverage = review_candidate_coverage(
        configuration[0],
        evidence.context,
        plan,
        review(configuration[0], evidence.context, plan),
        audit,
    )
    assert [fact.status for fact in audit.persisted_facts] == [
        "verified_in_markdown",
        "not_verified",
        "verified_in_markdown",
    ]
    assert coverage.items[0].status == "planned_unverified"
    assert coverage.pending_candidate_ids == ("candidate-1",)
    assert not coverage.safe_to_report_all_candidates_complete


@pytest.mark.parametrize("case_id", ["F17", "F20"])
def test_sensitive_negative_or_conditional_scope_does_not_gain_graph_write_authority(
    case_id, tmp_path
):
    from tests.runtime.test_fact_candidate_provenance_readback import _two_items
    from tests.runtime.test_fact_candidate_writes_e2e import _case

    case, context = _case(case_id)
    claims = tuple(
        CoreCandidateCoverageClaim(candidate.candidate_id, "planned_fact", fact_ordinals=(index,))
        for index, candidate in enumerate(context.candidates)
    )
    with pytest.raises(ValueError, match="Sensitive scoped fact"):
        build_candidate_coverage_manifest(case["source"], context, _two_items(), claims)
    assert list(tmp_path.iterdir()) == []


def test_ambiguous_pronoun_remains_pending_under_explicit_graph_claims():
    from dataclasses import replace

    from odyssey_core.request_planning import RequestPlan, WriteAction
    from tests.runtime.test_fact_candidate_writes_e2e import _case
    from tests.runtime.test_temporal_user_path_e2e import _day_plan

    case, context = _case("F27")
    original = _day_plan("2026-10-03", "Hablé con Eric.", "2026-10-03")
    unit = original.actions[0].units[0]
    compiled = replace(
        unit,
        facts=("Hablé con Eric.", "Hablé con Luis."),
        fact_temporal_anchors=unit.fact_temporal_anchors * 2,
    )
    plan = RequestPlan((WriteAction((compiled,)),), ())
    claims = (
        CoreCandidateCoverageClaim("candidate-1", "planned_fact", fact_ordinals=(0,)),
        CoreCandidateCoverageClaim("candidate-2", "planned_fact", fact_ordinals=(1,)),
        CoreCandidateCoverageClaim("candidate-3", "pending", pending_reason="ambiguous_identity"),
    )
    manifest = build_candidate_coverage_manifest(case["source"], context, plan, claims)
    assert manifest.claims[2].disposition == "pending"
    with pytest.raises(ValueError, match="Ambiguous identity"):
        build_candidate_coverage_manifest(
            case["source"],
            context,
            plan,
            (
                claims[0],
                claims[1],
                CoreCandidateCoverageClaim("candidate-3", "planned_fact", fact_ordinals=(0,)),
            ),
        )


def test_graph_review_does_not_fake_canonical_people_binding():
    from tests.runtime.test_fact_candidate_semantic_luna_vertical import _pipeline

    case, context, _scope, planner, _calls = _pipeline()
    plan = planner.plan(case["source"])
    graph = (
        CoreCandidateCoverageClaim("candidate-1", "planned_fact", fact_ordinals=(0,)),
        CoreCandidateCoverageClaim("candidate-2", "pending", pending_reason="ambiguous_identity"),
    )
    with pytest.raises(ValueError, match="reviewed identity provenance"):
        build_candidate_coverage_manifest(case["source"], context, plan, graph)
