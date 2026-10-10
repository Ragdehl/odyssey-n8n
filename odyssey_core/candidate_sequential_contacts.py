"""Narrow, source-grounded Core check for two explicitly successive contacts.

Never builds notes, resolves identities, or establishes semantic equivalence.
Only two exact names and a source-explicit 'y después con' connector are
eligible for this opt-in pilot; uncertain forms remain pending for Core review.
"""

from __future__ import annotations

from .candidate_context import CoreCandidateContext
from .request_planning import RequestPlan, WriteAction


class SequentialContactEvidenceError(ValueError):
    """Two distinct source events cannot be matched safely to the Core plan."""


def validate_two_sequential_contacts(
    context: CoreCandidateContext,
    plan: RequestPlan,
    action_index: int,
    unit_index: int,
) -> None:
    """Require exact ordered source references, helpers and two distinct facts.

    The reviewed template covers the explicitly spoken ``hablé con X y
    después con Y`` shape. It rejects additional facts/helpers and implicit
    inferred timing; other speech patterns need independent semantic review.
    """
    action = plan.actions[action_index]
    if not isinstance(action, WriteAction) or not 0 <= unit_index < len(action.units):
        raise SequentialContactEvidenceError("Sequential contacts need a Core write action")
    unit = action.units[unit_index]
    if len(context.candidates) != 3 or context.candidates[2].state != "ambiguous_identity":
        raise SequentialContactEvidenceError("One future ambiguous candidate must stay pending")
    first, second = context.candidates[:2]
    future = context.candidates[2]
    if not any(
        role.role == "reference"
        and role.span.text == "él"
        and any(
            anchor.start <= role.span.start and role.span.end <= anchor.end
            for anchor in future.anchors
        )
        for role in future.roles
    ):
        raise SequentialContactEvidenceError("Future reference ambiguity needs source evidence")
    if (
        first.state != "candidate"
        or second.state != "candidate"
        or first.kind != "occurrence"
        or second.kind != "occurrence"
    ):
        raise SequentialContactEvidenceError("Two source events are required")
    # Preserve the previously approved single-name-anchor pilot unchanged.
    legacy = (
        len(first.anchors) == len(second.anchors) == 1
        and first.anchors[0].text != "hablé"
        and all(
            any(
                role.role == "predicate" and role.span.text == "hablé con"
                for role in candidate.roles
            )
            and any(role.role == "date" for role in candidate.roles)
            for candidate in (first, second)
        )
    )
    if legacy:
        a, b = first.anchors[0], second.anchors[0]
    else:
        # Model-proposed split spans do not gain authority by themselves.
        # Reconstruct both names solely from exact source participant roles,
        # and verify their ordered contact words in the unchanged source.
        first_people = [role.span for role in first.roles if role.role == "participants"]
        second_people = [role.span for role in second.roles if role.role == "participants"]
        if len(first_people) != 1 or len(second_people) != 1:
            raise SequentialContactEvidenceError("Two separately evidenced contact names required")
        a, b = first_people[0], second_people[0]
        if (
            not all(
                any(
                    anchor.start <= span.start and span.end <= anchor.end
                    for anchor in candidate.anchors
                )
                for candidate, span in ((first, a), (second, b))
            )
            or not any(
                role.role == "predicate"
                and role.span.text in {"hablé", "hablé con"}
                and any(
                    anchor.start <= role.span.start and role.span.end <= anchor.end
                    for anchor in first.anchors
                )
                for role in first.roles
            )
            or not any(edge.role == "predicate" and edge.from_unit == 1 for edge in second.inherits)
            or not any(
                role.role == "order" and role.span.text == "después" and b.start > role.span.end
                for role in second.roles
            )
        ):
            raise SequentialContactEvidenceError("Sequential contact roles lack source proof")
    if (
        a.text == b.text
        or len(a.text) > 100
        or len(b.text) > 100
        or not a.text.strip()
        or not b.text.strip()
        or context.source[a.end : b.start] != " y después con "
        or not context.source[max(0, a.start - len("hablé con ")) : a.start].endswith("hablé con ")
        or any(char in a.text + b.text for char in "[]{}|\n\r")
    ):
        raise SequentialContactEvidenceError(
            "Explicit distinct ordered contacts are not source-grounded"
        )
    first_dates = [role.span for role in first.roles if role.role == "date"]
    future_dates = [role.span for role in future.roles if role.role == "date"]
    if (
        len(first_dates) != 1
        or len(future_dates) != 1
        or first_dates[0].end > a.start
        or future_dates[0].start <= b.end
        or any(mark in context.source[first_dates[0].end : a.start] for mark in ".;!?\n\r")
    ):
        raise SequentialContactEvidenceError("Sequential contacts need source-grounded dates")
    if not legacy:
        # The source literally says one dated speech event followed by another
        # in the same clause. No other date or independent clause intervenes.
        if context.source[first_dates[0].end : a.start] != " hablé con ":
            raise SequentialContactEvidenceError("Second contact cannot inherit unrelated date")
    else:
        for candidate in (first, second):
            if not any(
                role.role == "predicate" and role.span.text == "hablé con"
                for role in candidate.roles
            ):
                raise SequentialContactEvidenceError(
                    "Each event needs the original contact predicate"
                )
            if not any(role.role == "date" for role in candidate.roles):
                raise SequentialContactEvidenceError("Each event needs the original date scope")
    if (
        unit.intent != "record"
        or unit.force_create
        or unit.reference_lookup_only
        or unit.properties
        or unit.tag_changes
        or unit.destination_type is not None
        or len(unit.facts) != 2
        or len(unit.references) != 2
        or len(action.units) != 3
        or unit.facts != ("Hablé con {{ref:0}}.", "Después hablé con {{ref:1}}.")
        or len(unit.fact_temporal_anchors) != 2
        or not unit.fact_temporal_anchors[0]
        or unit.fact_temporal_anchors[0] != unit.fact_temporal_anchors[1]
    ):
        raise SequentialContactEvidenceError("Core must retain two separate dated contact facts")
    helper_indices: set[int] = set()
    for reference, name in zip(unit.references, (a.text, b.text), strict=True):
        index = reference.target_index
        if (
            reference.mention != name
            or reference.role not in {"identity", "person"}
            or not isinstance(index, int)
            or isinstance(index, bool)
            or index == unit_index
            or not 0 <= index < len(action.units)
            or index in helper_indices
        ):
            raise SequentialContactEvidenceError("Source participant mismatch or duplicate helper")
        helper_indices.add(index)
        helper = action.units[index]
        if (
            not helper.reference_lookup_only
            or helper.force_create
            or helper.intent != "record"
            or helper.facts
            or helper.references
            or helper.properties
            or helper.tag_changes
            or helper.destination_type is not None
            or helper.target.entity != name
            or helper.target.query != name
            or helper.target.type != "person"
            or helper.target.filters
            or helper.target.link_scope is not None
            or helper.target.semantic_set is not None
            or helper.target.relational_reference is not None
            or helper.target.self_target is not None
        ):
            raise SequentialContactEvidenceError(
                "Core references must resolve existing distinct people"
            )
    if helper_indices != set(range(len(action.units))) - {unit_index}:
        raise SequentialContactEvidenceError("Unexpected Core helper in sequential contact plan")
