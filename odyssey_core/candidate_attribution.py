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
from .candidate_correction_chain import correction_chain
from .candidate_coverage import MAX_COVERAGE_CLAIMS, MAX_COVERAGE_FACTS
from .candidate_multi_participant import (
    MultiParticipantEvidenceError,
    validate_two_named_participant_fact,
)
from .candidate_semantic_veto import CandidateSemanticVeto, veto_unsafe_literal_match
from .candidate_sequential_contacts import (
    SequentialContactEvidenceError,
    validate_two_sequential_contacts,
)
from .experimental_luna_planning import (
    LUNA_EXPERIMENT_MODEL,
    LUNA_EXPERIMENT_REASONING_EFFORT,
)
from .request_planning import RequestPlan, WriteAction, plan_fact_ordinals

MAX_ATTRIBUTION_INPUT_BYTES = 24_576
MAX_ATTRIBUTION_OUTPUT_TOKENS = 3072


def _reviewable_sensitive_literal(context: CoreCandidateContext) -> bool:
    """Typed group source allows N:1 *review*, never a source-free write."""
    return (
        context.hybrid_interpretation_mode
        and context.verified_sensitive_temporal is not None
        and all(c.state == "candidate" for c in context.candidates)
    )


def _reviewable_final_correction(context: CoreCandidateContext, position: int) -> bool:
    """Only the final candidate of a typed, exact-source linear correction.

    This is *not* write authority: the Core coverage preflight separately
    verifies cancelled scope, exact changed object, date, clock, target and fact.
    """
    return (
        context.hybrid_interpretation_mode
        and context.verified_correction_temporal is not None
        and correction_chain(context.candidates) is not None
        and position == len(context.candidates) - 1
        and context.candidates[position].state == "candidate"
        and any(r.role == "replacement" for r in context.candidates[position].roles)
    )


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
) -> tuple[dict[int, str], dict[int, str], dict[int, str]]:
    """Extract facts for attribution without accepting unclaimed Core helpers.

    Two named participants may share ONE event, or two explicitly sequential
    contacts may each own one separately referenced Core fact.
    This projection remains non-authoritative: Core's separate coverage gate
    and canonical materializer alone may authorize mutations.
    """
    if not isinstance(plan, RequestPlan) or not isinstance(context, CoreCandidateContext):
        raise CandidateAttributionError("Validated Core plan and context required")
    result: dict[int, str] = {}
    group_owners: dict[int, str] = {}
    lexical_fact: dict[int, str] = {}
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
                if len(unit.references) != 2:
                    raise CandidateAttributionError(
                        "Only two canonical reference helpers are supported"
                    )
                if len(unit.facts) == 1:
                    possible: list[str] = []
                    for candidate in context.candidates:
                        try:
                            validate_two_named_participant_fact(
                                context.source, candidate, plan, action_index, unit_index
                            )
                        except MultiParticipantEvidenceError:
                            continue
                        possible.append(candidate.candidate_id)
                    if len(possible) != 1:
                        raise CandidateAttributionError(
                            "Cannot source-bind a grouped Core fact uniquely"
                        )
                    group_owners[ordinals[0]] = possible[0]
                elif len(unit.facts) == 2:
                    try:
                        validate_two_sequential_contacts(context, plan, action_index, unit_index)
                    except SequentialContactEvidenceError as error:
                        raise CandidateAttributionError(str(error)) from error
                    for fact_index, ordinal in enumerate(ordinals):
                        group_owners[ordinal] = context.candidates[fact_index].candidate_id
                else:
                    raise CandidateAttributionError("Unreviewed referenced Core fact shape")
                for reference in unit.references:
                    helper_key = action_index, reference.target_index
                    if helper_key in referenced_helpers:
                        raise CandidateAttributionError(
                            "Core reference helper has duplicate source ownership"
                        )
                    referenced_helpers.add(helper_key)
            for ordinal, fact in zip(ordinals, unit.facts, strict=True):
                if not isinstance(fact, str) or not fact.strip() or len(fact) > 600:
                    raise CandidateAttributionError("Invalid or oversized planned fact")
                result[ordinal] = fact
                lexical = fact
                for reference_index, reference in enumerate(unit.references):
                    lexical = lexical.replace(f"{{{{ref:{reference_index}}}}}", reference.mention)
                lexical_fact[ordinal] = lexical
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
    return result, group_owners, lexical_fact


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
    facts, group_owners, lexical_facts = _facts(plan, context)
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
            if (
                candidate.kind in {"conditional", "negative"}
                or any(
                    role.role in {"condition", "polarity", "replacement", "modality"}
                    for role in candidate.roles
                )
            ) and not (
                _reviewable_final_correction(context, position)
                or _reviewable_sensitive_literal(context)
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
                veto_unsafe_literal_match(source, context, position, lexical_facts[ordinal])
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
        facts, _group_owners, _lexical_facts = _facts(plan, context)
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

    def propose_graph(
        self,
        source: str,
        context: CoreCandidateContext,
        plan: RequestPlan,
        *,
        canonical_binding: object | None = None,
        verified_temporal: object | None = None,
    ) -> CandidateFactGraph:
        """Independently propose complete 0..N links for the unmodified Core plan.

        This second model call is not an alternative Core planner. The output
        cannot carry actions, canonical identities, dates or Note content, and
        is checked again by the ordinary Core prewrite coverage validator.
        """
        context.validate(source)
        from .domain_interpretation import DomainInterpretation

        if verified_temporal is not None and (
            not isinstance(verified_temporal, DomainInterpretation)
            or verified_temporal.source_text != source
            or verified_temporal.capability_id != "temporal"
            or verified_temporal.intent != "TEMPORAL_RESOLUTION"
        ):
            raise CandidateAttributionError("Reviewer Temporal proof differs from current source")
        facts = _graph_plan_fact_texts(plan, context)
        canonical_proof = None
        if canonical_binding is not None:
            from .application import CanonicalReferenceEvidence, DependentReferenceGuard

            if (
                not isinstance(canonical_binding, DependentReferenceGuard)
                or not isinstance(canonical_binding.evidence, CanonicalReferenceEvidence)
                or canonical_binding.mention not in source
            ):
                raise CandidateAttributionError("Core predecessor reference proof is invalid")
            canonical_proof = {
                "source_mention": canonical_binding.mention,
                "canonical_type": canonical_binding.evidence.note_type,
                "canonical_name": canonical_binding.evidence.canonical_name,
                "source_proof_kind": (
                    "verified_written_direct_target"
                    if canonical_binding.evidence.source_reference_index == -1
                    else "verified_written_identity_link"
                ),
            }
        target_context = []
        ordinal_groups = iter(plan_fact_ordinals(plan))
        for action in plan.actions:
            if not isinstance(action, WriteAction):
                continue
            for unit in action.units:
                for ordinal in next(ordinal_groups):
                    target_context.append(
                        {
                            "fact_ordinal": ordinal,
                            "core_proposed_target": {
                                "entity": unit.target.entity,
                                "query": unit.target.query,
                                "type": unit.target.type,
                            },
                        }
                    )
        prompt_data = json.dumps(
            {
                "original_source": source,
                "trusted_core_predecessor_reference": canonical_proof,
                "core_verified_temporal_read_only": (
                    verified_temporal.to_prompt_payload() if verified_temporal is not None else None
                ),
                "core_proposed_targets_not_identity_proof": target_context,
                "unverified_source_candidates": [
                    candidate.to_payload() for candidate in context.candidates
                ],
                "shared_source_provenance": [
                    role.to_payload() for role in context.source_provenance
                ],
                "core_verified_inherited_subject": (
                    context.verified_inherited_subject.prompt_payload()
                    if context.verified_inherited_subject is not None
                    else None
                ),
                "core_verified_inherited_event": (
                    context.verified_inherited_event.prompt_payload()
                    if context.verified_inherited_event is not None
                    else None
                ),
                "core_planned_atomic_facts": [
                    {"fact_ordinal": ordinal, "fact_text": value}
                    for ordinal, value in facts.items()
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
            reply = self._client.responses.create(
                model=LUNA_EXPERIMENT_MODEL,
                reasoning={"effort": LUNA_EXPERIMENT_REASONING_EFFORT},
                max_output_tokens=MAX_ATTRIBUTION_OUTPUT_TOKENS,
                store=False,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You are a Core-only independent read-only semantic reviewer "
                            "of the CURRENT ROUTED USER SOURCE FRAGMENT against an already "
                            "compiled ordinary Core plan. Never request or reconstruct "
                            "sibling source text. These source candidates are "
                            "untrusted Router hints, not individual facts or identities. "
                            "core_verified_temporal_read_only contains the independently "
                            "validated Temporal source-text/date/time bindings for this "
                            "CURRENT fragment when supplied. It is read-only evidence, "
                            "NOT evidence an event happened or permission to change Core "
                            "facts. Use it to compare each Core fact's date and clock "
                            "with its actual originating source, including a second "
                            "event explicitly stated at the same earlier verified time. "
                            "Do not call an independently justified common-clock or "
                            "inherited-date event unsupported solely because Temporal "
                            "supplies one original clock and one source date shared by "
                            "several coordinated facts. Reject mismatched time, "
                            "unproved event ownership and missing source actions. "
                            "For every candidate in original order propose 0..N existing "
                            "Core atomic fact ordinals; multiple candidates may support "
                            "one fact, and one candidate may support several facts. "
                            "For every ordinal copy the EXACT planned fact text into "
                            "planned_fact_texts, preserving the order. Source_quote must "
                            "be the exact LITERAL characters of one candidate anchor, "
                            "WITHOUT surrounding quotation marks. Do not quote a "
                            "whole clause unless it is exactly one anchor. All Core "
                            "planned facts must have at least one fully justified source "
                            "candidate; all candidates must be accounted for. "
                            "core_proposed_targets_not_identity_proof describes which Note "
                            "Core proposes for each fact, NOT a verified identity or write "
                            "authority. Compare that target with the current source subject; "
                            "the fact sentence may omit its subject because the subject is "
                            "represented by the Core proposed target. For a straightforward "
                            "affirmative event whose grammatical subject matches the "
                            "Core-proposed target and whose predicate/object are grounded, "
                            "do not mark it pending solely because the fact sentence lacks "
                            "a repeated subject. Reject targets not justified by source. "
                            "When trusted_core_predecessor_reference explicitly carries "
                            "source_proof_kind=verified_written_direct_target, an OBJECT "
                            "pronoun in the CURRENT source may refer to that proven Note "
                            "as the target whose history the proposed fact updates. "
                            "This is not a grammatical-subject substitution: independently "
                            "verify the real sender/agent, predicate, object referent, "
                            "other named recipients and Temporal date. Do not reject a "
                            "genuine document/entity life event solely because the "
                            "proven referenced object is the proposed Note target rather "
                            "than the grammatical subject, but do reject unrelated "
                            "or invented targets and unsupported pronoun swaps. "
                            "SEPARATE source-reference semantics from canonical Note binding: "
                            "you have NO access to the note repository and MUST NOT judge "
                            "whether a mentioned person's Note exists or invent a canonical ID. "
                            "A clearly explicit, unambiguous named participant in the source "
                            "is NOT ambiguous_identity merely because its Note was not "
                            "provided; judge whether the planned fact preserves that exact "
                            "person, action and scope, leaving actual reuse or safe creation "
                            "to Core's independent canonical identity resolver. "
                            "Use ambiguous_identity only for genuine ambiguity of the SOURCE "
                            "referent itself, such as an unresolved pronoun with competing "
                            "antecedents, never as a generic substitute for absent note context. "
                            "For a first-person ordinary action (including a "
                            "grammatically elided singular first-person subject), "
                            "SPEAKER may be a symbolic SELF fact participant ONLY "
                            "when the CURRENT source unambiguously supports it; "
                            "a Core-owned authenticated binding must independently "
                            "resolve the canonical Person reference at preflight. "
                            "A literal Day fact remains valid if no symbolic "
                            "identity claim is supported; never invent a user, "
                            "treat write provenance as the grammatical subject, "
                            "or misattribute another named or collective subject. "
                            "Inside the CURRENT complete selected source group, "
                            "independently analyze COORDINATION and GRAMMATICAL ELLIPSIS: "
                            "a predicate stated once can govern several separate people, "
                            "days or locations. A second candidate may quote only its new "
                            "participant, date and place while its complete proposed Core "
                            "fact legitimately repeats that source predicate. Verify the "
                            "shared predicate and scope against the entire CURRENT original "
                            "source, not merely the second candidate anchor. Source "
                            "inheritance labels are untrusted hints; confirm the grammar "
                            "directly and reject any uncertain or competing antecedent. "
                            "When the grammar unambiguously supports two separate events, "
                            "attribute each to its own source candidate and Core fact, "
                            "rather than calling the second event needs_clarification "
                            "solely because its verb was omitted in the coordinated "
                            "clause. Preserve each original participant, tense, polarity, "
                            "place and time; never copy the prior participant or event "
                            "if the original source does not support that second fact. "
                            "For independent candidates and distinct proposed facts, "
                            "judge EACH candidate/fact semantic correspondence independently. "
                            "If a participant, event, polarity or temporal owner is lost, "
                            "swapped or invented, remain pending even if names overlap. "
                            "Compare full semantic meaning including subject, predicate, "
                            "participants, date/time ownership, tense, negation, modality "
                            "and conditional/correction scope. Never match merely because "
                            "positions, words, names or dates overlap. Never invent or "
                            "change any fact, identity, link, note, source quote or date. "
                            "For an ungrounded or ambiguous candidate return empty "
                            "fact_ordinals and planned_fact_texts plus one closed pending "
                            "reason. If the plan omits an asserted fact or changes its "
                            "meaning, do NOT invent an attribution to conceal it. "
                            "Never execute, plan, persist or authorize a write. "
                            "If trusted_core_predecessor_reference is present, "
                            "the source mention is already bound by an actual "
                            "Core-persisted and freshness-checked predecessor; "
                            "review the current Core fact with that typed name "
                            "and DO NOT declare ambiguity solely because the "
                            "source uses that pronoun. Never infer OTHER pronouns, "
                            "and reject a plan bound to a different identity. "
                            "All claims undergo independent Core validation; when "
                            "uncertain, return pending rather than guessing."
                        ),
                    },
                    {"role": "user", "content": prompt_data},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "odyssey_core_candidate_fact_graph_v2",
                        "strict": True,
                        "schema": candidate_fact_graph_json_schema(),
                    }
                },
            )
        except Exception as error:
            self.last_error_category = type(error).__name__[:100]
            raise CandidateAttributionError("Graph attribution provider failed") from error
        self.last_usage = getattr(reply, "usage", None)
        if getattr(reply, "status", None) != "completed":
            self.last_error_category = "IncompleteProviderResponse"
            raise CandidateAttributionError("Graph attribution response is incomplete")
        try:
            payload = json.loads(reply.output_text)
            return validate_candidate_fact_graph_proposal(source, context, plan, payload)
        except (CandidateAttributionError, TypeError, ValueError, AttributeError) as error:
            self.last_error_category = "InvalidGraphAttribution"
            raise CandidateAttributionError("Graph attribution evidence is invalid") from error


