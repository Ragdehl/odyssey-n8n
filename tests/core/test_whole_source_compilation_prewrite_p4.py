"""All reviewed operations must compile before P4 touches canonical Markdown.

Generic cardinality, mixed intent, actor and date permutations; not name/phrase
patches. The model's agreement is not the canonical preflight's authority.
"""

from __future__ import annotations

import copy
import re

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


@pytest.mark.parametrize("seed", range(28))
def test_generated_reference_variations_do_not_depend_on_familiar_examples(seed):
    """Metamorphic Core contract: generated identities, facts, order, cardinality and types.

    This is deterministic offline coverage of the *mechanism*, not live model
    approval or a claim that the whole P4 coordinator is already generic.
    """
    from random import Random

    rng = Random(seed)
    size = (0, 1, 2, 3, 5, 9, 12)[seed % 7]
    identities = [f"Nombre_{seed:02d}_{i:02d}" for i in range(size)]
    note_type = (
        f"custom_{seed:02d}" if seed % 3 == 0 else ("project" if seed % 3 == 1 else "document")
    )
    date = "2026-10-16" if seed % 2 else None
    facts = []
    for _ in range(1 + seed % 3):
        selected = rng.sample(identities, rng.randint(0, size))
        facts.append(
            {
                "kind": "record",
                "date": date,
                "reference_names": selected,
                "reviewed_text": (
                    "Registré " + " y ".join(f"{{{{ref:{i}}}}}" for i in range(len(selected))) + "."
                    if selected
                    else "Registré información."
                ),
            }
        )
    rng.shuffle(facts)
    original = copy.deepcopy(facts)
    operations = compile_reviewed_operations(
        {"facts": facts},
        (True,) * len(facts),
        reference_types={name: note_type for name in identities},
        declared_types=frozenset({note_type, "person", "calendar_day"}),
    )
    assert facts == original
    assert len(operations) == 1
    owner, *helpers = operations[0].plan.actions[0].units
    unique_names = list(dict.fromkeys(name for fact in facts for name in fact["reference_names"]))
    assert [unit.target.entity for unit in helpers[: len(unique_names)]] == unique_names
    assert all(unit.target.type == note_type for unit in helpers[: len(unique_names)])
    assert all(unit.reference_lookup_only for unit in helpers[: len(unique_names)])
    assert len(owner.facts) == len(facts)
    expected_refs = []
    for fact in facts:
        for name in fact["reference_names"]:
            expected_refs.append(unique_names.index(name) + 1)
    assert [ref.target_index for ref in owner.references[: len(expected_refs)]] == expected_refs
    offset = 0
    for fact, value in zip(facts, owner.facts, strict=True):
        # Independent oracle: slot positions enumerate source occurrences, not
        # distinct names, and only ORIGINAL tokens are substituted once.
        expected = re.sub(
            r"\{\{ref:(\d+)\}\}",
            lambda found, start=offset: "{{ref:" + str(start + int(found.group(1))) + "}}",
            fact["reviewed_text"],
        )
        offset += len(fact["reference_names"])
        assert value.startswith(expected[:-1])
    assert (owner.target.self_target == "self") is (date is None)
    if date is not None:
        assert len(helpers) == len(unique_names) + 1
        assert len(owner.fact_temporal_anchors) == len(facts)
    else:
        assert len(helpers) == len(unique_names)
        assert owner.fact_temporal_anchors == ()


@pytest.mark.parametrize("note_type", ["person", "project", "document", "concept"])
@pytest.mark.parametrize("reverse", [False, True])
def test_shared_reference_remapping_writes_correct_two_fact_links_to_markdown(
    tmp_path, note_type, reverse
):
    """Source-bound multi-fact links survive Core/E3 and physical readback."""
    from types import SimpleNamespace

    from odyssey_core import create_entity
    from odyssey_core.application import ApplicationStatus, execute_request
    from odyssey_core.notes import parse_note
    from odyssey_core.whole_message_coverage import validate_whole_message_coverage
    from tests.runtime.test_whole_source_light_product_p4 import _fixture

    pieces = [
        ("Registré Entidad00.", "Registré {{ref:0}}.", ["Entidad00"]),
        (
            "Después revisé Entidad01, Entidad02 y Entidad03.",
            "Después revisé {{ref:0}}, {{ref:1}} y {{ref:2}}.",
            ["Entidad01", "Entidad02", "Entidad03"],
        ),
    ]
    if reverse:
        pieces.reverse()
    source = " ".join(original for original, _review, _names in pieces)
    proposed = {
        "entities": [{"mention": name} for _s, _r, names in pieces for name in names],
        "facts": [
            {
                "meaning": original,
                "kind": "record",
                "subject": "yo",
                "date": None,
                "participants": names,
                "source_evidence": original,
                "dependent_on_fact_index": None,
                "needs_clarification": False,
            }
            for original, _text, names in pieces
        ],
        "unresolved": [],
    }
    review = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": i,
                "source_quote": original,
                "kind": "record",
                "reviewed_text": text,
                "date": None,
                "reference_names": names,
                "supported": True,
            }
            for i, (original, text, names) in enumerate(pieces)
        ],
    }
    assert not validate_whole_message_coverage(
        source, proposed, review, ["core"]
    ).has_write_authority
    ops = compile_reviewed_operations(
        review,
        (True, True),
        reference_types={name: note_type for _s, _r, names in pieces for name in names},
        declared_types=frozenset({note_type}),
    )
    repo, actor, service, _runtime = _fixture(tmp_path)
    names = [name for _s, _r, scope in pieces for name in scope]
    for i, name in enumerate(names):
        create_entity(
            repo,
            service.schema,
            path=f"{name}.md",
            entity_id=f"generated-id-{i}",
            metadata={"name": name, "type": note_type},
            content="",
            actor="fixture",
            now="2026-10-16T11:00:00+02:00",
        )
    service.refresh_affected_indexes(tuple(f"generated-id-{i}" for i in range(4)))
    outcome = execute_request(
        source,
        planner=SimpleNamespace(plan=lambda *_args: ops[0].plan),
        repository=repo,
        schema=service.schema,
        context_index=service.context_index,
        semantic_index=service.semantic_index,
        embedder=service.embedder,
        contextual_reasoner=service.reasoner,
        actor=actor.stable_user_id,
        now="2026-10-16T15:30:00+02:00",
        context_limit=20,
        authenticated_actor=actor,
        self_binding_repository=service.bindings,
        request_id_factory=lambda: f"multi-fact-{note_type}-{reverse}",
    )
    assert outcome.status is ApplicationStatus.COMPLETED, outcome
    physical = parse_note(repo.read_text("self.md")).content
    assert all(name in physical for name in names), physical
    assert "{{ref:" not in physical
    for source_text, _text, scope in pieces:
        anchor = source_text.split()[0]
        fact_lines = [line for line in physical.splitlines() if anchor in line]
        assert len(fact_lines) == 1, physical
        assert all(name in fact_lines[0] for name in scope), physical
        assert all(other not in fact_lines[0] for other in names if other not in scope), physical
