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


@pytest.mark.parametrize("note_type", ["person", "project", "document", "concept"])
def test_compiler_preserves_core_schema_type_without_person_assumption(note_type):
    from odyssey_core.request_planning import WriteAction

    checked = compile_reviewed_operations(
        {"facts": [_fact(text="Hoy revisé {{ref:0}}.", name="Atlas")]},
        (True,),
        reference_types={"Atlas": note_type},
        declared_types=frozenset(("person", "project", "document", "concept")),
    )
    assert len(checked) == 1
    action = checked[0].plan.actions[0]
    assert isinstance(action, WriteAction)
    # The third unit is the already-established SELF speaker link; do not
    # falsely treat that authorized metadata as an extra user fact.
    assert len(action.units) == 3
    assert action.units[1].target.type == note_type
    assert action.units[1].reference_lookup_only is True
    assert action.units[0].references[0].role == "related"


def test_unknown_model_invented_note_type_rejected_before_any_compilation():
    with pytest.raises(WholeSourceCompilationError, match="schema reference type"):
        compile_reviewed_operations(
            {"facts": [_fact()]},
            (True,),
            reference_types={"Clara": "unregistered_dynamic_type"},
            declared_types=frozenset(("person", "project", "document", "concept")),
        )


def test_no_type_hint_does_not_default_arbitrary_identity_to_person():
    from odyssey_core.request_planning import WriteAction

    checked = compile_reviewed_operations({"facts": [_fact()]}, (True,))
    action = checked[0].plan.actions[0]
    assert isinstance(action, WriteAction)
    assert action.units[1].target.type is None


@pytest.mark.parametrize("target", ["dated", "self"])
@pytest.mark.parametrize("type_hint", ["person", "project", "document", "concept"])
@pytest.mark.parametrize("reversed_order", [False, True])
def test_shared_record_renderer_deduplicates_links_across_facts_without_type_branches(
    target, type_hint, reversed_order
):
    """One lowerer must preserve the two facts and three independent references."""
    date = "2026-10-16" if target == "dated" else None
    reviewed = {
        "facts": [
            {
                "kind": "record",
                "date": date,
                "reviewed_text": "Hablé con {{ref:0}} sobre {{ref:1}}.",
                "reference_names": ["Eva", "Atlas"],
            },
            {
                "kind": "record",
                "date": date,
                "reviewed_text": "Después comenté {{ref:0}} con {{ref:1}}.",
                "reference_names": ["Atlas", "Nora"],
            },
        ]
    }
    if reversed_order:
        reviewed["facts"].reverse()
    operations = compile_reviewed_operations(
        reviewed,
        (True, True),
        reference_types={"Eva": type_hint, "Atlas": type_hint, "Nora": type_hint},
        declared_types=frozenset({"person", "project", "document", "concept"}),
    )
    assert len(operations) == 1
    owner, *helpers = operations[0].plan.actions[0].units
    assert len(owner.facts) == 2
    assert [r.target_index for r in owner.references[:4]] == (
        [1, 2, 3, 1] if reversed_order else [1, 2, 2, 3]
    )
    # Dated operations preserve independently attested SELF speaker backlinks.
    if target == "dated":
        assert [r.target_index for r in owner.references[4:]] == [4, 4]
    else:
        assert len(owner.references) == 4
    assert [unit.target.entity for unit in helpers[:3]] == (
        ["Atlas", "Nora", "Eva"] if reversed_order else ["Eva", "Atlas", "Nora"]
    )
    assert all(unit.target.type == type_hint for unit in helpers[:3])
    expected_second = (
        "Hablé con {{ref:2}} sobre {{ref:3}}."
        if reversed_order
        else "Después comenté {{ref:2}} con {{ref:3}}."
    )
    if target == "dated":
        assert owner.facts[1] == expected_second[:-1] + " (yo: {{ref:5}})."
        assert operations[0].locator_suffix == "day-2026-10-16"
        assert owner.fact_temporal_anchors and len(owner.fact_temporal_anchors) == 2
    else:
        assert owner.facts[1] == expected_second
        assert operations[0].locator_suffix == "self"
        assert owner.target.self_target == "self"
        assert not owner.fact_temporal_anchors


def test_shared_lowerer_still_keeps_task_lifecycle_and_refusal_boundaries():
    task = _fact(kind="task", date="2026-10-16", text="Llamar a {{ref:0}}.")
    operations = compile_reviewed_operations(
        {"facts": [task]},
        (False,),
        reference_types={"Clara": "person"},
        declared_types=frozenset({"person", "task"}),
    )
    task_unit, helper = operations[0].plan.actions[0].units
    assert operations[0].task_create
    assert task_unit.force_create
    assert task_unit.target.type == "task"
    assert [(p.field, p.value) for p in task_unit.properties] == [
        ("status", "pending"),
        ("target_date", "2026-10-16"),
    ]
    assert task_unit.fact_temporal_anchors == ((),)
    assert helper.reference_lookup_only and helper.target.type == "person"
    bad = copy.deepcopy(task)
    bad["date"] = None
    with pytest.raises(WholeSourceCompilationError):
        compile_reviewed_operations({"facts": [bad]}, (False,))
