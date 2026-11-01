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

from odyssey_core.identity import resolve_exact_entities_batch, resolve_exact_entity
from odyssey_core.request_planning import (
    KnowledgeReference,
    KnowledgeUnit,
    PropertyChange,
    RequestPlan,
    SelectionCriteria,
    WriteAction,
)
from odyssey_core.temporal import TemporalAnchor
from odyssey_core.whole_message_coverage import ReviewedFullSource
from odyssey_core.whole_message_speaker_proof import (
    AttestedSpeakerReview,
    attach_speaker_to_day_action,
)


def _record_action(
    items: list[dict[str, Any]],
    *,
    target: SelectionCriteria,
    date: str | None = None,
    reference_types: Mapping[str, str | None] | None = None,
    properties: tuple[PropertyChange, ...] = (),
    force_create: bool = False,
) -> WriteAction:
    """Use one Core reference/materialization shape for every reviewed record.

    Targets and Task lifecycle properties are supplied by existing owners;
    the model's text never authorizes target selection or canonical links.
    """
    helpers: dict[str, int] = {}
    references: list[KnowledgeReference] = []
    values: list[str] = []
    for item in items:
        local_slots: dict[int, int] = {}
        for index, name in enumerate(item["reference_names"]):
            helper = helpers.setdefault(name, len(helpers))
            local_slots[index] = len(references)
            references.append(KnowledgeReference(helper + 1, "related", name))
        # Translate ORIGINAL local tokens in one pass. Sequential str.replace
        # can renumber an earlier replacement a second time when a later local
        # marker has the same numeric index as a new global marker.
        text = re.sub(
            r"\{\{ref:(\d+)\}\}",
            lambda found, slots=local_slots: "{{ref:" + str(slots[int(found.group(1))]) + "}}",
            item["reviewed_text"],
        )
        values.append(text)
    primary = KnowledgeUnit(
        target,
        "record",
        properties,
        (),
        tuple(values),
        tuple(references),
        fact_temporal_anchors=(
            tuple((TemporalAnchor.from_value(date),) for _ in items)
            if date is not None
            else tuple(() for _ in items)
            if force_create
            else ()
        ),
        force_create=force_create,
    )
    types = reference_types or {}
    helpers_units = tuple(
        KnowledgeUnit(
            SelectionCriteria(name, name, types.get(name), (), None),
            "record",
            (),
            (),
            (),
            (),
            reference_lookup_only=True,
        )
        for name in helpers
    )
    return WriteAction((primary, *helpers_units))


def plan_for_record(
    review: dict[str, Any], date: str, *, reference_types: Mapping[str, str | None] | None = None
):
    items = [r for r in review["facts"] if r["kind"] == "record" and r["date"] == date]
    return RequestPlan(
        (
            _record_action(
                items,
                target=SelectionCriteria(None, date, "calendar_day", (), None),
                date=date,
                reference_types=reference_types,
            ),
        ),
        (),
    )


def plan_for_task(item: dict[str, Any], *, reference_types: Mapping[str, str | None] | None = None):
    date = item["date"]
    if not date:
        raise ValueError("Task creation requires one reviewed exact-date assertion")
    title = item["reviewed_text"]
    for index, name in enumerate(item["reference_names"]):
        title = title.replace("{{ref:" + str(index) + "}}", name)
    title = title.strip().rstrip(".")
    if not title or len(title) > 160:
        raise ValueError("Invalid bounded Task title")
    action = _record_action(
        [item],
        target=SelectionCriteria(title, title, "task", (), None),
        reference_types=reference_types,
        properties=(
            PropertyChange("status", "set", "pending"),
            PropertyChange("target_date", "set", date),
        ),
        force_create=True,
    )
    return RequestPlan((action,), ())


def undated_self_record(facts, *, reference_types: Mapping[str, str | None] | None = None):
    """Use the same reference lowering for an independently attested SELF owner."""
    action = _record_action(
        facts,
        target=SelectionCriteria(None, "yo", "person", (), None, self_target="self"),
        reference_types=reference_types,
    )
    return RequestPlan((action,), ())


class WholeSourceCompilationError(ValueError):
    """An entire source must be compilable before ANY canonical mutation."""


