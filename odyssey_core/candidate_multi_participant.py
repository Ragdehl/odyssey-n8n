"""Narrow Core-only source checks for one event with two named participants.

This is not a grammatical parser or a semantic identity resolver. A validated
Core WriteAction still owns both canonical reference selections and persistence.
The first opt-in pilot supports exactly two explicit names joined by " y ".
Other groups and group-member descriptions stay pending for Core review.
"""

from __future__ import annotations

from .candidate_context import CoreCandidate
from .request_planning import RequestPlan, WriteAction


class MultiParticipantEvidenceError(ValueError):
    """One proposed grouped event cannot be safely associated with two helpers."""


def validate_two_named_participant_fact(
    source: str,
    candidate: CoreCandidate,
    plan: RequestPlan,
    action_index: int,
    unit_index: int,
) -> None:
    """Reject omitted/extra participants and helper mutations before Core writes.

    The two names are still only textual evidence; Core must uniquely resolve
    each corresponding reference-only helper against canonical NoteSchema.
    This validator never creates identities or asserts the event is true.
    """
    action = plan.actions[action_index]
    if not isinstance(action, WriteAction) or not 0 <= unit_index < len(action.units):
        raise MultiParticipantEvidenceError("Grouped event needs a Core write action")
    unit = action.units[unit_index]
    participants = [role.span for role in candidate.roles if role.role == "participants"]
    if len(participants) == 1 and participants[0].text.count(" y ") == 1:
        group = participants[0]
        names = tuple(value.strip() for value in group.text.split(" y "))
        anchored_group = any(
            anchor.start <= group.start and group.end <= anchor.end for anchor in candidate.anchors
        )
    elif len(participants) == 2:
        # Two exact name roles are equivalent source evidence only when their
        # offsets prove the original source literally joins them in one clause.
        first, second = sorted(participants, key=lambda span: span.start)
        names = (first.text, second.text)
        predicate_spans = [role.span for role in candidate.roles if role.role == "predicate"]
        anchored_group = (
            source[first.end : second.start] == " y "
            and all(
                any(
                    anchor.start <= name.start and name.end <= anchor.end
                    for anchor in candidate.anchors
                )
                or any(
                    predicate.end <= name.start
                    and not any(mark in source[predicate.end : name.start] for mark in ".;!?\n\r")
                    for predicate in predicate_spans
                )
                for name in (first, second)
            )
            and any(
                any(
                    anchor.start <= predicate.start and predicate.end <= anchor.end
                    for anchor in candidate.anchors
                )
                and (
                    (
                        predicate.end < first.start
                        and not any(
                            mark in source[predicate.end : first.start] for mark in ".;!?\n\r"
                        )
                    )
                    or (
                        candidate.kind == "relationship"
                        and predicate.text.startswith("se ")
                        and source[second.end : predicate.start] == " "
                    )
                )
                for predicate in predicate_spans
            )
        )
    else:
        raise MultiParticipantEvidenceError("Explicit two-name participant evidence required")
    if (
        len(names) != 2
        or any(
            not name.strip() or len(name) > 100 or "[[" in name or "{{" in name for name in names
        )
        or len(set(names)) != 2
        or not anchored_group
    ):
        raise MultiParticipantEvidenceError("Participant names not uniquely anchored in the event")
    if (
        unit.intent != "record"
        or unit.reference_lookup_only
        or unit.force_create
        or unit.properties
        or unit.tag_changes
        or unit.destination_type is not None
        or len(unit.facts) != 1
        or len(unit.references) != 2
        or len(action.units) != 3
    ):
        raise MultiParticipantEvidenceError(
            "Grouped fact requires one non-mutating helper per named participant"
        )
    helper_indices: set[int] = set()
    for reference_index, (reference, expected_name) in enumerate(
        zip(unit.references, names, strict=True)
    ):
        helper_index = reference.target_index
        if (
            reference.mention != expected_name
            or not isinstance(helper_index, int)
            or isinstance(helper_index, bool)
            or helper_index == unit_index
            or not 0 <= helper_index < len(action.units)
            or helper_index in helper_indices
            or unit.facts[0].count(f"{{{{ref:{reference_index}}}}}") != 1
        ):
            raise MultiParticipantEvidenceError("A source participant lacks its own Core reference")
        helper_indices.add(helper_index)
        helper = action.units[helper_index]
        if (
            not helper.reference_lookup_only
            or helper.force_create
            or helper.intent != "record"
            or helper.facts
            or helper.references
            or helper.properties
            or helper.tag_changes
            or helper.destination_type is not None
            or helper.target.entity != expected_name
            or helper.target.query != expected_name
            or not helper.target.type
            or reference.role not in {"identity", helper.target.type}
            or helper.target.filters
            or helper.target.link_scope is not None
            or helper.target.semantic_set is not None
            or helper.target.relational_reference is not None
            or helper.target.self_target is not None
        ):
            raise MultiParticipantEvidenceError(
                "Core participant helper must only resolve the named identity"
            )
    if helper_indices != set(range(len(action.units))) - {unit_index}:
        raise MultiParticipantEvidenceError("Grouped Core write includes an unclaimed helper")
    if "{{ref" in unit.facts[0].replace("{{ref:0}}", "").replace("{{ref:1}}", ""):
        raise MultiParticipantEvidenceError("Grouped fact has an unverified extra reference")
