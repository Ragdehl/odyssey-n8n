"""Verify that explicit group participants remain in each inherited event fact.

Unresolved complete-set descriptions can be retained *literally* without
asserting group members or writing identity links. This gate does not turn
Router lexical provenance into a canonical people group or grant writes.
"""

from __future__ import annotations

from .candidate_context import CoreCandidateContext
from .candidate_semantic_veto import normalized_words
from .request_planning import KnowledgeUnit


def validate_group_participant_literal(
    source: str,
    context: CoreCandidateContext,
    candidate_index: int,
    unit: KnowledgeUnit,
    fact: str,
) -> None:
    if not (
        2 <= len(context.candidates) <= 8
        and len(unit.facts) == len(context.candidates)
        and unit.target.type == "calendar_day"
        and unit.intent == "record"
        and not unit.references
        and not unit.properties
        and not unit.tag_changes
        and not unit.force_create
        and all(c.state == "candidate" and c.kind == "occurrence" for c in context.candidates)
        and not any(
            role.role in {"condition", "polarity", "modality", "replacement", "reference"}
            for c in context.candidates
            for role in c.roles
        )
    ):
        raise ValueError("Literal group participants require simple dated events without links")
    explicit = [
        (j, role.span)
        for j, c in enumerate(context.candidates)
        for role in c.roles
        if role.role == "participants"
    ]
    if len(explicit) != 1:
        raise ValueError("Group participants need exactly one original literal source")
    original_index, phrase = explicit[0]
    if phrase.text not in source or not phrase.text.strip():
        raise ValueError("Group participant wording is not in the original source")
    candidate = context.candidates[candidate_index]
    if candidate_index != original_index and (
        len([edge for edge in candidate.inherits if edge.role == "participants"]) != 1
        or (
            candidate_index > original_index
            and not any(
                edge.role == "participants" and edge.from_unit == original_index + 1
                for edge in candidate.inherits
            )
        )
    ):
        raise ValueError("No verified source-level group participant inheritance")
    if phrase.text.casefold() not in fact.casefold():
        raise ValueError("Group participant description was omitted or paraphrased without proof")
    own = [role.span.text for role in candidate.roles if role.role == "object"]
    if len(own) != 1 or not normalized_words(own[0]) <= normalized_words(fact):
        raise ValueError("Group participant fact lost its own activity")
    others = {
        part
        for j, other in enumerate(context.candidates)
        if j != candidate_index
        for role in other.roles
        if role.role == "object"
        for part in normalized_words(role.span.text)
        if len(part) >= 4
    }
    if others & normalized_words(fact):
        raise ValueError("Group participant fact mixed activities from siblings")
