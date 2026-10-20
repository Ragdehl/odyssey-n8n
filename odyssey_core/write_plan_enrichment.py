"""Shared Core plan shaping for already-interpreted, bounded reference facts.

A domain application may describe its own reference labels/roles, but only Core
constructs RequestPlan KnowledgeUnits, symbolic references and visible facts.
These transformations are PURE; ordinary Core preflight/Writer remains the
sole authority for identity selection, mutation and canonical Markdown.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    RequestPlan,
    RequestPlanningError,
    SelectionCriteria,
    WriteAction,
)


@dataclass(frozen=True, slots=True)
class CoreLinkFactSpec:
    label: str
    mention: str
    target_type: str
    reference_role: str
    # Non-empty only when the caller already holds a fresh canonical Core
    # receipt; E3 write guard must check the precise target ID at time of use.
    canonical_target_name: str | None = None


def _sole_primary(plan: RequestPlan) -> tuple[WriteAction, list[KnowledgeUnit], int]:
    if len(plan.actions) != 1 or not isinstance(plan.actions[0], WriteAction):
        raise RequestPlanningError("One Core write action required for plan enrichment")
    action = plan.actions[0]
    units = list(action.units)
    primaries = [i for i, unit in enumerate(units) if not unit.reference_lookup_only]
    if len(primaries) != 1:
        raise RequestPlanningError("One source-owned primary fact target required")
    return action, units, primaries[0]


def ensure_visible_core_action_fact(plan: RequestPlan) -> RequestPlan:
    """Preserve an existing linked action or insert one plain-text action.

    The target label is model-proposed; no new identity or task obligation is
    invented here. The owning domain application separately validates its
    CREATE operation and target type before asking Core to enrich the plan.
    """
    action, units, index = _sole_primary(plan)
    unit = replace(units[index], force_create=True)
    label = (unit.target.entity or unit.target.query).strip()
    if not label:
        raise RequestPlanningError("Core create target has no visible action wording")
    if label[-1] not in ".!?":
        label += "."
    facts = list(unit.facts)
    anchors = list(unit.fact_temporal_anchors)
    if not anchors and facts:
        anchors = [() for _ in facts]
    elif len(anchors) != len(facts):
        raise RequestPlanningError("Core facts and temporal anchors are misaligned")
    normalized_label = label.rstrip(".!?").strip().casefold()

    def visible_source_fact(fact: str) -> str:
        rendered = fact
        for pos, ref in enumerate(unit.references):
            rendered = rendered.replace(f"{{{{ref:{pos}}}}}", ref.mention)
        return rendered.strip().rstrip(".!?").strip().casefold()

    if not any(visible_source_fact(fact) == normalized_label for fact in facts):
        facts.insert(0, label)
        anchors.insert(0, ())
    units[index] = replace(unit, facts=tuple(facts), fact_temporal_anchors=tuple(anchors))
    return replace(plan, actions=(replace(action, units=tuple(units)),))


def add_core_reference_facts(plan: RequestPlan, links: tuple[CoreLinkFactSpec, ...]) -> RequestPlan:
    """Convert app-owned role *evidence* into normal Core reference helpers.

    This method does not prove role evidence or create relationship identities.
    It only maintains generic unit/reference/marker index alignment for Core.
    """
    if not links:
        return plan
    if len(links) > 16 or any(
        not isinstance(spec, CoreLinkFactSpec)
        or not all(
            (
                spec.label.strip(),
                spec.mention.strip(),
                spec.target_type.strip(),
                spec.reference_role.strip(),
                spec.canonical_target_name.strip()
                if spec.canonical_target_name is not None
                else "ok",
            )
        )
        or any(char in spec.label + spec.mention for char in "[]{}\n\r")
        or any(
            len(value) > 160
            for value in (
                spec.label,
                spec.mention,
                spec.target_type,
                spec.reference_role,
                spec.canonical_target_name or "",
            )
        )
        for spec in links
    ):
        raise RequestPlanningError("Invalid bounded source reference facts")
    action, units, index = _sole_primary(plan)
    unit = units[index]
    facts = list(unit.facts)
    anchors = list(unit.fact_temporal_anchors)
    references = list(unit.references)
    helpers: list[KnowledgeUnit] = []
    for spec in links:
        selection = SelectionCriteria(
            spec.canonical_target_name,
            spec.canonical_target_name or spec.mention,
            spec.target_type,
            (),
            None,
        )
        target_index = len(units) + len(helpers)
        helpers.append(
            KnowledgeUnit(
                target=selection,
                intent="record",
                properties=(),
                tag_changes=(),
                facts=(),
                references=(),
                cardinality="one",
                destination_type=None,
                reference_lookup_only=True,
            )
        )
        reference_index = len(references)
        references.append(KnowledgeReference(target_index, spec.reference_role, spec.mention))
        facts.append(f"{spec.label}: {{{{ref:{reference_index}}}}}.")
        anchors.append(())
    units[index] = replace(
        unit,
        facts=tuple(facts),
        references=tuple(references),
        fact_temporal_anchors=tuple(anchors),
    )
    return replace(plan, actions=(replace(action, units=tuple((*units, *helpers))),))


def ensure_complete_core_reference_set(
    plan: RequestPlan,
    links: tuple[CoreLinkFactSpec, ...],
    *,
    compatible_roles: tuple[str, ...] = (),
) -> RequestPlan:
    """Complete a receipt-backed reference set using only Core plan mechanics.

    The caller provides preverified *canonical names*, never stable Note IDs.
    Reject foreign/duplicate references to a protected mention instead of
    silently augmenting an unsafe partial model plan. The ordinary E3 preflight
    must independently recheck every target's current physical Note ID.
    """
    if not links:
        return plan
    if len(links) > 16 or any(
        not isinstance(spec, CoreLinkFactSpec)
        or not isinstance(spec.canonical_target_name, str)
        or not spec.canonical_target_name.strip()
        for spec in links
    ):
        raise RequestPlanningError("Reference-set members require Core receipts")
    requested = {
        (spec.mention, spec.target_type, spec.canonical_target_name): spec for spec in links
    }
    if len(requested) != len(links):
        raise RequestPlanningError("Duplicate canonical reference-set members")
    action, units, primary_index = _sole_primary(plan)
    remaining = set(requested)
    protected_mentions = {spec.mention for spec in links}
    for ref in units[primary_index].references:
        if ref.mention not in protected_mentions:
            continue
        if not 0 <= ref.target_index < len(action.units):
            raise RequestPlanningError("Reference-set helper is missing")
        helper = action.units[ref.target_index]
        key = (ref.mention, helper.target.type, helper.target.entity)
        spec = requested.get(key)
        if (
            not helper.reference_lookup_only
            or spec is None
            or ref.role not in (spec.reference_role, *compatible_roles)
            or key not in remaining
        ):
            raise RequestPlanningError("Reference-set member is not one proven identity")
        remaining.remove(key)
    return add_core_reference_facts(
        plan, tuple(spec for key, spec in requested.items() if key in remaining)
    )