def resolve_attested_owner_targets(
    source_proof: ReviewedFullSource,
    speakers: AttestedSpeakerReview,
    repository: Any,
    schema: dict[str, Any],
) -> tuple[dict[int, SelectionCriteria], dict[int, str]]:
    """Core-only exact owner selection from two source and two speaker reviews.

    A model's note-type guess cannot disambiguate a homonym. An owner must
    resolve to ONE CURRENT existing canonical Note, or the entire source is
    refused before any mutation. E3 still independently preflights the target.
    """
    if (
        not isinstance(source_proof, ReviewedFullSource)
        or not isinstance(speakers, AttestedSpeakerReview)
        or len(source_proof.reviewed_facts) != len(speakers.facts)
    ):
        raise WholeSourceCompilationError("Mismatched source/actor owner proof")
    claims = [
        (index, fact.owner_name)
        for index, fact in enumerate(source_proof.reviewed_facts)
        if fact.owner_name is not None
    ]
    if any(
        source_proof.reviewed_facts[index].kind != "record" or speakers.requires_self_link(index)
        for index, _name in claims
    ):
        raise WholeSourceCompilationError("Claimed canonical owner conflicts with reviewed role")
    # Core's EXISTING batch resolver reads current Markdown once, regardless
    # of how many independently reviewed owners one source contains.
    try:
        matches = (
            resolve_exact_entities_batch(
                repository, schema, tuple((name, None) for _index, name in claims)
            )
            if claims
            else ()
        )
    except ValueError as error:
        raise WholeSourceCompilationError("Current canonical owner lookup failed") from error
    targets: dict[int, SelectionCriteria] = {}
    canonical_ids: dict[int, str] = {}
    for (index, _name), match in zip(claims, matches, strict=True):
        if match.candidate is None:
            raise WholeSourceCompilationError("Named owner not uniquely existing")
        canonical = match.candidate
        targets[index] = SelectionCriteria(
            canonical.primary_name, canonical.primary_name, canonical.type, (), None
        )
        canonical_ids[index] = canonical.id
    return targets, canonical_ids


@dataclass(frozen=True, slots=True)
class CanonicalSourceOwnerGuard:
    """Recheck one trusted canonical owner at the existing E3 prewrite seam.

    Prevent a stale name from selecting another Note after a prior Core
    identity proof, including a same-name replacement between two operations.
    The guard grants no independent permission to mutate.
    """

    name: str
    note_type: str
    stable_id: str

    def __call__(
        self, action: WriteAction, preflight: tuple[Any, ...], repository: Any, schema: dict
    ) -> None:
        from odyssey_core.application import WritePreflightGuardError

        primary = action.units[0] if action.units else None
        resolved = next((unit for unit in preflight if unit.unit_index == 0), None)
        if (
            primary is None
            or primary.target.entity != self.name
            or primary.target.type != self.note_type
            or resolved is None
            or resolved.stable_id != self.stable_id
            or resolved.canonical_name != self.name
        ):
            raise WritePreflightGuardError("SOURCE_OWNER_CANONICAL_TARGET_CHANGED")
        try:
            current = resolve_exact_entity(repository, schema, self.name)
        except ValueError as error:
            raise WritePreflightGuardError("SOURCE_OWNER_CANONICAL_LOOKUP_UNAVAILABLE") from error
        if (
            current.candidate is None
            or current.candidate.id != self.stable_id
            or current.candidate.type != self.note_type
        ):
            raise WritePreflightGuardError("SOURCE_OWNER_CANONICAL_TARGET_STALE")


def guard_for_reviewed_owner_operation(
    operation: ReviewedSourceOperation, canonical_ids: Mapping[int, str]
) -> CanonicalSourceOwnerGuard | None:
    """Build the E3 guard from Core's source-position and identity evidence."""
    if not operation.source_positions:
        return None
    ids = {canonical_ids.get(index) for index in operation.source_positions}
    if len(ids) != 1 or None in ids or not operation.plan.actions:
        raise WholeSourceCompilationError("Grouped owner identities are inconsistent")
    target = operation.plan.actions[0].units[0].target
    if not target.entity or not target.type:
        raise WholeSourceCompilationError("Grouped owner target is invalid")
    return CanonicalSourceOwnerGuard(target.entity, target.type, next(iter(ids)))


@dataclass(frozen=True, slots=True)
class ReviewedSourceOperation:
    """Core-owned, source-order-associated write, not a mutation permission."""

    locator_suffix: str
    plan: RequestPlan
    task_create: bool = False
    source_positions: tuple[int, ...] = ()


