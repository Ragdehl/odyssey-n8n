"""Verified real Router F23/F26 source segmentation, never executable directly."""

from __future__ import annotations

from dataclasses import replace

import pytest

from odyssey_core.candidate_dependent_scope import (
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