@dataclass(frozen=True, slots=True)
class CandidateFactLinks:
    """One source candidate's nonauthoritative relationship to 0..N Core facts.

    Empty fact_ordinals means *pending*, never silently dropped. This is a
    Core-owned diagnostic, not a PlannerResult, writer instruction or durable
    semantic attestation. Multiple source candidates can propose the same
    fact ordinal without assigning a canonical identity.
    """

    candidate_id: str
    source_quote: str
    fact_ordinals: tuple[int, ...]
    pending_reason: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateFactGraph:
    """Complete N:M candidate/fact graph, explicitly NOT a write authority."""

    links: tuple[CandidateFactLinks, ...]
    source_digest: str
    plan_digest: str
    candidate_count: int
    fact_count: int
    semantically_verified: bool = False
    may_authorize_writes: bool = False

    def matches_original_plan(self, source: str, plan: RequestPlan) -> bool:
        """Prevent unrelated messages/plans from using an old graph."""
        return (
            isinstance(source, str)
            and isinstance(plan, RequestPlan)
            and self.source_digest == hashlib.sha256(source.encode("utf-8")).hexdigest()
            and self.plan_digest == hashlib.sha256(repr(plan).encode("utf-8")).hexdigest()
        )


def inspect_candidate_fact_graph(
    source: str,
    context: CoreCandidateContext,
    plan: RequestPlan,
    links: tuple[CandidateFactLinks, ...],
) -> CandidateFactGraph:
    """Check structural completeness for N source candidates vs M atomic facts.

    Unlike the legacy one-to-one attribution pilot this never assumes that a
    Router unit is one Core fact. It deliberately does NOT authorize any
    canonical write or claim semantic equivalence: source-quote overlap,
    plausible ordinal assignments or a model's claim cannot establish that
    shared subjects, implied relations, polarity or anaphora are correct.

    No dependency on lexical wording, identity subtype, sentence punctuation
    or candidate position. Pending or sensitive candidates are preserved
    as unresolved rather than being converted to an invented planned fact.
    """
    if not isinstance(context, CoreCandidateContext) or not isinstance(plan, RequestPlan):
        raise CandidateAttributionError("Original Core context and validated plan required")
    context.validate(source)
    if (
        not isinstance(links, tuple)
        or len(links) != len(context.candidates)
        or any(not isinstance(link, CandidateFactLinks) for link in links)
    ):
        raise CandidateAttributionError("Each source candidate requires one typed graph link")
    if len(links) > MAX_COVERAGE_CLAIMS:
        raise CandidateAttributionError("Source graph exceeds the current technical budget")

    actual: set[int] = set()
    for ordinal_group in plan_fact_ordinals(plan):
        actual.update(ordinal_group)
    if len(actual) > MAX_COVERAGE_FACTS:
        raise CandidateAttributionError("Atomic fact graph exceeds the technical budget")
    accounted: set[int] = set()
    for position, (candidate, link) in enumerate(zip(context.candidates, links, strict=True)):
        if link.candidate_id != candidate.candidate_id:
            raise CandidateAttributionError("Graph source candidate ID or ordering mismatch")
        quote = link.source_quote
        exact = quote in {anchor.text for anchor in candidate.anchors}
        if not exact:
            # Accept a reviewer quote extending one exact Router anchor with
            # original adjacent source words, never an invented or cross-clause
            # quotation. The whole-plan Core review still runs separately.
            grounded = False
            if isinstance(quote, str) and 0 < len(quote) <= 256:
                pos = source.find(quote)
                while pos >= 0:
                    if not any(ch in quote for ch in ".;!?") and any(
                        pos <= a.start
                        and a.end <= pos + len(quote)
                        and source[a.start : a.end] == a.text
                        for a in candidate.anchors
                    ):
                        grounded = True
                        break
                    pos = source.find(quote, pos + 1)
            if not grounded:
                raise CandidateAttributionError(
                    "Graph source quote is not grounded around an original candidate anchor"
                )
        ordinals = link.fact_ordinals
        if (
            not isinstance(ordinals, tuple)
            or any(not isinstance(number, int) or isinstance(number, bool) for number in ordinals)
            or len(set(ordinals)) != len(ordinals)
            or any(number not in actual for number in ordinals)
            or tuple(sorted(ordinals)) != ordinals
        ):
            raise CandidateAttributionError("Invalid, duplicated or invented fact edge")
        if ordinals:
            if link.pending_reason is not None:
                raise CandidateAttributionError("Planned candidate cannot also claim to be pending")
            if (
                candidate.state == "ambiguous_identity"
                or (
                    candidate.kind in {"conditional", "negative"}
                    or any(
                        role.role in {"condition", "polarity", "replacement", "modality"}
                        for role in candidate.roles
                    )
                )
                and not _reviewable_final_correction(context, position)
                and not _reviewable_sensitive_literal(context)
            ):
                raise CandidateAttributionError(
                    "Sensitive or ambiguous meaning requires a separate Core semantic review"
                )
            accounted.update(ordinals)
        elif link.pending_reason not in {
            "ambiguous_identity",
            "needs_clarification",
            "needs_capability",
            "unsupported_scope",
        } or (candidate.state == "ambiguous_identity") != (
            link.pending_reason == "ambiguous_identity"
        ):
            raise CandidateAttributionError(
                "Unplanned candidate requires an explicit pending reason"
            )
    if accounted != actual:
        raise CandidateAttributionError("Every planned Core fact needs explicit source evidence")
    return CandidateFactGraph(
        links=links,
        source_digest=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        plan_digest=hashlib.sha256(repr(plan).encode("utf-8")).hexdigest(),
        candidate_count=len(context.candidates),
        fact_count=len(actual),
    )


