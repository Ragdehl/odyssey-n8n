"""Core-owned per-fact scoped handoff, using frozen real Router GPT-6 output.

All tests are provider-free, with no Notes writes and no runtime activation.
"""

from dataclasses import replace

import pytest

from odyssey_apps.fact_candidate_core import to_core_candidate_context
from odyssey_core.candidate_scoped_handoff import (
    CandidateScopeSafetyError,
    preview_independent_candidate_scopes,
)
from tests.benchmarks.test_fact_candidate_prompt_v3_observed import _case


@pytest.mark.parametrize("case_id,count", [("F14", 1), ("F27", 2)])
def test_each_safe_fact_has_its_own_core_scope_and_future_stays_pending(case_id, count):
    context = to_core_candidate_context(_case(case_id))
    preview = preview_independent_candidate_scopes(context.source, context)
    assert not preview.can_auto_execute
    assert len(preview.units) == count
    assert [unit.candidate_id for unit in preview.units] == [
        f"candidate-{index}" for index in range(1, count + 1)
    ]
    assert preview.pending_candidate_ids == (f"candidate-{count + 1}",)
    assert len({unit.candidate_id for unit in preview.units}) == count
    assert all(unit.source_digest == preview.full_source_digest for unit in preview.units)
    for unit in preview.units:
        assert unit.source_for_planner() == context.source.split(". ")[0] + "."
        assert "Mañana" not in unit.source_for_planner()
        assert "cine" not in unit.source_for_planner()
        assert unit.date_evidence[0].text == "Ayer"
        assert unit.subject_predicate_evidence.text.startswith("hablé")
        assert unit.clause_start == 0 and unit.clause_end < len(context.source)
        payload = unit.task_payload()
        assert payload["selected_candidate_id"] == unit.candidate_id
        assert payload["original_date_text"] == ["Ayer"]
        assert payload["write_authorized"] is False
        assert "Mañana" not in str(payload) and "cine" not in str(payload)
    if case_id == "F27":
        assert preview.units[0].sibling_candidate_ids == ("candidate-2",)
        assert preview.units[1].sibling_candidate_ids == ("candidate-1",)
        assert preview.units[1].inherited_from == ("candidate-1",)
        assert preview.units[0].task_payload() != preview.units[1].task_payload()
        assert (
            preview.units[0].task_payload()["selected_candidate_id"]
            != preview.units[1].task_payload()["selected_candidate_id"]
        )
        assert ("order", "después") in [(role, span.text) for role, span in preview.units[1].roles]


@pytest.mark.parametrize(
    "case_id,change",
    [
        ("F14", "drop_pending_reference"),
        ("F14", "drop_pending_date"),
        ("F14", "unresolved_not_ambiguous"),
        ("F14", "past_not_safe"),
        ("F14", "sensitive_role"),
        ("F27", "drop_inheritance"),
        ("F27", "drop_order"),
        ("F27", "drop_original_date"),
        ("F27", "sensitive_role"),
    ],
)
def test_invalid_or_dependent_source_does_not_get_a_planning_task(case_id, change):
    context = to_core_candidate_context(_case(case_id))
    units = list(context.candidates)
    if change == "drop_pending_reference":
        units[-1] = replace(
            units[-1], roles=tuple(role for role in units[-1].roles if role.role != "reference")
        )
    elif change == "drop_pending_date":
        units[-1] = replace(
            units[-1], roles=tuple(role for role in units[-1].roles if role.role != "date")
        )
    elif change == "unresolved_not_ambiguous":
        units[-1] = replace(units[-1], state="candidate")
    elif change == "past_not_safe":
        units[0] = replace(units[0], state="ambiguous_identity")
    elif change == "drop_inheritance":
        units[1] = replace(units[1], inherits=())
    elif change == "drop_order":
        units[1] = replace(
            units[1], roles=tuple(role for role in units[1].roles if role.role != "order")
        )
    elif change == "drop_original_date":
        units[0] = replace(
            units[0], roles=tuple(role for role in units[0].roles if role.role != "date")
        )
    else:
        role = units[0].roles[0]
        units[0] = replace(units[0], roles=(replace(role, role="condition"), *units[0].roles[1:]))
    changed = replace(context, candidates=tuple(units))
    with pytest.raises((CandidateScopeSafetyError, ValueError)):
        preview_independent_candidate_scopes(changed.source, changed)


def test_scoping_is_not_available_for_unrelated_f09_or_f10_prototypes():
    for case_id in ("F09", "F10"):
        context = to_core_candidate_context(_case(case_id))
        with pytest.raises(CandidateScopeSafetyError):
            preview_independent_candidate_scopes(context.source, context)


def test_no_naive_sentence_splitting_if_original_source_contains_more_clauses():
    context = to_core_candidate_context(_case("F14"))
    # The full source digest and exact source-span check refuse missing/
    # added text rather than silently dropping a later correction.
    for suffix in (" Pero en realidad fue Luis.", " No hablé con Eric."):
        updated = context.source + suffix
        with pytest.raises((CandidateScopeSafetyError, ValueError)):
            preview_independent_candidate_scopes(updated, context)
