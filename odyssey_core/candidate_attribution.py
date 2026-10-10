"""Opt-in, source-grounded Core semantic attribution proposal (never write authority).

One separately injected Luna Responses call may *propose* correspondence between
already-planned Core atomic facts and unverified Router candidates. Exact source
quotes and Core fact text are independently validated; even an entirely grounded
proposal is NOT a CoreCandidateCoverageManifest or semantic certification.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .candidate_context import CoreCandidateContext
from .candidate_coverage import MAX_COVERAGE_FACTS
from .candidate_multi_participant import (
    MultiParticipantEvidenceError,
    validate_two_named_participant_fact,
)
from .candidate_semantic_veto import CandidateSemanticVeto, veto_unsafe_literal_match
from .experimental_luna_planning import (
    LUNA_EXPERIMENT_MODEL,
    LUNA_EXPERIMENT_REASONING_EFFORT,
)
from .request_planning import RequestPlan, WriteAction, plan_fact_ordinals

MAX_ATTRIBUTION_INPUT_BYTES = 24_576
MAX_ATTRIBUTION_OUTPUT_TOKENS = 3072


class CandidateAttributionError(ValueError):
    """Reject incomplete or ungrounded candidate attribution without effects."""


@dataclass(frozen=True, slots=True)
class ProposedCandidateAttribution:
    """Describe model-suggested source-to-Core-fact relationship, without authority."""

    candidate_id: str
    disposition: str
    fact_ordinal: int | None
    pending_reason: str | None
    source_quote: str
    planned_fact_text: str | None


@dataclass(frozen=True, slots=True)
class CandidateAttributionProposal:
    """Hold source/plan-correlated suggestions; require independent Core review."""

    candidates: tuple[ProposedCandidateAttribution, ...]
    has_grounded_literals: bool
    source_digest: str
    plan_digest: str
    semantically_verified: bool = False
    may_authorize_writes: bool = False

    def matches_original_plan(self, source: str, plan: RequestPlan) -> bool:
        """Reject stale request/plan proposals, without granting write authority."""
        return (
            isinstance(source, str)
            and isinstance(plan, RequestPlan)
            and self.source_digest == hashlib.sha256(source.encode("utf-8")).hexdigest()
            and self.plan_digest == hashlib.sha256(repr(plan).encode("utf-8")).hexdigest()
        )


def _facts(
    plan: RequestPlan, context: CoreCandidateContext
) -> tuple[dict[int, str], dict[int, str]]:
    """Extract facts for attribution without accepting unclaimed Core helpers.

    Two named, source-scoped participants may share ONE referenced Core fact.
    This projection remains non-authoritative: Core's separate coverage gate
    and canonical materializer alone may authorize mutations.
    """
    if not isinstance(plan, RequestPlan) or not isinstance(context, CoreCandidateContext):
        raise CandidateAttributionError("Validated Core plan and context required")
    result: dict[int, str] = {}
    group_owners: dict[int, str] = {}
    referenced_helpers: set[tuple[int, int]] = set()
    flattened = iter(plan_fact_ordinals(plan))
    for action_index, action in enumerate(plan.actions):
        if not isinstance(action, WriteAction):
            continue
        for unit_index, unit in enumerate(action.units):
            ordinals = next(flattened)
            if (
                unit.intent != "record"
                or unit.properties
                or unit.tag_changes
                or unit.destination_type is not None
                or unit.force_create
                or len(ordinals) != len(unit.facts)
            ):
                raise CandidateAttributionError(
                    "Complex Core fact requires separate attribution review"
                )
            if unit.reference_lookup_only:
                if unit.facts or unit.references:
                    raise CandidateAttributionError("Reference helper cannot become an atomic fact")
                continue
            if unit.references:
                if len(unit.facts) != 1 or len(unit.references) != 2:
                    raise CandidateAttributionError(
                        "Only one verified two-participant fact is supported"
                    )
                possible: list[str] = []
                for candidate in context.candidates:
                    try:
                        validate_two_named_participant_fact(
                            candidate, plan, action_index, unit_index
                        )
                    except MultiParticipantEvidenceError:
                        continue
                    possible.append(candidate.candidate_id)
                if len(possible) != 1:
                    raise CandidateAttributionError(
                        "Cannot source-bind a grouped Core fact uniquely"
                    )
                group_owners[ordinals[0]] = possible[0]
                for reference in unit.references:
                    helper_key = action_index, reference.target_index
                    if helper_key in referenced_helpers:
                        raise CandidateAttributionError(
                            "Core group helper has duplicate source ownership"
                        )
                    referenced_helpers.add(helper_key)
            for ordinal, fact in zip(ordinals, unit.facts, strict=True):
                if not isinstance(fact, str) or not fact.strip() or len(fact) > 600:
                    raise CandidateAttributionError("Invalid or oversized planned fact")
                result[ordinal] = fact
    for action_index, action in enumerate(plan.actions):
        if isinstance(action, WriteAction):
            for unit_index, unit in enumerate(action.units):
                if (
                    unit.reference_lookup_only
                    and (action_index, unit_index) not in referenced_helpers
                ):
                    raise CandidateAttributionError(
                        "Unclaimed canonical reference helper in attribution"
                    )
    if len(result) > MAX_COVERAGE_FACTS:
        raise CandidateAttributionError("Core fact attribution exceeds bounded budget")
    return result, group_owners


def candidate_attribution_json_schema() -> dict[str, Any]:
    """Emit closed GPT structured-output fields with no selection/write intent."""
    item = {
        "type": "object",
        "properties": {
            "candidate_id": {"type": "string"},
            "disposition": {"type": "string", "enum": ["proposed_fact", "pending"]},
            "fact_ordinal": {"type": ["integer", "null"]},
            "pending_reason": {
                "type": ["string", "null"],
                "enum": [
                    "ambiguous_identity",
                    "needs_clarification",
                    "needs_capability",
                    "unsupported_scope",
                    None,
                ],
            },
            "source_quote": {"type": "string"},
            "planned_fact_text": {"type": ["string", "null"]},
        },
        "required": [
            "candidate_id",
            "disposition",
            "fact_ordinal",
            "pending_reason",
            "source_quote",
            "planned_fact_text",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"candidates": {"type": "array", "items": item}},
        "required": ["candidates"],
        "additionalProperties": False,
    }


def validate_candidate_attribution(
    source: str,
    context: CoreCandidateContext,
    plan: RequestPlan,
    payload: Mapping[str, Any],
) -> CandidateAttributionProposal:
    """Validate exact Core fact/source quotations and reject unsafe model claims.

    A syntactically valid proposal is NOT a semantic validation or an execution
    manifest. Claims omitted, reordered, duplicated or invented are rejected.
    """
    if not isinstance(context, CoreCandidateContext):
        raise CandidateAttributionError("Core-owned source candidate context required")
    context.validate(source)
    facts, group_owners = _facts(plan, context)
    if not isinstance(payload, dict) or set(payload) != {"candidates"}:
        raise CandidateAttributionError("Closed candidate attribution envelope required")
    entries = payload["candidates"]
    if not isinstance(entries, list) or len(entries) != len(context.candidates):
        raise CandidateAttributionError("Every source candidate requires exactly one disposition")
    consumed: set[int] = set()
    output: list[ProposedCandidateAttribution] = []
    for position, (candidate, entry) in enumerate(zip(context.candidates, entries, strict=True)):
        if not isinstance(entry, dict) or set(entry) != {
            "candidate_id",
            "disposition",
            "fact_ordinal",
            "pending_reason",
            "source_quote",
            "planned_fact_text",
        }:
            raise CandidateAttributionError("Candidate attribution fields must be closed")
        if entry["candidate_id"] != candidate.candidate_id:
            raise CandidateAttributionError("Attribution candidate ID/order mismatch")
        source_quote = entry["source_quote"]
        if not isinstance(source_quote, str) or source_quote not in {
            anchor.text for anchor in candidate.anchors
        }:
            raise CandidateAttributionError("Attribution source quote is not a candidate anchor")
        disposition = entry["disposition"]
        ordinal, reason = entry["fact_ordinal"], entry["pending_reason"]
        planned_text = entry["planned_fact_text"]
        if disposition == "pending":
            if (
                ordinal is not None
                or planned_text is not None
                or not isinstance(reason, str)
                or reason
                not in {
                    "ambiguous_identity",
                    "needs_clarification",
                    "needs_capability",
                    "unsupported_scope",
                }
                or (candidate.state == "ambiguous_identity") != (reason == "ambiguous_identity")
            ):
                raise CandidateAttributionError("Pending attribution is inconsistent")
        elif disposition == "proposed_fact":
            if candidate.state == "ambiguous_identity":
                raise CandidateAttributionError("Ambiguous identity cannot be attributed to a fact")
            if candidate.kind in {"conditional", "negative"} or any(
                role.role in {"condition", "polarity", "replacement", "modality"}
                for role in candidate.roles
            ):
                raise CandidateAttributionError(
                    "Sensitive source requires dedicated semantic review"
                )
            if (
                not isinstance(ordinal, int)
                or isinstance(ordinal, bool)
                or (ordinal in group_owners and group_owners[ordinal] != candidate.candidate_id)
                or ordinal not in facts
                or ordinal in consumed
                or planned_text != facts[ordinal]
                or reason is not None
            ):
                raise CandidateAttributionError("Fact ordinal or exact planned text mismatched")
            try:
                veto_unsafe_literal_match(source, context, position, planned_text)
            except CandidateSemanticVeto as error:
                raise CandidateAttributionError(str(error)) from error
            consumed.add(ordinal)
        else:
            raise CandidateAttributionError("Unsupported attribution disposition")
        output.append(
            ProposedCandidateAttribution(
                candidate.candidate_id, disposition, ordinal, reason, source_quote, planned_text
            )
        )
    if consumed != set(facts):
        raise CandidateAttributionError("All planned facts require one candidate proposal")
    return CandidateAttributionProposal(
        tuple(output),
        has_grounded_literals=True,
        source_digest=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        plan_digest=hashlib.sha256(repr(plan).encode("utf-8")).hexdigest(),
    )


class OpenAICoreCandidateAttributor:
    """Separate non-executing Luna proposer; current Core planner remains unchanged."""

    def __init__(self, client: Any) -> None:
        """Use an injected Responses-compatible client, never own credentials."""
        self._client = client
        self.last_usage: Any | None = None
        self.last_error_category: str | None = None

    def propose(
        self,
        source: str,
        context: CoreCandidateContext,
        plan: RequestPlan,
    ) -> CandidateAttributionProposal:
        """Propose an exhaustive, source-grounded, non-authoritative correspondence.

        No model call occurs for unsupported Core plans, stale original source,
        invalid scope, or oversized payload. This does NOT call execute_request.
        """
        if not isinstance(context, CoreCandidateContext):
            raise CandidateAttributionError("Core-owned candidate context required")
        context.validate(source)
        facts, _group_owners = _facts(plan, context)
        prompt_data = json.dumps(
            {
                "original_source": source,
                "unverified_source_candidates": [
                    candidate.to_payload() for candidate in context.candidates
                ],
                "core_planned_atomic_facts": [
                    {"fact_ordinal": ordinal, "fact_text": fact} for ordinal, fact in facts.items()
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(prompt_data.encode("utf-8")) > MAX_ATTRIBUTION_INPUT_BYTES:
            raise CandidateAttributionError("Attribution input exceeds provider safety budget")
        self.last_usage = None
        self.last_error_category = None
        try:
            response = self._client.responses.create(
                model=LUNA_EXPERIMENT_MODEL,
                reasoning={"effort": LUNA_EXPERIMENT_REASONING_EFFORT},
                max_output_tokens=MAX_ATTRIBUTION_OUTPUT_TOKENS,
                store=False,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You are a Core-only read-only fact correspondence reviewer. This is "
                            "not Router, Temporal, or a source of canonical identity, note type, "
                            "normalized date or write authority. Preserve Core's original selection, "
                            "reference, ambiguity, polarity, conditional, fact and safety rules. "
                            "For EACH source candidate in supplied order, either propose exactly "
                            "one existing Core planned fact ordinal with the EXACT fact text, or "
                            "mark it pending for a closed reason. Quote one exact original candidate "
                            "anchor (not a paraphrase) as source_quote. Never match a candidate "
                            "only by sequence, word overlap, shared participant, or temporal mention. "
                            "Require the whole statement, roles and temporal ownership to agree, "
                            "including negations and corrections. Mark ambiguous identities pending. "
                            "One Core fact ordinal can be proposed by at most one candidate in this "
                            "pilot; each Core fact must be represented. If one fact combines multiple "
                            "candidates, decline the unsupported plan rather than invent a split. "
                            "No modifications, execution, canonical IDs, Markdown or extra fields. "
                            "This is an untrusted proposal subject to independent Core review."
                        ),
                    },
                    {"role": "user", "content": prompt_data},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "odyssey_core_candidate_attribution_proposal_v1",
                        "strict": True,
                        "schema": candidate_attribution_json_schema(),
                    }
                },
            )
        except Exception as error:
            self.last_error_category = type(error).__name__[:100]
            raise CandidateAttributionError("Attribution provider call failed") from error
        self.last_usage = getattr(response, "usage", None)
        if getattr(response, "status", None) != "completed":
            self.last_error_category = "IncompleteProviderResponse"
            raise CandidateAttributionError("Attribution provider response is incomplete")
        try:
            data = json.loads(response.output_text)
        except (ValueError, TypeError, AttributeError) as error:
            self.last_error_category = "MalformedProviderResponse"
            raise CandidateAttributionError(
                "Attribution provider output is invalid JSON"
            ) from error
        try:
            return validate_candidate_attribution(source, context, plan, data)
        except (CandidateAttributionError, TypeError, ValueError) as error:
            self.last_error_category = "UngroundedAttribution"
            raise CandidateAttributionError(
                "Attribution provider output failed Core validation"
            ) from error