def _graph_plan_fact_texts(plan: RequestPlan, context: CoreCandidateContext) -> dict[int, str]:
    """Project arbitrary Core-recorded fact ordinals without limiting helper count.

    Source attribution NEVER approves references or Note targets. The ordinary
    coverage preflight verifies all reference helpers, canonical identities,
    and source meaning after the model proposes candidate/fact edges.
    """
    if not isinstance(plan, RequestPlan) or not isinstance(context, CoreCandidateContext):
        raise CandidateAttributionError("Validated Core plan/context required")
    facts: dict[int, str] = {}
    ordinals = iter(plan_fact_ordinals(plan))
    for action in plan.actions:
        if not isinstance(action, WriteAction):
            continue
        for unit in action.units:
            unit_ordinals = next(ordinals)
            if (
                unit.intent != "record"
                or unit.properties
                or unit.tag_changes
                or unit.destination_type is not None
                or unit.force_create
                or len(unit_ordinals) != len(unit.facts)
                or (unit.reference_lookup_only and (unit.facts or unit.references))
            ):
                raise CandidateAttributionError("Complex graph Core plan needs separate review")
            for ordinal, fact in zip(unit_ordinals, unit.facts, strict=True):
                if not isinstance(fact, str) or not fact.strip() or len(fact) > 600:
                    raise CandidateAttributionError("Graph planned fact is invalid")
                facts[ordinal] = fact
    if not 1 <= len(facts) <= MAX_COVERAGE_FACTS:
        raise CandidateAttributionError("Graph fact count exceeds technical budget")
    return facts


