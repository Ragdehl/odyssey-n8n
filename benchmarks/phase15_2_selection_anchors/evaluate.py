"""Fail-closed deterministic oracle for Phase 15.2 benchmark evidence."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from odyssey_core.request_planning import (
    KnowledgeUnit,
    LinkScope,
    RequestPlan,
    RequestPlanningError,
    RetrieveAction,
    WriteAction,
    validate_request_plan,
)

OracleHandler = Callable[[RequestPlan], list[str]]


def _contains(values: Sequence[str], term: str) -> bool:
    """Return whether a semantic term occurs in any free-text value."""
    return term.casefold() in " ".join(values).casefold()


def _filters(selection: Any) -> list[list[Any]]:
    """Convert deterministic filters to a comparison-friendly representation."""
    return [[item.field, item.op, item.value] for item in selection.filters]


def _exact_filters(selection: Any, expected: list[list[Any]]) -> list[str]:
    """Require exactly the expected deterministic filters, preserving their values."""
    return [] if _filters(selection) == expected else ["incorrect_filters"]


def _direct(selection: Any) -> list[str]:
    """Validate direct-note semantics shared by ordinary retrieval and writes."""
    return [] if selection.link_scope is None else ["unexpected_link_scope"]


def _one_retrieve(plan: RequestPlan) -> tuple[RetrieveAction | None, list[str]]:
    """Require exactly one retrieval action and return it for case-specific checks."""
    if len(plan.actions) != 1 or not isinstance(plan.actions[0], RetrieveAction):
        return None, ["expected_one_retrieve_action"]
    return plan.actions[0], []


def _one_write(plan: RequestPlan) -> tuple[KnowledgeUnit | None, list[str]]:
    """Require exactly one write action containing one unit."""
    if len(plan.actions) != 1 or not isinstance(plan.actions[0], WriteAction):
        return None, ["expected_one_write_action"]
    action = plan.actions[0]
    if len(action.units) != 1:
        return None, ["expected_one_knowledge_unit"]
    return action.units[0], []


def _entity_target(unit: KnowledgeUnit, *, entity: str | None, note_type: str | None) -> list[str]:
    """Validate nominal entity, canonical type, and direct target semantics."""
    findings: list[str] = []
    if unit.target.entity != entity:
        findings.append("incorrect_entity")
    if unit.target.type != note_type:
        findings.append("incorrect_target_type")
    findings += _direct(unit.target)
    return findings


def _handle_e01(plan: RequestPlan) -> list[str]:
    """Check explicit Marta identity and relationship mutation."""
    unit, findings = _one_write(plan)
    if unit is None:
        return findings
    findings += _entity_target(unit, entity="Marta", note_type="person")
    findings += _exact_filters(unit.target, [])
    if unit.intent != "record":
        findings.append("incorrect_intent")
    if [(c.field, c.op, c.value) for c in unit.properties] != [
        ("relationship_to_user", "set", "hermana")
    ]:
        findings.append("incorrect_relationship_mutation")
    if unit.facts or unit.tag_changes or unit.references:
        findings.append("unrelated_write_payload")
    return findings


def _handle_e02(plan: RequestPlan) -> list[str]:
    """Check explicit store identity and free-text closing-time knowledge."""
    unit, findings = _one_write(plan)
    if unit is None:
        return findings
    findings += _entity_target(unit, entity="Carrefour Balma", note_type="store")
    findings += _exact_filters(unit.target, [])
    if unit.intent != "record" or not _contains(unit.facts, "20:30"):
        findings.append("closing_time_fact_missing")
    if unit.properties:
        findings.append("invented_closing_time_property")
    return findings


def _handle_e03(plan: RequestPlan) -> list[str]:
    """Check contextual friend targeting, birth-year filters, and Lyon mutation."""
    unit, findings = _one_write(plan)
    if unit is None:
        return findings
    findings += _entity_target(unit, entity=None, note_type="person")
    findings += _exact_filters(
        unit.target, [["birth_date", "gte", "1990-01-01"], ["birth_date", "lt", "1991-01-01"]]
    )
    query = unit.target.query.casefold()
    if not all(term in query for term in ("amig", "marta", "1990")):
        findings.append("target_identity_context_missing")
    if unit.intent != "amend" or not _contains(unit.facts, "lyon"):
        findings.append("lyon_amendment_missing")
    if any("friend" in c.field or "amig" in c.field for c in unit.properties):
        findings.append("invented_relationship_property")
    return findings


def _handle_e04(plan: RequestPlan) -> list[str]:
    """Check contextual corner-store targeting and closing-time mutation."""
    unit, findings = _one_write(plan)
    if unit is None:
        return findings
    findings += _entity_target(unit, entity=None, note_type="store")
    findings += _exact_filters(unit.target, [])
    query = unit.target.query.casefold()
    if not all(term in query for term in ("tienda", "esquina")):
        findings.append("contextual_store_query_missing")
    if unit.intent != "amend" or not _contains(unit.facts, "20:30"):
        findings.append("closing_time_amendment_missing")
    return findings


def _handle_e05(plan: RequestPlan) -> list[str]:
    """Check direct n8n retrieval without concept fallback."""
    action, findings = _one_retrieve(plan)
    if action is None:
        return findings
    selection = action.plan
    if selection.entity != "n8n" or selection.type is not None:
        findings.append("incorrect_n8n_identity_or_type")
    findings += _exact_filters(selection, [])
    findings += _direct(selection)
    return findings


def _handle_e06(plan: RequestPlan) -> list[str]:
    """Check direct Marta retrieval without graph traversal."""
    action, findings = _one_retrieve(plan)
    if action is None:
        return findings
    selection = action.plan
    if selection.entity != "Marta" or selection.type != "person":
        findings.append("incorrect_marta_identity_or_type")
    findings += _exact_filters(selection, [])
    findings += _direct(selection)
    return findings


def _graph_action(plan: RequestPlan) -> tuple[RetrieveAction | None, LinkScope | None, list[str]]:
    """Require one retrieval whose graph scope can be checked by a case handler."""
    action, findings = _one_retrieve(plan)
    if action is None:
        return None, None, findings
    scope = action.plan.link_scope
    if scope is None:
        findings.append("missing_link_scope")
    return action, scope, findings


def _handle_g01(plan: RequestPlan) -> list[str]:
    """Check one-hop bidirectional related-note selection anchored on Marta."""
    action, scope, findings = _graph_action(plan)
    if action is None or scope is None:
        return findings
    if action.plan.entity is not None or action.plan.type is not None:
        findings.append("outer_selection_is_anchor")
    findings += _exact_filters(action.plan, [])
    anchor = scope.anchor
    if anchor.entity != "Marta" or anchor.type != "person" or anchor.filters:
        findings.append("incorrect_marta_anchor")
    if scope.direction != "both":
        findings.append("incorrect_graph_direction")
    if scope.max_depth != 1:
        findings.append("incorrect_graph_depth")
    return findings


def _handle_g02(plan: RequestPlan) -> list[str]:
    """Check incoming graph selection anchored by person birth date."""
    action, scope, findings = _graph_action(plan)
    if action is None or scope is None:
        return findings
    if action.plan.entity is not None or action.plan.type is not None:
        findings.append("outer_selection_is_anchor")
    findings += _exact_filters(action.plan, [])
    anchor = scope.anchor
    if anchor.entity is not None or anchor.type != "person":
        findings.append("incorrect_property_anchor_identity")
    findings += _exact_filters(anchor, [["birth_date", "eq", "1990-05-03"]])
    if scope.direction != "incoming":
        findings.append("incorrect_graph_direction")
    if scope.max_depth != 1:
        findings.append("incorrect_graph_depth")
    return findings


def _handle_g03(plan: RequestPlan) -> list[str]:
    """Check independent June result filters and birth-date anchor filters."""
    action, scope, findings = _graph_action(plan)
    if action is None or scope is None:
        return findings
    outer = action.plan
    if outer.entity is not None or outer.type != "journal_entry":
        findings.append("incorrect_outer_identity_or_type")
    findings += _exact_filters(
        outer, [["entry_date", "gte", "2026-06-01"], ["entry_date", "lt", "2026-07-01"]]
    )
    anchor = scope.anchor
    if anchor.entity is not None or anchor.type != "person":
        findings.append("incorrect_anchor_identity_or_type")
    findings += _exact_filters(anchor, [["birth_date", "eq", "1990-05-03"]])
    if scope.direction != "both":
        findings.append("incorrect_graph_direction")
    if scope.max_depth != 1:
        findings.append("incorrect_graph_depth")
    return findings


def _handle_g04(plan: RequestPlan) -> list[str]:
    """Check explicit two-hop bidirectional graph scope anchored on Marta."""
    _action, scope, findings = _graph_action(plan)
    if scope is None:
        return findings
    if scope.anchor.entity != "Marta" or scope.anchor.type != "person" or scope.anchor.filters:
        findings.append("incorrect_marta_anchor")
    if scope.direction != "both":
        findings.append("incorrect_graph_direction")
    if scope.max_depth != 2:
        findings.append("explicit_two_hop_depth_not_preserved")
    return findings


def _handle_t01(plan: RequestPlan) -> list[str]:
    """Check semantic idea/reflection words do not create tag operations."""
    if (
        len(plan.actions) != 2
        or not isinstance(plan.actions[0], RetrieveAction)
        or not isinstance(plan.actions[1], WriteAction)
    ):
        return ["retrieve_write_decomposition_missing"]
    findings: list[str] = []
    if any(item.field == "tags" for item in plan.actions[0].plan.filters):
        findings.append("semantic_tag_filter")
    if any(unit.tag_changes for unit in plan.actions[1].units):
        findings.append("semantic_tag_mutation")
    return findings


def _handle_t02(plan: RequestPlan) -> list[str]:
    """Check explicit canonical tag retrieval."""
    action, findings = _one_retrieve(plan)
    if action is None:
        return findings
    if _filters(action.plan) != [["tags", "contains", "idea"]]:
        findings.append("explicit_tag_filter_missing_or_inexact")
    return findings


def _handle_t03(plan: RequestPlan) -> list[str]:
    """Check ordered add/remove tag units and preserved relationship mutation."""
    if len(plan.actions) != 1 or not isinstance(plan.actions[0], WriteAction):
        return ["expected_one_write_action"]
    units = plan.actions[0].units
    if len(units) != 2:
        return ["tag_mutation_sequence_collapsed_or_split"]
    findings: list[str] = []
    first, second = units
    for unit in units:
        findings += _entity_target(unit, entity="Marta", note_type="person")
        findings += _exact_filters(unit.target, [])
    if first.intent != "amend" or [(p.field, p.op, p.value) for p in first.properties] != [
        ("relationship_to_user", "set", "hermana")
    ]:
        findings.append("relationship_amendment_missing")
    if [(c.op, c.value) for c in first.tag_changes] != [("add", "review")]:
        findings.append("tag_addition_missing_or_misordered")
    if second.intent != "remove" or second.properties:
        findings.append("tag_removal_unit_has_wrong_payload")
    if [(c.op, c.value) for c in second.tag_changes] != [("remove", "review")]:
        findings.append("tag_removal_missing_or_misordered")
    return findings


def _handle_r01(plan: RequestPlan) -> list[str]:
    """Check schema-aware birth-date property extraction regression."""
    unit, findings = _one_write(plan)
    if unit is None:
        return findings
    findings += _entity_target(unit, entity="Marta", note_type="person")
    findings += _exact_filters(unit.target, [])
    if unit.intent != "record":
        findings.append("incorrect_intent")
    if [(p.field, p.op, p.value) for p in unit.properties] != [("birth_date", "set", "1990-05-03")]:
        findings.append("birth_date_property_missing_or_wrong")
    if unit.facts:
        findings.append("birth_date_not_kept_structurally")
    return findings


def _handle_r02(plan: RequestPlan) -> list[str]:
    """Check retrieval/write decomposition and n8n ticket knowledge regression."""
    if (
        len(plan.actions) != 2
        or not isinstance(plan.actions[0], RetrieveAction)
        or not isinstance(plan.actions[1], WriteAction)
    ):
        return ["retrieve_write_decomposition_missing"]
    retrieve, write = plan.actions
    findings: list[str] = []
    if (
        retrieve.plan.entity != "n8n"
        or retrieve.plan.type is not None
        or retrieve.plan.filters
        or retrieve.plan.link_scope is not None
    ):
        findings.append("incorrect_retrieve_selection")
    if len(write.units) != 1:
        findings.append("unexpected_write_unit_count")
    else:
        unit = write.units[0]
        findings += _entity_target(unit, entity="n8n", note_type=None)
        if unit.intent != "record" or not _contains(unit.facts, "tickets"):
            findings.append("write_knowledge_missing")
    return findings


_HANDLERS: dict[str, OracleHandler] = {
    "marta_entity": _handle_e01,
    "carrefour_entity": _handle_e02,
    "contextual_person": _handle_e03,
    "contextual_store": _handle_e04,
    "n8n_direct": _handle_e05,
    "marta_direct": _handle_e06,
    "marta_graph": _handle_g01,
    "property_anchor": _handle_g02,
    "independent_filters": _handle_g03,
    "two_hops": _handle_g04,
    "semantic_no_tags": _handle_t01,
    "tag_retrieval": _handle_t02,
    "tag_mutations": _handle_t03,
    "property_regression": _handle_r01,
    "mixed_regression": _handle_r02,
}


def evaluate(expectation: str, payload: Any, schema: dict[str, Any]) -> tuple[str, list[str]]:
    """Validate a saved model output against a closed expectation-specific oracle.

    Unknown expectations fail closed even when the payload is structurally valid.
    """
    if expectation not in _HANDLERS:
        return "FAIL", ["unknown_expectation"]
    try:
        plan = validate_request_plan(payload, schema)
    except RequestPlanningError as error:
        return "INVALID", [f"invalid_plan:{error}"]
    findings = _HANDLERS[expectation](plan)
    return ("FAIL" if findings else "PASS"), findings
