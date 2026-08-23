"""Narrow deterministic oracle for Phase 15.2 benchmark evidence."""

from __future__ import annotations

from typing import Any

from odyssey_core.request_planning import RequestPlanningError, validate_request_plan


def evaluate(expectation: str, payload: Any, schema: dict[str, Any]) -> tuple[str, list[str]]:
    """Validate output locally and check only the focused acceptance invariant for its case."""
    try:
        plan = validate_request_plan(payload, schema)
    except RequestPlanningError as error:
        return "INVALID", [f"invalid_plan:{error}"]
    actions = plan.actions
    findings: list[str] = []
    if expectation in {"marta_entity", "carrefour_entity"}:
        expected = "Marta" if expectation == "marta_entity" else "Carrefour Balma"
        if not actions or actions[0].units[0].target.entity != expected:  # type: ignore[union-attr]
            findings.append("missing_explicit_entity")
    elif expectation.startswith("contextual_"):
        if not actions or actions[0].units[0].target.entity is not None:  # type: ignore[union-attr]
            findings.append("contextual_target_promoted_to_entity")
    elif expectation in {"n8n_direct", "marta_direct"}:
        if not actions or actions[0].plan.link_scope is not None:  # type: ignore[union-attr]
            findings.append("direct_note_became_graph_scope")
    elif expectation in {"marta_graph", "property_anchor", "independent_filters", "two_hops"}:
        scope = actions[0].plan.link_scope if actions else None  # type: ignore[union-attr]
        if scope is None:
            findings.append("missing_link_scope")
        elif expectation == "two_hops" and scope.max_depth != 2:
            findings.append("two_hop_depth_not_preserved")
    elif expectation == "semantic_no_tags":
        if any(
            filter.field == "tags"
            for action in actions
            if hasattr(action, "plan")
            for filter in action.plan.filters
        ):
            findings.append("semantic_tag_filter")
        if any(
            change
            for action in actions
            if hasattr(action, "units")
            for unit in action.units
            for change in unit.tag_changes
        ):
            findings.append("semantic_tag_mutation")
    elif expectation == "tag_retrieval":
        if not any(
            filter.field == "tags" and filter.value == "idea"
            for action in actions
            if hasattr(action, "plan")
            for filter in action.plan.filters
        ):
            findings.append("missing_explicit_tag_filter")
    elif expectation == "tag_mutations":
        changes = [
            change
            for action in actions
            if hasattr(action, "units")
            for unit in action.units
            for change in unit.tag_changes
        ]
        if not any(
            change.op == "add" and change.value == "review" for change in changes
        ) or not any(change.op == "remove" and change.value == "review" for change in changes):
            findings.append("missing_explicit_tag_changes")
    return ("FAIL" if findings else "PASS"), findings
