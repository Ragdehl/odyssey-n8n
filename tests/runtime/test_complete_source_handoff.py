"""Generic whole-message Router/Temporal->ordinary Core handoff regressions.

These tests deliberately vary candidate counts, kinds, punctuation, role
inheritance and the ratio of Router units to Core writes. No phrasing- or
example-ID-based code may live in the source handoff itself.
"""

from __future__ import annotations

import pytest

from odyssey_apps.fact_candidates import OpenAIFactCandidateRouter
from odyssey_core.candidate_dependencies import CandidateDependencyError
from odyssey_core.experimental_luna_planning import OpenAILunaExperimentalPlanner, PlannerEscalation
from odyssey_core.request_planning import RequestPlan
from odyssey_core.temporal_interpretation import OpenAITemporalInterpreter
from odyssey_runtime.complete_source_handoff import (
    collect_complete_source_evidence,
    plan_complete_source_with_core,
)
from tests.apps.test_fact_candidates import CASES, _from_design
from tests.runtime.test_fact_candidate_planning_vertical import CLOCK, _exact_date, _sdk_fake
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA


def _arbitrary_proposal(count: int, *, shared_subject: bool = False):
    """Create genuinely distinct source spans without hardcoding case sentences."""
    parts = [f"Entidad_{i} registra hecho_{i}" for i in range(count)]
    source = " ; ".join(parts)
    units = []
    for i in range(count):
        units.append(
            {
                "kind": ("occurrence", "property", "task")[i % 3],
                "anchors": [{"text": f"hecho_{i}", "occurrence": 0}],
                "scoped_source": [
                    {"role": "object", "anchor": {"text": f"hecho_{i}", "occurrence": 0}},
                    *(
                        [{"role": "subject", "anchor": {"text": f"Entidad_{i}", "occurrence": 0}}]
                        if not shared_subject or i == 0
                        else []
                    ),
                ],
                "inheritance": [{"role": "subject", "from_unit": i}]
                if shared_subject and i
                else [],
                "state": "candidate",
            }
        )
    return source, {"version": 1, "units": units}


@pytest.mark.parametrize("count", [1, 2, 3, 5, 8, 13, 26])
def test_entire_source_all_units_and_a_single_core_plan_no_one_fact_per_candidate(count):
    source, raw = _arbitrary_proposal(count)
    sdk, router_calls = _sdk_fake(raw)
    packet = collect_complete_source_evidence(
        source, router=OpenAIFactCandidateRouter(sdk, prompt_revision="v3")
    )
    assert len(packet.context.candidates) == count
    assert len(packet.dependency_trace) == count
    assert all(
        unit.candidate_id == f"candidate-{i + 1}" for i, unit in enumerate(packet.dependency_trace)
    )
    assert packet.source == source
    assert all(item.span.text in source for unit in packet.dependency_trace for item in unit.roles)
    assert packet.temporal_interpretation is None
    assert packet.domain_interpretation is None
    assert len(router_calls) == 1

    # Router candidates DO NOT imply a fixed number of actions or facts.
    core_calls = []
    result = RequestPlan((), ())

    class ExistingCore:
        def plan(self, request):
            core_calls.append(request)
            return result

    def factory(context, domain):
        assert context is packet.context and domain is None
        return ExistingCore()

    assert plan_complete_source_with_core(packet, core_planner_factory=factory) is result
    assert core_calls == [source]  # Not a separately scoped mini-request.


@pytest.mark.parametrize("count", [3, 5, 8])
def test_inherited_roles_are_transitive_without_changing_original_source(count):
    source, raw = _arbitrary_proposal(count, shared_subject=True)
    sdk, _ = _sdk_fake(raw)
    packet = collect_complete_source_evidence(
        source, router=OpenAIFactCandidateRouter(sdk, prompt_revision="v3")
    )
    for index, unit in enumerate(packet.dependency_trace):
        subjects = unit.for_role("subject")
        assert len(subjects) == 1
        assert subjects[0].span.text == "Entidad_0"
        assert subjects[0].source_candidate_id == "candidate-1"
        assert subjects[0].inherited == (index != 0)


