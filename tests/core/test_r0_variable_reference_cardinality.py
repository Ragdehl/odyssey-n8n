"""G03/G04: real source evidence may name more than eight typed entities.

No model, user data or E3 write; this tests the existing Core provenance and
reviewed-plan boundary independently of any particular NoteSchema type.
"""

from __future__ import annotations

import copy

import pytest

from odyssey_core.whole_message_coverage import validate_whole_message_coverage
from odyssey_core.whole_source_compiler import compile_reviewed_operations


def _source_packet(count: int):
    names = [f"Entidad{i:02d}" for i in range(count)]
    source = "Hoy vi a " + ", ".join(names) + "."
    reviewed_text = "Hoy vi a " + ", ".join(f"{{{{ref:{i}}}}}" for i in range(count)) + "."
    proposed = {
        "entities": [{"mention": name} for name in names],
        "unresolved": [],
        "facts": [
            {
                "meaning": source,
                "kind": "record",
                "subject": "yo",
                "date": None,
                "participants": names,
                "source_evidence": source,
                "dependent_on_fact_index": None,
                "needs_clarification": False,
            }
        ],
    }
    review = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": 0,
                "source_quote": source,
                "kind": "record",
                "reviewed_text": reviewed_text,
                "date": None,
                "reference_names": names,
                "supported": True,
            }
        ],
    }
    return source, proposed, review, names


@pytest.mark.parametrize("count", [1, 8, 9, 12])
def test_source_bound_cardinality_flows_through_existing_core_compiler(count):
    source, proposed, review, names = _source_packet(count)
    verified = validate_whole_message_coverage(source, proposed, review, ["core"])
    assert verified.has_write_authority is False
    assert verified.reviewed_facts[0].reference_names == tuple(names)
    operations = compile_reviewed_operations(
        review,
        (True,),
        reference_types={name: "person" for name in names},
        declared_types=frozenset({"person", "project", "document"}),
    )
    assert len(operations) == 1
    unit = operations[0].plan.actions[0].units
    assert len(unit) == count + 1
    assert len(unit[0].references) == count
    assert {child.target.entity for child in unit[1:]} == set(names)


@pytest.mark.parametrize("attack", ["invented", "duplicate", "missing_slot", "wrong_source"])
def test_many_references_remain_fail_closed_when_evidence_is_tampered(attack):
    source, proposed, review, names = _source_packet(9)
    proposed, review = copy.deepcopy(proposed), copy.deepcopy(review)
    if attack == "invented":
        review["facts"][0]["reference_names"][-1] = "Inventado"
    elif attack == "duplicate":
        review["facts"][0]["reference_names"][-1] = names[0]
    elif attack == "missing_slot":
        review["facts"][0]["reviewed_text"] = review["facts"][0]["reviewed_text"].replace(
            "{{ref:8}}", "sin vincular"
        )
    elif attack == "wrong_source":
        source = source.replace(names[0], "OtraEntidad")
    with pytest.raises(ValueError):
        validate_whole_message_coverage(source, proposed, review, ["core"])


def test_compiler_rejects_malformed_many_reference_slot_even_if_caller_skips_coverage():
    _source, _proposed, review, _names = _source_packet(9)
    review["facts"][0]["reviewed_text"] = review["facts"][0]["reviewed_text"].replace(
        "{{ref:8}}", "{{ref:0}}"
    )
    with pytest.raises(ValueError, match="Reference marker coverage"):
        compile_reviewed_operations(review, (True,))


def test_unverified_source_mentions_have_no_arbitrary_eight_item_cutoff():
    source, proposed, review, names = _source_packet(12)
    review["facts"][0]["reviewed_text"] = source
    review["facts"][0]["reference_names"] = []
    proof = validate_whole_message_coverage(
        source,
        proposed,
        review,
        ["core"],
        unverified_source_mentions=names,
    )
    assert proof.reviewed_facts[0].reference_names == ()
    with pytest.raises(ValueError, match="mention was not retained"):
        validate_whole_message_coverage(
            source,
            proposed,
            review,
            ["core"],
            unverified_source_mentions=[*names, "Inventado"],
        )


def test_verified_source_groups_have_no_arbitrary_eight_item_cutoff():
    phrases = [f"mi grupo{i:02d}" for i in range(12)]
    members = [f"Miembro{i:02d}" for i in range(12)]
    source = "Vi a " + ", ".join(phrases) + "."
    proposed = {
        "entities": [],
        "unresolved": [],
        "facts": [
            {
                "kind": "record",
                "meaning": source,
                "subject": "yo",
                "date": None,
                "participants": [],
                "source_evidence": source,
                "dependent_on_fact_index": None,
                "needs_clarification": False,
            }
        ],
    }
    review = {
        "approved": True,
        "complete": True,
        "reason": None,
        "facts": [
            {
                "ordinal": 0,
                "source_quote": source,
                "kind": "record",
                "reviewed_text": source,
                "date": None,
                "reference_names": [],
                "supported": True,
            }
        ],
    }
    groups = tuple((p, (m,)) for p, m in zip(phrases, members, strict=True))
    proof = validate_whole_message_coverage(
        source,
        proposed,
        review,
        ["core"],
        verified_relationship_members=members,
        verified_relationship_groups=groups,
    )
    assert proof.has_write_authority is False
    with pytest.raises(ValueError, match="relationship groups"):
        validate_whole_message_coverage(
            source,
            proposed,
            review,
            ["core"],
            verified_relationship_members=members,
            verified_relationship_groups=[*groups, ("grupo inventado", (members[0],))],
        )


@pytest.mark.parametrize("note_type", ["person", "project", "document", "concept"])
def test_nine_approved_source_refs_materialize_to_physical_markdown(tmp_path, note_type):
    """Core E3, never a benchmark caller, commits only physically resolved links."""
    from types import SimpleNamespace

    from odyssey_core import create_entity
    from odyssey_core.application import ApplicationStatus, execute_request
    from odyssey_core.request_planning import RequestPlan
    from tests.runtime.test_whole_source_light_product_p4 import _fixture

    source, proposed, review, names = _source_packet(9)
    validate_whole_message_coverage(source, proposed, review, ["core"])
    operations = compile_reviewed_operations(
        review,
        (True,),
        reference_types={name: note_type for name in names},
        declared_types=frozenset({note_type}),
    )
    repository, actor, service, _runtime = _fixture(tmp_path)
    for i, name in enumerate(names):
        create_entity(
            repository,
            service.schema,
            path=f"{name}.md",
            entity_id=f"note-{i:02d}",
            metadata={"name": name, "type": note_type},
            content="",
            actor="fixture",
            now="2026-10-16T11:00:00+02:00",
        )
    service.refresh_affected_indexes(tuple(f"note-{i:02d}" for i in range(9)))
    outcome = execute_request(
        source,
        planner=SimpleNamespace(plan=lambda *_args: RequestPlan(operations[0].plan.actions, ())),
        repository=repository,
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
        request_id_factory=lambda: "nine-names-core",
    )
    assert outcome.status is ApplicationStatus.COMPLETED, outcome
    physical = repository.read_text("self.md")
    assert all(name in physical for name in names)
    assert "{{ref:" not in physical
