"""Regression sentinels for arbitrary-length source-grounded corrections."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from odyssey_core.application import ApplicationStatus
from odyssey_core.candidate_context import (
    CoreCandidate,
    CoreCandidateContext,
    CoreCandidateInheritance,
    CoreCandidateRole,
    CoreSourceSpan,
)
from odyssey_core.candidate_coverage import (
    CoreCandidateCoverageClaim,
    build_candidate_coverage_manifest,
)
from odyssey_core.domain_interpretation import DomainEvidence, DomainInterpretation
from odyssey_core.request_planning import KnowledgeUnit, RequestPlan, SelectionCriteria, WriteAction
from odyssey_core.temporal import TemporalAnchor
from odyssey_runtime.candidate_route_dispatch import execute_candidate_routed_message
from odyssey_runtime.hybrid_group_compiler import _needs_joint_interpretation
from tests.runtime.test_candidate_pending_state import NOW
from tests.runtime.test_fact_candidate_semantic_luna_vertical import SCHEMA
from tests.runtime.test_full_message_corpus_regression import fresh_corpus_vault


def _span(source: str, text: str, start: int = 0) -> CoreSourceSpan:
    offset = source.index(text, start)
    return CoreSourceSpan(text, offset, offset + len(text))


def _chain(count: int) -> tuple[str, CoreCandidateContext, DomainInterpretation]:
    pieces = ["Mañana iremos al destino1 a las 9"]
    pieces.extend(
        f"no, mejor al destino{number} a las {number + 8}" for number in range(2, count + 1)
    )
    source = "; ".join(pieces) + "."
    date = _span(source, "Mañana")
    predicate = _span(source, "iremos")
    candidates = []
    evidence = [DomainEvidence("temporal_reference", date.text, "2026-10-05")]
    previous_object = None
    search_from = 0
    for number in range(1, count + 1):
        object_text = f"al destino{number}"
        object_span = _span(source, object_text, search_from)
        time_text = f"a las {9 if number == 1 else number + 8}"
        time_span = _span(source, time_text, object_span.end)
        roles = [CoreCandidateRole("object", object_span), CoreCandidateRole("time", time_span)]
        inherits = []
        if number == 1:
            roles.extend(
                [
                    CoreCandidateRole("predicate", predicate),
                    CoreCandidateRole("date", date),
                    CoreCandidateRole("polarity", _span(source, "no", time_span.end)),
                ]
            )
        else:
            roles.append(CoreCandidateRole("replacement", previous_object))
            inherits.extend(
                [
                    CoreCandidateInheritance("predicate", number - 1),
                    CoreCandidateInheritance("date", number - 1),
                ]
            )
        candidates.append(
            CoreCandidate(
                f"candidate-{number}",
                "occurrence",
                "candidate",
                (object_span,),
                tuple(roles),
                tuple(inherits),
            )
        )
        hour = 9 if number == 1 else number + 8
        evidence.append(
            DomainEvidence("temporal_reference", time_text, f"2026-10-05T{hour:02}:00:00+02:00")
        )
        previous_object = object_span
        search_from = time_span.end
    temporal = DomainInterpretation("temporal", source, "TEMPORAL_RESOLUTION", tuple(evidence))
    context = CoreCandidateContext(
        source,
        tuple(candidates),
        scoped_route_source=True,
        hybrid_interpretation_mode=True,
        verified_correction_temporal=temporal,
    )
    context.validate(source)
    return source, context, temporal


def _plan(count: int) -> RequestPlan:
    hour = 9 if count == 1 else count + 8
    fact = f"Iremos al destino{count} a las {hour:02}:00."
    return RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria(None, "2026-10-05", "calendar_day", (), None),
                        "record",
                        (),
                        (),
                        (fact,),
                        (),
                        fact_temporal_anchors=(
                            (TemporalAnchor.from_value(f"2026-10-05T{hour:02}:00:00+02:00"),),
                        ),
                    ),
                )
            ),
        ),
        (),
    )


def _claims(count: int) -> tuple[CoreCandidateCoverageClaim, ...]:
    return tuple(
        CoreCandidateCoverageClaim(
            f"candidate-{number}",
            "planned_fact" if number == count else "pending",
            fact_ordinal=0 if number == count else None,
            pending_reason=None if number == count else "superseded_by_correction",
        )
        for number in range(1, count + 1)
    )


@pytest.mark.parametrize("count", [2, 3, 5, 9])
def test_linear_correction_chain_accounts_for_every_replaced_candidate(count):
    source, context, _temporal = _chain(count)
    manifest = build_candidate_coverage_manifest(source, context, _plan(count), _claims(count))
    assert [claim.pending_reason for claim in manifest.claims[:-1]] == [
        "superseded_by_correction"
    ] * (count - 1)
    assert manifest.claims[-1].fact_ordinal == 0


def test_correction_chain_rejects_a_skipped_predecessor_or_wrong_replacement_span():
    source, context, _temporal = _chain(3)
    final = context.candidates[-1]
    bad = replace(
        final,
        roles=tuple(
            replace(role, span=context.candidates[0].roles[0].span)
            if role.role == "replacement"
            else role
            for role in final.roles
        ),
    )
    with pytest.raises(ValueError, match="Corrected-plan Temporal proof"):
        replace(context, candidates=(*context.candidates[:-1], bad)).validate(source)


def test_grouping_keeps_each_consecutive_correction_link_in_one_scope():
    _source, context, _temporal = _chain(5)
    assert all(
        _needs_joint_interpretation(left, right)
        for left, right in zip(context.candidates[:-1], context.candidates[1:], strict=True)
    )


def test_three_step_chain_writes_only_final_future_intention(tmp_path):
    source, context, temporal = _chain(3)
    repo, index, semantic, embedder = fresh_corpus_vault(tmp_path)

    class Router:
        def propose(self, received):
            assert received == source
            # The compiler ignores this opaque untrusted proposal and returns
            # the independently source-validated test bundle below.
            from odyssey_apps.fact_candidates import FactCandidateProposal

            return FactCandidateProposal(source, ())

    class BundleCompiler:
        def __call__(self, _proposal):
            from odyssey_apps.router import Route, RouteOutcome, RoutePlan
            from odyssey_runtime.source_scope_compiler import (
                CandidateRouteBundle,
                ScopedCandidateRoute,
            )

            route = Route("temporal", source)
            return CandidateRouteBundle(
                source,
                RoutePlan(RouteOutcome.ROUTE, (route,)),
                (
                    ScopedCandidateRoute(
                        route,
                        context,
                        0,
                        len(source),
                        tuple(c.candidate_id for c in context.candidates),
                    ),
                ),
            )

    class Temporal:
        def interpret(self, received):
            assert received == source
            from odyssey_core.temporal_interpretation import parse_temporal_interpretation

            mentions = [
                {
                    "temporal_text": entry.source_text,
                    "temporal": {
                        "kind": "EXACT_DATE" if "T" not in entry.value else "EXACT_DATETIME",
                        "exact_date": entry.value if "T" not in entry.value else None,
                        "exact_datetime": entry.value if "T" in entry.value else None,
                        "range_start": None,
                        "range_end_exclusive": None,
                    },
                }
                for entry in temporal.temporal_references()
            ]
            return parse_temporal_interpretation(
                {"mentions": mentions}, source, timezone="Europe/Paris"
            )

    def factory(received_context, interpreted):
        assert received_context.verified_correction_temporal == temporal
        assert interpreted == temporal
        return SimpleNamespace(plan=lambda _source: _plan(3))

    def review(received_source, received_context, received_plan, *, canonical_binding=None):
        return build_candidate_coverage_manifest(
            received_source,
            received_context,
            received_plan,
            _claims(3),
            canonical_binding=canonical_binding,
        )

    result = execute_candidate_routed_message(
        source,
        router=Router(),
        temporal=Temporal(),
        core_planner_factory=factory,
        candidate_coverage_factory=review,
        repository=repo,
        schema=SCHEMA,
        context_index=index,
        semantic_index=semantic,
        embedder=embedder,
        contextual_reasoner=object(),
        actor="hybrid-correction-chain",
        now=NOW,
        context_limit=5,
        request_id_factory=lambda: "hybrid-correction-chain-3",
        bundle_compiler=BundleCompiler(),
    )
    assert result.status is not ApplicationStatus.FAILED, result.execution_flow
    day = repo.read_text("calendar/days/2026-10-05.md")
    assert "destino3" in day and "11:00" in day
    assert "destino1" not in day and "destino2" not in day