def test_three_independent_dates_are_resolved_even_with_anaphoric_reference():
    original = next(item for item in CASES if item["id"] == "F13")
    source = original["source"]
    router_sdk, router_calls = _sdk_fake(_from_design(original))
    temporal_sdk, temporal_calls = _sdk_fake(
        {
            "mentions": [
                _exact_date("Ayer", "2026-10-08"),
                _exact_date("Mañana", "2026-10-10"),
                _exact_date("Hoy", "2026-10-09"),
            ]
        }
    )
    evidence = collect_complete_source_evidence(
        source,
        router=OpenAIFactCandidateRouter(router_sdk, prompt_revision="v3"),
        temporal=OpenAITemporalInterpreter(temporal_sdk, CLOCK),
    )
    assert len(evidence.context.candidates) == len(evidence.dependency_trace) == 3
    assert [item.resolution.exact_date for item in evidence.temporal_bindings] == [
        "2026-10-08",
        "2026-10-10",
        "2026-10-09",
    ]
    assert len(evidence.domain_interpretation.evidence) == 3
    assert len(evidence.dependency_trace[1].unresolved_references) == 1
    assert len(router_calls) == len(temporal_calls) == 1
    core_sdk, core_calls = _sdk_fake(
        {
            "result": {
                "outcome": "ESCALATE",
                "actions": None,
                "limitations": None,
                "clarification_code": None,
            }
        }
    )
    result = plan_complete_source_with_core(
        evidence,
        core_planner_factory=lambda context, domain: OpenAILunaExperimentalPlanner(
            core_sdk, SCHEMA, CLOCK, candidate_context=context, domain_interpretation=domain
        ),
    )
    assert isinstance(result, PlannerEscalation)
    assert len(core_calls) == 1
    assert core_calls[0]["input"][1]["content"] == source
    system_payload = str(core_calls[0]["input"][0]["content"])
    assert "candidate-3" in system_payload
    assert "2026-10-10" in system_payload


def test_temporal_runs_independently_even_if_router_did_not_propose_a_date_role():
    source, raw = _arbitrary_proposal(1)
    source += " mañana"
    router_sdk, _ = _sdk_fake(raw)
    temporal_sdk, calls = _sdk_fake({"mentions": [_exact_date("mañana", "2026-10-10")]})
    evidence = collect_complete_source_evidence(
        source,
        router=OpenAIFactCandidateRouter(router_sdk, prompt_revision="v3"),
        temporal=OpenAITemporalInterpreter(temporal_sdk, CLOCK),
    )
    assert len(calls) == 1
    assert evidence.temporal_bindings == ()
    assert [item.value for item in evidence.domain_interpretation.evidence] == ["2026-10-10"]


def test_unresolvable_inherited_role_fails_before_a_core_plan():
    source, raw = _arbitrary_proposal(3, shared_subject=True)
    raw["units"][0]["scoped_source"] = [
        role for role in raw["units"][0]["scoped_source"] if role["role"] != "subject"
    ]
    sdk, _ = _sdk_fake(raw)
    with pytest.raises(CandidateDependencyError, match="no evidence"):
        collect_complete_source_evidence(
            source, router=OpenAIFactCandidateRouter(sdk, prompt_revision="v3")
        )


def test_mismatched_temporal_source_cannot_be_passed_to_core():
    source, raw = _arbitrary_proposal(2)
    router_sdk, _ = _sdk_fake(raw)
    temporal_sdk, _ = _sdk_fake({"mentions": [_exact_date("hoy", "2026-10-09")]})
    with pytest.raises(ValueError):
        collect_complete_source_evidence(
            source,
            router=OpenAIFactCandidateRouter(router_sdk, prompt_revision="v3"),
            temporal=OpenAITemporalInterpreter(temporal_sdk, CLOCK),
        )


