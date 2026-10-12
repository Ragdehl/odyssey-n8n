"""Exact-source sensitive statement, not an occurred event.

This is an information-only N:1 contract: every verified candidate supports
one fully preserved literal statement on one proven Day Note, with no
canonical identity refs. Candidate cardinality is bounded by the ordinary Core
context and coverage budgets, never by a semantic scenario count.
"""

from __future__ import annotations

from .candidate_context import CoreCandidateContext
from .request_planning import RequestPlan, WriteAction, plan_fact_ordinals


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
        raise ValueError("Sensitive joint meaning requires reviewed two-to-one coverage")

    negative = all(
        c.kind == "negative"
        and all(
            any(r.role == role for r in c.roles) for role in ("polarity", "predicate", "object")
        )
        and not any(r.role == "condition" for r in c.roles)
        for c in candidates
    )
    conditional = all(
        c.kind == "occurrence"
        and all(any(r.role == role for r in c.roles) for role in ("condition", "predicate"))
        and not any(r.role == "polarity" for r in c.roles)
        for c in candidates
    )
    if not (negative or conditional):
        raise ValueError("Mixed polarity and invented condition scope are not certified")

    if negative:
        polarity = {
            (r.span.start, r.span.end) for c in candidates for r in c.roles if r.role == "polarity"
        }
        predicates = {
            (r.span.start, r.span.end) for c in candidates for r in c.roles if r.role == "predicate"
        }
        objects = [
            tuple((r.span.start, r.span.end) for r in c.roles if r.role == "object")
            for c in candidates
        ]
        if (
            len(polarity) != 1
            or len(predicates) != 1
            or any(len(scopes) != 1 for scopes in objects)
            or len({scope[0] for scope in objects}) != len(objects)
        ):
            raise ValueError(
                "Negative group does not prove common negated predicate and each object scope"
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
