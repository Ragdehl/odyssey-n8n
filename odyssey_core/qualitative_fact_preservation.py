"""E2 Core-owned lossless daypart preservation for unambiguous Day facts.

This does NOT interpret linguistic phrases or choose a write target. It only
preserves one source-exact qualifier on the sole already-planned dated fact,
under the canonical Temporal proof and before the ordinary preflight/Writer.
Never fabricates a time or changes NoteSchema, links, ownership or identity.
"""

from __future__ import annotations

from dataclasses import replace

from .execution_context import ContextContractError, ExecutionContext
from .request_planning import KnowledgeUnit, RequestPlan, WriteAction


def preserve_qualitative_day_facts(plan: RequestPlan, *, context: ExecutionContext) -> RequestPlan:
    """Preserve one uniquely scoped natural time qualifier in a Calendar Day fact.

    If the plan has another shape, only allow it unchanged if the literal
    qualifier is already recorded; otherwise refuse an ambiguous loss rather
    than attaching the qualifier to the wrong person's event or date.
    """
    if not isinstance(plan, RequestPlan) or not isinstance(context, ExecutionContext):
        raise ContextContractError("Daypart preservation requires Core plan and E2 context")
    if not context.qualitative_times:
        return plan
    active_writes = [action for action in plan.actions if isinstance(action, WriteAction)]
    if not active_writes:
        return plan  # reads do not require a stored fact
    if len(context.qualitative_times) != 1:
        raise ContextContractError("Multiple qualitative dates need explicit fact ownership")
    qualifier = context.qualitative_times[0]
    exact = [item for domain in context.domains for item in domain.temporal_references()]
    if (
        len(exact) != 1
        or exact[0].source_text != qualifier.source_text
        or exact[0].value != qualifier.date
        or qualifier.source_text not in context.source
    ):
        raise ContextContractError("Daypart lacks one matching exact Temporal date proof")
    if len(active_writes) != 1 or len(active_writes[0].units) == 0:
        raise ContextContractError("Daypart requires one scoped Core write")
    action = active_writes[0]
    factual = [
        i for i, unit in enumerate(action.units) if unit.facts and not unit.reference_lookup_only
    ]
    if len(factual) != 1:
        raise ContextContractError("Daypart has no unique fact owner")
    fact_index = factual[0]
    unit: KnowledgeUnit = action.units[fact_index]
    if (
        unit.target.type != "calendar_day"
        or unit.target.query != qualifier.date
        or len(unit.facts) != 1
        or len(unit.fact_temporal_anchors) != 1
        or len(unit.fact_temporal_anchors[0]) != 1
        or unit.fact_temporal_anchors[0][0].date != qualifier.date
        or unit.fact_temporal_anchors[0][0].time is not None
    ):
        raise ContextContractError("Daypart cannot be safely attached to a dated Day fact")
    text = unit.facts[0]
    if qualifier.qualifier.casefold() in text.casefold():
        return plan  # Core already retained the exact qualitative expression
    if not text.strip() or text.count("{{ref:") != text.count("}}"):
        raise ContextContractError("Daypart fact text is invalid")
    # Parentheses preserve the exact wording without a language-dependent
    # grammatical rewrite. Core's existing fact validation/coverage still runs.
    trimmed = text.rstrip()
    punctuation = trimmed[-1] if trimmed.endswith((".", "!", "?")) else ""
    stem = trimmed[:-1].rstrip() if punctuation else trimmed
    enriched = f"{stem} ({qualifier.qualifier}){punctuation}"
    changed_unit = replace(unit, facts=(enriched,))
    units = tuple(
        changed_unit if i == fact_index else original for i, original in enumerate(action.units)
    )
    changed_action = replace(action, units=units)
    return replace(
        plan, actions=tuple(changed_action if item is action else item for item in plan.actions)
    )
