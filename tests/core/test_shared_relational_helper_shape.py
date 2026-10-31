"""Core owns one structural continuation rule across active and saved plans."""

from dataclasses import replace

import pytest

from odyssey_core.reference_preflight import single_relational_reference_helper_index
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RelationalReference,
    SelectionCriteria,
    WriteAction,
)


def _candidate(note_type: str, relation: bool) -> SelectionCriteria:
    return SelectionCriteria(
        None,
        "a related note",
        note_type,
        (),
        None,
        relational_reference=(
            RelationalReference("my associated item", "self", None, "one") if relation else None
        ),
    )


def _typed_action(note_type: str) -> WriteAction:
    helper = KnowledgeUnit(_candidate(note_type, True), "record", (), (), (), ())
    consumer = KnowledgeUnit(
        _candidate("journal_entry", False),
        "record",
        (),
        (),
        ("Checked {{ref:0}}.",),
        (KnowledgeReference(0, "related", "a related note"),),
    )
    return WriteAction((helper, consumer))


def _stored_action(note_type: str) -> dict:
    return {
        "kind": "write",
        "units": [
            {
                "target": {
                    "type": note_type,
                    "relational_reference": {"reference": "my associated item", "members": "one"},
                },
                "intent": "record",
                "cardinality": "one",
                "facts": [],
                "properties": [],
                "tag_changes": [],
                "references": [],
                "destination_type": None,
            },
            {
                "target": {"type": "journal_entry", "relational_reference": None},
                "intent": "record",
                "facts": ["Checked {{ref:0}}."],
                "references": [{"target_index": 0}],
            },
        ],
    }


@pytest.mark.parametrize("note_type", ["person", "project", "document", "concept"])
def test_same_core_policy_for_typed_and_stored_arbitrary_note_types(note_type):
    assert single_relational_reference_helper_index(_typed_action(note_type)) == 0
    assert single_relational_reference_helper_index(_stored_action(note_type)) == 0


def test_inverted_source_order_is_not_a_semantic_special_case():
    plan = _typed_action("project")
    reordered = WriteAction((plan.units[1], replace(plan.units[0])))
    reordered = WriteAction(
        (
            replace(reordered.units[0], references=(KnowledgeReference(1, "related", "note"),)),
            reordered.units[1],
        )
    )
    assert single_relational_reference_helper_index(reordered) == 1
    stored = _stored_action("project")
    stored["units"].reverse()
    stored["units"][0]["references"][0]["target_index"] = 1
    assert single_relational_reference_helper_index(stored) == 1


def test_dependency_requires_one_helper_and_one_source_proven_consumer():
    typed = _typed_action("project")
    bad_reference = replace(
        typed.units[1], references=(KnowledgeReference(None, "related", "note"),)
    )
    assert (
        single_relational_reference_helper_index(WriteAction((typed.units[0], bad_reference)))
        is None
    )
    stored = _stored_action("project")
    stored["units"][1]["references"][0]["target_index"] = 99
    assert single_relational_reference_helper_index(stored) is None
    stored = _stored_action("project")
    stored["units"][0]["facts"] = ["I also wrote a different fact"]
    assert single_relational_reference_helper_index(stored) is None
    assert single_relational_reference_helper_index({"kind": "write", "units": []}) is None
    assert (
        single_relational_reference_helper_index({"kind": "retrieve", "units": stored["units"]})
        is None
    )


def test_only_core_owns_helper_policy_not_runtime_composition():
    from pathlib import Path

    runtime = (Path(__file__).resolve().parents[2] / "odyssey_runtime/composition.py").read_text()
    assert "def _dependent_relational_helper_index(" not in runtime
    assert runtime.count("single_relational_reference_helper_index(") >= 3