def candidate_fact_graph_json_schema() -> dict[str, Any]:
    """Strict non-executing N:M graph proposal schema for independent Core review."""
    item = {
        "type": "object",
        "properties": {
            "candidate_id": {"type": "string"},
            "source_quote": {"type": "string"},
            "fact_ordinals": {"type": "array", "items": {"type": "integer"}},
            "planned_fact_texts": {"type": "array", "items": {"type": "string"}},
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
        },
        "required": [
            "candidate_id",
            "source_quote",
            "fact_ordinals",
            "planned_fact_texts",
            "pending_reason",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"candidates": {"type": "array", "items": item}},
        "required": ["candidates"],
        "additionalProperties": False,
    }


def validate_candidate_fact_graph_proposal(
    source: str,
    context: CoreCandidateContext,
    plan: RequestPlan,
    payload: Any,
) -> CandidateFactGraph:
    """Validate each model-claimed N:M edge and source quotation before prewrite review.

    Do not duplicate Core's semantic fact/target review here: the established
    coverage validator checks both literal and canonically scoped target
    evidence, including facts whose subject belongs to the target Note.
    The result is not authority to write until that validator passes.
    """
    facts = _graph_plan_fact_texts(plan, context)
    if not isinstance(payload, dict) or set(payload) != {"candidates"}:
        raise CandidateAttributionError("Closed graph proposal required")
    entries = payload["candidates"]
    if not isinstance(entries, list) or len(entries) != len(context.candidates):
        raise CandidateAttributionError("Every source candidate needs one graph proposal")
    links: list[CandidateFactLinks] = []
    for _candidate, entry in zip(context.candidates, entries, strict=True):
        if not isinstance(entry, dict) or set(entry) != {
            "candidate_id",
            "source_quote",
            "fact_ordinals",
            "planned_fact_texts",
            "pending_reason",
        }:
            raise CandidateAttributionError("Closed graph candidate fields required")
        ordinals, planned_texts = entry["fact_ordinals"], entry["planned_fact_texts"]
        if (
            not isinstance(ordinals, list)
            or not isinstance(planned_texts, list)
            or len(ordinals) != len(planned_texts)
            or len(ordinals) > MAX_COVERAGE_FACTS
        ):
            raise CandidateAttributionError("Graph ordinal/text correspondence is invalid")
        if any(
            not isinstance(ordinal, int)
            or isinstance(ordinal, bool)
            or ordinal not in facts
            or text != facts.get(ordinal)
            for ordinal, text in zip(ordinals, planned_texts, strict=True)
        ):
            raise CandidateAttributionError("Graph proposes a fabricated or modified Core fact")
        links.append(
            CandidateFactLinks(
                entry["candidate_id"],
                entry["source_quote"],
                tuple(ordinals),
                entry["pending_reason"],
            )
        )
    return inspect_candidate_fact_graph(source, context, plan, tuple(links))


