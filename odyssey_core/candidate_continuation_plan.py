"""Inspect a Core proposal for unresolved candidate facts without granting E3 access.

An already-selected identity is trusted *source evidence*, not proof that
an LLM's proposed facts, dates or targets preserve the user's meaning.
This structural gate accepts arbitrary fact cardinality and defers semantic
attestation and canonical read/write authority to separate Core stages.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .atomic_facts import normalize_atomic_fact
from .candidate_continuation_context import CoreCandidateContinuationContext
from .request_planning import RequestPlan, WriteAction, plan_fact_ordinals

_MAX_FACTS = 128
_MAX_PAYLOAD_BYTES = 40_960


class CandidateContinuationPlanError(ValueError):
    """Reject a malformed, unrelated or unsupported continuation proposal."""


@dataclass(frozen=True, slots=True)
class CoreContinuationProposedFact:
    """One Core-plan fact, still not independently verified against source."""

    ordinal: int
    text: str
    destination_type: str | None
    destination_query: str
    temporal_values: tuple[str, ...]
    reference_mentions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CoreContinuationPlanInspection:
    """A plan-bound, non-executing input for a future semantic reviewer."""

    source_digest: str
    pending_record_digest: str
    plan_digest: str
    captured_at: str
    proposed_facts: tuple[CoreContinuationProposedFact, ...]
    selected_identity_reference_ordinals: tuple[int, ...]

    @property
    def may_execute(self) -> bool:
        return False

    def review_payload(self, context: CoreCandidateContinuationContext) -> dict[str, Any]:
        """Review the exact source and *all* newly proposed facts, not old facts.

        IDs, physical note guards and write permissions must never be exposed
        to a provider or inferred from this read-only request.
        """
        if not isinstance(context, CoreCandidateContinuationContext) or (
            context.source_digest != self.source_digest
            or context.pending_record_digest != self.pending_record_digest
            or context.captured_at != self.captured_at
        ):
            raise CandidateContinuationPlanError("Proposed review input is stale")
        content = {
            **context.review_payload(),
            "source_digest": self.source_digest,
            "plan_digest": self.plan_digest,
            "proposed_facts": [
                {
                    "ordinal": item.ordinal,
                    "text": item.text,
                    "destination_type": item.destination_type,
                    "destination_query": item.destination_query,
                    "temporal_values": list(item.temporal_values),
                    "reference_mentions": list(item.reference_mentions),
                }
                for item in self.proposed_facts
            ],
            "selected_identity_reference_ordinals": list(self.selected_identity_reference_ordinals),
        }
        if len(json.dumps(content, ensure_ascii=False).encode("utf-8")) > _MAX_PAYLOAD_BYTES:
            raise CandidateContinuationPlanError("Review input exceeds bounded size")
        return content


def inspect_selected_candidate_plan(
    context: CoreCandidateContinuationContext, plan: RequestPlan
) -> CoreContinuationPlanInspection:
    """Require a source-bound, only-record continuation before semantic review.

    This is deliberately *not* proof of temporal truth, polarity, action
    ownership or identity resolution. No E3 write path consumes this result.
    No example phrases, pronouns or candidate counts drive the inspection.
    """
    if (
        not isinstance(context, CoreCandidateContinuationContext)
        or not isinstance(plan, RequestPlan)
        or not plan.actions
        or any(not isinstance(action, WriteAction) for action in plan.actions)
        or plan.limitations
        or plan.presentation_intent != "answer"
    ):
        raise CandidateContinuationPlanError("Only unresolved Core record proposals are supported")
    try:
        ordinals_by_unit = iter(plan_fact_ordinals(plan))
        completed_digests = {marker.fact_digest for marker in context.completed_facts}
        facts: list[CoreContinuationProposedFact] = []
        bound: list[int] = []
        for action in plan.actions:
            if not 1 <= len(action.units) <= _MAX_FACTS:
                raise CandidateContinuationPlanError("Empty or oversized continuation action")
            referred_helpers: set[int] = set()
            helper_indexes: set[int] = set()
            for index, unit in enumerate(action.units):
                if (
                    unit.intent != "record"
                    or unit.force_create
                    or unit.properties
                    or unit.tag_changes
                    or unit.destination_type is not None
                    or unit.cardinality != "one"
                ):
                    raise CandidateContinuationPlanError("Continuation has unsupported mutations")
                if unit.reference_lookup_only:
                    if (
                        unit.facts
                        or unit.references
                        or unit.fact_temporal_anchors
                        or unit.target.entity is None
                    ):
                        raise CandidateContinuationPlanError("Unsafe reference-only helper")
                    helper_indexes.add(index)
            for unit in action.units:
                unit_ordinals = next(ordinals_by_unit)
                if unit.reference_lookup_only:
                    if unit_ordinals:
                        raise CandidateContinuationPlanError("Helper must not write facts")
                    continue
                if not unit.facts:
                    raise CandidateContinuationPlanError("Empty continuation writer")
                if len(unit.facts) != len(unit.fact_temporal_anchors):
                    raise CandidateContinuationPlanError("Missing temporal fact positions")
                mentions: list[str] = []
                selected_reference_indexes: set[int] = set()
                for reference_index, reference in enumerate(unit.references):
                    if (
                        reference.selection is not None
                        or type(reference.target_index) is not int
                        or reference.target_index not in helper_indexes
                    ):
                        raise CandidateContinuationPlanError("Unresolved continuation lookup")
                    referred_helpers.add(reference.target_index)
                    mentions.append(reference.mention)
                    if reference.mention == context.reference_text:
                        helper = action.units[reference.target_index]
                        if (
                            helper.target.entity is None
                            or helper.target.entity.casefold() != context.selected_name.casefold()
                        ):
                            raise CandidateContinuationPlanError(
                                "Selected reference is not bound to chosen identity hint"
                            )
                        selected_reference_indexes.add(reference_index)
                for ordinal, literal, temporal in zip(
                    unit_ordinals, unit.facts, unit.fact_temporal_anchors, strict=True
                ):
                    if (
                        not isinstance(literal, str)
                        or not literal.strip()
                        or len(literal) > 600
                        or any(not hasattr(anchor, "value") for anchor in temporal)
                    ):
                        raise CandidateContinuationPlanError("Invalid proposed fact")
                    if (
                        hashlib.sha256(normalize_atomic_fact(literal).encode("utf-8")).hexdigest()
                        in completed_digests
                    ):
                        raise CandidateContinuationPlanError(
                            "Proposal repeats previously verified atomic knowledge"
                        )
                    facts.append(
                        CoreContinuationProposedFact(
                            ordinal,
                            literal,
                            unit.target.type,
                            unit.target.query,
                            tuple(anchor.value for anchor in temporal),
                            tuple(mentions),
                        )
                    )
                    if any(
                        "{{ref:" + str(index) + "}}" in literal
                        for index in selected_reference_indexes
                    ):
                        bound.append(ordinal)
            if referred_helpers != helper_indexes:
                raise CandidateContinuationPlanError("Unreferenced continuation identity helper")
        if not 1 <= len(facts) <= _MAX_FACTS or not bound:
            raise CandidateContinuationPlanError("Selected source reference is absent from facts")
        result = CoreContinuationPlanInspection(
            source_digest=context.source_digest,
            pending_record_digest=context.pending_record_digest,
            plan_digest=hashlib.sha256(repr(plan).encode("utf-8")).hexdigest(),
            captured_at=context.captured_at,
            proposed_facts=tuple(facts),
            selected_identity_reference_ordinals=tuple(bound),
        )
        result.review_payload(context)
        return result
    except (ValueError, TypeError, AttributeError) as error:
        if isinstance(error, CandidateContinuationPlanError):
            raise
        raise CandidateContinuationPlanError("Invalid typed Core proposal") from error