def compile_reviewed_operations(
    review: Mapping[str, Any],
    self_roles: Sequence[bool],
    *,
    reference_types: Mapping[str, str | None] | None = None,
    declared_types: frozenset[str] | None = None,
    verified_owner_targets: Mapping[int, SelectionCriteria] | None = None,
) -> tuple[ReviewedSourceOperation, ...]:
    """Pure preflight of EVERY reviewed fact to avoid avoidable partial writes.

    The caller must first prove source coverage, identity and speaker roles.
    A later Core preflight may still reject identity, status or concurrency;
    this only guarantees that one unsupported fact cannot be found after
    earlier facts were already persisted by the same delivery.
    """
    if reference_types is not None and (
        not isinstance(reference_types, Mapping)
        or any(
            not isinstance(name, str)
            or not name.strip()
            or note_type is not None
            and (
                not isinstance(note_type, str)
                or declared_types is not None
                and note_type not in declared_types
            )
            for name, note_type in reference_types.items()
        )
    ):
        raise WholeSourceCompilationError("Unsupported or ambiguous schema reference type")
    facts = review.get("facts")
    if (
        not isinstance(facts, list)
        or not 1 <= len(facts) <= 16
        or len(facts) != len(self_roles)
        or any(type(flag) is not bool for flag in self_roles)
    ):
        raise WholeSourceCompilationError("Whole-source fact/speaker alignment invalid")
    owners = verified_owner_targets or {}
    if not isinstance(owners, Mapping) or any(
        type(i) is not int
        or i < 0
        or i >= len(facts)
        or not isinstance(target, SelectionCriteria)
        or not isinstance(target.entity, str)
        or not target.entity.strip()
        or target.query != target.entity
        or not isinstance(target.type, str)
        or declared_types is None
        or target.type not in declared_types
        or target.self_target is not None
        or target.link_scope is not None
        or target.filters
        or target.relational_reference is not None
        or target.semantic_set is not None
        or target.collection_subject is not None
        for i, target in owners.items()
    ):
        raise WholeSourceCompilationError("Unverified canonical owner target")
    days: dict[str, list[int]] = {}
    undated: list[tuple[int, dict[str, Any]]] = []
    tasks: list[tuple[int, dict[str, Any]]] = []
    owner_facts: dict[tuple[SelectionCriteria, str | None], list[tuple[int, dict[str, Any]]]] = {}
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
            or any(not isinstance(n, str) or not n.strip() for n in names)
            or len(set(names)) != len(names)
            or "[[" in raw_text
            or "<!--" in raw_text
        ):
            raise WholeSourceCompilationError("Invalid complete reviewed fact structure")
        slots = [int(number) for number in re.findall(r"\{\{ref:(\d+)\}\}", raw_text)]
        if sorted(slots) != list(range(len(names))):
            raise WholeSourceCompilationError(
                "Reference marker coverage does not match canonical entities"
            )
        kind, date = fact.get("kind"), fact.get("date")
        if position in owners:
            if (
                kind != "record"
                or self_roles[position]
                or (date is not None and not isinstance(date, str))
            ):
                raise WholeSourceCompilationError("Reviewed owner contradicts fact or speaker")
            owner_facts.setdefault((owners[position], date), []).append((position, fact))
        elif kind == "record" and isinstance(date, str) and date:
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
            plan = plan_for_record({"facts": facts}, day, reference_types=reference_types)
            action = attach_speaker_to_day_action(
                plan.actions[0], [self_roles[position] for position in positions]
            )
            operations.append(
                ReviewedSourceOperation("day-" + day, replace(plan, actions=(action,)))
            )
        if undated:
            operations.append(
                ReviewedSourceOperation(
                    "self",
                    undated_self_record(
                        [fact for _, fact in undated], reference_types=reference_types
                    ),
                )
            )
        for (owner, date), items in owner_facts.items():
            action = _record_action(
                [fact for _, fact in items],
                target=owner,
                date=date,
                reference_types=reference_types,
            )
            operations.append(
                ReviewedSourceOperation(
                    "owner-" + str(items[0][0]),
                    RequestPlan((action,), ()),
                    source_positions=tuple(position for position, _fact in items),
                )
            )
        for position, fact in tasks:
            operations.append(
                ReviewedSourceOperation(
                    "task-" + str(position),
                    plan_for_task(fact, reference_types=reference_types),
                    True,
                )
            )
    except (AssertionError, KeyError, TypeError, ValueError) as error:
        raise WholeSourceCompilationError("A reviewed fact cannot be compiled safely") from error
    if not operations:
        raise WholeSourceCompilationError("No compilable atomic operation")
    return tuple(operations)
