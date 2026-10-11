"""Verified real Router F23/F26 source segmentation, never executable directly."""

from __future__ import annotations

from dataclasses import replace

import pytest

from benchmarks.fact_candidate_core_live.legacy_dependent_scope import (
    CoreDependentScopeError,
    preview_dependent_clause_scopes,
)
from tests.core.test_candidate_dependencies_observed import _observed


@pytest.mark.parametrize("case_id", ("F23", "F26"))
def test_two_distinct_scopes_with_unmodified_linguistic_context(case_id):
    source, context = _observed(case_id)
    preview = preview_dependent_clause_scopes(source, context)
    assert not preview.executable
    assert len(preview.units) == 2
    assert preview.units[0].full_source_digest == preview.units[1].full_source_digest
    assert all(not unit.is_semantically_authorized for unit in preview.units)
    assert preview.units[0].preceding_quote is None
    assert preview.units[1].preceding_quote == preview.units[0].selected_quote
    assert preview.units[0].selected_source_end < preview.units[1].selected_source_start
    assert preview.units[0].candidate_id == "candidate-1"
    assert preview.units[1].candidate_id == "candidate-2"
    assert "CONTEXTO ANTERIOR" in preview.units[1].planner_request()
    assert "SEGMENTO ACTUAL" in preview.units[1].planner_request()
    assert source.startswith(preview.units[0].selected_quote)
    assert source.endswith(preview.units[1].selected_quote)


def test_project_ellipsis_is_not_materialized_as_an_unproven_fact():
    _, context = _observed("F23")
    left, right = preview_dependent_clause_scopes(context.source, context).units
    assert left.planner_request() == "El proyecto Odyssey tiene un fallo en Router."
    assert [role.role for role in right.inherited_roles] == ["subject", "predicate"]
    assert [role.span.text for role in right.inherited_roles] == ["El proyecto Odyssey", "tiene"]
    assert not right.unresolved_references
    assert "otro fallo en Temporal" not in right.planner_request()
    assert "otro en Temporal" in right.planner_request()
    # A model may infer the omitted noun, but no parser is allowed to invent it.


def test_document_pronoun_stays_unbound_and_date_does_not_leak():
    _, context = _observed("F26")
    left, right = preview_dependent_clause_scopes(context.source, context).units
    assert left.planner_request() == "El informe llegó ayer."
    assert [role.span.text for role in right.explicit_roles if role.role == "date"] == ["hoy"]
    assert [role.text for role in right.unresolved_references] == ["lo"]
    assert not right.inherited_roles
    assert "El informe llegó ayer" in right.planner_request()
    assert "hoy lo envié a Ana" in right.planner_request()
    assert "ayer y hoy" not in right.planner_request()


@pytest.mark.parametrize("case_id", ["F08", "F19", "F20", "F25"])
def test_no_unsupported_scope_can_reach_a_core_planning_request(case_id):
    source, context = _observed(case_id)
    with pytest.raises(CoreDependentScopeError):
        preview_dependent_clause_scopes(source, context)


def test_cross_clause_rollback_words_abort_both_plans():
    source, context = _observed("F23")
    altered_source = source.replace(" y otro", " pero otro")
    # Original role evidence is stale; fail closed even if candidate syntax
    # superficially looks like exactly two grammatical assertions.
    with pytest.raises((CoreDependentScopeError, ValueError)):
        preview_dependent_clause_scopes(altered_source, context)


def test_tampering_scope_roles_cannot_create_an_unauthorized_plan():
    source, context = _observed("F26")
    from odyssey_core.candidate_context import CoreCandidateRole

    first = context.candidates[0]
    second = context.candidates[1]
    fake = replace(
        second,
        roles=(*second.roles, CoreCandidateRole("condition", second.roles[0].span)),
    )
    with pytest.raises(CoreDependentScopeError, match="Conditional"):
        preview_dependent_clause_scopes(source, replace(context, candidates=(first, fake)))


def _synthetic_role_source(
    source: str,
    selected: tuple[tuple[str, str], ...],
    second: tuple[tuple[str, str], ...],
    *,
    inherit: tuple[str, ...] = (),
):
    """Construct a new source-proven proposal to check generalization."""
    from odyssey_core.candidate_context import (
        CoreCandidate,
        CoreCandidateContext,
        CoreCandidateInheritance,
        CoreCandidateRole,
        CoreSourceSpan,
    )

    def span(text):
        start = source.index(text)
        return CoreSourceSpan(text, start, start + len(text))

    first = CoreCandidate(
        "candidate-1",
        "property" if not any(role == "date" for role, _ in selected) else "occurrence",
        "candidate",
        (span(selected[0][1]),),
        tuple(CoreCandidateRole(role, span(text)) for role, text in selected),
        (),
    )
    last = CoreCandidate(
        "candidate-2",
        first.kind,
        "candidate",
        (span(second[0][1]),),
        tuple(CoreCandidateRole(role, span(text)) for role, text in second),
        tuple(CoreCandidateInheritance(role, 1) for role in inherit),
    )
    context = CoreCandidateContext(source, (first, last))
    context.validate(source)
    return context


def test_new_project_property_and_ellipsis_use_same_provenance_rules():
    """New vocabulary and new named entities, no case-ID-dependent behavior."""
    source = "El sistema Nébula presenta un problema en API y otro en interfaz."
    context = _synthetic_role_source(
        source,
        (
            ("subject", "El sistema Nébula"),
            ("predicate", "presenta"),
            ("object", "un problema"),
            ("location", "API"),
        ),
        (("object", "otro"), ("location", "interfaz")),
        inherit=("subject", "predicate"),
    )
    first, second = preview_dependent_clause_scopes(source, context).units
    assert first.planner_request() == "El sistema Nébula presenta un problema en API."
    assert "otro en interfaz" in second.planner_request()
    assert "un problema" in second.planner_request()
    assert [x.span.text for x in second.inherited_roles] == [
        "El sistema Nébula",
        "presenta",
    ]


def test_new_document_and_person_coreference_remain_unbound_not_guessed():
    source = "El contrato llegó el lunes y ayer lo envié a Marta."
    context = _synthetic_role_source(
        source,
        (("subject", "El contrato"), ("predicate", "llegó"), ("date", "el lunes")),
        (("date", "ayer"), ("reference", "lo"), ("predicate", "envié"), ("participants", "Marta")),
    )
    first, second = preview_dependent_clause_scopes(source, context).units
    assert first.planner_request() == "El contrato llegó el lunes."
    assert [item.text for item in second.unresolved_references] == ["lo"]
    assert second.preceding_quote == "El contrato llegó el lunes"
    assert "lo envié a Marta" in second.planner_request()
    assert not first.is_semantically_authorized
    assert not second.is_semantically_authorized
