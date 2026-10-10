"""Source-linked Core guard for one reciprocal relation between two people.

The candidate says that two subjects share one reciprocal relationship.
Core may store one fact on either person's canonical Note and resolve the
other by a normal immutable-reference helper. Router never chooses either ID.
"""

from __future__ import annotations

from .candidate_context import CoreCandidate
from .candidate_semantic_veto import normalized_words
from .request_planning import RequestPlan, WriteAction


class MutualRelationshipEvidenceError(ValueError):
    """One mutual source relation lacks independently verifiable Core evidence."""


def validate_one_mutual_relationship_fact(
    source: str,
    candidate: CoreCandidate,
    plan: RequestPlan,
    action_index: int,
    unit_index: int,
) -> None:
    """Check two original named parties against one directed canonical fact.

    This guards only reciprocal constructions with explicit two-name subjects
    and a shared `se ...` predicate. It does not claim a general ontology
    resolver or semantic equivalence proof for other relation classes.
    """
    if candidate.kind != "relationship" or candidate.state != "candidate":
        raise MutualRelationshipEvidenceError("A reciprocal source relation is required")
    action = plan.actions[action_index]
    if not isinstance(action, WriteAction) or len(action.units) != 2:
        raise MutualRelationshipEvidenceError("One relation needs one target and one helper")
    if not 0 <= unit_index < 2:
        raise MutualRelationshipEvidenceError("Relation target unit index is invalid")
    unit = action.units[unit_index]
    people = sorted(
        (role.span for role in candidate.roles if role.role == "participants"),
        key=lambda item: item.start,
    )
    predicates = [role.span for role in candidate.roles if role.role == "predicate"]
    locations = [role.span for role in candidate.roles if role.role == "location"]
    if (
        len(people) != 2
        or len(predicates) != 1
        or len(locations) > 1
        or len({span.text for span in people}) != 2
        or not all(len(span.text) <= 100 and "[[" not in span.text for span in people)
    ):
        raise MutualRelationshipEvidenceError("Two distinct original participants required")
    first, second = people
    predicate = predicates[0]
    if (
        source[first.end : second.start] != " y "
        or source[second.end : predicate.start] != " "
        or not predicate.text.startswith("se ")
        or not all(
            any(
                anchor.start <= span.start and span.end <= anchor.end
                for anchor in candidate.anchors
            )
            for span in (first, second, predicate)
        )
        or any(mark in source[first.start : predicate.end] for mark in ".;!?\n\r")
    ):
        raise MutualRelationshipEvidenceError("Source does not prove one reciprocal clause")
    if locations and (
        locations[0].start < predicate.end
        or any(mark in source[predicate.end : locations[0].end] for mark in ".;!?\n\r")
    ):
        raise MutualRelationshipEvidenceError("Relation location is outside its source clause")
    names = (first.text, second.text)
    target = unit.target
    if (
        target.entity not in names
        or target.query != target.entity
        or target.type != "person"
        or target.filters
        or target.link_scope is not None
        or target.semantic_set is not None
        or target.relational_reference is not None
        or target.self_target is not None
        or unit.intent != "record"
        or unit.reference_lookup_only
        or unit.force_create
        or unit.properties
        or unit.tag_changes
        or unit.destination_type is not None
        or len(unit.facts) != 1
        or len(unit.references) != 1
        or unit.fact_temporal_anchors
    ):
        raise MutualRelationshipEvidenceError("Core relation target has unsupported write shape")
    reference = unit.references[0]
    if (
        reference.target_index == unit_index
        or reference.target_index not in {0, 1}
        or reference.mention not in names
        or reference.mention == target.entity
        or reference.role not in {"identity", "person"}
        or unit.facts[0].count("{{ref:0}}") != 1
        or "{{ref:" in unit.facts[0].replace("{{ref:0}}", "")
    ):
        raise MutualRelationshipEvidenceError("Other reciprocal person is not referenced exactly")
    helper = action.units[reference.target_index]
    if (
        not helper.reference_lookup_only
        or helper.target.entity != reference.mention
        or helper.target.query != reference.mention
        or helper.target.type != "person"
        or helper.target.filters
        or helper.target.link_scope is not None
        or helper.target.semantic_set is not None
        or helper.target.relational_reference is not None
        or helper.target.self_target is not None
        or helper.intent != "record"
        or helper.force_create
        or helper.facts
        or helper.references
        or helper.properties
        or helper.tag_changes
        or helper.destination_type is not None
    ):
        raise MutualRelationshipEvidenceError("Reference helper cannot mutate the other person")
    fact_words = normalized_words(unit.facts[0].replace("{{ref:0}}", reference.mention))
    if locations and not normalized_words(locations[0].text) <= fact_words:
        raise MutualRelationshipEvidenceError("Core relation changes original location")
    original_predicate = [
        word for word in normalized_words(predicate.text) if word != "se" and len(word) >= 4
    ]
    output_words = [word for word in fact_words if len(word) >= 4]
    if not original_predicate or not any(
        left[:4] == right[:4] for left in original_predicate for right in output_words
    ):
        raise MutualRelationshipEvidenceError("Core relation changes original predicate")
    if any(word.isdigit() and word not in normalized_words(source) for word in fact_words):
        raise MutualRelationshipEvidenceError("Core relation introduces unsupported date/number")
