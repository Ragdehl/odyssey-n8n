from __future__ import annotations

from benchmarks.planner_prompt_regression_v5 import run_live as gate
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RelationalReference,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)


def selection(
    query: str,
    note_type: str,
    *,
    entity: str | None = None,
    relation: RelationalReference | None = None,
) -> SelectionCriteria:
    return SelectionCriteria(entity, query, note_type, (), None, relational_reference=relation)


def unit(
    target: SelectionCriteria,
    *,
    facts: tuple[str, ...] = (),
    references: tuple[KnowledgeReference, ...] = (),
    lookup: bool = False,
) -> KnowledgeUnit:
    return KnowledgeUnit(
        target,
        "record",
        (),
        (),
        facts,
        references,
        reference_lookup_only=lookup,
    )


def test_v5_registry_is_current_and_has_no_accepted_failure_holes() -> None:
    cases, context = gate.load_gate_cases()
    ids = {case["id"] for case in cases}

    assert len(cases) == gate.MAX_CALLS == 23
    assert context == {"date": "2026-09-28", "time": "20:30", "timezone": "Europe/Paris"}
    assert gate.OBSOLETE_INHERITED_IDS.isdisjoint(ids)
    assert "PPR16-unknown-self-project-member-write" in ids
    assert {
        "PPRV5-NESTED-PERSON-01",
        "PPRV5-NESTED-PROJECT-01",
        "PPRV5-NESTED-DOCUMENT-01",
        "PPRV5-NESTED-CONCEPT-01",
        "PPRV5-COORDINATED-SPOUSE-CHILDREN-01",
        "PPRV5-COORDINATED-CHILDREN-SPOUSE-01",
        "PPRV5-UNKNOWN-COMPLETE-SET-01",
    } <= ids


def test_v5_manifest_pins_current_production_composed_contract() -> None:
    cases, context = gate.load_gate_cases()
    schema = gate.production_schema()

    gate.verify_manifest(schema, context)

    assert gate.conservative_cost_ceiling(cases, context, schema) <= gate.MAX_CONSERVATIVE_COST_USD


def test_v5_nested_identity_oracle_preserves_literal_context() -> None:
    source = unit(
        selection("yo", "person"),
        facts=("Voy con unos papás del cole de {{ref:0}}.",),
        references=(KnowledgeReference(1, "related", "Cloe"),),
    )
    lookup = unit(selection("Cloe", "person", entity="Cloe"), lookup=True)
    result = RequestPlan((WriteAction((source, lookup)),), ())
    case = {
        "lineage": "nested_identity",
        "expect": {
            "note_type": "person",
            "mention": "Cloe",
            "entity": "Cloe",
            "forbidden_identity_terms": ["papás", "cole"],
        },
    }

    assert gate.evaluate_case(result, case) == (True, [])


def test_v5_coordinated_relation_oracle_requires_two_independent_scopes() -> None:
    spouse_relation = RelationalReference("mi mujer", "self", None, "one")
    children_relation = RelationalReference("mis hijos", "self", None, "complete_set")
    source = unit(
        selection("yo", "person"),
        facts=("Merendé con {{ref:0}} e hijos ({{ref:1}}).",),
        references=(
            KnowledgeReference(1, "companion", "mi mujer"),
            KnowledgeReference(
                None,
                "companion",
                "hijos",
                selection=selection("mis hijos", "person", relation=children_relation),
            ),
        ),
    )
    spouse = unit(selection("mi mujer", "person", relation=spouse_relation), lookup=True)
    result = RequestPlan((WriteAction((source, spouse)),), ())

    assert gate.evaluate_case(result, {"lineage": "coordinated_relations"}) == (True, [])


def test_v5_complete_set_oracle_keeps_unknown_group_semantic() -> None:
    relation = RelationalReference("mis primos de Canadá", "self", None, "complete_set")
    source = unit(
        selection("yo", "person"),
        facts=("Cené con mis primos de Canadá ({{ref:0}}).",),
        references=(
            KnowledgeReference(
                None,
                "companion",
                "mis primos de Canadá",
                selection=selection("mis primos de Canadá", "person", relation=relation),
            ),
        ),
    )
    result = RequestPlan((WriteAction((source,)),), ())

    assert gate.evaluate_case(result, {"lineage": "complete_set"}) == (True, [])
