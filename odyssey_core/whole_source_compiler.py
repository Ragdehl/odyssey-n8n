"""Core-owned compiler of attested whole-source atomic facts into ordinary RequestPlans.

This bridge is not a model planner and never grants identity or mutation
permission. It only converts independently reviewed, source-bound structured
facts; execute_request does all canonical preflight, validation and persistence.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
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
from odyssey_core.whole_message_speaker_proof import attach_speaker_to_day_action


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


class WholeSourceCompilationError(ValueError):
    """An entire source must be compilable before ANY canonical mutation."""


@dataclass(frozen=True, slots=True)
class ReviewedSourceOperation:
    """Core-owned, source-order-associated write, not a mutation permission."""

    locator_suffix: str
    plan: RequestPlan
    task_create: bool = False


def compile_reviewed_operations(
    review: Mapping[str, Any], self_roles: Sequence[bool]
) -> tuple[ReviewedSourceOperation, ...]:
    """Pure preflight of EVERY reviewed fact to avoid avoidable partial writes.

    The caller must first prove source coverage, identity and speaker roles.
    A later Core preflight may still reject identity, status or concurrency;
    this only guarantees that one unsupported fact cannot be found after
    earlier facts were already persisted by the same delivery.
    """
    facts = review.get("facts")
    if (
        not isinstance(facts, list)
        or not 1 <= len(facts) <= 16
        or len(facts) != len(self_roles)
        or any(type(flag) is not bool for flag in self_roles)
    ):
        raise WholeSourceCompilationError("Whole-source fact/speaker alignment invalid")
    days: dict[str, list[int]] = {}
    undated: list[tuple[int, dict[str, Any]]] = []
    tasks: list[tuple[int, dict[str, Any]]] = []
    for position, fact in enumerate(facts):
        if not isinstance(fact, dict):
            raise WholeSourceCompilationError("Reviewed fact must be an object")
        # Independent structural defence: a compiler must never silently
        # drop references even if a prior semantic reviewer was bypassed.
        raw_text, names = fact.get("reviewed_text"), fact.get("reference_names")
        if (
            not isinstance(raw_text, str)
            or not raw_text.strip()
            or len(raw_text) > 320
            or not isinstance(names, list)
            or len(names) > 8
            or any(not isinstance(n, str) or not n.strip() for n in names)
            or len(set(names)) != len(names)
            or "[[" in raw_text
            or "<!--" in raw_text
        ):
            raise WholeSourceCompilationError("Invalid complete reviewed fact structure")
        slots = [int(number) for number in re.findall(r"\{\{ref:(\d+)\}\}", raw_text)]
        if sorted(slots) != list(range(len(names))):
            raise WholeSourceCompilationError("Reference marker coverage does not match people")
        kind, date = fact.get("kind"), fact.get("date")
        if kind == "record" and isinstance(date, str) and date:
            days.setdefault(date, []).append(position)
        elif kind == "record" and date is None and self_roles[position]:
            undated.append((position, fact))
        elif kind == "task" and isinstance(date, str) and date:
            tasks.append((position, fact))
        else:
            raise WholeSourceCompilationError("Unsupported task/date/owner; no prior source writes")
    try:
        operations = []
        for day, positions in sorted(days.items()):
            plan = plan_for_record({"facts": facts}, day)
            action = attach_speaker_to_day_action(
                plan.actions[0], [self_roles[position] for position in positions]
            )
            operations.append(
                ReviewedSourceOperation("day-" + day, replace(plan, actions=(action,)))
            )
        if undated:
            operations.append(
                ReviewedSourceOperation("self", undated_self_record([fact for _, fact in undated]))
            )
        for position, fact in tasks:
            operations.append(
                ReviewedSourceOperation("task-" + str(position), plan_for_task(fact), True)
            )
    except (AssertionError, KeyError, TypeError, ValueError) as error:
        raise WholeSourceCompilationError("A reviewed fact cannot be compiled safely") from error
    if not operations:
        raise WholeSourceCompilationError("No compilable atomic operation")
    return tuple(operations)
