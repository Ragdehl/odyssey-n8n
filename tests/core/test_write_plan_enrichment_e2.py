"""Pure generic Core plan enrichment; no application-specific planning authority."""

from __future__ import annotations

from dataclasses import replace

import pytest

from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RequestPlan,
    RequestPlanningError,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.write_plan_enrichment import (
    CoreLinkFactSpec,
    add_core_reference_facts,
    ensure_visible_core_action_fact,
)


def plan(kind="document", entity="Preparar resumen"):
    return RequestPlan(
        (
            WriteAction(
                (
                    KnowledgeUnit(
                        SelectionCriteria(entity, entity, kind, (), None),
                        "record",
                        (),
                        (),
                        (),
                        (),
                    ),
                )
            ),
        ),
        (),
    )


def test_visible_action_is_core_owned_and_does_not_duplicate_existing_fact():
    original = plan("task", "Preparar informe")
    prepared = ensure_visible_core_action_fact(original)
    primary = prepared.actions[0].units[0]
    assert primary.force_create and primary.facts == ("Preparar informe.",)
    assert primary.fact_temporal_anchors == ((),)
    assert original.actions[0].units[0].facts == ()
    assert ensure_visible_core_action_fact(prepared) == prepared


@pytest.mark.parametrize("kind", ["task", "project", "document", "person"])
def test_reference_enrichment_is_generic_for_any_note_type(kind):
    original = plan(kind)
    roles = (
        CoreLinkFactSpec("Responsable", "Nadia", "person", "assignee"),
        CoreLinkFactSpec("Documento", "Informe Omega", "document", "related_document"),
    )
    written = add_core_reference_facts(original, roles)
    units = written.actions[0].units
    assert len(units) == 3
    assert units[0].target.type == kind
    assert units[0].facts == ("Responsable: {{ref:0}}.", "Documento: {{ref:1}}.")
    assert units[0].references == (
        KnowledgeReference(1, "assignee", "Nadia"),
        KnowledgeReference(2, "related_document", "Informe Omega"),
    )
    assert units[1].reference_lookup_only and units[2].reference_lookup_only
    assert units[1].target.type == "person" and units[2].target.type == "document"
    assert original.actions[0].units[0].facts == ()


def test_existing_reference_slots_are_preserved_when_appends_follow():
    original = plan()
    action = original.actions[0]
    consumer = replace(
        action.units[0],
        facts=("Vi a {{ref:0}}.",),
        references=(KnowledgeReference(1, "person", "Nadia"),),
        fact_temporal_anchors=((),),
    )
    helper = KnowledgeUnit(
        SelectionCriteria("Nadia", "Nadia", "person", (), None),
        "record",
        (),
        (),
        (),
        (),
        reference_lookup_only=True,
    )
    original = replace(original, actions=(replace(action, units=(consumer, helper)),))
    expanded = add_core_reference_facts(
        original, (CoreLinkFactSpec("Fuente", "Omega", "document", "source"),)
    )
    consumer = expanded.actions[0].units[0]
    assert consumer.facts[-1] == "Fuente: {{ref:1}}."
    assert consumer.references[-1] == KnowledgeReference(2, "source", "Omega")


@pytest.mark.parametrize(
    "invalid",
    [
        CoreLinkFactSpec("", "Nadia", "person", "assignee"),
        CoreLinkFactSpec("Responsable", "", "person", "assignee"),
        CoreLinkFactSpec("[[Actor]]", "Nadia", "person", "assignee"),
        CoreLinkFactSpec("Responsable", "[[Nadia]]", "person", "assignee"),
        CoreLinkFactSpec("Responsable", "Nadia" * 50, "person", "assignee"),
    ],
)
def test_bad_link_specs_do_not_change_canonical_plan(invalid):
    original = plan()
    with pytest.raises(RequestPlanningError):
        add_core_reference_facts(original, (invalid,))
    assert original.actions[0].units[0].facts == ()
