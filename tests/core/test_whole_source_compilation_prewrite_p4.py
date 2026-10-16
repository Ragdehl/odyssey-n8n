"""All reviewed operations must compile before P4 touches canonical Markdown.

Generic cardinality, mixed intent, actor and date permutations; not name/phrase
patches. The model's agreement is not the canonical preflight's authority.
"""

from __future__ import annotations

import copy

import pytest

from odyssey_core.whole_source_compiler import (
    WholeSourceCompilationError,
    compile_reviewed_operations,
)


def _fact(*, kind="record", date="2026-10-16", text="He visto {{ref:0}}.", name="Clara"):
    return {
        "kind": kind,
        "date": date,
        "reviewed_text": text,
        "reference_names": [name] if "{{ref:0}}" in text else [],
    }


@pytest.mark.parametrize("number", [1, 2, 5, 10])
def test_all_days_are_precompiled_without_hardcoded_number_of_facts(number):
    facts = [_fact(date=f"2026-10-{i + 16:02d}") for i in range(number)]
    prepared = compile_reviewed_operations({"facts": facts}, (True,) * number)
    assert len(prepared) == number
    assert all(not op.task_create for op in prepared)
    assert [op.locator_suffix for op in prepared] == [
        "day-" + f"2026-10-{i + 16:02d}" for i in range(number)
    ]


def test_day_self_and_task_plan_are_compiled_together_before_execution():
    review = {
        "facts": [
            _fact(date="2026-10-17"),
            _fact(date=None, text="Me gusta caminar.", name=""),
            _fact(kind="task", date="2026-10-18", text="Llamar a {{ref:0}}."),
            _fact(date="2026-10-16"),
        ]
    }
    plan = compile_reviewed_operations(review, (True, True, False, True))
    assert [(op.locator_suffix, op.task_create) for op in plan] == [
        ("day-2026-10-16", False),
        ("day-2026-10-17", False),
        ("self", False),
        ("task-2", True),
    ]
    assert plan[-1].plan.actions[0].units[0].force_create
    assert plan[-1].plan.actions[0].units[0].target.type == "task"
    assert plan[-1].plan.actions[0].units[0].properties


@pytest.mark.parametrize(
    "invalid",
    [
        "undated_third_party",
        "undated_task",
        "unsupported_kind",
        "bad_last_date",
        "bad_last_reference",
        "missing_text",
        "untrusted_speaker",
        "wrong_count",
    ],
)
def test_any_unsupported_later_fact_fails_before_compiling_any_write(invalid):
    facts = [_fact(), _fact(date="2026-10-17")]
    roles = [True, True]
    if invalid == "undated_third_party":
        facts[1]["date"] = None
        roles[1] = False
    elif invalid == "undated_task":
        facts[1]["kind"] = "task"
        facts[1]["date"] = None
    elif invalid == "unsupported_kind":
        facts[1]["kind"] = "session"
    elif invalid == "bad_last_date":
        facts[1]["date"] = "2026-99-99"
    elif invalid == "bad_last_reference":
        facts[1]["reference_names"] = ["Clara", "Alba"]
    elif invalid == "missing_text":
        del facts[1]["reviewed_text"]
    elif invalid == "untrusted_speaker":
        roles[1] = "yes"
    elif invalid == "wrong_count":
        roles = roles[:1]
    with pytest.raises((WholeSourceCompilationError, ValueError, KeyError)):
        compile_reviewed_operations({"facts": copy.deepcopy(facts)}, tuple(roles))
