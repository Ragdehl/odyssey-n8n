"""Exact-source sensitive statement, not an occurred event.

This is an information-only N:1 contract: every verified candidate supports
one fully preserved literal statement on one proven Day Note, with no
canonical identity refs. Candidate cardinality is bounded by the ordinary Core
context and coverage budgets, never by a semantic scenario count.
"""

from __future__ import annotations

from .candidate_context import CoreCandidateContext
from .request_planning import RequestPlan, WriteAction, plan_fact_ordinals


def supports_sensitive_literal_candidates(candidates) -> bool:
    """Return whether source roles describe one safe literal-sensitive shape.

    This establishes only that every negative or conditional candidate has
    source-owned semantic roles.  Temporal proof, whole-source preservation,
    target selection, coverage, and Markdown readback remain separate gates.
    """
    if not candidates or any(candidate.state != "candidate" for candidate in candidates):
        return False
    negative = all(candidate.kind == "negative" for candidate in candidates)
    conditional = all(candidate.kind == "occurrence" for candidate in candidates)
    if negative:
        for candidate in candidates:
            roles = {role.role for role in candidate.roles}
            scoped_people_or_objects = [
                role for role in candidate.roles if role.role in {"object", "participants"}
            ]
            if (
                not {"polarity", "predicate"} <= roles
                or "condition" in roles
                or len(scoped_people_or_objects) != 1
            ):
                return False
        return True
    if conditional:
        return all(
            {"condition", "predicate"} <= {role.role for role in candidate.roles}
            and not any(role.role == "polarity" for role in candidate.roles)
            for candidate in candidates
        )
    return False


def validate_sensitive_group_statement(
    source, context: CoreCandidateContext, plan: RequestPlan, claims
):
    temporal = context.verified_sensitive_temporal
    if temporal is None or temporal.source_text != source or not context.hybrid_interpretation_mode:
        raise ValueError("Sensitive statement lacks scoped Temporal proof")
    candidates = context.candidates
    if (
        not candidates
        or any(c.state != "candidate" for c in candidates)
        or len(claims) != len(candidates)
        or any(
            c.disposition != "planned_fact" or c.fact_ordinal is not None or c.fact_ordinals != (0,)
            for c in claims
        )
        or len(plan.actions) != 1
        or not isinstance(plan.actions[0], WriteAction)
        or len(plan.actions[0].units) != 1
        or plan_fact_ordinals(plan) != ((0,),)
    ):
        raise ValueError("Sensitive meaning requires reviewed N-to-one coverage")

    if not supports_sensitive_literal_candidates(candidates):
        raise ValueError("Mixed polarity and invented condition scope are not certified")
    negative = all(c.kind == "negative" for c in candidates)

    if negative:
        polarity = {
            (r.span.start, r.span.end) for c in candidates for r in c.roles if r.role == "polarity"
        }
        predicates = {
            (r.span.start, r.span.end) for c in candidates for r in c.roles if r.role == "predicate"
        }
        scopes = [
            tuple(
                (r.span.start, r.span.end) for r in c.roles if r.role in {"object", "participants"}
            )
            for c in candidates
        ]
        if (
            len(polarity) != 1
            or len(predicates) != 1
            or any(len(candidate_scopes) != 1 for candidate_scopes in scopes)
            or len({candidate_scopes[0] for candidate_scopes in scopes}) != len(scopes)
        ):
            raise ValueError(
                "Negative group does not prove common negated predicate and each source scope"
            )
    else:
        conditions = [
            tuple((r.span.start, r.span.end) for r in c.roles if r.role == "condition")
            for c in candidates
        ]
        predicates = [
            tuple((r.span.start, r.span.end) for r in c.roles if r.role == "predicate")
            for c in candidates
        ]
        objects = [
            tuple((r.span.start, r.span.end) for r in c.roles if r.role == "object")
            for c in candidates
        ]
        if (
            any(len(scopes) != 1 for scopes in conditions + predicates)
            or any(len(scopes) > 1 for scopes in objects)
            or len({scope[0] for scope in conditions}) != len(conditions)
            or len({scope[0] for scope in predicates}) != len(predicates)
            or len({scope[0] for scopes in objects for scope in scopes})
            != sum(len(scopes) for scopes in objects)
        ):
            raise ValueError(
                "Conditional clauses need distinct exact condition, predicate and object scopes"
            )
    unit = plan.actions[0].units[0]
    target = unit.target
    if (
        unit.intent != "record"
        or len(unit.facts) != 1
        or unit.facts[0] != source
        or unit.references
        or unit.reference_lookup_only
        or unit.properties
        or unit.tag_changes
        or unit.force_create
        or unit.destination_type is not None
        or unit.cardinality != "one"
        or target.type != "calendar_day"
        or target.entity is not None
        or target.filters
        or target.self_target is not None
        or target.relational_reference is not None
        or target.semantic_set is not None
        or target.link_scope is not None
        or not isinstance(target.query, str)
    ):
        raise ValueError("Sensitive statement must be literal full source on one Day Note")
    date_roles = {r.span.text for c in candidates for r in c.roles if r.role == "date"}
    scope_dates = {r.span.text for c in candidates for r in c.roles if r.role == "date_scope"}
    mentions = date_roles | scope_dates
    if len(mentions) != 1:
        raise ValueError("Sensitive source must have exactly one shared date")
    matched = [
        e
        for e in temporal.temporal_references()
        if e.source_text in mentions
        and e.temporal_anchor().time is None
        and e.value == target.query
    ]
    if len(matched) != 1:
        raise ValueError("Day Note is not proved by this source's Temporal date")
    anchors = unit.fact_temporal_anchors
    if anchors and (
        len(anchors) != 1 or len(anchors[0]) != 1 or anchors[0][0].value != target.query
    ):
        raise ValueError("Sensitive statement fact has conflicting Temporal anchors")
