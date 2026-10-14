"""DEV regression: bare modifiers require source cohesion; purpose remains under review.

All candidates and substrings are synthetic. The production compiler is tested
with immutable source provenance; no providers, network or vault writes.
"""

from odyssey_apps.fact_candidates import (
    FactCandidate,
    FactCandidateProposal,
    SourceAnchor,
    SourceRole,
)
from odyssey_runtime.hybrid_group_compiler import compile_hybrid_candidate_bundle


def _span(source: str, text: str) -> SourceAnchor:
    start = source.index(text)
    return SourceAnchor(text, 0, start, start + len(text))


def _unit(
    source: str,
    ordinal: int,
    kind: str,
    anchor: str,
    roles: tuple[tuple[str, str], ...] = (),
) -> FactCandidate:
    return FactCandidate(
        f"candidate-{ordinal}",
        kind,
        (_span(source, anchor),),
        tuple(SourceRole(role, _span(source, text)) for role, text in roles),
        (),
        "candidate",
    )


def test_bare_modifier_requires_shared_source_review_without_absorbing_a_predicate() -> None:
    source = "Hoy he comido una pera roja para probar el indicador de progreso de Odyssey."
    proposal = FactCandidateProposal(
        source,
        (
            _unit(
                source,
                1,
                "occurrence",
                "Hoy he comido una pera",
                (("date", "Hoy"), ("predicate", "comido"), ("object", "una pera")),
            ),
            _unit(source, 2, "property", "roja", (("object", "roja"),)),
            _unit(
                source,
                3,
                "occurrence",
                "probar el indicador de progreso",
                (("predicate", "probar"), ("object", "el indicador de progreso")),
            ),
        ),
    )
    bundle = compile_hybrid_candidate_bundle(proposal)
    # The adjective is an unproven standalone assertion. The third candidate
    # does have its own lexical predicate, so its purpose/independence needs
    # further semantic review rather than being inferred from this guard.
    assert len(bundle.units) == 2
    assert bundle.units[0].original_candidate_ids == ("candidate-1", "candidate-2")
    assert bundle.units[1].original_candidate_ids == ("candidate-3",)
    assert "".join(unit.route.source_text for unit in bundle.units) == source


def test_distinct_sentences_remain_independent_without_date_roles() -> None:
    source = "Compré pan. Llamé al banco."
    proposal = FactCandidateProposal(
        source,
        (
            _unit(source, 1, "purchase_item", "Compré pan", (("predicate", "Compré"),)),
            _unit(source, 2, "occurrence", "Llamé al banco", (("predicate", "Llamé"),)),
        ),
    )
    bundle = compile_hybrid_candidate_bundle(proposal)
    assert len(bundle.units) == 2
    assert "".join(u.route.source_text for u in bundle.units) == source


def test_task_lifecycle_routes_are_never_generic_core_merged() -> None:
    source = "Enviar informe y llamar al banco."
    proposal = FactCandidateProposal(
        source,
        (
            _unit(source, 1, "task", "Enviar informe", (("predicate", "Enviar"),)),
            _unit(source, 2, "task", "llamar al banco", (("predicate", "llamar"),)),
        ),
    )
    bundle = compile_hybrid_candidate_bundle(proposal, enable_tasks=True)
    assert [r.capability_id for r in bundle.plan.routes] == ["tasks", "tasks"]
