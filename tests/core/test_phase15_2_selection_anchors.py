"""Focused deterministic coverage for Phase 15.2 selection and explicit tag contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odyssey_core.request_planning import (
    LinkScope,
    RequestPlanningError,
    RetrieveAction,
    TagChange,
    validate_request_plan,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def schema() -> dict:
    """Load the canonical schema used to derive the Phase 15.2 contract."""
    return json.loads((ROOT / "config/note-schema.json").read_text(encoding="utf-8"))


def selection(
    query: str,
    *,
    entity: str | None = None,
    note_type: str | None = None,
    filters: list[dict] | None = None,
    link_scope: dict | None = None,
) -> dict:
    """Build a complete raw Phase 15.2 selection fixture."""
    return {
        "entity": entity,
        "query": query,
        "type": note_type,
        "filters": filters or [],
        "link_scope": link_scope,
    }


def anchor(query: str, **kwargs: object) -> dict:
    """Build the intentionally non-recursive graph-anchor selector fixture."""
    return {key: value for key, value in selection(query, **kwargs).items() if key != "link_scope"}


def output(*actions: dict) -> dict:
    """Build a complete raw RequestPlan fixture."""
    return {"actions": list(actions), "limitations": []}


def retrieve(query: str, **kwargs: object) -> dict:
    """Build one raw retrieval action fixture."""
    return {"kind": "retrieve", "plan": selection(query, **kwargs)}


def unit(
    query: str,
    *,
    entity: str | None = None,
    note_type: str | None = None,
    filters: list[dict] | None = None,
    intent: str = "record",
    properties: list[dict] | None = None,
    tag_changes: list[dict] | None = None,
    facts: list[str] | None = None,
) -> dict:
    """Build one raw write unit fixture with no in-plan references."""
    return {
        "target": selection(query, entity=entity, note_type=note_type, filters=filters),
        "intent": intent,
        "properties": properties or [],
        "tag_changes": tag_changes or [],
        "facts": facts or [],
        "references": [],
    }


def write(*units: dict) -> dict:
    """Build one raw non-executing write action."""
    return {"kind": "write", "units": list(units)}


def test_explicit_nominal_entities_and_contextual_targets(schema: dict) -> None:
    """Preserve safe names while leaving contextual descriptions unresolved."""
    plan = validate_request_plan(
        output(
            write(unit("Marta", entity="Marta", note_type="person", facts=["Es mi hermana."])),
            write(
                unit(
                    "Carrefour Balma",
                    entity="Carrefour Balma",
                    note_type="store",
                    facts=["Cierra a las 20:30."],
                )
            ),
            write(
                unit(
                    "amiga de Marta nacida en 1990",
                    note_type="person",
                    filters=[
                        {"field": "birth_date", "op": "gte", "value": "1990-01-01"},
                        {"field": "birth_date", "op": "lt", "value": "1991-01-01"},
                    ],
                    intent="amend",
                    facts=["Ahora vive en Lyon."],
                )
            ),
            write(unit("tienda de la esquina", intent="amend", facts=["Cierra a las 20:30."])),
            retrieve("n8n", entity="n8n"),
        ),
        schema,
    )
    assert plan.actions[0].units[0].target.entity == "Marta"  # type: ignore[union-attr]
    assert plan.actions[1].units[0].target.entity == "Carrefour Balma"  # type: ignore[union-attr]
    assert plan.actions[2].units[0].target.entity is None  # type: ignore[union-attr]
    assert plan.actions[3].units[0].target.entity is None  # type: ignore[union-attr]
    assert isinstance(plan.actions[4], RetrieveAction) and plan.actions[4].plan.type is None


def test_direct_note_and_graph_intent_are_distinct(schema: dict) -> None:
    """Keep direct Marta retrieval untraversed and represent explicit graph selection only."""
    related = {
        "anchor": anchor("Marta", entity="Marta", note_type="person"),
        "direction": "both",
        "max_depth": 1,
    }
    plan = validate_request_plan(
        output(
            retrieve("Marta", entity="Marta"),
            retrieve("notas relacionadas con Marta", link_scope=related),
        ),
        schema,
    )
    direct, graph = plan.actions
    assert isinstance(direct, RetrieveAction) and direct.plan.link_scope is None
    assert isinstance(graph, RetrieveAction) and isinstance(graph.plan.link_scope, LinkScope)
    assert graph.plan.link_scope.anchor.entity == "Marta"


def test_independent_graph_anchor_filters_and_requested_depth(schema: dict) -> None:
    """Validate non-nominal anchors independently from result selection restrictions."""
    scope = {
        "anchor": anchor(
            "persona nacida el 3 de mayo de 1990",
            note_type="person",
            filters=[{"field": "birth_date", "op": "eq", "value": "1990-05-03"}],
        ),
        "direction": "incoming",
        "max_depth": 2,
    }
    plan = validate_request_plan(
        output(
            retrieve(
                "entradas de diario de junio relacionadas",
                note_type="journal_entry",
                filters=[
                    {"field": "entry_date", "op": "gte", "value": "2026-06-01"},
                    {"field": "entry_date", "op": "lt", "value": "2026-07-01"},
                ],
                link_scope=scope,
            )
        ),
        schema,
    )
    action = plan.actions[0]
    assert isinstance(action, RetrieveAction)
    assert action.plan.link_scope is not None
    assert action.plan.link_scope.anchor.entity is None
    assert action.plan.link_scope.direction == "incoming"
    assert action.plan.link_scope.max_depth == 2


def test_malformed_graph_shapes_fail_closed(schema: dict) -> None:
    """Reject unsupported direction/depth and recursive anchor structures."""
    malformed = [
        {"anchor": anchor("Marta"), "direction": "sideways", "max_depth": 1},
        {"anchor": anchor("Marta"), "direction": "both", "max_depth": 0},
        {
            "anchor": anchor("Marta") | {"link_scope": None},
            "direction": "both",
            "max_depth": 1,
        },
    ]
    for scope in malformed:
        with pytest.raises(RequestPlanningError):
            validate_request_plan(output(retrieve("related", link_scope=scope)), schema)


def test_controlled_tags_are_item_level_and_fail_closed(schema: dict) -> None:
    """Allow only canonical tag filters and compatible add/remove item mutations."""
    plan = validate_request_plan(
        output(
            retrieve("ideas sobre Odyssey"),
            retrieve(
                "notas con el tag idea",
                filters=[{"field": "tags", "op": "contains", "value": "idea"}],
            ),
            write(unit("reflexión", facts=["Una reflexión."])),
            write(unit("Marta", entity="Marta", tag_changes=[{"op": "add", "value": "review"}])),
            write(
                unit(
                    "Marta",
                    entity="Marta",
                    intent="remove",
                    tag_changes=[{"op": "remove", "value": "review"}],
                )
            ),
        ),
        schema,
    )
    assert isinstance(plan.actions[0], RetrieveAction) and plan.actions[0].plan.filters == ()
    assert plan.actions[2].units[0].tag_changes == ()  # type: ignore[union-attr]
    assert plan.actions[3].units[0].tag_changes == (TagChange("add", "review"),)  # type: ignore[union-attr]
    assert plan.actions[4].units[0].tag_changes == (TagChange("remove", "review"),)  # type: ignore[union-attr]
    invalid = [
        retrieve("unknown tag", filters=[{"field": "tags", "op": "contains", "value": "unknown"}]),
        write(unit("Marta", tag_changes=[{"op": "add", "value": "unknown"}])),
        write(
            unit(
                "Marta",
                tag_changes=[{"op": "add", "value": "review"}, {"op": "remove", "value": "review"}],
            )
        ),
        write(unit("Marta", intent="delete", tag_changes=[{"op": "remove", "value": "review"}])),
    ]
    for action in invalid:
        with pytest.raises(RequestPlanningError):
            validate_request_plan(output(action), schema)
