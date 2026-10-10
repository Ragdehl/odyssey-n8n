"""Real-provider frozen semantic sentinels for 23 GPT-6 Router v3 cases.

Never replace an observed failure with an oracle fake or mark a valid JSON
as Core-safe. This is provider-free, no Note access or execution authority.
"""

from __future__ import annotations

import pytest

from benchmarks.fact_candidate_v2_live import run_remaining
from benchmarks.fact_candidate_v2_live.analyze_remaining import analyze


@pytest.fixture(scope="module")
def actual():
    """Parse each once through the existing original-source validator."""
    return analyze()


def test_exactly_23_real_provider_results_with_grounded_source(actual):
    assert actual["completed"] == actual["total"] == 23
    assert actual["model"] == "gpt-6-luna"
    assert actual["prompt_revision"] == "v3"
    assert all(
        x["source_validation"] == "source_valid" and x["provider_status"] == "completed"
        for x in actual["items"]
    )
    assert actual["core_plans_verified"] is False
    assert actual["semantic_human_review_required"] is True
    assert set(x["id"] for x in actual["items"]) == set(run_remaining.IDS)


def test_22_cases_preserve_fact_count_but_correction_does_not(actual):
    differences = [x["id"] for x in actual["items"] if x.get("count") != x["expected_count"]]
    assert differences == ["F19"]


def test_local_fixture_type_mismatches_are_not_all_auto_semantic_failures(actual):
    """Purchases/inspections may be reasonable alternative granularities."""
    assert {x["id"] for x in actual["items"] if x["result"] == "material_structure_mismatch"} == {
        "F06",
        "F13",
        "F16",
        "F19",
        "F20",
        "F24",
        "F25",
    }


def test_f19_danger_correction_was_split_into_two_executable_candidates(actual):
    case = next(x for x in actual["items"] if x["id"] == "F19")
    assert case["expected_count"] == 1
    assert case["expected_kinds"] == ["plan"]
    assert case["count"] == 2
    assert case["kinds"] == ["occurrence", "occurrence"]
    assert any(("polarity", "no") in unit["roles"] for unit in case["candidates"])
    assert any(("replacement", "al parque") in unit["roles"] for unit in case["candidates"])
    # Model saw the correction words, but failed the required ONE-PLAN semantics.


def test_f20_condition_words_survive_but_conditional_type_does_not(actual):
    case = next(x for x in actual["items"] if x["id"] == "F20")
    assert case["expected_kinds"] == ["conditional", "conditional"]
    assert case["kinds"] == ["occurrence", "occurrence"]
    assert [
        [text for role, text in unit["roles"] if role == "condition"] for unit in case["candidates"]
    ] == [["si no llueve"], ["si llueve"]]


def test_f25_unassigned_roof_need_is_classified_as_task(actual):
    """Warn against turning an observed property into an assigned user task."""
    case = next(x for x in actual["items"] if x["id"] == "F25")
    assert case["expected_kinds"] == ["property", "property"]
    assert case["kinds"] == ["property", "task"]
    assert ("object", "el tejado") in case["candidates"][1]["roles"]


def test_f08_same_hour_has_literal_temporal_but_not_source_relation(actual):
    case = next(x for x in actual["items"] if x["id"] == "F08")
    second = case["candidates"][1]
    assert ("time", "a la misma hora") in second["roles"]
    assert not any(role == "time_relation" for role, _ in second["roles"])
    assert not any(role == "time" for role, _ in case["candidates"][1]["inherits"])


def test_f26_pronoun_is_not_explicitly_linked_to_previous_object(actual):
    case = next(x for x in actual["items"] if x["id"] == "F26")
    assert ("reference", "lo") in case["candidates"][1]["roles"]
    assert not any(role == "object" for role, _ in case["candidates"][1]["inherits"])


def test_f17_protects_both_negated_people_and_f22_three_tasks(actual):
    negative = next(x for x in actual["items"] if x["id"] == "F17")
    assert negative["kinds"] == ["negative", "negative"]
    assert all(("polarity", "no") in unit["roles"] for unit in negative["candidates"])
    tasks = next(x for x in actual["items"] if x["id"] == "F22")
    assert tasks["kinds"] == ["task", "task", "task"]
    assert [unit["state"] for unit in tasks["candidates"]] == ["candidate"] * 3


def test_original_budget_stays_below_approved_user_limit(actual):
    assert actual["estimated_new_usd"] == 0.00777
    assert actual["estimated_cumulative_usd"] == 0.0337352
    assert actual["estimated_cumulative_usd"] < actual["authorized_total_usd"] == 0.07
