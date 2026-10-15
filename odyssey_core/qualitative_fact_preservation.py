"""E2 lossless Core daypart preservation for provably owned dated facts.

Only associates already-proven dates and source-exact qualitative wording with
already-planned canonical Calendar Day facts. Never chooses identity, targets,
language-specific rewrite, or clock. The existing Core Coverage and Writer
remain authoritative after this immutable, pre-write augmentation.
"""

from __future__ import annotations

from dataclasses import replace

from .execution_context import ContextContractError, ExecutionContext, QualitativeTime
from .request_planning import RequestPlan, WriteAction


def _qualified_day_fact(text: str, qualifier: str) -> str:
    """Only augment an existing fact, without changing links or punctuation."""
    if qualifier.casefold() in text.casefold():
        return text
    if not text.strip() or text.count("{{ref:") != text.count("}}"):
        raise ContextContractError("Daypart fact text is invalid")
    # Preserve the original literal as-is, using language-neutral parenthesis
    # rather than guessing where a Spanish/French/English adverb must go.
    trimmed = text.rstrip()
    punctuation = trimmed[-1] if trimmed.endswith((".", "!", "?")) else ""
    stem = trimmed[:-1].rstrip() if punctuation else trimmed
    return f"{stem} ({qualifier}){punctuation}"


def _unique_qualified_fact_owner(plan: RequestPlan, qualifier: QualitativeTime) -> tuple[int, int]:
    """Locate exactly one already-planned Day fact using the verified date."""
    possibilities: list[tuple[int, int]] = []
    for action_index, action in enumerate(plan.actions):
        if not isinstance(action, WriteAction):
            continue
        for unit_index, unit in enumerate(action.units):
            if unit.target.type != "calendar_day" or unit.target.query != qualifier.date:
                continue
            # Two facts of the SAME Day do not identify which owns this phrase.
            # Do not use list order or lexical resemblance as an ownership guess.
            if (
                unit.reference_lookup_only
                or len(unit.facts) != 1
                or len(unit.fact_temporal_anchors) != 1
                or len(unit.fact_temporal_anchors[0]) != 1
                or unit.fact_temporal_anchors[0][0].date != qualifier.date
                or unit.fact_temporal_anchors[0][0].time is not None
            ):
                raise ContextContractError("Daypart cannot be safely attached to a dated Day fact")
            possibilities.append((action_index, unit_index))
    if len(possibilities) != 1:
        raise ContextContractError("Daypart has no unique fact owner")
    return possibilities[0]


def preserve_qualitative_day_facts(plan: RequestPlan, *, context: ExecutionContext) -> RequestPlan:
    """Map source-proven qualifiers to different uniquely dated Day facts.

    Multiple different dates are supported. Repeated dates, duplicated proof,
    same-day multiple facts, or non-Day mutation ownership remain ambiguous.
    All mappings are proven before returning ANY amended plan, so one unsafe
    qualifier cannot lead to a partial write of an earlier safe qualifier.
    """
    if not isinstance(plan, RequestPlan) or not isinstance(context, ExecutionContext):
        raise ContextContractError("Daypart preservation requires Core plan and E2 context")
    if not context.qualitative_times:
        return plan
    if not any(isinstance(action, WriteAction) for action in plan.actions):
        return plan  # A read-only request does not require durable facts.
    qualifiers = context.qualitative_times
    if len({item.date for item in qualifiers}) != len(qualifiers):
        raise ContextContractError("Multiple qualitative dates need explicit fact ownership")

    original_evidence = [
        item for domain in context.domains for item in domain.temporal_references()
    ]
    replacements: dict[tuple[int, int], str] = {}
    for qualifier in qualifiers:
        matching_source = [
            item for item in original_evidence if item.source_text == qualifier.source_text
        ]
        if (
            len(matching_source) != 1
            or matching_source[0].value != qualifier.date
            or context.source.count(qualifier.source_text) != 1
        ):
            raise ContextContractError("Daypart lacks one matching exact Temporal date proof")
        key = _unique_qualified_fact_owner(plan, qualifier)
        if key in replacements:
            raise ContextContractError("Daypart has no unique fact owner")
        action_index, unit_index = key
        action = plan.actions[action_index]
        unit = action.units[unit_index]
        replacements[key] = _qualified_day_fact(unit.facts[0], qualifier.qualifier)

    updated_actions = []
    changed = False
    for action_index, action in enumerate(plan.actions):
        if not isinstance(action, WriteAction):
            updated_actions.append(action)
            continue
        units = []
        for unit_index, unit in enumerate(action.units):
            updated_text = replacements.get((action_index, unit_index))
            if updated_text is not None and updated_text != unit.facts[0]:
                changed = True
                units.append(replace(unit, facts=(updated_text,)))
            else:
                units.append(unit)
        updated_actions.append(
            replace(action, units=tuple(units)) if tuple(units) != action.units else action
        )
    return replace(plan, actions=tuple(updated_actions)) if changed else plan