def test_core_does_not_need_one_action_per_source_candidate():
    source, raw = _arbitrary_proposal(5)
    sdk, _ = _sdk_fake(raw)
    packet = collect_complete_source_evidence(
        source, router=OpenAIFactCandidateRouter(sdk, prompt_revision="v3")
    )
    from odyssey_core.request_planning import WriteAction

    results = [
        RequestPlan((), ()),
        RequestPlan((WriteAction(()),), ()),
        RequestPlan((WriteAction(()), WriteAction(()), WriteAction(())), ()),
    ]
    for result in results:
        core_calls = []

        class ExistingCore:
            def __init__(self, answer, calls):
                self.answer = answer
                self.calls = calls

            def plan(self, request):
                self.calls.append(request)
                return self.answer

        def make_core(_context, _domain, answer=result, calls=core_calls):
            return ExistingCore(answer, calls)

        assert plan_complete_source_with_core(packet, core_planner_factory=make_core) == result
        assert core_calls == [source]


def test_router_output_has_no_mutation_authority():
    source, raw = _arbitrary_proposal(5)
    sdk, _ = _sdk_fake(raw)
    packet = collect_complete_source_evidence(
        source, router=OpenAIFactCandidateRouter(sdk, prompt_revision="v3")
    )
    assert not hasattr(packet, "execute")
    assert not hasattr(packet, "write")
    assert not any(hasattr(unit, "note_type") for unit in packet.context.candidates)


@pytest.mark.parametrize("count", [1, 3, 5, 8, 13])
def test_full_source_reaches_normal_core_and_persists_n_atomic_facts(count, tmp_path):
    """One Core action writes N independent source facts; no two-fact path.

    Provider-model interpretation is synthetic. The *normal* Core write,
    identity/day selection, original-source coverage and Markdown readback
    are real and disposable. Source coverage does not assert semantic truth.
    """
    from dataclasses import replace

    from odyssey_core.application import ApplicationStatus
    from odyssey_core.candidate_coverage import (
        CoreCandidateCoverageClaim,
        build_candidate_coverage_manifest,
        review_candidate_coverage,
    )
    from odyssey_core.candidate_fact_readback import readback_core_facts
    from odyssey_core.request_planning import WriteAction
    from tests.runtime.test_fact_candidate_coverage_gate import _run
    from tests.runtime.test_temporal_user_path_e2e import _day_plan

    objects = [f"item{chr(ord('a') + index)}" for index in range(count)]
    source = "Hoy " + "; ".join(f"compré {word}" for word in objects) + "."
    raw = {
        "version": 1,
        "units": [
            {
                "kind": "purchase_item",
                "anchors": [{"text": word, "occurrence": 0}],
                "scoped_source": [
                    {"role": "object", "anchor": {"text": word, "occurrence": 0}},
                    *(
                        [{"role": "date", "anchor": {"text": "Hoy", "occurrence": 0}}]
                        if index == 0
                        else []
                    ),
                ],
                "inheritance": [{"role": "date", "from_unit": 1}] if index else [],
                "state": "candidate",
            }
            for index, word in enumerate(objects)
        ],
    }
    router_sdk, router_calls = _sdk_fake(raw)
    temporal_sdk, temporal_calls = _sdk_fake({"mentions": [_exact_date("Hoy", "2026-10-04")]})
    evidence = collect_complete_source_evidence(
        source,
        router=OpenAIFactCandidateRouter(router_sdk, prompt_revision="v3"),
        temporal=OpenAITemporalInterpreter(temporal_sdk, CLOCK),
    )
    assert len(evidence.context.candidates) == count
    assert len(evidence.temporal_bindings) == count
    assert all(
        edge.status == "matched" and edge.resolution.exact_date == "2026-10-04"
        for edge in evidence.temporal_bindings
    )
    base = _day_plan("2026-10-04", f"Compré {objects[0]}.", "2026-10-04")
    unit = base.actions[0].units[0]
    adapted = replace(
        unit,
        facts=tuple(f"Compré {word}." for word in objects),
        fact_temporal_anchors=unit.fact_temporal_anchors * count,
    )
    normal_core_plan = RequestPlan((WriteAction((adapted,)),), ())
    core_calls = []

    class OrdinaryCore:
        def plan(self, request):
            core_calls.append(request)
            return normal_core_plan

    assert (
        plan_complete_source_with_core(
            evidence, core_planner_factory=lambda context, domain: OrdinaryCore()
        )
        is normal_core_plan
    )
    assert core_calls == [source]
    claims = tuple(
        CoreCandidateCoverageClaim(f"candidate-{index + 1}", "planned_fact", index)
        for index in range(count)
    )

    def independently_reviewed(original, context, plan):
        return build_candidate_coverage_manifest(original, context, plan, claims)

    result, repository = _run(
        tmp_path,
        source,
        evidence.context,
        normal_core_plan,
        independently_reviewed,
    )
    assert result.status is ApplicationStatus.COMPLETED
    assert len(result.action_results) == 1
    assert len(repository.list_markdown_paths()) == 1
    readback = readback_core_facts(
        source, evidence.context, normal_core_plan, result, repository, SCHEMA
    )
    assert len(readback.persisted_facts) == count
    assert all(fact.status == "verified_in_markdown" for fact in readback.persisted_facts)
    review = review_candidate_coverage(
        source,
        evidence.context,
        normal_core_plan,
        independently_reviewed(source, evidence.context, normal_core_plan),
        readback,
    )
    assert len(review.items) == count
    assert not review.candidate_semantics_verified
    assert not review.safe_to_report_all_candidates_complete
    assert len(router_calls) == len(temporal_calls) == 1


