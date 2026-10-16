"""Core-owned compiler of attested whole-source atomic facts into ordinary RequestPlans.

This bridge is not a model planner and never grants identity or mutation
permission. It only converts independently reviewed, source-bound structured
facts; execute_request does all canonical preflight, validation and persistence.
"""

from __future__ import annotations

from typing import Any

from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    PropertyChange,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.temporal import TemporalAnchor


def make_action(items: list[dict[str, Any]], *, date: str | None, kind: str):
    if kind == "task":
        if len(items) != 1 or not date:
            raise ValueError("Task creation requires one reviewed exact-date assertion")
        item = items[0]
        title = item["reviewed_text"]
        for i, name in enumerate(item["reference_names"]):
            title = title.replace("{{ref:" + str(i) + "}}", name)
        title = title.strip().rstrip(".")
        if not title or len(title) > 160:
            raise ValueError("Invalid bounded Task title")
        primary = KnowledgeUnit(
            SelectionCriteria(title, title, "task", (), None),
            "record",
            (
                PropertyChange("status", "set", "pending"),
                PropertyChange("target_date", "set", date),
            ),
            (),
            (item["reviewed_text"],),
            tuple(
                KnowledgeReference(i + 1, "person", name)
                for i, name in enumerate(item["reference_names"])
            ),
            fact_temporal_anchors=((),),
            force_create=True,
        )
    elif kind == "record":
        if date is None:
            raise ValueError("Undated Core fact requires explicit owner, not Day")
        references = []
        fact_texts = []
        anchors = []
        helpers = {}
        for item in items:
            value = item["reviewed_text"]
            for index, name in enumerate(item["reference_names"]):
                helper = helpers.setdefault(name, len(helpers))
                local = len(references)
                references.append(KnowledgeReference(helper + 1, "person", name))
                value = value.replace("{{ref:" + str(index) + "}}", "{{ref:" + str(local) + "}}")
            fact_texts.append(value)
            anchors.append((TemporalAnchor.from_value(date),))
        primary = KnowledgeUnit(
            SelectionCriteria(None, date, "calendar_day", (), None),
            "record",
            (),
            (),
            tuple(fact_texts),
            tuple(references),
            fact_temporal_anchors=tuple(anchors),
        )
    else:
        raise ValueError("Unknown operation kind")
    seen = []
    if kind == "record":
        seen = list(helpers)
    else:
        seen = item["reference_names"]
    helpers_units = [
        KnowledgeUnit(
            SelectionCriteria(name, name, "person", (), None),
            "record",
            (),
            (),
            (),
            (),
            reference_lookup_only=True,
        )
        for name in seen
    ]
    return WriteAction((primary, *helpers_units))


def plan_for_record(review: dict[str, Any], date: str):
    items = [r for r in review["facts"] if r["kind"] == "record" and r["date"] == date]
    return RequestPlan((make_action(items, date=date, kind="record"),), ())


def plan_for_task(item: dict[str, Any]):
    return RequestPlan((make_action([item], date=item["date"], kind="task"),), ())


def undated_self_record(facts):
    """A validated speaker assertion belongs to SELF, not an invented Day."""
    helpers = {}
    refs = []
    values = []
    for item in facts:
        text = item["reviewed_text"]
        for index, name in enumerate(item["reference_names"]):
            helper = helpers.setdefault(name, len(helpers))
            slot = len(refs)
            refs.append(KnowledgeReference(helper + 1, "person", name))
            text = text.replace("{{ref:" + str(index) + "}}", "{{ref:" + str(slot) + "}}")
        values.append(text)
    owner = KnowledgeUnit(
        SelectionCriteria(None, "yo", "person", (), None, self_target="self"),
        "record",
        (),
        (),
        tuple(values),
        tuple(refs),
    )
    helper_units = tuple(
        KnowledgeUnit(
            SelectionCriteria(name, name, "person", (), None),
            "record",
            (),
            (),
            (),
            (),
            reference_lookup_only=True,
        )
        for name in helpers
    )
    return RequestPlan((WriteAction((owner, *helper_units)),), ())
