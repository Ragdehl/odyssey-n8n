"""Closed deterministic oracle for Phase 15.3 delegation evidence."""

from __future__ import annotations

from typing import Any

from odyssey_core.request_planning import (
    DelegateAction,
    RequestPlanningError,
    RetrieveAction,
    WriteAction,
    validate_request_plan,
)


def _contains(values: tuple[str, ...], *terms: str) -> bool:
    """Return whether every material term occurs in retained free text."""
    rendered = " ".join(values).casefold()
    return all(term.casefold() in rendered for term in terms)


def _one(plan: Any, action_type: type[Any]) -> tuple[Any | None, list[str]]:
    """Require one action of the expected direct or delegated type."""
    if len(plan.actions) != 1 or not isinstance(plan.actions[0], action_type):
        return None, ["incorrect_action_kind_or_count"]
    return plan.actions[0], []


def _related_selection(selection: Any) -> bool:
    """Return whether selection exactly preserves canonical one-hop Marta graph semantics."""
    if (
        selection is None
        or selection.entity is not None
        or selection.type is not None
        or selection.filters
        or selection.link_scope is None
    ):
        return False
    scope = selection.link_scope
    return bool(
        scope.anchor.entity == "Marta"
        and scope.anchor.type == "person"
        and not scope.anchor.filters
        and scope.direction == "both"
        and scope.max_depth == 1
    )


def _delegate(plan: Any, *, selection_required: bool = False) -> list[str]:
    """Validate one generic delegation without a concrete application choice."""
    action, findings = _one(plan, DelegateAction)
    if action is None:
        return findings
    if not action.request.strip():
        findings.append("delegated_request_missing")
    if selection_required:
        if not _related_selection(action.selection):
            findings.append("related_selection_missing")
    return findings


def _retrieve(plan: Any, *, related: bool = False) -> list[str]:
    """Validate one direct retrieval and optional existing related-note semantics."""
    action, findings = _one(plan, RetrieveAction)
    if action is None:
        return findings
    if related:
        if not _related_selection(action.plan):
            findings.append("phase15_2_link_scope_missing_or_wrong")
    return findings


def _write(plan: Any, *, terms: tuple[str, ...]) -> list[str]:
    """Validate one direct write retaining material knowledge in a write unit."""
    action, findings = _one(plan, WriteAction)
    if action is None:
        return findings
    if not action.units or not any(_contains(unit.facts, *terms) for unit in action.units):
        findings.append("write_knowledge_missing")
    return findings


def _mixed_direct(plan: Any) -> list[str]:
    """Check Phase 15.2 retrieve/write regression without delegation."""
    if (
        len(plan.actions) != 2
        or not isinstance(plan.actions[0], RetrieveAction)
        or not isinstance(plan.actions[1], WriteAction)
    ):
        return ["retrieve_write_order_missing"]
    retrieve, write = plan.actions
    findings: list[str] = []
    if (
        retrieve.plan.entity != "n8n"
        or retrieve.plan.type is not None
        or retrieve.plan.link_scope is not None
    ):
        findings.append("n8n_retrieval_semantics_missing")
    if not write.units or not _contains(write.units[0].facts, "tickets"):
        findings.append("ticket_write_missing")
    return findings


def _mixed_delegate_write(plan: Any) -> list[str]:
    """Check computation delegation precedes independent budget write without dataflow."""
    if (
        len(plan.actions) != 2
        or not isinstance(plan.actions[0], DelegateAction)
        or not isinstance(plan.actions[1], WriteAction)
    ):
        return ["delegate_write_order_missing"]
    if not plan.actions[1].units or not _contains(plan.actions[1].units[0].facts, "presupuesto"):
        return ["independent_budget_write_missing"]
    return []


_DELEGATES = {
    "purchase_count",
    "price_average",
    "ticket_analysis",
    "translation",
    "purchase_total",
    "spending_comparison",
}
_RETRIEVES = {
    "marta_retrieve",
    "purchase_retrieve",
    "price_retrieve",
    "purchase_memory_retrieve",
    "purchase_year_retrieve",
    "spending_retrieve",
}


def evaluate(expectation: str, payload: Any, schema: dict[str, Any]) -> tuple[str, list[str]]:
    """Evaluate one output with an explicit fail-closed Phase 15.3 expectation handler."""
    try:
        plan = validate_request_plan(payload, schema)
    except RequestPlanningError as error:
        return "INVALID", [f"invalid_plan:{error}"]
    if expectation in _DELEGATES:
        findings = _delegate(plan)
    elif expectation in _RETRIEVES:
        findings = _retrieve(plan)
    elif expectation == "related_retrieve":
        findings = _retrieve(plan, related=True)
    elif expectation == "related_count":
        findings = _delegate(plan, selection_required=True)
    elif expectation == "marta_write":
        findings = _write(plan, terms=("lyon",))
    elif expectation == "comparison_intention_write":
        findings = _write(plan, terms=("compar", "carrefour", "lidl"))
    elif expectation == "mixed_direct":
        findings = _mixed_direct(plan)
    elif expectation == "mixed_delegate_write":
        findings = _mixed_delegate_write(plan)
    else:
        return "FAIL", ["unknown_expectation"]
    return ("FAIL" if findings else "PASS"), findings