def test_original_temporal_roles_and_normalized_values_cannot_be_forged_after_handoff():
    from dataclasses import replace

    source, raw = _arbitrary_proposal(3)
    source = "Hoy " + source
    raw["units"][0]["scoped_source"].append(
        {"role": "date", "anchor": {"text": "Hoy", "occurrence": 0}}
    )
    router_sdk, _ = _sdk_fake(raw)
    temporal_sdk, _ = _sdk_fake({"mentions": [_exact_date("Hoy", "2026-10-09")]})
    packet = collect_complete_source_evidence(
        source,
        router=OpenAIFactCandidateRouter(router_sdk, prompt_revision="v3"),
        temporal=OpenAITemporalInterpreter(temporal_sdk, CLOCK),
    )
    assert len(packet.temporal_bindings) == 1
    original_binding = packet.temporal_bindings[0]
    for mutated in (
        replace(packet, temporal_bindings=()),
        replace(
            packet,
            temporal_bindings=(replace(original_binding, candidate_id="candidate-2"),),
        ),
        replace(
            packet,
            temporal_bindings=(replace(original_binding, temporal_text="Mañana"),),
        ),
        replace(packet, domain_interpretation=None),
    ):
        with pytest.raises(ValueError):
            plan_complete_source_with_core(
                mutated,
                core_planner_factory=lambda *_: pytest.fail(
                    "Changed Router or Temporal evidence must never reach Core"
                ),
            )


def test_router_claims_a_time_but_missing_temporal_capability_does_not_continue():
    source, raw = _arbitrary_proposal(1)
    source = "Hoy " + source
    raw["units"][0]["scoped_source"].append(
        {"role": "date", "anchor": {"text": "Hoy", "occurrence": 0}}
    )
    router_sdk, _ = _sdk_fake(raw)
    with pytest.raises(ValueError, match="Temporal interpreter"):
        collect_complete_source_evidence(
            source,
            router=OpenAIFactCandidateRouter(router_sdk, prompt_revision="v3"),
        )
