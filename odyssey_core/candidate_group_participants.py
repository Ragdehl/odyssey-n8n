"""Source evidence checks for grouped events that carry participants.

Router roles remain untrusted linguistic evidence. This module only proves
that an already reviewed Core fact preserves the participant and event words
owned by its source candidate. It never resolves a person, expands a group,
or grants a reference helper mutation authority.
"""

from __future__ import annotations

import re

from .candidate_context import CoreCandidate, CoreCandidateContext, CoreSourceSpan
from .candidate_semantic_veto import normalized_words
from .request_planning import KnowledgeUnit, WriteAction

_REFERENCE = re.compile(r"\{\{ref:(\d+)\}\}")
_EVENT_ROLES = frozenset({"predicate", "object", "location"})


def _direct_participants(candidate: CoreCandidate) -> tuple[CoreSourceSpan, ...]:
    """Return nonempty participant roles physically owned by one candidate."""
    return tuple(
        role.span
        for role in candidate.roles
        if role.role == "participants" and role.span.text.strip()
    )


def _participant_evidence(
    context: CoreCandidateContext, candidate_index: int
) -> tuple[CoreSourceSpan, ...]:
    """Resolve only explicit, immediate source inheritance for participants.

    The result is lexical source evidence, not a canonical group membership.
    A candidate may own several participant spans; inherited participant scope
    is accepted only from one earlier candidate that itself owns exact spans.
    """
    candidate = context.candidates[candidate_index]
    direct = _direct_participants(candidate)
    if direct:
        return direct
    parents = [edge.from_unit - 1 for edge in candidate.inherits if edge.role == "participants"]
    if len(parents) != 1 or not 0 <= parents[0] < candidate_index:
        raise ValueError("Event participants need direct or immediate source evidence")
    inherited = _direct_participants(context.candidates[parents[0]])
    if not inherited:
        raise ValueError("Inherited participants have no original source span")
    return inherited


def _event_words(context: CoreCandidateContext, candidate_index: int) -> frozenset[str]:
    """Return local event words, or one exact inherited predicate when needed."""
    candidate = context.candidates[candidate_index]
    local = frozenset().union(
        *(normalized_words(role.span.text) for role in candidate.roles if role.role in _EVENT_ROLES)
    )
    if local:
        return local
    parents = [edge.from_unit - 1 for edge in candidate.inherits if edge.role == "predicate"]
    if len(parents) != 1 or not 0 <= parents[0] < candidate_index:
        return frozenset()
    return frozenset().union(
        *(
            normalized_words(role.span.text)
            for role in context.candidates[parents[0]].roles
            if role.role == "predicate"
        )
    )


def _validate_reference_helper(
    action: WriteAction,
    unit_index: int,
    unit: KnowledgeUnit,
    reference_index: int,
    expected_mentions: tuple[str, ...],
) -> int:
    """Check a source-matched lookup helper without resolving its identity.

    Canonical existence and identity binding deliberately remain ordinary Core
    responsibilities. This only prevents a reviewed grouped fact from
    directing a helper at a name that the source candidate did not own.
    """
    if not 0 <= reference_index < len(unit.references):
        raise ValueError("Grouped participant fact has an invented reference marker")
    reference = unit.references[reference_index]
    helper_index = reference.target_index
    if (
        reference.mention not in expected_mentions
        or reference.role not in {"identity", "person", "project", "concept", "document"}
        or not isinstance(helper_index, int)
        or isinstance(helper_index, bool)
        or helper_index == unit_index
        or not 0 <= helper_index < len(action.units)
    ):
        raise ValueError("Grouped participant reference is not owned by its source event")
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
        or helper.target.entity != reference.mention
        or helper.target.query != reference.mention
        or not helper.target.type
        or helper.target.filters
        or helper.target.link_scope is not None
        or helper.target.semantic_set is not None
        or helper.target.relational_reference is not None
        or helper.target.self_target is not None
    ):
        raise ValueError("Grouped participant helper is not a pure source-matched lookup")
    return helper_index


def validate_group_participant_fact(
    source: str,
    context: CoreCandidateContext,
    candidate_index: int,
    action: WriteAction,
    unit_index: int,
    unit: KnowledgeUnit,
    fact: str,
    lexical_fact: str,
) -> tuple[int, ...]:
    """Validate one grouped event fact against its source candidate.

    Returns lookup-helper indices claimed by this fact. Raises ``ValueError``
    when an actor, event, reference, or helper is swapped, omitted, fabricated,
    or cannot be traced to source.
    """
    if not (
        context.scoped_route_source
        and unit.intent == "record"
        and not unit.properties
        and not unit.tag_changes
        and not unit.force_create
        and 0 <= candidate_index < len(context.candidates)
        and source == context.source
    ):
        raise ValueError("Grouped participant evidence requires a scoped simple Core event")
    candidate = context.candidates[candidate_index]
    if candidate.state != "candidate" or candidate.kind != "occurrence":
        raise ValueError("Grouped participant fact needs an affirmative source event")
    participants = _participant_evidence(context, candidate_index)
    if any(source[span.start : span.end] != span.text for span in participants):
        raise ValueError("Grouped participant wording is not in the original source")
    expected_mentions = tuple(span.text for span in participants)
    fact_words = normalized_words(lexical_fact)
    if any(not normalized_words(mention) <= fact_words for mention in expected_mentions):
        raise ValueError("Grouped event fact lost a source participant")
    own_event = _event_words(context, candidate_index)
    if not own_event or not own_event & fact_words:
        raise ValueError("Grouped participant fact lost its own event evidence")
    local_arguments = tuple(
        normalized_words(role.span.text)
        for role in candidate.roles
        if role.role in {"object", "location"}
    )
    if any(argument and not argument <= fact_words for argument in local_arguments):
        raise ValueError("Grouped participant fact lost its own event object")
    sibling_event_words = frozenset().union(
        *(
            _event_words(context, index)
            for index, _other in enumerate(context.candidates)
            if index != candidate_index
        )
    )
    distinctive = own_event - sibling_event_words
    if distinctive and not distinctive & fact_words:
        raise ValueError("Grouped participant fact was swapped with a sibling event")

    markers = tuple(int(value) for value in _REFERENCE.findall(fact))
    if len(markers) != len(set(markers)):
        raise ValueError("Grouped participant fact reuses a reference marker")
    helpers = tuple(
        _validate_reference_helper(action, unit_index, unit, marker, expected_mentions)
        for marker in markers
    )
    if len(helpers) != len(set(helpers)):
        raise ValueError("Grouped participant fact reuses a canonical lookup helper")
    return helpers


def validate_group_participant_literal(
    source: str,
    context: CoreCandidateContext,
    candidate_index: int,
    unit: KnowledgeUnit,
    fact: str,
) -> None:
    """Backward-compatible literal-only adapter for direct validator callers."""
    if unit.references or _REFERENCE.search(fact):
        raise ValueError("Literal group participant validation cannot certify references")
    synthetic_action = WriteAction((unit,))
    validate_group_participant_fact(
        source,
        context,
        candidate_index,
        synthetic_action,
        0,
        unit,
        fact,
        fact,
    )