def review_model_candidate_fact_coverage(
    source: str,
    context: CoreCandidateContext,
    plan: RequestPlan,
    attributor: OpenAICoreCandidateAttributor,
    *,
    canonical_binding: object | None = None,
    verified_temporal: object | None = None,
):
    """Pass an independent model proposal through existing Core prewrite authority.

    Invalid model output or unsupported graph shapes fail closed without
    permitting a partial write. This is not semantic certification: the
    candidate-to-fact result remains unverified until subsequent evidence.
    """
    from .candidate_coverage import CoreCandidateCoverageClaim, build_candidate_coverage_manifest

    graph = attributor.propose_graph(
        source,
        context,
        plan,
        canonical_binding=canonical_binding,
        verified_temporal=verified_temporal,
    )
    if not graph.matches_original_plan(source, plan) or graph.may_authorize_writes:
        raise CandidateAttributionError("Candidate graph does not match the current Core plan")
    # Retain existing strict legacy 1:1 canonical reference validation when
    # the independent model proposes exactly one unshared fact per candidate.
    # General 1:N / N:1 graphs use the separate existing N:M gate instead.
    occupied = [ordinal for link in graph.links for ordinal in link.fact_ordinals]
    one_to_one = len(occupied) == len(set(occupied)) and all(
        len(link.fact_ordinals) <= 1 for link in graph.links
    )
    # The independent reviewer still calls the abandoned source candidate
    # unsupported. Only when the final fact is explicitly reviewed and
    # the typed Temporal correction proof is present can Core reclassify
    # that first non-write as a proven supersession. The later coverage
    # gate must independently check original polarity/replacement/target/
    # clock and will refuse invented or incorrectly dated final facts.
    marked_supersession = (
        context.verified_correction_temporal is not None
        and context.hybrid_interpretation_mode
        and correction_chain(context.candidates) is not None
        and all(
            link.pending_reason == "unsupported_scope" and not link.fact_ordinals
            for link in graph.links[:-1]
        )
        and graph.links[-1].fact_ordinals == (0,)
        and graph.links[-1].pending_reason is None
        and any(r.role == "polarity" for r in context.candidates[0].roles)
        and any(r.role == "replacement" for r in context.candidates[-1].roles)
    )
    claims = tuple(
        CoreCandidateCoverageClaim(
            link.candidate_id,
            "planned_fact" if link.fact_ordinals else "pending",
            fact_ordinal=link.fact_ordinals[0] if link.fact_ordinals and one_to_one else None,
            fact_ordinals=link.fact_ordinals if link.fact_ordinals and not one_to_one else None,
            pending_reason=(
                "superseded_by_correction"
                if marked_supersession and position < len(graph.links) - 1
                else link.pending_reason
            ),
        )
        for position, link in enumerate(graph.links)
    )
    return build_candidate_coverage_manifest(
        source, context, plan, claims, canonical_binding=canonical_binding
    )
