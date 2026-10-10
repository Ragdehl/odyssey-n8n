"""Core-only provenance-preserving contextual selection, no write authority."""

from __future__ import annotations

from dataclasses import replace

import pytest

from odyssey_core.candidate_context import CoreCandidateRole
from odyssey_core.candidate_dependencies import (
    CandidateDependencyError,
    preview_contextual_dependency_tasks,
)
from tests.core.test_candidate_dependencies_observed import _observed


@pytest.mark.parametrize("case_id", ["F23", "F26"])
def test_contextual_selection_is_one_fact_per_unit_with_literal_quotes(case_id):
    source, context = _observed(case_id)
    tasks = preview_contextual_dependency_tasks(source, context)
    assert len(tasks) == 2
    assert [t.candidate_id for t in tasks] == ["candidate-1", "candidate-2"]
    assert tasks[0].prior_context_quote is None
    assert tasks[1].prior_context_quote == tasks[0].selected_quote
    assert not any(t.may_authorize_writes for t in tasks)
    assert all(t.source_digest == tasks[0].source_digest for t in tasks)
    assert all(t.selected_quote in source for t in tasks)
    assert tasks[1].selected_quote not in tasks[0].scoped_request()
    assert tasks[0].selected_quote in tasks[1].scoped_request()
    assert "exclusivamente" in tasks[1].scoped_request()
    assert tasks[0].scoped_request() != tasks[1].scoped_request()


def test_f23_missing_predicate_and_subject_remain_original_evidence_not_invented():
    source, context = _observed("F23")
    a, b = preview_contextual_dependency_tasks(source, context)
    assert a.selected_quote == "El proyecto Odyssey tiene un fallo en Router"
    assert b.selected_quote == "otro en Temporal"
    assert [(r.role, r.span.text) for r in b.effective_roles if r.inherited] == [
        ("subject", "El proyecto Odyssey"),
        ("predicate", "tiene"),
    ]
    assert b.unresolved_reference_quotes == ()
    # The noun 'fallo' is context only, not an invented direct role.
    assert [(r.role, r.span.text) for r in b.effective_roles if r.role == "object"] == [
        ("object", "otro")
    ]


def test_f26_document_coreference_remains_an_unresolved_identity_choice():
    source, context = _observed("F26")
    first, second = preview_contextual_dependency_tasks(source, context)
    assert first.selected_quote == "El informe llegó ayer"
    assert second.selected_quote == "hoy lo envié a Ana"
    assert second.unresolved_reference_quotes == ("lo",)
    assert "informe" not in second.selected_quote
    assert "El informe" in second.prior_context_quote
    assert [r.span.text for r in second.effective_roles if r.role == "participants"] == ["Ana"]
    assert all(not r.inherited for r in second.effective_roles)


def test_cross_clause_polarity_and_conditions_stay_blocked():
    for case_id in ("F19", "F20", "F17", "F27"):
        source, context = _observed(case_id) if case_id != "F27" else _from_frozen_f27()
        with pytest.raises(CandidateDependencyError):
            preview_contextual_dependency_tasks(source, context)


def _from_frozen_f27():
    from odyssey_apps.fact_candidate_core import to_core_candidate_context
    from tests.benchmarks.test_fact_candidate_prompt_v3_observed import _case

    context = to_core_candidate_context(_case("F27"))
    return context.source, context


def test_untrusted_role_can_not_reference_a_separate_clause():
    source, context = _observed("F26")
    target = context.candidates[1]
    other = context.candidates[0].roles[0].span
    altered = replace(
        target,
        roles=tuple(
            CoreCandidateRole("reference", other) if role.role == "reference" else role
            for role in target.roles
        ),
    )
    with pytest.raises(CandidateDependencyError, match="Overlapping"):
        preview_contextual_dependency_tasks(
            source, replace(context, candidates=(context.candidates[0], altered))
        )


def test_fake_inheritance_missing_evidence_fails_closed():
    source, context = _observed("F23")
    # Source verified role predecessor missing after a fabricated edge.
    from odyssey_core.candidate_context import CoreCandidateInheritance

    last = context.candidates[1]
    tampered = replace(last, inherits=(*last.inherits, CoreCandidateInheritance("time", 1)))
    with pytest.raises(CandidateDependencyError, match="no evidence"):
        preview_contextual_dependency_tasks(
            source, replace(context, candidates=(context.candidates[0], tampered))
        )


def test_source_digest_changes_when_context_changes():
    source, context = _observed("F26")
    with pytest.raises(ValueError):
        preview_contextual_dependency_tasks(source.replace("informe", "documento"), context)
